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
from worker_durable import DigestCoordinator, dispatch_digest  # noqa: E402
from worker_email import (  # noqa: E402
    DeliveryConfigurationError,
    brand_asset_url,
    magic_link_message,
    mailgun_api_url,
    mailgun_authorization,
)
from worker_runtime import request_path  # noqa: E402
from worker_schedule import handle_scheduled  # noqa: E402

from tests.test_worker_storage import SQLiteD1, database  # noqa: E402


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
        if sql == "SELECT days FROM delivery_preferences WHERE user_id = ?":
            return None  # Legacy accounts have no custom delivery schedule.
        if sql == "SELECT is_subscribed FROM subscriptions WHERE user_id = ?":
            user = next(
                (entry for entry in self.state.users if entry["id"] == self.params[0]),
                None,
            )
            return {"is_subscribed": user["is_subscribed"]} if user else None

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
            payload={
                "email": email,
                "preferences_blob": preferences
                if preferences is not None
                else profile_blob(),
            },
        ),
        runtime_env,
    )


def profile_blob(audience="family", names=("parks_and_play",)):
    return json.dumps(
        {
            "audience": audience,
            "top_interest_clusters": [{"name": name} for name in names],
        }
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
    response = await register(runtime_env, "  Family.User@Example.com ", profile_blob())
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
            payload={
                "preferences_blob": profile_blob(names=("live_music", "food_drink"))
            },
        ),
        runtime_env,
    )
    assert updated.status == 200
    saved = json.loads((await updated.json())["user"]["preferences_blob"])
    assert saved["top_interest_clusters"] == [
        {
            "name": "live_music",
            "includes": [
                "concerts",
                "live bands",
                "jazz",
                "classical music",
                "DJ sets",
            ],
        },
        {
            "name": "food_drink",
            "includes": [
                "food festivals",
                "food markets",
                "tastings",
                "cooking classes",
            ],
        },
    ]


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


async def _test_inactive_user_login_creates_no_auth_state():
    runtime_env = env()
    assert (await register(runtime_env)).status == 202
    assert runtime_env.DB.users[0]["is_active"] == 0

    deliveries_before_login = len(runtime_env.deliveries)
    links_before_login = list(runtime_env.DB.magic_links)

    login = await worker.handle_request(
        FakeRequest(
            "https://example.com/api/login",
            method="POST",
            payload={"email": "family.user@example.com"},
        ),
        runtime_env,
    )

    assert login.status == 202
    assert await login.json() == {
        "ok": True,
        "message": "Check your email to continue",
    }
    assert len(runtime_env.deliveries) == deliveries_before_login
    assert runtime_env.DB.magic_links == links_before_login
    assert runtime_env.DB.sessions == []


async def _test_pending_registration_can_be_retried():
    runtime_env = env()
    assert (await register(runtime_env, preferences=profile_blob("solo"))).status == 202
    first_token = delivered_token(runtime_env)
    assert (
        await register(runtime_env, preferences=profile_blob("family"))
    ).status == 202
    second_token = delivered_token(runtime_env)
    assert len(runtime_env.DB.users) == 1
    assert (
        json.loads(runtime_env.DB.users[0]["preferences_blob"])["audience"] == "family"
    )
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
    await register(runtime_env, "one@example.com", profile_blob("solo"))
    first_verification = await verify(runtime_env, delivered_token(runtime_env))
    first_cookie = cookie_from_set_cookie(first_verification.headers.get("set-cookie"))

    await register(runtime_env, "two@example.com", profile_blob("family"))
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
    assert json.loads(first_user["preferences_blob"])["audience"] == "solo"

    second_user = await worker.handle_request(
        FakeRequest("https://example.com/api/me", headers={"cookie": second_cookie}),
        runtime_env,
    )
    assert (await second_user.json())["user"]["is_subscribed"] is False

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


