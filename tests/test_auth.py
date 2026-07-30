"""Tests for multi-user auth — signup, login, sessions, ownership."""

import pytest
from fastapi.testclient import TestClient

from sceneforge.server import create_app
from sceneforge.server.auth import AuthDB, _check_password, _hash_password


# --------------------------------------------------------- unit tests


def test_hash_and_check_password():
    hashed = _hash_password("test-password-123")
    assert _check_password("test-password-123", hashed)
    assert not _check_password("wrong-password", hashed)


def test_auth_db_create_user(tmp_path):
    db = AuthDB(tmp_path / "auth.db")
    user = db.create_user("test@example.com", "Test User", password="secret123")
    assert user["email"] == "test@example.com"
    assert user["name"] == "Test User"
    assert user["provider"] == "email"
    assert user["id"]
    db.close()


def test_auth_db_duplicate_email(tmp_path):
    db = AuthDB(tmp_path / "auth.db")
    db.create_user("test@example.com", "User 1", password="pass1234")
    with pytest.raises(Exception):
        db.create_user("test@example.com", "User 2", password="pass5678")
    db.close()


def test_auth_db_get_user_by_email(tmp_path):
    db = AuthDB(tmp_path / "auth.db")
    db.create_user("test@example.com", "Test", password="pass1234")
    user = db.get_user_by_email("test@example.com")
    assert user is not None
    assert user["name"] == "Test"
    assert db.get_user_by_email("nope@example.com") is None
    db.close()


def test_auth_db_sessions(tmp_path):
    db = AuthDB(tmp_path / "auth.db")
    user = db.create_user("test@example.com", "Test", password="pass1234")
    token = db.create_session(user["id"])
    assert token

    validated = db.validate_session(token)
    assert validated is not None
    assert validated["id"] == user["id"]

    db.revoke_session(token)
    assert db.validate_session(token) is None
    db.close()


def test_auth_db_oauth_state(tmp_path):
    db = AuthDB(tmp_path / "auth.db")
    state = db.save_oauth_state("google")
    assert state

    consumed = db.consume_oauth_state(state)
    assert consumed is not None
    assert consumed["provider"] == "google"

    assert db.consume_oauth_state(state) is None
    db.close()


def test_auth_db_get_or_create_oauth_user(tmp_path):
    db = AuthDB(tmp_path / "auth.db")
    user1 = db.get_or_create_oauth_user(
        "oauth@example.com", "OAuth User", "https://pic.url",
        "google", "google-123",
    )
    assert user1["email"] == "oauth@example.com"
    assert user1["provider"] == "google"

    user2 = db.get_or_create_oauth_user(
        "oauth@example.com", "OAuth User", "https://pic.url",
        "google", "google-123",
    )
    assert user2["id"] == user1["id"]
    db.close()


# ---------------------------------------------------------- API tests


def make_client(tmp_path):
    return TestClient(create_app(tmp_path))


