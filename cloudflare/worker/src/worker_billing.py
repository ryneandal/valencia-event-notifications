"""Stripe-hosted billing. No payment details or provider secrets reach the app."""

import hashlib
import hmac
import json
import re
import secrets
import time
from typing import Any
from urllib.parse import urlencode, urlsplit

from worker_http import AppResponse, json_response
from worker_runtime import env_value, header_get, to_python

STRIPE_API_VERSION = "2025-09-30.clover"
OPEN_STATUSES = {"active", "trialing", "past_due", "unpaid", "paused", "incomplete"}


class BillingUnavailableError(RuntimeError):
    pass


def billing_config(env: Any) -> dict[str, Any]:
    key = str(env_value(env, "STRIPE_SECRET_KEY", ""))
    base = str(env_value(env, "APP_BASE_URL", "")).rstrip("/")
    price = str(env_value(env, "STRIPE_PRICE_ID", ""))
    webhook = str(env_value(env, "STRIPE_WEBHOOK_SECRET", ""))
    live = key.startswith(("sk_live_", "rk_live_"))
    valid_key = key.startswith(("sk_test_", "sk_live_", "rk_test_", "rk_live_"))
    ready = bool(
        valid_key
        and re.fullmatch(r"price_[A-Za-z0-9]+", price)
        and webhook.startswith("whsec_")
        and base.startswith("https://")
        and str(env_value(env, "BILLING_ENABLED", "false")).lower() == "true"
    )
    return {
        "key": key,
        "base": base,
        "price": price,
        "webhook": webhook,
        "livemode": live,
        "ready": ready,
    }


async def stripe_request(
    env: Any,
    method: str,
    path: str,
    params: dict[str, str] | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """An injected async transport makes every billing test offline."""
    fake = env_value(env, "STRIPE_TRANSPORT")
    if callable(fake):
        return await fake(method, path, params or {}, idempotency_key)
    from js import AbortSignal, Object, fetch  # type: ignore[import-not-found]
    from pyodide.ffi import to_js  # type: ignore[import-not-found]

    headers = {
        "authorization": "Bearer " + billing_config(env)["key"],
        "Stripe-Version": STRIPE_API_VERSION,
        "content-type": "application/x-www-form-urlencoded",
    }
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    options = {
        "method": method,
        "headers": headers,
        "signal": AbortSignal.timeout(15000),
    }
    if method == "POST":
        options["body"] = urlencode(params or {})
    response = await fetch(
        "https://api.stripe.com/v1/" + path,
        to_js(options, dict_converter=Object.fromEntries),
    )
    if not response.ok:
        raise BillingUnavailableError("billing_provider_unavailable")
    payload = to_python(await response.json())
    if not isinstance(payload, dict):
        raise BillingUnavailableError("invalid_billing_response")
    return payload


async def _account(db: Any, user_id: int, live: bool) -> dict[str, Any] | None:
    return to_python(
        await db.prepare(
            "SELECT * FROM billing_accounts WHERE user_id=? AND livemode=?"
        )
        .bind(user_id, int(live))
        .first()
    )


def hosted_url(value: Any, host: str) -> str:
    if not isinstance(value, str) or len(value) > 4096 or re.search(r"[\s\\]", value):
        raise BillingUnavailableError("invalid_checkout_url")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.netloc != host
        or parsed.username
        or parsed.password
    ):
        raise BillingUnavailableError("invalid_checkout_url")
    return value


async def _price(env: Any, config: dict[str, Any]) -> dict[str, Any]:
    price = await stripe_request(env, "GET", "prices/" + config["price"])
    if (
        price.get("active") is not True
        or price.get("currency") != "eur"
        or price.get("unit_amount") != 300
        or price.get("recurring", {}).get("interval") != "month"
        or price.get("recurring", {}).get("interval_count") != 1
        or price.get("livemode") is not config["livemode"]
    ):
        raise BillingUnavailableError("membership_price_not_configured")
    return price


