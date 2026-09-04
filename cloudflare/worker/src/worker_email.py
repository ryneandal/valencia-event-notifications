# ruff: noqa: E501

from base64 import b64encode
from collections.abc import Awaitable, Callable
from html import escape
from typing import Any
from urllib.parse import quote, urlsplit

from worker_runtime import env_value, to_python

DeliveryFake = Callable[[str, str], Awaitable[None]]
DigestDeliveryFake = Callable[[str, dict[str, str]], Awaitable[str | None]]
MAILGUN_TIMEOUT_MS = 30_000


class DeliveryConfigurationError(RuntimeError):
    pass


def magic_link_url(env: Any, token: str) -> str:
    app_base_url = str(env_value(env, "APP_BASE_URL", "")).strip().rstrip("/")
    if not app_base_url:
        raise DeliveryConfigurationError("APP_BASE_URL is required")
    return f"{app_base_url}/auth/verify?token={token}"


def mailgun_api_url(domain: str, region: str = "us") -> str:
    region = region.strip().lower()
    if region not in {"us", "eu"}:
        raise DeliveryConfigurationError("MAILGUN_REGION must be 'us' or 'eu'")
    api_host = "api.eu.mailgun.net" if region == "eu" else "api.mailgun.net"
    return f"https://{api_host}/v3/{quote(domain.strip(), safe='')}/messages"


def mailgun_authorization(api_key: str) -> str:
    encoded = b64encode(f"api:{api_key}".encode()).decode("ascii")
    return f"Basic {encoded}"


def brand_asset_url(link: str) -> str:
    parsed = urlsplit(link)
    return f"{parsed.scheme}://{parsed.netloc}/brand/brisa-mark.png"