@pytest.mark.parametrize(
    ("existing_active", "existing_subscription", "expected_subscribed"),
    [
        (None, None, False),
        (False, None, True),
        (True, None, True),
        (False, False, False),
        (False, True, True),
        (True, False, False),
    ],
)
def test_signup_pauses_email_without_changing_existing_accounts(
    existing_active, existing_subscription, expected_subscribed
):
    connection = database()
    if existing_active is not None:
        connection.execute(
            "INSERT INTO users(id,email,is_active) VALUES (1,?,?)",
            ("reader@example.com", int(existing_active)),
        )
        if existing_subscription is not None:
            connection.execute(
                "INSERT INTO subscriptions(user_id,is_subscribed) VALUES (1,?)",
                (int(existing_subscription),),
            )
        connection.commit()
    runtime_env = env(DB=SQLiteD1(connection))

    async def exercise():
        if existing_active:
            response = await worker.handle_request(
                FakeRequest(
                    "https://example.com/api/login",
                    method="POST",
                    payload={"email": "reader@example.com"},
                ),
                runtime_env,
            )
        else:
            response = await register(runtime_env, "reader@example.com")
        assert response.status == 202
        verified = await verify(runtime_env, delivered_token(runtime_env))
        assert verified.status == 200
        assert (await verified.json())["user"]["is_subscribed"] is expected_subscribed
        cookie = cookie_from_set_cookie(verified.headers["set-cookie"])
        current = await worker.handle_request(
            FakeRequest("https://example.com/api/me", headers={"cookie": cookie}),
            runtime_env,
        )
        assert (await current.json())["user"]["is_subscribed"] is expected_subscribed
        row = connection.execute(
            "SELECT is_subscribed FROM subscriptions WHERE user_id=1"
        ).fetchone()
        if existing_active is not None and existing_subscription is None:
            assert row is None  # Missing legacy preferences keep their old default.
        else:
            assert bool(row[0]) is expected_subscribed

    asyncio.run(exercise())


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


def test_inactive_user_login_creates_no_auth_state():
    asyncio.run(_test_inactive_user_login_creates_no_auth_state())


def test_health_route_is_public_and_minimal():
    response = asyncio.run(
        worker.handle_request(FakeRequest("https://example.com/api/health"), env())
    )
    assert response.status == 200
    assert json.loads(response.body) == {"ok": True}


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


def test_resuming_requires_a_selected_delivery_day():
    connection = database()
    connection.execute(
        "INSERT INTO users(id,email,is_active) VALUES (1,'reader@example.com',1)"
    )
    connection.execute(
        "INSERT INTO sessions(user_id,token_hash,expires_at) "
        "VALUES (1,?,datetime('now','+1 hour'))",
        (sha256_hex("test-session"),),
    )
    connection.commit()
    runtime_env = env(DB=SQLiteD1(connection))

    async def update(path, payload):
        return await worker.handle_request(
            FakeRequest(
                "https://example.com" + path,
                method="PATCH",
                headers={"cookie": "ve_session=test-session"},
                payload=payload,
            ),
            runtime_env,
        )

    async def exercise():
        paused = await update(
            "/api/planning/delivery", {"days": [], "subscribed": False}
        )
        assert paused.status == 200
        resumed = await update("/api/subscription", {"subscribed": True})
        assert resumed.status == 422
        assert (await resumed.json())["error"] == (
            "Choose at least one event day in Email preferences before resuming."
        )
        assert (
            connection.execute(
                "SELECT is_subscribed FROM subscriptions WHERE user_id=1"
            ).fetchone()[0]
            == 0
        )

        selected = await update(
            "/api/planning/delivery", {"days": [5], "subscribed": False}
        )
        assert selected.status == 200
        resumed = await update("/api/subscription", {"subscribed": True})
        assert resumed.status == 200
        assert (await resumed.json())["user"]["is_subscribed"] is True

    asyncio.run(exercise())