async def handle_billing_request(
    env: Any, request: Any, user: dict[str, Any], path: str, method: str
) -> AppResponse:
    if (path, method) not in {
        ("/api/billing", "GET"),
        ("/api/billing/checkout", "POST"),
        ("/api/billing/portal", "POST"),
    }:
        return json_response({"error": "Not found"}, 404)
    config, db, user_id = billing_config(env), env_value(env, "DB"), int(user["id"])
    account = await _account(db, user_id, config["livemode"])
    if method == "GET":
        ready = config["ready"]
        if ready:
            try:
                await _price(env, config)
            except Exception:
                ready = False
        return json_response(
            {
                "membership": {
                    "available": ready,
                    "livemode": config["livemode"],
                    "price_eur": 3,
                    "interval": "month",
                    "status": account["status"] if account else "none",
                    "active": bool(
                        account and account["status"] in {"active", "trialing"}
                    ),
                    "can_manage": bool(account and config["key"]),
                    "cancel_at_period_end": bool(
                        account and account["cancel_at_period_end"]
                    ),
                    "current_period_end": account["current_period_end"]
                    if account
                    else 0,
                }
            }
        )
    # SameSite cookies already protect cross-site POSTs; reject a mismatched
    # Origin explicitly as well, including same-site sibling subdomains.
    origin = header_get(request.headers, "origin")
    if origin and origin != config["base"]:
        return json_response({"error": "Invalid request origin"}, 403)
    try:
        if path.endswith("/portal"):
            if not account or not config["key"]:
                return json_response({"error": "No billing account exists yet"}, 409)
            portal = await stripe_request(
                env,
                "POST",
                "billing_portal/sessions",
                {
                    "customer": account["customer_id"],
                    "return_url": config["base"] + "/?billing=returned",
                },
            )
            return json_response(
                {"url": hosted_url(portal.get("url"), "billing.stripe.com")}
            )
        if not config["ready"]:
            return json_response({"error": "Membership checkout is not open yet"}, 503)
        await _price(env, config)
        if not account:
            customer = await stripe_request(
                env,
                "POST",
                "customers",
                {"email": user["email"], "metadata[brisa_user_id]": str(user_id)},
                f"brisa-customer-{int(config['livemode'])}-{user_id}",
            )
            if not re.fullmatch(r"cus_[A-Za-z0-9]+", str(customer.get("id", ""))):
                raise BillingUnavailableError("invalid_customer")
            await (
                db.prepare(
                    "INSERT OR IGNORE INTO billing_accounts"
                    "(user_id,livemode,customer_id) VALUES (?,?,?)"
                )
                .bind(user_id, int(config["livemode"]), customer["id"])
                .run()
            )
            account = await _account(db, user_id, config["livemode"])
        # Query Stripe, not only webhook state: returning from Checkout before
        # the webhook arrives must never offer a second paid subscription.
        subscriptions = await stripe_request(
            env,
            "GET",
            "subscriptions?"
            + urlencode(
                {"customer": account["customer_id"], "status": "all", "limit": "100"}
            ),
        )
        if subscriptions.get("has_more") or any(
            item.get("status") in OPEN_STATUSES
            for item in subscriptions.get("data", [])
        ):
            return json_response(
                {"error": "You already have a membership. Use Manage billing."}, 409
            )
        now = int(time.time())
        await (
            db.prepare(
                "UPDATE billing_accounts SET checkout_key=?,"
                "checkout_created_at=?,checkout_url='',checkout_session_id='' "
                "WHERE user_id=? AND livemode=? AND checkout_created_at <= ?"
            )
            .bind(
                secrets.token_hex(16), now, user_id, int(config["livemode"]), now - 3600
            )
            .run()
        )
        account = await _account(db, user_id, config["livemode"])
        if account["checkout_url"]:
            cached = await stripe_request(
                env, "GET", "checkout/sessions/" + account["checkout_session_id"]
            )
            if cached.get("customer") != account["customer_id"]:
                raise BillingUnavailableError("invalid_checkout_customer")
            if cached.get("status") == "open":
                return json_response(
                    {"url": hosted_url(cached.get("url"), "checkout.stripe.com")}
                )
            if cached.get("status") == "complete":
                subscription_id = cached.get("subscription")
                if not isinstance(subscription_id, str) or not re.fullmatch(
                    r"sub_[A-Za-z0-9]+", subscription_id
                ):
                    raise BillingUnavailableError("checkout_not_synchronized")
                completed = await stripe_request(
                    env, "GET", "subscriptions/" + subscription_id
                )
                if completed.get("customer") != account["customer_id"]:
                    raise BillingUnavailableError("invalid_checkout_customer")
                # Payment can complete between the first subscription lookup
                # and the session lookup. Never rotate an active paid session.
                if completed.get("status") not in {"canceled", "incomplete_expired"}:
                    return json_response(
                        {"error": "You already have a membership. Use Manage billing."},
                        409,
                    )
            elif cached.get("status") != "expired":
                raise BillingUnavailableError("invalid_checkout_status")
            # Completed/expired sessions cannot be reused after cancellation.
            # Compare-and-swap keeps concurrent renewals on one idempotency key.
            await (
                db.prepare(
                    "UPDATE billing_accounts SET checkout_key=?,checkout_created_at=?,"
                    "checkout_url='',checkout_session_id='' "
                    "WHERE user_id=? AND livemode=? AND checkout_key=?"
                )
                .bind(
                    secrets.token_hex(16),
                    now,
                    user_id,
                    int(config["livemode"]),
                    account["checkout_key"],
                )
                .run()
            )
            account = await _account(db, user_id, config["livemode"])
        session = await stripe_request(
            env,
            "POST",
            "checkout/sessions",
            {
                "mode": "subscription",
                "customer": account["customer_id"],
                "line_items[0][price]": config["price"],
                "line_items[0][quantity]": "1",
                "client_reference_id": str(user_id),
                "subscription_data[metadata][brisa_user_id]": str(user_id),
                "success_url": config["base"] + "/?billing=success",
                "cancel_url": config["base"] + "/?billing=cancelled",
                "expires_at": str(account["checkout_created_at"] + 3600),
            },
            "brisa-checkout-" + account["checkout_key"],
        )
        url = hosted_url(session.get("url"), "checkout.stripe.com")
        session_id = session.get("id")
        if not isinstance(session_id, str) or not re.fullmatch(
            r"cs_[A-Za-z0-9_]+", session_id
        ):
            raise BillingUnavailableError("invalid_checkout_session")
        await (
            db.prepare(
                "UPDATE billing_accounts SET checkout_url=?,checkout_session_id=? "
                "WHERE user_id=? AND livemode=? AND checkout_key=?"
            )
            .bind(
                url,
                session_id,
                user_id,
                int(config["livemode"]),
                account["checkout_key"],
            )
            .run()
        )
        return json_response({"url": url})
    except Exception:
        # Do not log Stripe responses: they can contain customer billing data.
        return json_response(
            {"error": "Billing is temporarily unavailable. Please try again."}, 502
        )


