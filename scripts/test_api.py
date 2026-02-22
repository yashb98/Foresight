#!/usr/bin/env python3
"""
FORESIGHT — Comprehensive API Test Suite
Tests all major API endpoints
"""

import requests
import json
import sys
from datetime import datetime, timedelta
from uuid import uuid4, UUID
import time

# Configuration
BASE_URL = "http://localhost:8000"
TENANT_ID = "550e8400-e29b-41d4-a716-446655440000"

# Colors for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'


class APITester:
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.token = None
        self.headers = {}
        self.test_results = []
        self.created_asset_ids = []
        self.created_alert_ids = []
    
    def log_success(self, message: str):
        print(f"{GREEN}✓{RESET} {message}")
        self.test_results.append(("PASS", message))
    
    def log_failure(self, message: str, error: str = None):
        print(f"{RED}✗{RESET} {message}")
        if error:
            print(f"   Error: {error}")
        self.test_results.append(("FAIL", message))
    
    def log_info(self, message: str):
        print(f"{YELLOW}ℹ{RESET} {message}")
    
    def set_token(self, token: str):
        self.token = token
        self.headers = {"Authorization": f"Bearer {token}"}
    
    # =================================================================
    # Health Checks
    # =================================================================
    
    def test_health(self):
        """Test health endpoints."""
        self.log_info("\n=== Testing Health Endpoints ===")
        
        try:
            # Basic health
            resp = requests.get(f"{self.base_url}/health")
            if resp.status_code == 200:
                self.log_success("Health endpoint is responding")
            else:
                self.log_failure(f"Health endpoint returned {resp.status_code}")
                return False
            
            # Liveness
            resp = requests.get(f"{self.base_url}/health/live")
            if resp.status_code == 200:
                self.log_success("Liveness probe is working")
            
            # Readiness
            resp = requests.get(f"{self.base_url}/health/ready")
            if resp.status_code == 200:
                self.log_success("Readiness probe is working")
            else:
                self.log_failure(f"Readiness probe failed: {resp.text}")
            
            return True
        except Exception as e:
            self.log_failure("Health check failed", str(e))
            return False
    
    # =================================================================
    # Authentication
    # =================================================================
    
    def test_authentication(self):
        """Test login and token generation."""
        self.log_info("\n=== Testing Authentication ===")
        
        try:
            # Login
            login_data = {
                "email": "admin@assetpulse.local",
                "password": "admin123"
            }
            resp = requests.post(
                f"{self.base_url}/auth/token",
                json=login_data
            )
            
            if resp.status_code == 200:
                data = resp.json()
                self.set_token(data["access_token"])
                self.log_success(f"Login successful (tenant: {data['tenant_id']})")
                return True
            else:
                self.log_failure(f"Login failed: {resp.status_code}", resp.text)
                return False
        except Exception as e:
            self.log_failure("Authentication failed", str(e))
            return False
    
    def test_get_current_user(self):
        """Test /auth/me endpoint."""
        try:
            resp = requests.get(
                f"{self.base_url}/auth/me",
                headers=self.headers
            )
            
            if resp.status_code == 200:
                user = resp.json()
                self.log_success(f"Current user: {user['full_name']} ({user['role']})")
            else:
                self.log_failure(f"Get user failed: {resp.status_code}")
        except Exception as e:
            self.log_failure("Get current user failed", str(e))
    
    # =================================================================
    # Assets
    # =================================================================
    
    def test_create_asset(self):
        """Test asset creation."""
        self.log_info("\n=== Testing Asset Management ===")
        
        assets = [
            {
                "asset_id": f"TEST-PUMP-{uuid4().hex[:8].upper()}",
                "name": "Test Centrifugal Pump",
                "asset_type": "pump",
                "category": "rotating",
                "criticality": "critical",
                "manufacturer": "TestCorp",
                "location": "Building A",
                "department": "Production",
                "status": "operational"
            },
            {
                "asset_id": f"TEST-MOTOR-{uuid4().hex[:8].upper()}",
                "name": "Test Electric Motor",
                "asset_type": "motor",
                "category": "electrical",
                "criticality": "high",
                "manufacturer": "Siemens",
                "location": "Building B",
                "department": "Utilities",
                "status": "operational"
            }
        ]
        
        for asset in assets:
            try:
                resp = requests.post(
                    f"{self.base_url}/assets/{TENANT_ID}",
                    headers=self.headers,
                    json=asset
                )
                
                if resp.status_code == 201:
                    created = resp.json()
                    self.created_asset_ids.append(created['id'])
                    self.log_success(f"Created asset: {asset['name']} ({asset['asset_id']})")
                else:
                    self.log_failure(f"Create asset failed: {resp.status_code}", resp.text)
            except Exception as e:
                self.log_failure("Create asset failed", str(e))
    
    def test_list_assets(self):
        """Test listing assets."""
        try:
            resp = requests.get(
                f"{self.base_url}/assets/{TENANT_ID}?page_size=10",
                headers=self.headers
            )
            
            if resp.status_code == 200:
                data = resp.json()
                self.log_success(f"Listed {data['total']} assets (showing {len(data['items'])})")
            else:
                self.log_failure(f"List assets failed: {resp.status_code}")
        except Exception as e:
            self.log_failure("List assets failed", str(e))
    
    def test_add_sensor(self):
        """Test adding sensors to assets."""
        if not self.created_asset_ids:
            self.log_info("No assets to add sensors to")
            return
        
        sensors = [
            {
                "sensor_id": f"TEMP-{uuid4().hex[:8].upper()}",
                "asset_id": self.created_asset_ids[0],
                "name": "Temperature Sensor",
                "sensor_type": "temperature",
                "unit": "celsius",
                "sampling_rate": 60,
                "min_threshold": 20,
                "max_threshold": 100
            },
            {
                "sensor_id": f"VIB-{uuid4().hex[:8].upper()}",
                "asset_id": self.created_asset_ids[0],
                "name": "Vibration Sensor",
                "sensor_type": "vibration",
                "unit": "mm/s",
                "sampling_rate": 60,
                "min_threshold": 1,
                "max_threshold": 15
            }
        ]
        
        for sensor in sensors:
            try:
                resp = requests.post(
                    f"{self.base_url}/assets/{TENANT_ID}/TEST-PUMP/sensors",
                    headers=self.headers,
                    json=sensor
                )
                
                if resp.status_code == 201:
                    self.log_success(f"Added sensor: {sensor['name']}")
                else:
                    # Try with actual asset_id if the above fails
                    self.log_failure(f"Add sensor failed: {resp.status_code}")
            except Exception as e:
                self.log_failure("Add sensor failed", str(e))
    
    def test_add_maintenance(self):
        """Test adding maintenance records."""
        if not self.created_asset_ids:
            return
        
        maintenance = {
            "asset_id": self.created_asset_ids[0],
            "record_type": "preventive",
            "title": "Scheduled Maintenance",
            "description": "Regular preventive maintenance check",
            "status": "completed",
            "priority": "medium",
            "completed_date": (datetime.now() - timedelta(days=30)).isoformat(),
            "technician_name": "John Smith",
            "cost_total": 1500.00,
            "downtime_hours": 4
        }
        
        try:
            resp = requests.post(
                f"{self.base_url}/assets/{TENANT_ID}/TEST-PUMP/maintenance",
                headers=self.headers,
                json=maintenance
            )
            
            if resp.status_code == 201:
                self.log_success("Added maintenance record")
            else:
                self.log_failure(f"Add maintenance failed: {resp.status_code}")
        except Exception as e:
            self.log_failure("Add maintenance failed", str(e))
    
    # =================================================================
    # Alerts
    # =================================================================
    
    def test_create_alert_rule(self):
        """Test creating alert rules."""
        self.log_info("\n=== Testing Alert System ===")
        
        rules = [
            {
                "name": "High Temperature Warning",
                "description": "Alert when temperature exceeds 85°C",
                "metric": "temperature",
                "operator": ">",
                "threshold_value": 85,
                "severity": "warning",
                "cooldown_minutes": 30
            },
            {
                "name": "Critical Temperature",
                "description": "Critical alert when temperature exceeds 95°C",
                "metric": "temperature",
                "operator": ">",
                "threshold_value": 95,
                "severity": "critical",
                "cooldown_minutes": 15
            }
        ]
        
        for rule in rules:
            try:
                resp = requests.post(
                    f"{self.base_url}/alerts/{TENANT_ID}/rules",
                    headers=self.headers,
                    json=rule
                )
                
                if resp.status_code == 201:
                    self.log_success(f"Created alert rule: {rule['name']}")
                else:
                    self.log_failure(f"Create rule failed: {resp.status_code}")
            except Exception as e:
                self.log_failure("Create rule failed", str(e))
    
    def test_list_alerts(self):
        """Test listing alerts."""
        try:
            resp = requests.get(
                f"{self.base_url}/alerts/{TENANT_ID}",
                headers=self.headers
            )
            
            if resp.status_code == 200:
                data = resp.json()
                self.log_success(f"Listed {data['total']} alerts")
            else:
                self.log_failure(f"List alerts failed: {resp.status_code}")
        except Exception as e:
            self.log_failure("List alerts failed", str(e))
    
    # =================================================================
    # Predictions
    # =================================================================
    
    def test_health_predictions(self):
        """Test health prediction endpoints."""
        self.log_info("\n=== Testing Predictions ===")
        
        if not self.created_asset_ids:
            self.log_info("No assets to predict")
            return
        
        try:
            # Fleet health
            resp = requests.get(
                f"{self.base_url}/predict/{TENANT_ID}/fleet-health",
                headers=self.headers
            )
            
            if resp.status_code == 200:
                data = resp.json()
                self.log_success(f"Fleet health: {data['average_score']:.1f} avg score, {data['total_assets']} assets")
            else:
                self.log_failure(f"Fleet health failed: {resp.status_code}")
        except Exception as e:
            self.log_failure("Fleet health failed", str(e))
    
    # =================================================================
    # Reports
    # =================================================================
    
    def test_reports(self):
        """Test reporting endpoints."""
        self.log_info("\n=== Testing Reports ===")
        
        endpoints = [
            ("summary", f"{self.base_url}/reports/{TENANT_ID}/summary"),
            ("trends", f"{self.base_url}/reports/{TENANT_ID}/trends"),
            ("dashboard", f"{self.base_url}/reports/{TENANT_ID}/dashboard"),
        ]
        
        for name, url in endpoints:
            try:
                resp = requests.get(url, headers=self.headers)
                if resp.status_code == 200:
                    self.log_success(f"{name.capitalize()} report retrieved")
                else:
                    self.log_failure(f"{name.capitalize()} report failed: {resp.status_code}")
            except Exception as e:
                self.log_failure(f"{name.capitalize()} report failed", str(e))
    
    # =================================================================
    # Summary
    # =================================================================
    
    def print_summary(self):
        """Print test summary."""
        self.log_info("\n" + "="*60)
        self.log_info("TEST SUMMARY")
        self.log_info("="*60)
        
        passed = sum(1 for r in self.test_results if r[0] == "PASS")
        failed = sum(1 for r in self.test_results if r[0] == "FAIL")
        total = len(self.test_results)
        
        print(f"\nTotal Tests: {total}")
        print(f"{GREEN}Passed: {passed}{RESET}")
        print(f"{RED}Failed: {failed}{RESET}")
        print(f"Success Rate: {(passed/total*100):.1f}%" if total > 0 else "N/A")
        
        if failed > 0:
            print(f"\n{RED}Failed Tests:{RESET}")
            for status, msg in self.test_results:
                if status == "FAIL":
                    print(f"  - {msg}")
        
        return failed == 0


def main():
    print("="*60)
    print("FORESIGHT API Test Suite")
    print("="*60)
    
    tester = APITester()
    
    # Run tests
    if not tester.test_health():
        print("\n❌ Health checks failed. Is the API running?")
        print("   Start with: ./scripts/start.sh")
        sys.exit(1)
    
    if not tester.test_authentication():
        print("\n❌ Authentication failed. Check credentials.")
        sys.exit(1)
    
    # Run all tests
    tester.test_get_current_user()
    tester.test_create_asset()
    tester.test_list_assets()
    tester.test_add_sensor()
    tester.test_add_maintenance()
    tester.test_create_alert_rule()
    tester.test_list_alerts()
    tester.test_health_predictions()
    tester.test_reports()
    
    # Summary
    success = tester.print_summary()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