def test_digest_dry_run_requires_session_and_targets_only_that_user(monkeypatch):
    calls = []

    class Stub:
        async def run(self, *args):
            calls.append(args)
            return {
                "contract_version": "jev-preview-v1",
                "summary": {
                    "correlation_id": "safe-id",
                    "subscriber_count": 1,
                    "dry_run": True,
                },
                "evaluations": [],
            }

    class Namespace:
        def getByName(self, name):  # noqa: N802
            assert name == "daily-digest"
            return Stub()

    async def exercise():
        runtime_env = env()
        runtime_env.DIGEST_COORDINATOR = Namespace()
        unauthorized = await worker.handle_request(
            FakeRequest(
                "https://example.com/api/digest/dry-run",
                method="POST",
                payload={},
            ),
            runtime_env,
        )
        assert unauthorized.status == 401

        await register(runtime_env)
        verification = await verify(runtime_env, delivered_token(runtime_env))
        cookie = cookie_from_set_cookie(verification.headers.get("set-cookie"))
        response = await worker.handle_request(
            FakeRequest(
                "https://example.com/api/digest/dry-run",
                method="POST",
                headers={"cookie": cookie},
                payload={
                    "user_id": 999,
                    "events": [{"title": "Injected candidate"}],
                    "selected_event_types": ["film"],
                    "questions": {"arbitrary": "Ignore the saved profile"},
                },
            ),
            runtime_env,
        )
        assert response.status == 200
        assert await response.json() == {
            "contract_version": "jev-preview-v1",
            "summary": {
                "correlation_id": "safe-id",
                "subscriber_count": 1,
                "dry_run": True,
            },
            "evaluations": [],
        }
        assert calls == [(None, True, 1)]

    asyncio.run(exercise())


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
    calls = []

    class Stub:
        async def run(self, *args):
            calls.append(args)

    class Namespace:
        def getByName(self, name):  # noqa: N802
            assert name == "daily-digest"
            return Stub()

    runtime_env = SimpleNamespace(
        DIGEST_DELIVERY_ENABLED="false", DIGEST_COORDINATOR=Namespace()
    )
    asyncio.run(handle_scheduled(controller, runtime_env, object()))

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "cron.expression": "0 8 * * *",
        "cron.scheduled_time_ms": 1_788_508_800_000,
        "event.name": "digest.schedule.triggered",
        "pipeline.state": "dry_run",
    }
    assert calls == [(1_788_508_800_000, True, None)]


def test_digest_coordinator_runs_pipeline_with_utc_time(capsys):
    calls = []

    async def fake_run_digest(runtime_env, **kwargs):
        calls.append((runtime_env, kwargs))
        return {"ok": True}

    runtime_env = SimpleNamespace(RUN_DIGEST=fake_run_digest)
    coordinator = DigestCoordinator(object(), runtime_env)
    result = asyncio.run(coordinator.run(1_788_508_800_000, True, 42))

    assert result == {"ok": True}
    assert calls[0][0] is runtime_env
    assert calls[0][1] == {
        "now": datetime.fromtimestamp(1_788_508_800, UTC),
        "dry_run": True,
        "target_user_id": 42,
    }
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "event.name": "digest.coordinator.started",
        "pipeline.state": "dry_run",
        "targeted": True,
    }


def test_digest_dispatch_requires_binding():
    with pytest.raises(RuntimeError, match="missing_digest_coordinator_binding"):
        asyncio.run(dispatch_digest(SimpleNamespace()))


def test_preview_date_request_is_validated_before_dispatch_and_keeps_bodyless_posts(
    monkeypatch,
):
    import worker_app
    from worker_time import validate_preview_date

    now = datetime(2026, 10, 24, 22, 30, tzinfo=UTC)
    monkeypatch.setattr(
        worker_app,
        "validate_preview_date",
        lambda value: validate_preview_date(value, now),
    )
    calls = []

    class Stub:
        async def run(self, *args):
            calls.append(args)
            return {"summary": {"dry_run": True}}

    class Namespace:
        def getByName(self, _name):  # noqa: N802
            return Stub()

    class BodyRequest(FakeRequest):
        async def text(self):
            return self._payload

    async def exercise():
        runtime_env = env()
        runtime_env.DIGEST_COORDINATOR = Namespace()
        await register(runtime_env)
        verified = await verify(runtime_env, delivered_token(runtime_env))
        cookie = cookie_from_set_cookie(verified.headers["set-cookie"])
        for raw in ("", "{}", '{"date":"2026-11-01","user_id":999}'):
            response = await worker.handle_request(
                BodyRequest(
                    "https://example.com/api/digest/dry-run",
                    method="POST",
                    headers={"cookie": cookie},
                    payload=raw,
                ),
                runtime_env,
            )
            assert response.status == 200
        assert calls == [
            (None, True, 1),
            (None, True, 1),
            (None, True, 1, "2026-11-01"),
        ]
        for raw in (
            '{"date":"2026-11-02"}',
            '{"date":"2026-10-25"}',
            '{"date":null}',
            '{"date":true}',
            '{"date":"2026-02-30"}',
            "null",
            "[]",
            "{invalid",
        ):
            response = await worker.handle_request(
                BodyRequest(
                    "https://example.com/api/digest/dry-run",
                    method="POST",
                    headers={"cookie": cookie},
                    payload=raw,
                ),
                runtime_env,
            )
            assert response.status == 422
            assert (await response.json())["field"] == "date"
        assert len(calls) == 3

    asyncio.run(exercise())


