from typing import Any

from worker_auth import (
    DEFAULT_MAGIC_LINK_TTL_MINUTES,
    DEFAULT_SESSION_TTL_HOURS,
    SESSION_COOKIE_NAME,
    clear_cookie_options,
    consume_magic_link,
    cookie_options,
    create_magic_link,
    create_session,
    normalize_email,
    parse_cookie_header,
    resolve_session_user,
    sha256_hex,
)
from worker_email import DeliveryConfigurationError, deliver_magic_link
from worker_http import AppResponse, json_response
from worker_orchestrator import run_digest
from worker_runtime import (
    env_value,
    header_get,
    record_to_dict,
    request_json,
    request_path,
)


def user_payload(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user["id"],
        "email": user["email"],
        "preferences_blob": user.get("preferences_blob"),
        "is_active": bool(user.get("is_active")),
        "is_subscribed": bool(user.get("is_subscribed", True)),
    }


async def send_magic_link(
    env: Any,
    user: dict[str, Any],
    purpose: str,
    ttl_minutes: int,
) -> AppResponse | None:
    token = await create_magic_link(env, user["id"], purpose, ttl_minutes)
    try:
        await deliver_magic_link(env, user["email"], token)
    except DeliveryConfigurationError:
        return json_response({"error": "Email delivery is not configured"}, 503)
    except Exception:
        return json_response({"error": "Unable to send sign-in email"}, 502)
    return None


