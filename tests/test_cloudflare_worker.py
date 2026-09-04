import asyncio
import importlib.util
import json
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

WORKER_PATH = (
    Path(__file__).resolve().parents[1] / "cloudflare" / "worker" / "src" / "index.py"
)

sys.path.insert(0, str(WORKER_PATH.parent))
spec = importlib.util.spec_from_file_location("cloudflare_worker_index", WORKER_PATH)
worker = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(worker)

from worker_auth import sha256_hex  # noqa: E402
from worker_email import (  # noqa: E402
    DeliveryConfigurationError,
    brand_asset_url,
    magic_link_message,
    mailgun_api_url,
    mailgun_authorization,
)
from worker_runtime import request_path  # noqa: E402
from worker_schedule import handle_scheduled  # noqa: E402


class Headers(dict):
    def __init__(self, initial=None):
        super().__init__()
        for key, value in (initial or {}).items():
            self[key] = value

    def __setitem__(self, key, value):
        super().__setitem__(str(key).lower(), value)

    def get(self, key, default=None):
        return super().get(str(key).lower(), default)


class FakeRequest:
    def __init__(
        self, url, method="GET", headers=None, payload=None, invalid_json=False
    ):
        self.url = url
        self.method = method
        self.headers = Headers(headers)
        self._payload = payload
        self._invalid_json = invalid_json

    async def json(self):
        if self._invalid_json:
            raise ValueError("invalid json")
        return self._payload


class InMemoryD1:
    def __init__(self):
        self.users = []
        self.sessions = []
        self.magic_links = []
        self.user_id = 0
        self.session_id = 0
        self.magic_link_id = 0

    def prepare(self, sql):
        return InMemoryStatement(self, sql)


