import asyncio
import hashlib
import hmac
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "cloudflare/worker/src"))

from worker_billing import (  # noqa: E402
    handle_billing_request,
    handle_billing_webhook,
    verify_webhook,
)

from tests.test_worker_storage import SQLiteD1, database  # noqa: E402


class Request:
    def __init__(self, payload="", headers=None):
        self.raw = payload
        self.headers = headers or {}

    async def text(self):
        return self.raw


class Stripe:
    def __init__(self):
        self.calls = []
        self.subscriptions = []
        self.price = {
            "active": True,
            "currency": "eur",
            "unit_amount": 300,
            "recurring": {"interval": "month", "interval_count": 1},
            "livemode": False,
        }
        self.subscription = {
            "id": "sub_one",
            "customer": "cus_one",
            "status": "active",
            "livemode": False,
            "cancel_at_period_end": False,
            "items": {
                "data": [
                    {"price": {"id": "price_month"}, "current_period_end": 2000000000}
                ]
            },
        }
        self.url = "https://checkout.stripe.com/c/pay/example"
        self.session_status = "open"

    async def __call__(self, method, path, params, key):
        self.calls.append((method, path, params, key))
        if path == "prices/price_month":
            return self.price
        if path == "customers":
            return {"id": "cus_one"}
        if path.startswith("subscriptions?"):
            return {"data": self.subscriptions, "has_more": False}
        if path == "checkout/sessions":
            return {"id": "cs_test_example", "url": self.url}
        if path == "checkout/sessions/cs_test_example":
            return {
                "url": self.url,
                "status": self.session_status,
                "customer": "cus_one",
                "subscription": "sub_one",
            }
        if path == "billing_portal/sessions":
            return {"url": "https://billing.stripe.com/p/session/example"}
        if path == "subscriptions/sub_one":
            self.subscriptions = [self.subscription]
            return self.subscription
        raise AssertionError(path)


def setup():
    connection = database()
    connection.executemany(
        "INSERT INTO users(id,email,is_active) VALUES (?,?,1)",
        [(1, "one@example.com"), (2, "two@example.com")],
    )
    connection.commit()
    stripe = Stripe()
    env = SimpleNamespace(
        DB=SQLiteD1(connection),
        STRIPE_TRANSPORT=stripe,
        STRIPE_SECRET_KEY="sk_test_fake",
        STRIPE_PRICE_ID="price_month",
        STRIPE_WEBHOOK_SECRET="whsec_obviouslyfake",
        BILLING_ENABLED="true",
        APP_BASE_URL="https://brisa.example",
    )
    return connection, env, stripe


def call(env, action="", method="GET", user_id=1, headers=None):
    response = asyncio.run(
        handle_billing_request(
            env,
            Request(headers=headers),
            {"id": user_id, "email": f"user{user_id}@example.com"},
            "/api/billing" + action,
            method,
        )
    )
    return response.status, json.loads(response.body)


def webhook_request(
    env, *, created=100, signature_valid=True, customer="cus_one", identifier="sub_one"
):
    raw = json.dumps(
        {
            "id": "evt_example",
            "type": "customer.subscription.updated",
            "livemode": False,
            "created": created,
            "data": {"object": {"id": identifier, "customer": customer}},
        }
    )
    timestamp = int(time.time())
    sig = hmac.new(
        env.STRIPE_WEBHOOK_SECRET.encode(),
        f"{timestamp}.{raw}".encode(),
        hashlib.sha256,
    ).hexdigest()
    signed = sig if signature_valid else "invalid"
    request = Request(
        raw,
        {"stripe-signature": f"t={timestamp},v1={signed}"},
    )
    return request


def webhook(env, **kwargs):
    return asyncio.run(handle_billing_webhook(env, webhook_request(env, **kwargs)))


def test_checkout_uses_server_price_identity_and_idempotency():
    connection, env, stripe = setup()
    for _ in range(2):
        status, body = call(env, "/checkout", "POST")
        assert status == 200 and body["url"].startswith("https://checkout.stripe.com/")
    creates = [entry for entry in stripe.calls if entry[1] == "checkout/sessions"]
    assert len(creates) == 1
    params, key = creates[0][2:]
    assert params["line_items[0][price]"] == "price_month"
    assert params["subscription_data[metadata][brisa_user_id]"] == "1"
    assert params["success_url"] == "https://brisa.example/?billing=success"
    assert key.startswith("brisa-checkout-")
    assert "preferences" not in json.dumps(stripe.calls)
    assert (
        connection.execute("SELECT COUNT(*) FROM billing_accounts").fetchone()[0] == 1
    )
    # A return URL or completed checkout request is not paid membership proof.
    assert call(env)[1]["membership"]["active"] is False


