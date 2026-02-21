"""
FORESIGHT — FastAPI Unit Tests

Tests all API endpoints using FastAPI's TestClient with dependency overrides
to avoid real DB/ML dependencies.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient


# ─────────────────────────────────────────────────────────────────────────────
# App fixture — overrides env vars and DB dependencies
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def test_client():
    """
    Creates a FastAPI TestClient with DB dependency overridden.
    """
    import os
    os.environ["DATABASE_URL"] = "postgresql+asyncpg://test:test@localhost:5432/test"
    os.environ["ENVIRONMENT"] = "test"

    from api.main import app
    from api.dependencies import get_db

    async def _mock_db() -> AsyncGenerator:
        """Yields a MagicMock as the DB session."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))),
            scalar_one=MagicMock(return_value=0),
            scalar_one_or_none=MagicMock(return_value=None),
            all=MagicMock(return_value=[]),
        ))
        yield mock_session

    app.dependency_overrides[get_db] = _mock_db

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client

    app.dependency_overrides.clear()


TENANT_ID = "11111111-1111-1111-1111-111111111111"


# ─────────────────────────────────────────────────────────────────────────────
# System Endpoints
# ─────────────────────────────────────────────────────────────────────────────

class TestSystemEndpoints:
    def test_root_returns_service_info(self, test_client):
        resp = test_client.get("/")
        assert resp.status_code == 200
        body = resp.json()
        assert "FORESIGHT" in body["service"]
        assert body["docs"] == "/docs"

    def test_health_check_returns_status(self, test_client):
        resp = test_client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["service"] == "foresight-api"
        assert body["version"] == "0.1.0"
        assert body["status"] in ("healthy", "degraded")
        assert "checks" in body

    def test_health_includes_x_process_time_header(self, test_client):
        resp = test_client.get("/health")
        assert "x-process-time" in resp.headers

    def test_openapi_schema_accessible(self, test_client):
        resp = test_client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert schema["info"]["title"] == "FORESIGHT Predictive Asset Maintenance API"

    def test_docs_ui_accessible(self, test_client):
        resp = test_client.get("/docs")
        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# Assets Endpoints
# ─────────────────────────────────────────────────────────────────────────────

class TestAssetsEndpoints:
    def test_list_assets_returns_200(self, test_client):
        resp = test_client.get(f"/assets/{TENANT_ID}")
        assert resp.status_code == 200
        body = resp.json()
        assert "assets" in body
        assert "total" in body
        assert body["tenant_id"] == TENANT_ID

    def test_list_assets_with_filters(self, test_client):
        resp = test_client.get(
            f"/assets/{TENANT_ID}",
            params={"asset_type": "pump", "risk_level": "high"},
        )
        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# Alerts Endpoints
# ─────────────────────────────────────────────────────────────────────────────

class TestAlertsEndpoints:
    def test_list_alerts_returns_200(self, test_client):
        resp = test_client.get(f"/alerts/{TENANT_ID}")
        assert resp.status_code == 200
        body = resp.json()
        assert "alerts" in body
        assert body["tenant_id"] == TENANT_ID

    def test_list_alerts_with_filters(self, test_client):
        resp = test_client.get(
            f"/alerts/{TENANT_ID}",
            params={"severity": "critical", "status": "active"},
        )
        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# Predictions Endpoints
# ─────────────────────────────────────────────────────────────────────────────

class TestPredictionsEndpoints:
    def test_predict_missing_fields_returns_422(self, test_client):
        resp = test_client.post(
            "/predict",
            json={"tenant_id": TENANT_ID},  # missing asset_id
        )
        assert resp.status_code == 422

    def test_predict_with_features_returns_200_or_503(self, test_client):
        """Returns 200 (with demo prediction) or 503 if ML model unavailable."""
        resp = test_client.post(
            "/predict",
            json={
                "asset_id": str(uuid.uuid4()),
                "tenant_id": TENANT_ID,
                "features": {"temp_mean_7d": 65.0, "vibration_mean_7d": 15.0},
            },
        )
        assert resp.status_code in (200, 503)