class InMemoryStatement:
    def __init__(self, state, sql):
        self.state = state
        self.sql = " ".join(sql.split())
        self.params = []

    def bind(self, *params):
        self.params = list(params)
        return self

    async def run(self):
        sql = self.sql
        if sql.startswith("INSERT INTO users (email, preferences_blob, is_active)"):
            email, preferences_blob = self.params
            if any(user["email"] == email for user in self.state.users):
                raise ValueError("UNIQUE constraint failed: users.email")
            user = {
                "id": self.state.user_id + 1,
                "email": email,
                "preferences_blob": preferences_blob,
                "is_active": 0,
                "is_subscribed": True,
            }
            self.state.user_id = user["id"]
            self.state.users.append(user)
            return changed(1, user["id"])

        if sql.startswith("INSERT INTO sessions (user_id, token_hash, expires_at)"):
            user_id, token_hash, ttl_clause = self.params
            session = {
                "id": self.state.session_id + 1,
                "user_id": int(user_id),
                "token_hash": token_hash,
                "expires_at": expiry(ttl_clause),
            }
            self.state.session_id = session["id"]
            self.state.sessions.append(session)
            return changed(1, session["id"])

        if sql.startswith(
            "INSERT INTO magic_links (user_id, token_hash, purpose, expires_at)"
        ):
            user_id, token_hash, purpose, ttl_clause = self.params
            link = {
                "id": self.state.magic_link_id + 1,
                "user_id": int(user_id),
                "token_hash": token_hash,
                "purpose": purpose,
                "expires_at": expiry(ttl_clause),
                "consumed_at": None,
            }
            self.state.magic_link_id = link["id"]
            self.state.magic_links.append(link)
            return changed(1, link["id"])

        if sql.startswith("UPDATE users SET preferences_blob = ? WHERE id = ?"):
            preferences_blob, user_id = self.params
            for user in self.state.users:
                if user["id"] == int(user_id):
                    user["preferences_blob"] = preferences_blob
                    return changed(1)
            return changed(0)

        if sql.startswith("UPDATE users SET is_active = 1 WHERE id = ?"):
            user_id = int(self.params[0])
            for user in self.state.users:
                if user["id"] == user_id:
                    user["is_active"] = 1
                    return changed(1)
            return changed(0)

        if sql.startswith("UPDATE magic_links SET consumed_at = CURRENT_TIMESTAMP"):
            link_id = int(self.params[0])
            for link in self.state.magic_links:
                if (
                    link["id"] == link_id
                    and link["consumed_at"] is None
                    and link["expires_at"] > datetime.now(UTC)
                ):
                    link["consumed_at"] = datetime.now(UTC)
                    return changed(1)
            return changed(0)

        if sql.startswith("DELETE FROM sessions WHERE token_hash = ?"):
            token_hash = self.params[0]
            before = len(self.state.sessions)
            self.state.sessions = [
                session
                for session in self.state.sessions
                if session["token_hash"] != token_hash
            ]
            return changed(before - len(self.state.sessions))

        if sql.startswith("DELETE FROM magic_links WHERE user_id = ?"):
            user_id, purpose = self.params
            before = len(self.state.magic_links)
            self.state.magic_links = [
                link
                for link in self.state.magic_links
                if not (link["user_id"] == int(user_id) and link["purpose"] == purpose)
            ]
            return changed(before - len(self.state.magic_links))

        if sql.startswith("INSERT INTO subscriptions (user_id, is_subscribed"):
            user_id, subscribed = self.params
            for user in self.state.users:
                if user["id"] == int(user_id):
                    user["is_subscribed"] = bool(subscribed)
                    return changed(1)
            return changed(0)

        raise AssertionError(f"Unhandled run SQL: {sql}")

    async def first(self):
        sql = self.sql
        if sql.startswith(
            "SELECT id, email, preferences_blob, is_active FROM users WHERE email = ?"
        ):
            email = self.params[0]
            return next(
                (user for user in self.state.users if user["email"] == email), None
            )

        if sql.startswith(
            "SELECT id, email, preferences_blob, is_active FROM users WHERE id = ?"
        ):
            user_id = int(self.params[0])
            return next(
                (user for user in self.state.users if user["id"] == user_id), None
            )

        if sql.startswith("SELECT ml.id, ml.user_id, ml.purpose FROM magic_links"):
            token_hash = self.params[0]
            return next(
                (
                    {
                        "id": link["id"],
                        "user_id": link["user_id"],
                        "purpose": link["purpose"],
                    }
                    for link in self.state.magic_links
                    if link["token_hash"] == token_hash
                    and link["consumed_at"] is None
                    and link["expires_at"] > datetime.now(UTC)
                ),
                None,
            )

        if "FROM sessions AS s INNER JOIN users AS u" in sql:
            token_hash = self.params[0]
            session = next(
                (
                    entry
                    for entry in self.state.sessions
                    if entry["token_hash"] == token_hash
                ),
                None,
            )
            if session is None or session["expires_at"] <= datetime.now(UTC):
                return None
            user = next(
                (
                    entry
                    for entry in self.state.users
                    if entry["id"] == session["user_id"]
                ),
                None,
            )
            if user is None or not user["is_active"]:
                return None
            return {**user, "session_id": session["id"]}

        raise AssertionError(f"Unhandled first SQL: {sql}")


def changed(changes, last_row_id=None):
    return {"success": True, "meta": {"changes": changes, "last_row_id": last_row_id}}


def expiry(ttl_clause):
    amount, unit = str(ttl_clause).replace("+", "").split()
    delta = (
        timedelta(hours=int(amount))
        if unit == "hours"
        else timedelta(minutes=int(amount))
    )
    return datetime.now(UTC) + delta