def test_stripe_subscription_prevents_duplicate_even_before_webhook():
    _, env, stripe = setup()
    stripe.subscriptions = [{"id": "sub_one", "status": "active"}]
    assert call(env, "/checkout", "POST")[0] == 409
    assert not any(entry[1] == "checkout/sessions" for entry in stripe.calls)


def test_checkout_failure_is_retryable_with_same_idempotency_key():
    _, env, stripe = setup()
    stripe.url = "https://evil.example/pay"
    assert call(env, "/checkout", "POST")[0] == 502
    stripe.url = "https://checkout.stripe.com/c/pay/example"
    assert call(env, "/checkout", "POST")[0] == 200
    keys = [entry[3] for entry in stripe.calls if entry[1] == "checkout/sessions"]
    assert len(keys) == 2 and keys[0] == keys[1]


def test_billing_gate_blocks_checkout_but_keeps_customer_portal_available():
    _, env, stripe = setup()
    assert call(env, "/checkout", "POST")[0] == 200
    env.BILLING_ENABLED = "false"
    assert call(env)[1]["membership"]["available"] is False
    assert call(env, "/checkout", "POST")[0] == 503
    assert call(env, "/portal", "POST")[0] == 200
    assert call(env, "/portal", "POST", user_id=2)[0] == 409
    assert stripe.calls[-1][2]["customer"] == "cus_one"


@pytest.mark.parametrize(
    "change",
    [
        {"currency": "usd"},
        {"unit_amount": 500},
        {"livemode": True},
        {"active": False},
        {"recurring": {"interval": "year"}},
    ],
)
def test_unexpected_price_never_opens_checkout(change):
    _, env, stripe = setup()
    stripe.price.update(change)
    assert call(env)[1]["membership"]["available"] is False
    assert call(env, "/checkout", "POST")[0] == 502
    assert not any(entry[1] == "checkout/sessions" for entry in stripe.calls)


def test_cross_origin_billing_mutation_is_rejected():
    _, env, stripe = setup()
    assert (
        call(env, "/checkout", "POST", headers={"origin": "https://evil.example"})[0]
        == 403
    )
    assert stripe.calls == []


def test_signed_webhook_activates_and_updates_cancellation_idempotently():
    connection, env, stripe = setup()
    call(env, "/checkout", "POST")
    assert webhook(env, signature_valid=False).status == 400
    assert call(env)[1]["membership"]["active"] is False
    assert webhook(env).status == 200
    assert webhook(env).status == 200
    body = call(env)[1]["membership"]
    assert body["active"] is True and body["current_period_end"] == 2000000000
    assert "customer_id" not in body
    stripe.subscription["cancel_at_period_end"] = True
    assert webhook(env, created=101).status == 200
    assert call(env)[1]["membership"]["cancel_at_period_end"] is True
    stripe.subscription["status"] = "canceled"
    assert webhook(env, created=102).status == 200
    assert call(env)[1]["membership"]["active"] is False
    stripe.subscription["status"] = "active"
    webhook(env, created=100)
    assert (
        connection.execute("SELECT status FROM billing_accounts").fetchone()[0]
        == "canceled"
    )


def test_webhook_ignores_unknown_customer_wrong_price_and_mode():
    _, env, stripe = setup()
    call(env, "/checkout", "POST")
    stripe.subscription["customer"] = "cus_other"
    assert webhook(env, customer="cus_other").status == 200
    assert webhook(env).status == 502
    assert call(env)[1]["membership"]["active"] is False
    stripe.subscription["customer"] = "cus_one"
    stripe.subscription["items"]["data"][0]["price"]["id"] = "price_other"
    webhook(env)
    assert call(env)[1]["membership"]["active"] is False
    env.STRIPE_SECRET_KEY = "sk_live_fake"
    webhook(env)
    assert call(env)[1]["membership"]["active"] is False


@pytest.mark.parametrize(
    "raw,signature", [("{}", ""), ("{}", "t=0,v1=bad"), ("[]", "t=100,v1=bad")]
)
def test_invalid_webhook_signatures(raw, signature):
    with pytest.raises(ValueError):
        verify_webhook(raw, signature, "whsec_fake", now=100)


def test_signature_checks_raw_bytes_tolerance_and_rotation():
    raw, now, secret = '{"ok":true}', 1000, "whsec_fake"
    sig = hmac.new(secret.encode(), f"{now}.{raw}".encode(), hashlib.sha256).hexdigest()
    assert verify_webhook(raw, f"t={now},v1=old,v1={sig}", secret, now=1001) == {
        "ok": True
    }
    with pytest.raises(ValueError):
        verify_webhook(raw + " ", f"t={now},v1={sig}", secret, now=1001)
    with pytest.raises(ValueError):
        verify_webhook(raw, f"t={now},v1={sig}", secret, now=1301)