async def handle_request(request: Any, env: Any) -> AppResponse:
    method = str(request.method).upper()
    path = request_path(request.url)
    session_ttl_hours = int(
        env_value(env, "SESSION_TTL_HOURS", DEFAULT_SESSION_TTL_HOURS)
    )
    magic_link_ttl_minutes = int(
        env_value(
            env,
            "MAGIC_LINK_TTL_MINUTES",
            DEFAULT_MAGIC_LINK_TTL_MINUTES,
        )
    )

    if path == "/api/health" and method == "GET":
        return json_response({"ok": True})

    if path == "/api/register" and method == "POST":
        try:
            payload = await request_json(request)
        except Exception:
            return json_response({"error": "Invalid JSON payload"}, 400)

        preferences_blob = payload.get("preferences_blob")

        try:
            email = normalize_email(payload.get("email"))
        except ValueError:
            return json_response({"error": "Invalid email"}, 400)

        db = env_value(env, "DB")
        user = record_to_dict(
            await db.prepare(
                """
                    SELECT id, email, preferences_blob, is_active
                    FROM users
                    WHERE email = ?
                    LIMIT 1
                    """
            )
            .bind(email)
            .first()
        )

        if user and user.get("is_active"):
            return json_response({"error": "User already exists"}, 409)

        if user:
            await (
                db.prepare("UPDATE users SET preferences_blob = ? WHERE id = ?")
                .bind(preferences_blob, user["id"])
                .run()
            )
            user["preferences_blob"] = preferences_blob
        else:
            await (
                db.prepare(
                    """
                    INSERT INTO users (email, preferences_blob, is_active)
                    VALUES (?, ?, 0)
                    """
                )
                .bind(email, preferences_blob)
                .run()
            )
            user = record_to_dict(
                await db.prepare(
                    """
                    SELECT id, email, preferences_blob, is_active
                    FROM users
                    WHERE email = ?
                    LIMIT 1
                    """
                )
                .bind(email)
                .first()
            )

        delivery_error = await send_magic_link(
            env,
            user,
            "register",
            magic_link_ttl_minutes,
        )
        if delivery_error:
            return delivery_error

        return json_response(
            {"ok": True, "message": "Check your email to continue"},
            202,
        )

    if path == "/api/login" and method == "POST":
        try:
            payload = await request_json(request)
        except Exception:
            return json_response({"error": "Invalid JSON payload"}, 400)

        try:
            email = normalize_email(payload.get("email"))
        except ValueError:
            return json_response({"error": "Invalid email"}, 400)

        user = record_to_dict(
            await env_value(env, "DB")
            .prepare(
                """
                    SELECT id, email, preferences_blob, is_active
                    FROM users
                    WHERE email = ?
                    LIMIT 1
                    """
            )
            .bind(email)
            .first()
        )

        if user and user.get("is_active"):
            delivery_error = await send_magic_link(
                env,
                user,
                "login",
                magic_link_ttl_minutes,
            )
            if delivery_error:
                return delivery_error

        return json_response(
            {"ok": True, "message": "Check your email to continue"},
            202,
        )

    if path == "/api/auth/verify" and method == "POST":
        try:
            payload = await request_json(request)
        except Exception:
            return json_response({"error": "Invalid JSON payload"}, 400)

        if not isinstance(payload.get("token"), str) or not payload["token"].strip():
            return json_response({"error": "Invalid token"}, 400)

        link = await consume_magic_link(env, payload["token"])
        if not link:
            return json_response({"error": "Invalid or expired token"}, 401)

        db = env_value(env, "DB")
        if link["purpose"] == "register":
            await (
                db.prepare("UPDATE users SET is_active = 1 WHERE id = ?")
                .bind(link["user_id"])
                .run()
            )

        user = record_to_dict(
            await db.prepare(
                """
                SELECT id, email, preferences_blob, is_active
                FROM users
                WHERE id = ?
                LIMIT 1
                """
            )
            .bind(link["user_id"])
            .first()
        )
        if not user or not user.get("is_active"):
            return json_response({"error": "Invalid or expired token"}, 401)

        session_token = await create_session(env, user["id"], session_ttl_hours)
        return json_response(
            {"user": user_payload(user)},
            200,
            {
                "set-cookie": (
                    f"{SESSION_COOKIE_NAME}={session_token}; "
                    f"{cookie_options(session_ttl_hours * 3600)}"
                )
            },
        )

    if path == "/api/logout" and method == "POST":
        user = await resolve_session_user(env, request)
        if user:
            cookies = parse_cookie_header(header_get(request.headers, "cookie"))
            session_token = cookies.get(SESSION_COOKIE_NAME)
            if session_token:
                token_hash = sha256_hex(session_token)
                await (
                    env_value(env, "DB")
                    .prepare("DELETE FROM sessions WHERE token_hash = ?")
                    .bind(token_hash)
                    .run()
                )

        return json_response(
            {"ok": True},
            200,
            {"set-cookie": f"{SESSION_COOKIE_NAME}=; {clear_cookie_options()}"},
        )

    if path == "/api/me" and method == "GET":
        user = await resolve_session_user(env, request)
        if not user:
            return json_response({"error": "Unauthorized"}, 401)
        return json_response({"user": user_payload(user)})

    if path == "/api/preferences" and method == "PATCH":
        user = await resolve_session_user(env, request)
        if not user:
            return json_response({"error": "Unauthorized"}, 401)

        try:
            payload = await request_json(request)
        except Exception:
            return json_response({"error": "Invalid JSON payload"}, 400)

        preferences_blob = payload.get("preferences_blob")

        await (
            env_value(env, "DB")
            .prepare("UPDATE users SET preferences_blob = ? WHERE id = ?")
            .bind(preferences_blob, user["id"])
            .run()
        )
        user["preferences_blob"] = preferences_blob
        return json_response({"user": user_payload(user)})

    if path == "/api/subscription" and method == "PATCH":
        user = await resolve_session_user(env, request)
        if not user:
            return json_response({"error": "Unauthorized"}, 401)

        try:
            payload = await request_json(request)
        except Exception:
            return json_response({"error": "Invalid JSON payload"}, 400)

        subscribed = payload.get("subscribed")
        if not isinstance(subscribed, bool):
            return json_response({"error": "subscribed must be a boolean"}, 400)

        await (
            env_value(env, "DB")
            .prepare(
                """
                INSERT INTO subscriptions (user_id, is_subscribed, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                  is_subscribed = excluded.is_subscribed,
                  updated_at = CURRENT_TIMESTAMP
                """
            )
            .bind(user["id"], int(subscribed))
            .run()
        )
        user["is_subscribed"] = subscribed
        return json_response({"user": user_payload(user)})

    if path == "/api/digest/dry-run" and method == "POST":
        user = await resolve_session_user(env, request)
        if not user:
            return json_response({"error": "Unauthorized"}, 401)
        try:
            summary = await run_digest(
                env,
                dry_run=True,
                target_user_id=int(user["id"]),
            )
        except Exception:
            return json_response({"error": "Unable to run digest preview"}, 502)
        return json_response({"summary": summary})

    return json_response({"error": "Not found"}, 404)