def env(**overrides):
    deliveries = []

    async def deliver(recipient, link):
        deliveries.append((recipient, link))

    values = {
        "DB": InMemoryD1(),
        "SESSION_TTL_HOURS": "24",
        "MAGIC_LINK_TTL_MINUTES": "15",
        "APP_BASE_URL": "https://events.example.com",
        "MAGIC_LINK_DELIVERY": deliver,
        "deliveries": deliveries,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def cookie_from_set_cookie(set_cookie_header):
    return set_cookie_header.split(";", 1)[0]


def delivered_token(runtime_env):
    return parse_qs(urlsplit(runtime_env.deliveries[-1][1]).query)["token"][0]


async def register(runtime_env, email="family.user@example.com", preferences=None):
    return await worker.handle_request(
        FakeRequest(
            "https://example.com/api/register",
            method="POST",
            payload={"email": email, "preferences_blob": preferences},
        ),
        runtime_env,
    )


async def verify(runtime_env, token):
    return await worker.handle_request(
        FakeRequest(
            "https://example.com/api/auth/verify",
            method="POST",
            payload={"token": token},
        ),
        runtime_env,
    )


async def _test_registration_verification_and_preferences():
    runtime_env = env()
    response = await register(
        runtime_env, "  Family.User@Example.com ", '{"audience":"family"}'
    )
    assert response.status == 202
    assert response.headers.get("set-cookie") is None
    assert await response.json() == {
        "ok": True,
        "message": "Check your email to continue",
    }
    assert runtime_env.DB.users[0]["is_active"] == 0

    token = delivered_token(runtime_env)
    stored = runtime_env.DB.magic_links[0]
    assert stored["token_hash"] == sha256_hex(token)
    assert stored["token_hash"] != token
    assert runtime_env.deliveries[0][0] == "family.user@example.com"

    verified = await verify(runtime_env, token)
    assert verified.status == 200
    assert runtime_env.DB.users[0]["is_active"] == 1
    set_cookie = verified.headers.get("set-cookie")
    assert "ve_session=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie

    cookie = cookie_from_set_cookie(set_cookie)
    me_response = await worker.handle_request(
        FakeRequest("https://example.com/api/me", headers={"cookie": cookie}),
        runtime_env,
    )
    assert me_response.status == 200
    updated = await worker.handle_request(
        FakeRequest(
            "https://example.com/api/preferences",
            method="PATCH",
            headers={"cookie": cookie},
            payload={"preferences_blob": '{"interests":["music"]}'},
        ),
        runtime_env,
    )
    assert updated.status == 200
    assert (await updated.json())["user"][
        "preferences_blob"
    ] == '{"interests":["music"]}'


async def _test_magic_link_is_single_use():
    runtime_env = env()
    await register(runtime_env)
    token = delivered_token(runtime_env)
    assert (await verify(runtime_env, token)).status == 200
    sessions_after_first_use = len(runtime_env.DB.sessions)
    assert (await verify(runtime_env, token)).status == 401
    assert len(runtime_env.DB.sessions) == sessions_after_first_use


async def _test_expired_magic_link_is_rejected():
    runtime_env = env(MAGIC_LINK_TTL_MINUTES="-1")
    await register(runtime_env)
    assert (await verify(runtime_env, delivered_token(runtime_env))).status == 401
    assert runtime_env.DB.users[0]["is_active"] == 0
    assert runtime_env.DB.sessions == []


async def _test_login_sends_link_and_logout_revokes_session():
    runtime_env = env()
    await register(runtime_env)
    registration = await verify(runtime_env, delivered_token(runtime_env))
    initial_cookie = cookie_from_set_cookie(registration.headers.get("set-cookie"))
    logout = await worker.handle_request(
        FakeRequest(
            "https://example.com/api/logout",
            method="POST",
            headers={"cookie": initial_cookie},
        ),
        runtime_env,
    )
    assert logout.status == 200
    assert "Max-Age=0" in logout.headers.get("set-cookie")

    login = await worker.handle_request(
        FakeRequest(
            "https://example.com/api/login",
            method="POST",
            payload={"email": "family.user@example.com"},
        ),
        runtime_env,
    )
    assert login.status == 202
    assert (await verify(runtime_env, delivered_token(runtime_env))).status == 200
    deliveries = len(runtime_env.deliveries)
    missing = await worker.handle_request(
        FakeRequest(
            "https://example.com/api/login",
            method="POST",
            payload={"email": "unknown@example.com"},
        ),
        runtime_env,
    )
    assert missing.status == 202
    assert len(runtime_env.deliveries) == deliveries


async def _test_pending_registration_can_be_retried():
    runtime_env = env()
    assert (await register(runtime_env, preferences="first")).status == 202
    first_token = delivered_token(runtime_env)
    assert (await register(runtime_env, preferences="second")).status == 202
    second_token = delivered_token(runtime_env)
    assert len(runtime_env.DB.users) == 1
    assert runtime_env.DB.users[0]["preferences_blob"] == "second"
    assert len(runtime_env.DB.magic_links) == 1
    assert (await verify(runtime_env, first_token)).status == 401
    assert (await verify(runtime_env, second_token)).status == 200


async def _test_active_duplicate_registration_conflicts():
    runtime_env = env()
    await register(runtime_env)
    await verify(runtime_env, delivered_token(runtime_env))
    assert (await register(runtime_env)).status == 409


async def _test_delivery_requires_explicit_configuration():
    runtime_env = env(MAGIC_LINK_DELIVERY=None)
    response = await register(runtime_env)
    assert response.status == 503
    assert await response.json() == {"error": "Email delivery is not configured"}


async def _test_invalid_inputs_and_session_are_rejected():
    runtime_env = env()
    invalid_json = await worker.handle_request(
        FakeRequest(
            "https://example.com/api/register", method="POST", invalid_json=True
        ),
        runtime_env,
    )
    assert invalid_json.status == 400
    assert (await register(runtime_env, "not-an-email")).status == 400
    assert (await verify(runtime_env, "")).status == 400
    no_session = await worker.handle_request(
        FakeRequest("https://example.com/api/me"), runtime_env
    )
    assert no_session.status == 401


async def _test_subscription_controls_are_authenticated_and_isolated():
    runtime_env = env()
    await register(runtime_env, "one@example.com", '{"audience":"solo"}')
    first_verification = await verify(runtime_env, delivered_token(runtime_env))
    first_cookie = cookie_from_set_cookie(first_verification.headers.get("set-cookie"))

    await register(runtime_env, "two@example.com", '{"audience":"family"}')
    second_verification = await verify(runtime_env, delivered_token(runtime_env))
    second_cookie = cookie_from_set_cookie(
        second_verification.headers.get("set-cookie")
    )

    unauthorized = await worker.handle_request(
        FakeRequest(
            "https://example.com/api/subscription",
            method="PATCH",
            payload={"subscribed": False},
        ),
        runtime_env,
    )
    assert unauthorized.status == 401

    for _ in range(2):
        paused = await worker.handle_request(
            FakeRequest(
                "https://example.com/api/subscription",
                method="PATCH",
                headers={"cookie": first_cookie},
                payload={"subscribed": False},
            ),
            runtime_env,
        )
        assert paused.status == 200
        assert (await paused.json())["user"]["is_subscribed"] is False

    still_authenticated = await worker.handle_request(
        FakeRequest("https://example.com/api/me", headers={"cookie": first_cookie}),
        runtime_env,
    )
    first_user = (await still_authenticated.json())["user"]
    assert first_user["is_subscribed"] is False
    assert first_user["preferences_blob"] == '{"audience":"solo"}'

    second_user = await worker.handle_request(
        FakeRequest("https://example.com/api/me", headers={"cookie": second_cookie}),
        runtime_env,
    )
    assert (await second_user.json())["user"]["is_subscribed"] is True

    resumed = await worker.handle_request(
        FakeRequest(
            "https://example.com/api/subscription",
            method="PATCH",
            headers={"cookie": first_cookie},
            payload={"subscribed": True},
        ),
        runtime_env,
    )
    assert resumed.status == 200
    assert (await resumed.json())["user"]["is_subscribed"] is True

    invalid = await worker.handle_request(
        FakeRequest(
            "https://example.com/api/subscription",
            method="PATCH",
            headers={"cookie": first_cookie},
            payload={"subscribed": "false"},
        ),
        runtime_env,
    )
    assert invalid.status == 400


def test_registration_verification_and_preferences():
    asyncio.run(_test_registration_verification_and_preferences())


def test_mailgun_request_helpers():
    assert mailgun_api_url("sandbox.example.mailgun.org") == (
        "https://api.mailgun.net/v3/sandbox.example.mailgun.org/messages"
    )
    assert mailgun_api_url("messages.example.com", "EU") == (
        "https://api.eu.mailgun.net/v3/messages.example.com/messages"
    )
    assert mailgun_authorization("key-example") == "Basic YXBpOmtleS1leGFtcGxl"

    message = magic_link_message(
        "reader@example.com",
        "València Events <postmaster@sandbox.example.mailgun.org>",
        'https://events.example.com/auth/verify?token=a&next="setup"',
    )
    assert message["to"] == "reader@example.com"
    assert message["subject"] == "Your Brisa sign-in link for València"
    assert "Your next day in València is waiting" in message["text"]
    assert "<!doctype html>" in message["html"]
    assert 'role="presentation"' in message["html"]
    assert "Continue to Brisa" in message["html"]
    assert "a&amp;next=&quot;setup&quot;" in message["html"]
    assert 'src="https://events.example.com/brand/brisa-mark.png"' in message["html"]
    assert brand_asset_url("https://events.example.com/auth/verify?token=a") == (
        "https://events.example.com/brand/brisa-mark.png"
    )

    with pytest.raises(DeliveryConfigurationError, match="MAILGUN_REGION"):
        mailgun_api_url("sandbox.example.mailgun.org", "apac")


def test_magic_link_is_single_use():
    asyncio.run(_test_magic_link_is_single_use())


def test_expired_magic_link_is_rejected():
    asyncio.run(_test_expired_magic_link_is_rejected())


def test_login_sends_link_and_logout_revokes_session():
    asyncio.run(_test_login_sends_link_and_logout_revokes_session())


def test_pending_registration_can_be_retried():
    asyncio.run(_test_pending_registration_can_be_retried())


def test_active_duplicate_registration_conflicts():
    asyncio.run(_test_active_duplicate_registration_conflicts())


def test_delivery_requires_explicit_configuration():
    asyncio.run(_test_delivery_requires_explicit_configuration())


def test_invalid_inputs_and_session_are_rejected():
    asyncio.run(_test_invalid_inputs_and_session_are_rejected())


def test_subscription_controls_are_authenticated_and_isolated():
    asyncio.run(_test_subscription_controls_are_authenticated_and_isolated())


def test_request_path_ignores_query_and_fragment():
    assert (
        request_path("https://example.com/api/health?probe=1#status") == "/api/health"
    )


def test_schema_migration_is_additive_and_idempotent():
    schema_path = WORKER_PATH.parent / "schema.sql"
    database = sqlite3.connect(":memory:")
    database.executescript(
        """
        CREATE TABLE users (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          email TEXT UNIQUE NOT NULL,
          preferences_blob TEXT,
          is_active INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE sessions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          token_hash TEXT UNIQUE NOT NULL,
          expires_at TEXT NOT NULL,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    schema = schema_path.read_text()
    database.executescript(schema)
    database.executescript(schema)

    tables = {
        row[0]
        for row in database.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert {
        "users",
        "sessions",
        "magic_links",
        "subscriptions",
        "events",
        "digest_runs",
        "recommendations",
        "deliveries",
    } <= tables


def test_scheduled_handler_emits_safe_scaffold_event(capsys):
    controller = SimpleNamespace(cron="0 8 * * *", scheduledTime=1_788_508_800_000)

    asyncio.run(handle_scheduled(controller, object(), object()))

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "cron.expression": "0 8 * * *",
        "cron.scheduled_time_ms": 1_788_508_800_000,
        "event.name": "digest.schedule.triggered",
        "pipeline.state": "scaffolded",
    }


def test_worker_scheduled_entrypoint_delegates(monkeypatch):
    calls = []

    async def fake_handle_scheduled(controller, runtime_env, ctx):  # noqa: ANN001
        calls.append((controller, runtime_env, ctx))

    monkeypatch.setattr(worker, "handle_scheduled", fake_handle_scheduled)
    controller = SimpleNamespace(cron="0 8 * * *", scheduledTime=0)
    runtime_env = object()
    ctx = object()

    asyncio.run(worker.Default().scheduled(controller, runtime_env, ctx))

    assert calls == [(controller, runtime_env, ctx)]