# ─────────────────────────────────────────────────────────────────────────────
# Rules Endpoints
# ─────────────────────────────────────────────────────────────────────────────

class TestRulesEndpoints:
    def test_list_rules_returns_200(self, test_client):
        resp = test_client.get(f"/rules/{TENANT_ID}")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)

    def test_create_rule_invalid_operator_returns_422(self, test_client):
        resp = test_client.post(
            f"/rules/{TENANT_ID}",
            json={
                "name": "Test Rule",
                "metric": "vibration_rms",
                "operator": "INVALID",   # invalid
                "threshold": 5.0,
                "severity": "high",
            },
        )
        assert resp.status_code == 422

    def test_create_rule_invalid_severity_returns_422(self, test_client):
        resp = test_client.post(
            f"/rules/{TENANT_ID}",
            json={
                "name": "Test Rule",
                "metric": "vibration_rms",
                "operator": "gt",
                "threshold": 5.0,
                "severity": "extreme",  # invalid
            },
        )
        assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# Reports Endpoints
# ─────────────────────────────────────────────────────────────────────────────

class TestReportsEndpoints:
    def test_fleet_summary_returns_200(self, test_client):
        resp = test_client.get(f"/reports/{TENANT_ID}/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert body["tenant_id"] == TENANT_ID
        assert "fleet_health_score" in body
        assert "total_assets" in body

    def test_trends_returns_200(self, test_client):
        resp = test_client.get(
            f"/reports/{TENANT_ID}/trends",
            params={"metric": "vibration_rms", "days": 7},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["metric"] == "vibration_rms"
        assert body["days"] == 7

    def test_trends_invalid_days_returns_422(self, test_client):
        resp = test_client.get(
            f"/reports/{TENANT_ID}/trends",
            params={"metric": "vibration_rms", "days": 999},  # > 365
        )
        assert resp.status_code == 422

    def test_cost_avoidance_returns_200(self, test_client):
        resp = test_client.get(f"/reports/{TENANT_ID}/cost-avoidance")
        assert resp.status_code == 200
        body = resp.json()
        assert body["tenant_id"] == TENANT_ID
        assert "estimated_cost_avoided_usd" in body
        assert "roi_percent" in body


# ─────────────────────────────────────────────────────────────────────────────
# Schema Validation Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSchemas:
    """Pure unit tests for Pydantic schema validation logic (no HTTP)."""

    def test_alert_rule_create_valid(self):
        from api.models.schemas import AlertRuleCreate
        rule = AlertRuleCreate(
            name="High Vibration",
            metric="vibration_rms",
            operator="gt",
            threshold=8.0,
            severity="critical",
        )
        assert rule.name == "High Vibration"
        assert rule.threshold == 8.0

    def test_alert_rule_create_rejects_negative_threshold(self):
        from api.models.schemas import AlertRuleCreate
        import pydantic
        with pytest.raises((pydantic.ValidationError, ValueError)):
            AlertRuleCreate(
                name="Bad Rule",
                metric="temp",
                operator="gt",
                threshold=-5.0,
                severity="low",
            )

    def test_alert_rule_create_rejects_invalid_operator(self):
        from api.models.schemas import AlertRuleCreate
        import pydantic
        with pytest.raises((pydantic.ValidationError, ValueError)):
            AlertRuleCreate(
                name="Bad Rule",
                metric="temp",
                operator="GREATER_THAN",  # invalid
                threshold=5.0,
                severity="low",
            )

    def test_prediction_request_valid(self):
        from api.models.schemas import PredictionRequest
        req = PredictionRequest(asset_id=str(uuid.uuid4()), tenant_id=TENANT_ID)
        assert req.tenant_id == TENANT_ID

    def test_fleet_summary_response_valid(self):
        from api.models.schemas import FleetSummaryResponse
        summary = FleetSummaryResponse(
            tenant_id=TENANT_ID,
            total_assets=100,
            active_assets=95,
            critical_alerts=2,
            high_alerts=5,
            medium_alerts=10,
            low_alerts=20,
            assets_at_risk=7,
            fleet_health_score=88.5,
            as_of=datetime.now(timezone.utc),
        )
        assert summary.fleet_health_score == 88.5
