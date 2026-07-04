"""Integration tests for authentication endpoints."""

import pytest
import httpx


class TestRegistration:
    """Test user registration flow."""

    async def test_register_success(self, client: httpx.AsyncClient):
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "new@example.com", "password": "securepass123"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "new@example.com"
        assert "id" in data
        assert "password_hash" not in data

    async def test_register_normalizes_email(self, client: httpx.AsyncClient):
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "  USER@Example.COM  ", "password": "securepass123"},
        )
        assert resp.status_code == 201
        assert resp.json()["email"] == "user@example.com"

    async def test_register_duplicate_email_rejected(
        self, client: httpx.AsyncClient, test_user
    ):
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "test@example.com", "password": "securepass123"},
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "CONFLICT"

    async def test_register_invalid_email_rejected(self, client: httpx.AsyncClient):
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "not-an-email", "password": "securepass123"},
        )
        assert resp.status_code == 422

    async def test_register_short_password_rejected(self, client: httpx.AsyncClient):
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "new2@example.com", "password": "short"},
        )
        assert resp.status_code == 422


class TestLogin:
    """Test user login flow."""

    async def test_login_success(self, client: httpx.AsyncClient, test_user):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "test@example.com", "password": "testpassword123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    async def test_login_wrong_password(self, client: httpx.AsyncClient, test_user):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "test@example.com", "password": "wrongpassword"},
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "INVALID_CREDENTIALS"

    async def test_login_nonexistent_user(self, client: httpx.AsyncClient):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "somepassword123"},
        )
        assert resp.status_code == 401
        # Generic error — no user enumeration
        assert resp.json()["error"]["code"] == "INVALID_CREDENTIALS"


class TestGetMe:
    """Test /auth/me endpoint."""

    async def test_get_me_success(
        self, client: httpx.AsyncClient, test_user, auth_headers
    ):
        resp = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "test@example.com"
        assert "id" in data
        assert "password_hash" not in data

    async def test_get_me_no_token(self, client: httpx.AsyncClient):
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    async def test_get_me_invalid_token(self, client: httpx.AsyncClient):
        resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid-token-here"},
        )
        assert resp.status_code == 401
