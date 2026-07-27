"""Shared test fixtures — authenticated client for all API tests."""

import pytest
from fastapi.testclient import TestClient

from sceneforge.server import create_app


@pytest.fixture
def auth_client(tmp_path):
    """Returns (client, token) — a TestClient with a pre-authenticated user."""
    client = TestClient(create_app(tmp_path))
    r = client.post("/api/auth/signup", json={
        "email": "test@sceneforge.dev",
        "password": "test-password-123",
        "name": "Test User",
    })
    token = r.json()["token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client