def signup(client, email="test@example.com", password="test-password-123", name="Test"):
    r = client.post("/api/auth/signup", json={
        "email": email, "password": password, "name": name,
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert "token" in data
    assert data["user"]["email"] == email
    return data["token"]


def test_signup_and_login(tmp_path):
    client = make_client(tmp_path)
    token = signup(client)
    assert token

    r = client.post("/api/auth/login", json={
        "email": "test@example.com", "password": "test-password-123",
    })
    assert r.status_code == 200
    assert r.json()["token"]


def test_signup_duplicate(tmp_path):
    client = make_client(tmp_path)
    signup(client)
    r = client.post("/api/auth/signup", json={
        "email": "test@example.com", "password": "another-pass",
    })
    assert r.status_code == 409


def test_signup_short_password(tmp_path):
    client = make_client(tmp_path)
    r = client.post("/api/auth/signup", json={
        "email": "test@example.com", "password": "short",
    })
    assert r.status_code == 400


def test_login_wrong_password(tmp_path):
    client = make_client(tmp_path)
    signup(client)
    r = client.post("/api/auth/login", json={
        "email": "test@example.com", "password": "wrong-password",
    })
    assert r.status_code == 401


def test_auth_me(tmp_path):
    client = make_client(tmp_path)
    token = signup(client)

    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["user"]["email"] == "test@example.com"


def test_auth_me_no_token(tmp_path):
    client = make_client(tmp_path)
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["user"] is None


def test_logout(tmp_path):
    client = make_client(tmp_path)
    token = signup(client)

    r = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200

    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.json()["user"] is None


def test_api_requires_auth(tmp_path):
    client = make_client(tmp_path)
    r = client.get("/api/profiles")
    assert r.status_code == 401


def test_profile_ownership(tmp_path):
    client = make_client(tmp_path)
    token1 = signup(client, "user1@example.com")
    token2 = signup(client, "user2@example.com")

    # User 1 creates a profile
    r = client.post("/api/profiles",
                    json={"name": "User1 Brand"},
                    headers={"Authorization": f"Bearer {token1}"})
    assert r.status_code == 201

    # User 1 sees the profile
    r = client.get("/api/profiles", headers={"Authorization": f"Bearer {token1}"})
    assert len(r.json()) == 1

    # User 2 does not see it
    r = client.get("/api/profiles", headers={"Authorization": f"Bearer {token2}"})
    assert len(r.json()) == 0


def test_claim_profile(tmp_path):
    client = make_client(tmp_path)
    token = signup(client)

    # Create a profile without auth (simulate old unclaimed profile)
    from sceneforge.profile import create_profile
    create_profile("Old Brand", tmp_path)

    # User sees unclaimed profile
    r = client.get("/api/profiles", headers={"Authorization": f"Bearer {token}"})
    profiles = r.json()
    assert len(profiles) == 1
    assert profiles[0]["unclaimed"] is True

    # Claim it
    r = client.post(f"/api/profiles/{profiles[0]['slug']}/claim",
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200

    # Now it's owned
    r = client.get("/api/profiles", headers={"Authorization": f"Bearer {token}"})
    assert r.json()[0]["owned"] is True


def test_providers_endpoint(tmp_path):
    client = make_client(tmp_path)
    r = client.get("/api/auth/providers")
    assert r.status_code == 200
    data = r.json()
    assert data["email"] is True
    assert "google" in data
    assert "github" in data


# ------------------------------------------------- preferences tests


def test_preferences_db_crud(tmp_path):
    db = AuthDB(tmp_path / "auth.db")
    user = db.create_user("test@example.com", "Test", password="pass1234")
    prefs = db.get_preferences(user["id"])
    assert prefs == {}

    db.set_preferences(user["id"], {"last_profile": "my-brand", "theme": "dark"})
    prefs = db.get_preferences(user["id"])
    assert prefs["last_profile"] == "my-brand"
    assert prefs["theme"] == "dark"

    db.set_preferences(user["id"], {"last_profile": "other-brand"})
    prefs = db.get_preferences(user["id"])
    assert prefs["last_profile"] == "other-brand"
    assert prefs["theme"] == "dark"
    db.close()


def test_auth_me_includes_preferences(tmp_path):
    client = make_client(tmp_path)
    token = signup(client)

    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    data = r.json()
    assert "preferences" in data
    assert data["preferences"] == {}


def test_get_preferences_endpoint(tmp_path):
    client = make_client(tmp_path)
    token = signup(client)

    r = client.get("/api/auth/preferences",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json() == {}


def test_patch_preferences_endpoint(tmp_path):
    client = make_client(tmp_path)
    token = signup(client)

    r = client.patch("/api/auth/preferences",
                     json={"last_profile": "my-brand", "theme": "dark"},
                     headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["last_profile"] == "my-brand"
    assert r.json()["theme"] == "dark"

    # Verify via GET
    r = client.get("/api/auth/preferences",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.json()["last_profile"] == "my-brand"


def test_patch_preferences_filters_unknown_keys(tmp_path):
    client = make_client(tmp_path)
    token = signup(client)

    r = client.patch("/api/auth/preferences",
                     json={"last_profile": "ok", "hacker_key": "bad"},
                     headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert "hacker_key" not in r.json()
    assert r.json()["last_profile"] == "ok"


def test_preferences_require_auth(tmp_path):
    client = make_client(tmp_path)
    r = client.get("/api/auth/preferences")
    assert r.status_code == 401