def verify_webhook(
    raw: str, signature: str, secret: str, now: int | None = None
) -> dict[str, Any]:
    if not secret.startswith("whsec_") or len(raw.encode()) > 262144:
        raise ValueError("invalid_webhook")
    pairs = [part.split("=", 1) for part in signature.split(",") if "=" in part]
    timestamps = [value for key, value in pairs if key == "t"]
    if len(timestamps) != 1:
        raise ValueError("invalid_signature")
    timestamp = int(timestamps[0])
    if abs((int(time.time()) if now is None else now) - timestamp) > 300:
        raise ValueError("expired_signature")
    expected = hmac.new(
        secret.encode(), f"{timestamp}.{raw}".encode(), hashlib.sha256
    ).hexdigest()
    if not any(
        hmac.compare_digest(expected, value) for key, value in pairs if key == "v1"
    ):
        raise ValueError("invalid_signature")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("invalid_event")
    return payload


async def handle_billing_webhook(env: Any, request: Any) -> AppResponse:
    config = billing_config(env)
    try:
        event = verify_webhook(
            str(await request.text()),
            str(header_get(request.headers, "stripe-signature") or ""),
            config["webhook"],
        )
    except (ValueError, TypeError):
        return json_response({"error": "Invalid webhook signature"}, 400)
    event_type = event.get("type", "")
    if event_type not in {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "checkout.session.completed",
    }:
        return json_response({"received": True})
    try:
        obj = event["data"]["object"]
        identifier = (
            obj.get("subscription")
            if event_type.startswith("checkout.")
            else obj.get("id")
        )
        customer_id = obj.get("customer")
        if (
            event.get("livemode") is not config["livemode"]
            or not isinstance(identifier, str)
            or not re.fullmatch(r"sub_[A-Za-z0-9]+", identifier)
            or not isinstance(customer_id, str)
            or not re.fullmatch(r"cus_[A-Za-z0-9]+", customer_id)
            or type(event.get("created")) is not int
        ):
            return json_response({"received": True})
        db = env_value(env, "DB")
        account = to_python(
            await db.prepare(
                "SELECT subscription_id FROM billing_accounts "
                "WHERE customer_id=? AND livemode=?"
            )
            .bind(customer_id, int(config["livemode"]))
            .first()
        )
        if not account:
            return json_response({"received": True})
        candidate = await stripe_request(env, "GET", "subscriptions/" + identifier)
        if (
            candidate.get("customer") != customer_id
            or candidate.get("livemode") is not config["livemode"]
        ):
            raise ValueError("invalid_subscription")
        relevant = any(
            item.get("price", {}).get("id") == config["price"]
            for item in candidate.get("items", {}).get("data", [])
        )
        if not relevant and account["subscription_id"] != identifier:
            return json_response({"received": True})
        # Ignore unrelated products before claiming the membership revision.
        # Claim atomically *before* fetching canonical customer state. If two
        # events have the same second timestamp, only the newest claim may
        # publish its snapshot; a delayed older fetch cannot overwrite it.
        claim = to_python(
            await db.prepare(
                "UPDATE billing_accounts SET sync_version=sync_version+1,"
                "last_event_created=? WHERE customer_id=? AND livemode=? "
                "AND last_event_created<=? RETURNING sync_version"
            )
            .bind(
                event["created"], customer_id, int(config["livemode"]), event["created"]
            )
            .first()
        )
        if not claim:
            return json_response({"received": True})
        current = await stripe_request(
            env,
            "GET",
            "subscriptions?"
            + urlencode({"customer": customer_id, "status": "all", "limit": "100"}),
        )
        if current.get("has_more"):
            raise BillingUnavailableError("too_many_subscriptions")
        memberships = [
            item
            for item in current.get("data", [])
            if item.get("customer") == customer_id
            and item.get("livemode") is config["livemode"]
            and any(
                line.get("price", {}).get("id") == config["price"]
                for line in item.get("items", {}).get("data", [])
            )
        ]
        # An old cancellation cannot replace a newer active membership, even
        # when both events carry the same second timestamp.
        sub = max(
            memberships,
            key=lambda item: (
                item.get("status") in {"active", "trialing"},
                item.get("status") in OPEN_STATUSES,
                item.get("created", 0),
                item.get("id", ""),
            ),
            default={},
        )
        items = sub.get("items", {}).get("data", [])
        period_end = max(
            (item.get("current_period_end", 0) for item in items), default=0
        )
        period_end = sub.get("current_period_end", period_end)
        if type(period_end) is not int:
            raise ValueError("invalid_period")
        await (
            db.prepare(
                "UPDATE billing_accounts SET subscription_id=?,status=?,"
                "cancel_at_period_end=?,current_period_end=?,last_event_created=? "
                "WHERE customer_id=? AND livemode=? "
                "AND sync_version=?"
            )
            .bind(
                str(sub.get("id", "")),
                str(sub.get("status", "none")),
                int(bool(sub.get("cancel_at_period_end"))),
                period_end,
                event["created"],
                customer_id,
                int(config["livemode"]),
                claim["sync_version"],
            )
            .run()
        )
        return json_response({"received": True})
    except Exception:
        return json_response({"error": "Unable to synchronize billing"}, 502)