def magic_link_message(recipient: str, sender: str, link: str) -> dict[str, str]:
    escaped_link = escape(link, quote=True)
    escaped_logo = escape(brand_asset_url(link), quote=True)
    return {
        "from": sender,
        "to": recipient,
        "subject": "Your Brisa sign-in link for València",
        "text": (
            "Your next day in València is waiting.\n\n"
            "Continue setting up your personalised events digest:\n"
            f"{link}\n\n"
            "This private link can be used once and expires soon. If you did "
            "not request it, you can safely ignore this email."
        ),
        "html": f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Your Brisa sign-in link</title>
  </head>
  <body style="margin:0;padding:0;background:#f4efe5;color:#173746;font-family:Arial,sans-serif;">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;">Your next day in València is waiting.</div>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f4efe5;">
      <tr>
        <td align="center" style="padding:32px 16px;">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width:600px;background:#fffdfa;border:1px solid #e7e1d6;border-radius:18px;overflow:hidden;">
            <tr>
              <td style="padding:24px 32px;background:#12394a;">
                <table role="presentation" cellspacing="0" cellpadding="0" border="0">
                  <tr>
                    <td style="padding-right:14px;">
                      <img src="{escaped_logo}" width="56" height="56" alt="" style="display:block;width:56px;height:56px;border-radius:16px;background:#fbf7ef;">
                    </td>
                    <td>
                      <div style="color:#fff8ed;font-family:Georgia,serif;font-size:25px;font-weight:bold;letter-spacing:1px;">BRISA</div>
                      <div style="padding-top:4px;color:#b7d4cc;font-size:11px;letter-spacing:1.4px;text-transform:uppercase;">Next day in València</div>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td style="padding:42px 40px 38px;">
                <div style="margin-bottom:12px;color:#ee6b52;font-size:12px;font-weight:bold;letter-spacing:1.5px;text-transform:uppercase;">One small step</div>
                <h1 style="margin:0 0 18px;color:#12394a;font-family:Georgia,serif;font-size:34px;line-height:1.15;font-weight:normal;">Your next day is<br><em style="color:#197c7b;">almost ready.</em></h1>
                <p style="margin:0 0 28px;color:#587079;font-size:16px;line-height:1.65;">Use this private link to verify your email and continue shaping a thoughtful digest around your people, your pace, and your València.</p>
                <table role="presentation" cellspacing="0" cellpadding="0" border="0">
                  <tr>
                    <td style="border-radius:999px;background:#ee6b52;">
                      <a href="{escaped_link}" style="display:inline-block;padding:15px 24px;color:#ffffff;font-size:15px;font-weight:bold;text-decoration:none;">Continue to Brisa&nbsp;&nbsp;→</a>
                    </td>
                  </tr>
                </table>
                <div style="margin-top:30px;padding:18px 20px;border-radius:12px;background:#eaf4ed;color:#52706f;font-size:13px;line-height:1.55;">
                  <strong style="color:#197c7b;">A quiet security note</strong><br>
                  This link can be used once and expires soon. If you did not request it, there is nothing you need to do.
                </div>
                <p style="margin:28px 0 8px;color:#8b9898;font-size:11px;line-height:1.5;">Button not working? Copy this address into your browser:</p>
                <p style="margin:0;color:#197c7b;font-size:11px;line-height:1.5;word-break:break-all;"><a href="{escaped_link}" style="color:#197c7b;">{escaped_link}</a></p>
              </td>
            </tr>
            <tr>
              <td style="padding:20px 32px;border-top:1px solid #eee8dc;color:#83908f;font-size:11px;line-height:1.5;text-align:center;">A little local knowledge, delivered with the morning light.</td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>""",
    }


def _safe_link(value: str) -> str:
    parsed = urlsplit(value)
    return value if parsed.scheme in {"http", "https"} else "#"


def digest_message(
    recipient: str,
    sender: str,
    app_base_url: str,
    digest_date: str,
    ranked_events: list[dict[str, Any]],
) -> dict[str, str]:
    """Render escaped Brisa HTML and text alternatives for ranked events."""
    if not ranked_events:
        raise ValueError("cannot render an empty digest")

    account_url = f"{app_base_url.strip().rstrip('/')}/"
    escaped_account_url = escape(_safe_link(account_url), quote=True)
    escaped_logo = escape(brand_asset_url(account_url), quote=True)
    html_cards: list[str] = []
    text_cards: list[str] = []
    for position, event in enumerate(ranked_events, start=1):
        title = str(event.get("title", "")).strip()
        start_at = str(event.get("start_at", "")).strip()
        description = str(event.get("description", "")).strip()
        reason = str(event.get("relevance_reason", "")).strip()
        url = _safe_link(str(event.get("url", "")).strip())
        html_cards.append(
            f"""
            <tr>
              <td style="padding:0 32px 18px;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border:1px solid #e7e1d6;border-radius:14px;background:#fffdfa;">
                  <tr><td style="padding:22px 24px;">
                    <div style="color:#ee6b52;font-size:11px;font-weight:bold;letter-spacing:1px;text-transform:uppercase;">Pick {position} · {escape(start_at)}</div>
                    <h2 style="margin:8px 0 10px;color:#12394a;font-family:Georgia,serif;font-size:24px;line-height:1.25;">{escape(title)}</h2>
                    <p style="margin:0 0 10px;color:#587079;font-size:14px;line-height:1.55;">{escape(description)}</p>
                    <p style="margin:0 0 14px;padding:11px 13px;border-radius:10px;background:#eaf4ed;color:#376b68;font-size:13px;line-height:1.5;"><strong>Why it fits:</strong> {escape(reason)}</p>
                    <a href="{escape(url, quote=True)}" style="color:#197c7b;font-size:13px;font-weight:bold;">View event →</a>
                  </td></tr>
                </table>
              </td>
            </tr>"""
        )
        text_cards.append(f"{position}. {title}\n{start_at}\n{reason}\n{url}")

    return {
        "from": sender,
        "to": recipient,
        "subject": f"Brisa picks for València · {digest_date}",
        "text": (
            f"Your Brisa picks for {digest_date}\n\n"
            + "\n\n".join(text_cards)
            + f"\n\nManage your digest: {account_url}"
        ),
        "html": f"""<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Your Brisa picks</title></head>
  <body style="margin:0;padding:0;background:#f4efe5;color:#173746;font-family:Arial,sans-serif;">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;">Thoughtful events for tomorrow in València.</div>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f4efe5;">
      <tr><td align="center" style="padding:30px 12px;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width:640px;">
          <tr><td style="padding:24px 32px;background:#12394a;border-radius:18px 18px 0 0;">
            <table role="presentation" cellspacing="0" cellpadding="0" border="0"><tr>
              <td style="padding-right:14px;"><img src="{escaped_logo}" width="54" height="54" alt="" style="display:block;border-radius:15px;background:#fbf7ef;"></td>
              <td><div style="color:#fff8ed;font-family:Georgia,serif;font-size:25px;font-weight:bold;letter-spacing:1px;">BRISA</div><div style="padding-top:4px;color:#b7d4cc;font-size:11px;letter-spacing:1.4px;text-transform:uppercase;">València · {escape(digest_date)}</div></td>
            </tr></table>
          </td></tr>
          <tr><td style="padding:34px 32px 24px;background:#fffdfa;"><div style="color:#ee6b52;font-size:11px;font-weight:bold;letter-spacing:1.4px;text-transform:uppercase;">Tomorrow, considered</div><h1 style="margin:9px 0 10px;color:#12394a;font-family:Georgia,serif;font-size:32px;font-weight:normal;">A few lovely possibilities.</h1><p style="margin:0;color:#587079;font-size:15px;line-height:1.6;">Chosen around your saved profile, with links to the original event pages.</p></td></tr>
          {"".join(html_cards)}
          <tr><td style="padding:12px 32px 28px;text-align:center;"><a href="{escaped_account_url}" style="color:#197c7b;font-size:12px;">Edit or pause your Brisa digest</a></td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>""",
    }


async def _deliver_mailgun_message(env: Any, message: dict[str, str]) -> str | None:
    api_key = str(env_value(env, "MAILGUN_API_KEY", "")).strip()
    domain = str(env_value(env, "MAILGUN_DOMAIN", "")).strip()
    region = str(env_value(env, "MAILGUN_REGION", "us")).strip()
    if not api_key or not domain or not message.get("from"):
        raise DeliveryConfigurationError(
            "MAILGUN_API_KEY, MAILGUN_DOMAIN, and EMAIL_FROM are required"
        )
    endpoint = mailgun_api_url(domain, region)

    try:  # Imports exist in the Cloudflare Python runtime, not local CPython.
        from js import (  # type: ignore[import-not-found]
            AbortSignal,
            FormData,
            Object,
            fetch,
        )
        from pyodide.ffi import to_js  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - Cloudflare runtime boundary
        raise DeliveryConfigurationError(
            "HTTP email delivery runtime unavailable"
        ) from exc

    form_data = FormData.new()
    for name, value in message.items():
        form_data.append(name, value)
    options = to_js(
        {
            "method": "POST",
            "headers": {"authorization": mailgun_authorization(api_key)},
            "body": form_data,
            "signal": AbortSignal.timeout(MAILGUN_TIMEOUT_MS),
        },
        dict_converter=Object.fromEntries,
    )
    response = await fetch(endpoint, options)
    if not bool(response.ok):
        raise RuntimeError(f"Email delivery failed with status {response.status}")
    try:
        payload = to_python(await response.json())
    except Exception:
        return None
    return (
        str(payload.get("id"))
        if isinstance(payload, dict) and payload.get("id")
        else None
    )


async def deliver_magic_link(env: Any, recipient: str, token: str) -> None:
    """Deliver a raw token only through the configured email boundary.

    Tests may inject an async ``MAGIC_LINK_DELIVERY`` callable. Production uses
    Mailgun's HTTP API configured with MAILGUN_API_KEY, MAILGUN_DOMAIN,
    MAILGUN_REGION, EMAIL_FROM, and APP_BASE_URL.
    """

    link = magic_link_url(env, token)
    fake: DeliveryFake | None = env_value(env, "MAGIC_LINK_DELIVERY")
    if callable(fake):
        await fake(recipient, link)
        return

    sender = str(env_value(env, "EMAIL_FROM", "")).strip()
    await _deliver_mailgun_message(env, magic_link_message(recipient, sender, link))


async def deliver_digest(
    env: Any,
    recipient: str,
    digest_date: str,
    ranked_events: list[dict[str, Any]],
) -> str | None:
    """Deliver a non-empty personalized digest through the configured boundary."""
    sender = str(env_value(env, "EMAIL_FROM", "")).strip()
    app_base_url = str(env_value(env, "APP_BASE_URL", "")).strip()
    if not sender or not app_base_url:
        raise DeliveryConfigurationError("EMAIL_FROM and APP_BASE_URL are required")
    message = digest_message(
        recipient,
        sender,
        app_base_url,
        digest_date,
        ranked_events,
    )
    fake: DigestDeliveryFake | None = env_value(env, "DIGEST_DELIVERY")
    if callable(fake):
        return await fake(recipient, message)
    return await _deliver_mailgun_message(env, message)
