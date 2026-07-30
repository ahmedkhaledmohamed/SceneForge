"""Multi-user authentication: SQLite-backed users, sessions, and OAuth state."""

import hashlib
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bcrypt

SESSION_TTL_DAYS = 30

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    avatar_url TEXT DEFAULT '',
    password_hash TEXT DEFAULT '',
    provider TEXT DEFAULT 'email',
    provider_id TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_provider
    ON users(provider, provider_id) WHERE provider_id != '';

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS oauth_states (
    state TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS user_preferences (
    user_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (user_id, key),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _check_password(password: str, hashed: str) -> bool:
    if hashed.startswith("$2"):
        return bcrypt.checkpw(password.encode(), hashed.encode())
    # Legacy PBKDF2 from old profile passwords — format is hex(pbkdf2(pw, salt))
    # Not supported for user accounts, only bcrypt
    return False


def _check_legacy_pbkdf2(password: str, hash_hex: str, salt: str) -> bool:
    computed = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), 100_000
    ).hex()
    return computed == hash_hex


class AuthDB:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def _migrate(self):
        self.conn.executescript(SCHEMA_SQL)
        self.conn.execute(
            "DELETE FROM sessions WHERE expires_at < datetime('now')"
        )
        self.conn.execute(
            "DELETE FROM oauth_states WHERE created_at < datetime('now', '-10 minutes')"
        )
        self.conn.commit()

    def create_user(self, email: str, name: str, password: str = "",
                    provider: str = "email", provider_id: str = "",
                    avatar_url: str = "") -> dict:
        user_id = str(uuid.uuid4())
        pw_hash = _hash_password(password) if password else ""
        self.conn.execute(
            "INSERT INTO users (id, email, name, password_hash, provider, provider_id, avatar_url) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, email.lower().strip(), name, pw_hash, provider, provider_id, avatar_url),
        )
        self.conn.commit()
        return self.get_user(user_id)

    def get_user(self, user_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_user_by_email(self, email: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM users WHERE email = ?", (email.lower().strip(),)
        ).fetchone()
        return dict(row) if row else None

    def get_user_by_provider(self, provider: str, provider_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM users WHERE provider = ? AND provider_id = ?",
            (provider, provider_id),
        ).fetchone()
        return dict(row) if row else None

    def get_or_create_oauth_user(self, email: str, name: str, avatar_url: str,
                                  provider: str, provider_id: str) -> dict:
        user = self.get_user_by_provider(provider, provider_id)
        if user:
            return user
        user = self.get_user_by_email(email)
        if user:
            return user
        return self.create_user(
            email=email, name=name, provider=provider,
            provider_id=provider_id, avatar_url=avatar_url,
        )

    def create_session(self, user_id: str) -> str:
        token = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(days=SESSION_TTL_DAYS)
        self.conn.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user_id, expires.isoformat()),
        )
        self.conn.commit()
        return token

    def validate_session(self, token: str) -> dict | None:
        row = self.conn.execute(
            "SELECT u.* FROM sessions s "
            "JOIN users u ON s.user_id = u.id "
            "WHERE s.token = ? AND s.expires_at > datetime('now')",
            (token,),
        ).fetchone()
        return dict(row) if row else None

    def revoke_session(self, token: str) -> None:
        self.conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        self.conn.commit()

    def save_oauth_state(self, provider: str) -> str:
        state = secrets.token_urlsafe(32)
        self.conn.execute(
            "INSERT INTO oauth_states (state, provider) VALUES (?, ?)",
            (state, provider),
        )
        self.conn.commit()
        return state

    def consume_oauth_state(self, state: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM oauth_states WHERE state = ? "
            "AND created_at > datetime('now', '-10 minutes')",
            (state,),
        ).fetchone()
        if row:
            self.conn.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
            self.conn.commit()
            return dict(row)
        return None

    def get_preferences(self, user_id: str) -> dict:
        rows = self.conn.execute(
            "SELECT key, value FROM user_preferences WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        return {row["key"]: row["value"] for row in rows}

    def set_preferences(self, user_id: str, prefs: dict) -> dict:
        for key, value in prefs.items():
            self.conn.execute(
                "INSERT INTO user_preferences (user_id, key, value) "
                "VALUES (?, ?, ?) ON CONFLICT(user_id, key) DO UPDATE SET value = ?",
                (user_id, key, str(value), str(value)),
            )
        self.conn.commit()
        return self.get_preferences(user_id)

    def close(self):
        self.conn.close()
