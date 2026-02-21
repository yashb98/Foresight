#!/usr/bin/env python3
"""
FORESIGHT Smoke Test — Post-deployment health verification

Runs a lightweight set of critical-path checks against the live API
to verify a successful deployment. Called by CI/CD after every staging deploy.

Usage:
    python tests/smoke_test.py --base-url https://api-staging.foresight.example.com
    python tests/smoke_test.py --base-url http://localhost:8000 --verbose
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

import requests


# ─────────────────────────────────────────────────────────────────────────────
# Result tracking
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SmokeResult:
    name: str
    passed: bool
    duration_ms: float
    error: Optional[str] = None


results: list[SmokeResult] = []


def check(name: str, fn) -> bool:
    """Run a single smoke check and record the result."""
    start = time.perf_counter()
    try:
        fn()
        duration_ms = (time.perf_counter() - start) * 1000
        results.append(SmokeResult(name=name, passed=True, duration_ms=duration_ms))
        print(f"  ✅ {name} ({duration_ms:.0f}ms)")
        return True
    except AssertionError as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        error = str(exc) or "Assertion failed"
        results.append(SmokeResult(name=name, passed=False, duration_ms=duration_ms, error=error))
        print(f"  ❌ {name} — {error} ({duration_ms:.0f}ms)")
        return False
    except Exception as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        error = f"{type(exc).__name__}: {exc}"
        results.append(SmokeResult(name=name, passed=False, duration_ms=duration_ms, error=error))
        print(f"  ❌ {name} — {error}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Smoke test suites
# ─────────────────────────────────────────────────────────────────────────────

def run_smoke_tests(base_url: str, token: Optional[str] = None, verbose: bool = False):
    s = requests.Session()
    s.timeout = 15

    if token:
        s.headers["Authorization"] = f"Bearer {token}"

    print(f"\n🚀 FORESIGHT Smoke Tests — {base_url}")
    print("=" * 60)

    # ── System endpoints ──────────────────────────────────────────────────────
    print("\n📡 System Endpoints")

    def test_root():
        r = s.get(f"{base_url}/")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        assert "FORESIGHT" in r.json().get("service", ""), "Service name missing"

    def test_health():
        r = s.get(f"{base_url}/health")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        body = r.json()
        assert body.get("service") == "foresight-api", f"Unexpected service: {body.get('service')}"
        assert body.get("status") in ("healthy", "degraded"), f"Bad status: {body.get('status')}"

    def test_health_response_time():
        start = time.perf_counter()
        r = s.get(f"{base_url}/health")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert r.status_code == 200
        assert elapsed_ms < 2000, f"Health check took {elapsed_ms:.0f}ms (max: 2000ms)"

    def test_openapi():
        r = s.get(f"{base_url}/openapi.json")
        assert r.status_code == 200, f"OpenAPI spec returned {r.status_code}"
        schema = r.json()
        assert schema.get("info", {}).get("title") == "FORESIGHT Predictive Asset Maintenance API"

    def test_docs_accessible():
        r = s.get(f"{base_url}/docs")
        assert r.status_code == 200, f"/docs returned {r.status_code}"

    def test_x_process_time_header():
        r = s.get(f"{base_url}/health")
        assert "x-process-time" in r.headers, "X-Process-Time header missing"

    check("Root endpoint returns service info",   test_root)
    check("Health check returns 200",             test_health)
    check("Health check responds < 2s",           test_health_response_time)
    check("OpenAPI schema accessible",            test_openapi)
    check("Swagger UI accessible",                test_docs_accessible)
    check("X-Process-Time header present",        test_x_process_time_header)

    # ── Auth endpoints ────────────────────────────────────────────────────────
    print("\n🔐 Auth Endpoints")

    def test_auth_missing_credentials():
        r = s.post(f"{base_url}/auth/token", json={})
        assert r.status_code == 422, f"Expected 422, got {r.status_code}"

    def test_auth_invalid_credentials():
        r = s.post(
            f"{base_url}/auth/token",
            json={"client_id": "smoke-test-fake", "client_secret": "wrong"},
        )
        assert r.status_code in (401, 503), f"Expected 401 or 503, got {r.status_code}"

    def test_protected_endpoint_without_token():
        r = requests.get(f"{base_url}/assets/some-tenant", timeout=10)
        assert r.status_code == 401, f"Expected 401, got {r.status_code}"

    check("Missing credentials returns 422",      test_auth_missing_credentials)
    check("Invalid credentials returns 401",      test_auth_invalid_credentials)
    check("Protected endpoint requires auth",     test_protected_endpoint_without_token)

    # ── Tenant isolation ─────────────────────────────────────────────────────
    if token:
        print("\n🔒 Tenant Isolation")

        def test_cross_tenant_assets():
            r = s.get(f"{base_url}/assets/definitely-not-my-tenant")
            assert r.status_code == 403, f"Expected 403, got {r.status_code}"

        def test_cross_tenant_alerts():
            r = s.get(f"{base_url}/alerts/definitely-not-my-tenant")
            assert r.status_code == 403, f"Expected 403, got {r.status_code}"

        def test_cross_tenant_reports():
            r = s.get(f"{base_url}/reports/definitely-not-my-tenant/summary")
            assert r.status_code == 403, f"Expected 403, got {r.status_code}"

        check("Cross-tenant asset access returns 403",   test_cross_tenant_assets)
        check("Cross-tenant alert access returns 403",   test_cross_tenant_alerts)
        check("Cross-tenant report access returns 403",  test_cross_tenant_reports)

    # ── Performance checks ────────────────────────────────────────────────────
    print("\n⚡ Performance Checks")

    def test_concurrent_health_checks():
        """10 concurrent health checks should all complete within 5s."""
        import threading
        errors = []
        def hit_health():
            try:
                r = s.get(f"{base_url}/health")
                assert r.status_code == 200
            except Exception as exc:
                errors.append(str(exc))

        threads = [threading.Thread(target=hit_health) for _ in range(10)]
        start = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        elapsed = time.perf_counter() - start
        assert not errors, f"Concurrent failures: {errors}"
        assert elapsed < 5.0, f"10 concurrent requests took {elapsed:.1f}s (max: 5s)"

    check("10 concurrent health checks < 5s",   test_concurrent_health_checks)

    # ── Print summary ─────────────────────────────────────────────────────────
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    avg_ms = sum(r.duration_ms for r in results) / max(total, 1)

    print(f"\n{'=' * 60}")
    print(f"📊 Smoke Test Results: {passed}/{total} passed | avg {avg_ms:.0f}ms per check")

    if passed < total:
        print("\nFailed checks:")
        for r in results:
            if not r.passed:
                print(f"  • {r.name}: {r.error}")
        print(f"\n❌ Smoke tests FAILED ({total - passed} failures)")
        sys.exit(1)
    else:
        print("✅ All smoke tests PASSED — deployment is healthy!")
        sys.exit(0)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FORESIGHT Smoke Tests")
    parser.add_argument(
        "--base-url",
        default=os.getenv("STAGING_API_URL", "http://localhost:8000"),
        help="Base URL of the API",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("K6_STAGING_TOKEN"),
        help="JWT token for authenticated tests",
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    run_smoke_tests(
        base_url=args.base_url.rstrip("/"),
        token=args.token,
        verbose=args.verbose,
    )