def test_same_second_webhooks_cannot_publish_an_older_snapshot():
    connection, env, stripe = setup()
    call(env, "/checkout", "POST")

    async def concurrent():
        first_started, release_first = asyncio.Event(), asyncio.Event()
        calls = 0

        async def transport(method, path, params, key):
            nonlocal calls
            if path == "subscriptions/sub_one":
                return stripe.subscription
            calls += 1
            snapshot = {
                **stripe.subscription,
                "status": "active" if calls == 1 else "canceled",
            }
            if calls == 1:
                first_started.set()
                await release_first.wait()
            return {"data": [snapshot], "has_more": False}

        env.STRIPE_TRANSPORT = transport
        raw = json.dumps(
            {
                "type": "customer.subscription.updated",
                "livemode": False,
                "created": 100,
                "data": {"object": {"id": "sub_one", "customer": "cus_one"}},
            }
        )
        now = int(time.time())
        sig = hmac.new(
            env.STRIPE_WEBHOOK_SECRET.encode(), f"{now}.{raw}".encode(), hashlib.sha256
        ).hexdigest()
        request = Request(raw, {"stripe-signature": f"t={now},v1={sig}"})
        first = asyncio.create_task(handle_billing_webhook(env, request))
        await first_started.wait()
        second = await handle_billing_webhook(env, request)
        release_first.set()
        assert (await first).status == second.status == 200

    asyncio.run(concurrent())
    assert (
        connection.execute("SELECT status FROM billing_accounts").fetchone()[0]
        == "canceled"
    )


def test_unrelated_product_event_does_not_suppress_inflight_membership():
    connection, env, stripe = setup()
    call(env, "/checkout", "POST")

    async def concurrent():
        started, release = asyncio.Event(), asyncio.Event()
        wrong = {
            **stripe.subscription,
            "id": "sub_other",
            "items": {"data": [{"price": {"id": "price_other"}}]},
        }

        async def transport(method, path, params, key):
            if path == "subscriptions/sub_other":
                return wrong
            if path == "subscriptions/sub_one":
                return stripe.subscription
            started.set()
            await release.wait()
            return {"data": [stripe.subscription, wrong], "has_more": False}

        env.STRIPE_TRANSPORT = transport
        first = asyncio.create_task(handle_billing_webhook(env, webhook_request(env)))
        await started.wait()
        second = await handle_billing_webhook(
            env, webhook_request(env, identifier="sub_other", created=101)
        )
        release.set()
        assert second.status == (await first).status == 200

    asyncio.run(concurrent())
    row = connection.execute(
        "SELECT status,last_event_created FROM billing_accounts"
    ).fetchone()
    assert tuple(row) == ("active", 100)


def test_old_cancellation_same_second_cannot_revoke_new_membership():
    connection, env, stripe = setup()
    call(env, "/checkout", "POST")
    old = {**stripe.subscription, "status": "canceled", "created": 99}
    new = {**stripe.subscription, "id": "sub_new", "created": 100}

    async def transport(method, path, params, key):
        if path == "subscriptions/sub_new":
            return new
        if path == "subscriptions/sub_one":
            return old
        return {"data": [new, old], "has_more": False}

    env.STRIPE_TRANSPORT = transport
    assert webhook(env, identifier="sub_new").status == 200
    assert webhook(env).status == 200
    row = connection.execute(
        "SELECT status,subscription_id FROM billing_accounts"
    ).fetchone()
    assert tuple(row) == ("active", "sub_new")


def test_canceled_member_gets_fresh_checkout_without_waiting_an_hour():
    _, env, stripe = setup()
    call(env, "/checkout", "POST")
    webhook(env)
    stripe.subscription["status"] = "canceled"
    stripe.session_status = "complete"
    webhook(env, created=101)
    assert call(env, "/checkout", "POST")[0] == 200
    keys = [entry[3] for entry in stripe.calls if entry[1] == "checkout/sessions"]
    assert len(keys) == 2 and keys[0] != keys[1]


def test_checkout_completing_during_cache_lookup_cannot_create_duplicate():
    _, env, stripe = setup()
    call(env, "/checkout", "POST")
    original = env.STRIPE_TRANSPORT

    async def transport(method, path, params, key):
        if path == "checkout/sessions/cs_test_example":
            stripe.session_status = "complete"
        return await original(method, path, params, key)

    env.STRIPE_TRANSPORT = transport
    assert call(env, "/checkout", "POST")[0] == 409
    assert (
        len([entry for entry in stripe.calls if entry[1] == "checkout/sessions"]) == 1
    )