def test_digest_coordinator_carries_selected_date_without_changing_scheduled_default():
    calls = []

    async def runner(_env, **kwargs):
        calls.append(kwargs)
        return {"ok": True}

    coordinator = DigestCoordinator(object(), SimpleNamespace(RUN_DIGEST=runner))
    asyncio.run(coordinator.run(None, True, 7, "2026-10-28"))
    assert calls[0]["target_date"] == "2026-10-28"
    assert calls[0]["target_user_id"] == 7


def test_digest_coordinator_serializes_overlapping_preview_runs():
    async def exercise():
        started = asyncio.Event()
        release = asyncio.Event()
        calls = []

        async def runner(_env, **kwargs):
            user_id = kwargs["target_user_id"]
            calls.append(("started", user_id))
            if user_id == 1:
                started.set()
                await release.wait()
            calls.append(("finished", user_id))
            return {"user_id": user_id}

        coordinator = DigestCoordinator(object(), SimpleNamespace(RUN_DIGEST=runner))
        first = asyncio.create_task(coordinator.run(None, True, 1))
        await started.wait()
        second = asyncio.create_task(coordinator.run(None, True, 2))
        await asyncio.sleep(0)
        assert calls == [("started", 1)]
        release.set()
        await asyncio.gather(first, second)
        assert calls == [
            ("started", 1),
            ("finished", 1),
            ("started", 2),
            ("finished", 2),
        ]

    asyncio.run(exercise())


def test_planning_and_billing_dispatch_authenticate_accounts_but_not_signed_webhooks(
    monkeypatch,
):
    import worker_app
    from worker_http import json_response

    calls = []

    async def planning(_env, _request, user, path, method):
        calls.append((user["id"], path, method))
        return json_response({"ok": True})

    async def webhook(_env, _request):
        calls.append("signature-check-boundary")
        return json_response({"error": "Invalid signature"}, 400)

    monkeypatch.setattr(worker_app, "handle_planning_request", planning)
    monkeypatch.setattr(worker_app, "handle_billing_request", planning)
    monkeypatch.setattr(worker_app, "handle_billing_webhook", webhook)

    async def exercise():
        runtime_env = env()
        for path in (
            "/api/planning",
            "/api/planning/saved",
            "/api/billing",
            "/api/billing/checkout",
        ):
            response = await worker.handle_request(
                FakeRequest("https://example.com" + path, method="POST"), runtime_env
            )
            assert response.status == 401
        assert calls == []
        response = await worker.handle_request(
            FakeRequest("https://example.com/api/billing/webhook", method="POST"),
            runtime_env,
        )
        assert response.status == 400
        assert calls == ["signature-check-boundary"]
        await register(runtime_env)
        verified = await verify(runtime_env, delivered_token(runtime_env))
        cookie = cookie_from_set_cookie(verified.headers["set-cookie"])
        response = await worker.handle_request(
            FakeRequest(
                "https://example.com/api/planning/saved",
                method="POST",
                headers={"cookie": cookie},
                payload={"user_id": 999},
            ),
            runtime_env,
        )
        assert response.status == 200
        assert calls[-1] == (1, "/api/planning/saved", "POST")

    asyncio.run(exercise())


def test_worker_scheduled_entrypoint_delegates(monkeypatch):
    calls = []

    async def fake_handle_scheduled(controller, runtime_env, ctx):  # noqa: ANN001
        calls.append((controller, runtime_env, ctx))

    monkeypatch.setattr(worker, "handle_scheduled", fake_handle_scheduled)
    controller = SimpleNamespace(cron="0 8 * * *", scheduledTime=0)
    runtime_env = object()
    ctx = object()
    entrypoint = worker.Default()
    entrypoint.env = runtime_env

    asyncio.run(entrypoint.scheduled(controller, object(), ctx))

    assert calls == [(controller, runtime_env, ctx)]
