"""API integration tests.

Tests the full HTTP request/response cycle with a test database.
"""

import uuid

import pytest
from fastapi.testclient import TestClient


class TestHealthAPI:
    def test_health_check(self, client: TestClient):
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


class TestUserAPI:
    def test_create_user(self, client: TestClient):
        response = client.post(
            "/api/v1/users",
            json={
                "email": f"new_{uuid.uuid4().hex[:8]}@example.com",
                "name": "New User",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["email"].startswith("new_")
        assert data["status"] == "ACTIVE"

    def test_create_duplicate_email(self, client: TestClient):
        email = f"dup_{uuid.uuid4().hex[:8]}@example.com"
        client.post("/api/v1/users", json={"email": email, "name": "First"})
        response = client.post("/api/v1/users", json={"email": email, "name": "Second"})
        assert response.status_code == 400
        assert "already registered" in response.json()["detail"]


class TestBrandAPI:
    def test_create_brand(self, client: TestClient):
        # First create a user to use as admin
        user_resp = client.post(
            "/api/v1/users",
            json={
                "email": f"admin_{uuid.uuid4().hex[:8]}@example.com",
                "name": "Admin User",
            },
        )
        assert user_resp.status_code == 201
        user_id = user_resp.json()["id"]

        code = f"BRAND_{uuid.uuid4().hex[:6]}"
        response = client.post(
            "/api/v1/brands",
            json={"name": "Test Brand", "code": code},
            headers={"X-User-Id": user_id, "X-Admin-Key": "admin-secret-key"},
        )
        assert response.status_code == 201
        assert response.json()["code"] == code


class TestSaleAPI:
    def test_create_sale(self, client: TestClient, db_session):
        """Test full sale creation flow via API."""
        # Create user
        user_resp = client.post(
            "/api/v1/users",
            json={
                "email": f"sale_user_{uuid.uuid4().hex[:8]}@example.com",
                "name": "Sale User",
            },
        )
        assert user_resp.status_code == 201
        user_id = user_resp.json()["id"]

        # Create brand
        brand_resp = client.post(
            "/api/v1/brands",
            json={"name": "Sale Brand", "code": f"SALE_{uuid.uuid4().hex[:6]}"},
            headers={"X-User-Id": user_id, "X-Admin-Key": "admin-secret-key"},
        )
        assert brand_resp.status_code == 201
        brand_id = brand_resp.json()["id"]

        # Create sale
        ext_id = f"EXT_{uuid.uuid4().hex}"
        sale_resp = client.post(
            "/api/v1/sales",
            json={
                "user_id": user_id,
                "brand_id": brand_id,
                "external_id": ext_id,
                "earnings": 500.00,
            },
            headers={
                "X-User-Id": user_id,
                "Idempotency-Key": f"idem_{uuid.uuid4().hex}",
            },
        )
        assert sale_resp.status_code == 201
        assert sale_resp.json()["status"] == "PENDING"
        assert sale_resp.json()["earnings"] == 500.00

    def test_create_sale_without_auth(self, client: TestClient):
        response = client.post(
            "/api/v1/sales",
            json={
                "user_id": str(uuid.uuid4()),
                "brand_id": str(uuid.uuid4()),
                "external_id": f"EXT_{uuid.uuid4().hex}",
                "earnings": 500.00,
            },
        )
        assert response.status_code == 401


class TestWithdrawalAPI:
    def test_request_withdrawal(self, client: TestClient, user, user_balance):
        user_id = str(user.id)

        response = client.post(
            "/api/v1/withdrawals",
            json={"amount": 1000.00},
            headers={
                "X-User-Id": user_id,
                "Idempotency-Key": f"wd_api_{uuid.uuid4().hex}",
            },
        )
        assert response.status_code == 201
        assert response.json()["status"] == "PENDING"
        assert response.json()["amount"] == 1000.00

    def test_withdrawal_without_idempotency(self, client: TestClient, user, user_balance):
        response = client.post(
            "/api/v1/withdrawals",
            json={"amount": 1000.00},
            headers={"X-User-Id": str(user.id)},
        )
        assert response.status_code == 400
        assert "Idempotency-Key" in response.json()["detail"]

    def test_idempotent_withdrawal(self, client: TestClient, user, user_balance):
        user_id = str(user.id)
        idem_key = f"wd_idem_{uuid.uuid4().hex}"

        # First request
        resp1 = client.post(
            "/api/v1/withdrawals",
            json={"amount": 500.00},
            headers={"X-User-Id": user_id, "Idempotency-Key": idem_key},
        )
        assert resp1.status_code == 201

        # Duplicate request with same key
        resp2 = client.post(
            "/api/v1/withdrawals",
            json={"amount": 500.00},
            headers={"X-User-Id": user_id, "Idempotency-Key": idem_key},
        )
        assert resp2.status_code == 201
        assert resp2.headers.get("X-Idempotency-Replay") == "true"


class TestAdminAPI:
    def test_reconcile_sale(self, client: TestClient, pending_sale, admin_user):
        sale_id = str(pending_sale.id)
        admin_id = str(admin_user.id)

        response = client.post(
            "/api/v1/admin/reconcile",
            json={"sale_id": sale_id, "decision": "APPROVED"},
            headers={
                "X-User-Id": admin_id,
                "X-Admin-Key": "admin-secret-key",
                "Idempotency-Key": f"reconcile_{uuid.uuid4().hex}",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "APPROVED"

    def test_reconcile_without_admin_key(self, client: TestClient, pending_sale, user):
        response = client.post(
            "/api/v1/admin/reconcile",
            json={"sale_id": str(pending_sale.id), "decision": "APPROVED"},
            headers={"X-User-Id": str(user.id)},
        )
        assert response.status_code == 403
