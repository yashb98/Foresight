/**
 * FORESIGHT Load Test — k6 Script
 *
 * Simulates realistic multi-tenant API traffic across all major endpoints.
 *
 * Stages:
 *   0–1 min : Ramp up to 50 VUs  (warm-up)
 *   1–5 min : Hold at 50 VUs     (steady state)
 *   5–8 min : Spike to 150 VUs   (peak load)
 *   8–10min : Ramp down to 0     (cool-down)
 *
 * SLOs (failure criteria):
 *   - p95 latency < 500ms
 *   - p99 latency < 1000ms
 *   - Error rate < 1%
 *   - All checks pass > 99%
 *
 * Usage:
 *   k6 run tests/load/load_test.js \
 *     -e K6_API_URL=https://api-staging.foresight.example.com \
 *     -e K6_STAGING_TOKEN=eyJhbGc...
 */

import http from 'k6/http'
import { check, sleep, group } from 'k6'
import { Counter, Rate, Trend } from 'k6/metrics'

// ─────────────────────────────────────────────────────────────────────────────
// Config
// ─────────────────────────────────────────────────────────────────────────────

const BASE_URL = __ENV.K6_API_URL || 'http://localhost:8000'
const TOKEN = __ENV.K6_STAGING_TOKEN || ''

// Test tenant IDs (pre-seeded in staging)
const TENANT_IDS = [
  __ENV.K6_TENANT_A || 'staging-tenant-alpha',
  __ENV.K6_TENANT_B || 'staging-tenant-beta',
]

// ─────────────────────────────────────────────────────────────────────────────
// Custom Metrics
// ─────────────────────────────────────────────────────────────────────────────

const errorRate = new Rate('error_rate')
const apiDuration = new Trend('api_duration_ms', true)
const predictionDuration = new Trend('prediction_duration_ms', true)
const alertsFetched = new Counter('alerts_fetched_total')

// ─────────────────────────────────────────────────────────────────────────────
// Load Stages
// ─────────────────────────────────────────────────────────────────────────────

