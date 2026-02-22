#!/bin/bash
# =============================================================================
# FORESIGHT — Quick Test Script (Bash/Curl)
# Simple tests using only curl and jq
# =============================================================================

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Config
BASE_URL="http://localhost:8000"
TENANT_ID="550e8400-e29b-41d4-a716-446655440000"
TOKEN=""

# =============================================================================
# Helper Functions
# =============================================================================

log_info() {
    echo -e "${YELLOW}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[PASS]${NC} $1"
}

log_error() {
    echo -e "${RED}[FAIL]${NC} $1"
}

check_jq() {
    if ! command -v jq &> /dev/null; then
        echo "jq is required but not installed. Install with:"
        echo "  Mac: brew install jq"
        echo "  Ubuntu: apt-get install jq"
        exit 1
    fi
}

# =============================================================================
# Tests
# =============================================================================

test_health() {
    log_info "Testing health endpoint..."
    
    if curl -s "$BASE_URL/health" | grep -q "healthy"; then
        log_success "Health check passed"
        return 0
    else
        log_error "Health check failed"
        return 1
    fi
}

test_login() {
    log_info "Testing authentication..."
    
    TOKEN=$(curl -s -X POST "$BASE_URL/auth/token" \
        -H "Content-Type: application/json" \
        -d '{
            "email": "admin@assetpulse.local",
            "password": "admin123"
        }' | jq -r '.access_token')
    
    if [ "$TOKEN" != "null" ] && [ -n "$TOKEN" ]; then
        log_success "Login successful"
        echo "Token: ${TOKEN:0:20}..."
        return 0
    else
        log_error "Login failed"
        return 1
    fi
}

test_create_asset() {
    log_info "Testing asset creation..."
    
    RESPONSE=$(curl -s -X POST "$BASE_URL/assets/$TENANT_ID" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d '{
            "asset_id": "TEST-PUMP-'$(date +%s)'",
            "name": "Test Pump",
            "asset_type": "pump",
            "criticality": "high",
            "location": "Test Location"
        }')
    
    if echo "$RESPONSE" | jq -e '.id' > /dev/null 2>&1; then
        ASSET_ID=$(echo "$RESPONSE" | jq -r '.id')
        log_success "Asset created: $ASSET_ID"
        return 0
    else
        log_error "Asset creation failed"
        echo "Response: $RESPONSE"
        return 1
    fi
}

test_list_assets() {
    log_info "Testing asset listing..."
    
    COUNT=$(curl -s "$BASE_URL/assets/$TENANT_ID" \
        -H "Authorization: Bearer $TOKEN" | jq '.total')
    
    if [ "$COUNT" -gt 0 ] 2>/dev/null; then
        log_success "Found $COUNT assets"
        return 0
    else
        log_error "No assets found"
        return 1
    fi
}

test_create_alert_rule() {
    log_info "Testing alert rule creation..."
    
    RESPONSE=$(curl -s -X POST "$BASE_URL/alerts/$TENANT_ID/rules" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d '{
            "name": "Test High Temperature",
            "metric": "temperature",
            "operator": ">",
            "threshold_value": 85,
            "severity": "warning"
        }')
    
    if echo "$RESPONSE" | jq -e '.id' > /dev/null 2>&1; then
        log_success "Alert rule created"
        return 0
    else
        log_error "Alert rule creation failed"
        echo "Response: $RESPONSE"
        return 1
    fi
}

test_dashboard_report() {
    log_info "Testing dashboard report..."
    
    RESPONSE=$(curl -s "$BASE_URL/reports/$TENANT_ID/dashboard" \
        -H "Authorization: Bearer $TOKEN")
    
    if echo "$RESPONSE" | jq -e '.total_assets' > /dev/null 2>&1; then
        TOTAL=$(echo "$RESPONSE" | jq '.total_assets')
        log_success "Dashboard report retrieved ($TOTAL assets)"
        return 0
    else
        log_error "Dashboard report failed"
        return 1
    fi
}

# =============================================================================
# Main
# =============================================================================

echo "=========================================="
echo "FORESIGHT Quick API Test"
echo "=========================================="
echo ""

check_jq

PASSED=0
FAILED=0

# Run tests
test_health && ((PASSED++)) || ((FAILED++))
test_login && ((PASSED++)) || ((FAILED++))
test_create_asset && ((PASSED++)) || ((FAILED++))
test_list_assets && ((PASSED++)) || ((FAILED++))
test_create_alert_rule && ((PASSED++)) || ((FAILED++))
test_dashboard_report && ((PASSED++)) || ((FAILED++))

# Summary
echo ""
echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo -e "${GREEN}Passed: $PASSED${NC}"
echo -e "${RED}Failed: $FAILED${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}All tests passed! ✅${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed ❌${NC}"
    exit 1
fi