export const options = {
  stages: [
    { duration: '1m',  target: 50  },  // Ramp up
    { duration: '4m',  target: 50  },  // Steady state
    { duration: '3m',  target: 150 },  // Peak spike
    { duration: '2m',  target: 0   },  // Cool-down
  ],
  thresholds: {
    // HTTP duration thresholds
    http_req_duration: [
      'p(95) < 500',   // 95% of requests under 500ms
      'p(99) < 1000',  // 99% of requests under 1s
    ],
    // Custom metrics
    api_duration_ms:        ['p(95) < 400'],
    prediction_duration_ms: ['p(95) < 2000'],  // ML inference is slower
    error_rate:             ['rate < 0.01'],    // < 1% errors
    checks:                 ['rate > 0.99'],    // > 99% checks pass
  },
  // Output to InfluxDB/Grafana in staging
  // ext: {
  //   loadimpact: { name: 'FORESIGHT Load Test' }
  // }
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function authHeaders(token = TOKEN) {
  return {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json',
  }
}

function randomTenant() {
  return TENANT_IDS[Math.floor(Math.random() * TENANT_IDS.length)]
}

function recordDuration(res) {
  apiDuration.add(res.timings.duration)
  errorRate.add(res.status >= 500)
}

// ─────────────────────────────────────────────────────────────────────────────
// Setup — obtain auth tokens for each tenant
// ─────────────────────────────────────────────────────────────────────────────

export function setup() {
  // In a real test, we'd authenticate each tenant here.
  // For now, use the pre-provided staging token.
  return { token: TOKEN }
}

// ─────────────────────────────────────────────────────────────────────────────
// Main VU scenario
// ─────────────────────────────────────────────────────────────────────────────

export default function (data) {
  const tenantId = randomTenant()
  const headers = authHeaders(data.token)

  // ── Health check (every VU, every iteration) ──────────────────────────────
  group('health', () => {
    const res = http.get(`${BASE_URL}/health`, { tags: { endpoint: 'health' } })
    check(res, {
      'health: status 200': (r) => r.status === 200,
      'health: status ok':  (r) => r.json('status') !== undefined,
    })
    recordDuration(res)
  })

  sleep(0.5)

  // ── Fleet summary ─────────────────────────────────────────────────────────
  group('fleet_summary', () => {
    const res = http.get(
      `${BASE_URL}/reports/${tenantId}/summary`,
      { headers, tags: { endpoint: 'fleet-summary' } }
    )
    check(res, {
      'fleet summary: status 200':            (r) => r.status === 200,
      'fleet summary: has fleet_health_score': (r) => r.json('fleet_health_score') !== undefined,
      'fleet summary: tenant_id matches':      (r) => r.json('tenant_id') === tenantId,
    })
    recordDuration(res)
  })

  sleep(0.3)

  // ── Assets list ───────────────────────────────────────────────────────────
  group('assets_list', () => {
    const res = http.get(
      `${BASE_URL}/assets/${tenantId}`,
      { headers, tags: { endpoint: 'assets-list' } }
    )
    check(res, {
      'assets: status 200':   (r) => r.status === 200,
      'assets: has assets':   (r) => Array.isArray(r.json('assets')),
    })
    recordDuration(res)
  })

  sleep(0.3)

  // ── Alerts list ───────────────────────────────────────────────────────────
  group('alerts_list', () => {
    const res = http.get(
      `${BASE_URL}/alerts/${tenantId}?status=open`,
      { headers, tags: { endpoint: 'alerts-list' } }
    )
    const ok = check(res, {
      'alerts: status 200': (r) => r.status === 200,
      'alerts: has alerts': (r) => Array.isArray(r.json('alerts')),
    })
    if (ok) {
      const count = res.json('total') || 0
      alertsFetched.add(count)
    }
    recordDuration(res)
  })

  sleep(0.3)

  // ── Alert rules list ──────────────────────────────────────────────────────
  group('rules_list', () => {
    const res = http.get(
      `${BASE_URL}/rules/${tenantId}`,
      { headers, tags: { endpoint: 'rules-list' } }
    )
    check(res, {
      'rules: status 200':  (r) => r.status === 200,
      'rules: is array':    (r) => Array.isArray(r.json()),
    })
    recordDuration(res)
  })

  sleep(0.3)

  // ── On-demand prediction (10% of VUs, expensive endpoint) ─────────────────
  if (Math.random() < 0.1) {
    group('prediction', () => {
      const fakeAssetId = `load-test-asset-${Math.floor(Math.random() * 100)}`
      const res = http.post(
        `${BASE_URL}/predict`,
        JSON.stringify({ tenant_id: tenantId, asset_id: fakeAssetId }),
        { headers, tags: { endpoint: 'predict' } }
      )
      check(res, {
        'predict: status 200 or 503':  (r) => [200, 503].includes(r.status),
        'predict: not 5xx crash':      (r) => r.status !== 500,
      })
      predictionDuration.add(res.timings.duration)
      errorRate.add(res.status >= 500)
    })
  }

  // ── Trend data ─────────────────────────────────────────────────────────────
  if (Math.random() < 0.3) {
    group('trends', () => {
      const metric = ['vibration_rms', 'bearing_temp_celsius'][Math.floor(Math.random() * 2)]
      const res = http.get(
        `${BASE_URL}/reports/${tenantId}/trends?metric=${metric}&days=7`,
        { headers, tags: { endpoint: 'trends' } }
      )
      check(res, {
        'trends: status 200':         (r) => r.status === 200,
        'trends: has data_points':    (r) => Array.isArray(r.json('data_points')),
      })
      recordDuration(res)
    })
  }

  // ── Cross-tenant access attempt (should always fail with 403) ──────────────
  // This verifies tenant isolation is NOT broken under load
  group('tenant_isolation_check', () => {
    const wrongTenant = TENANT_IDS.find((t) => t !== tenantId) || 'attacker-tenant'
    const res = http.get(
      `${BASE_URL}/assets/${wrongTenant}`,
      { headers, tags: { endpoint: 'isolation-check' } }
    )
    check(res, {
      'isolation: cross-tenant returns 403': (r) => r.status === 403,
    })
    // 403 is correct — DO NOT add to error rate
  })

  // Random think-time between 0.5 and 2s (simulates real user behaviour)
  sleep(0.5 + Math.random() * 1.5)
}

// ─────────────────────────────────────────────────────────────────────────────
// Teardown — log summary
// ─────────────────────────────────────────────────────────────────────────────

export function teardown(data) {
  console.log(`Load test complete. Token used: ${data.token ? '✓' : '✗'}`)
}
