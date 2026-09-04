# ruff: noqa: E501

from base64 import b64encode
from collections.abc import Awaitable, Callable
from html import escape
from typing import Any
from urllib.parse import quote, urlsplit

from worker_runtime import env_value

DeliveryFake = Callable[[str, str], Awaitable[None]]


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

    api_key = str(env_value(env, "MAILGUN_API_KEY", "")).strip()
    domain = str(env_value(env, "MAILGUN_DOMAIN", "")).strip()
    region = str(env_value(env, "MAILGUN_REGION", "us")).strip()
    sender = str(env_value(env, "EMAIL_FROM", "")).strip()
    if not api_key or not domain or not sender:
        raise DeliveryConfigurationError(
            "MAILGUN_API_KEY, MAILGUN_DOMAIN, and EMAIL_FROM are required"
        )
    endpoint = mailgun_api_url(domain, region)

    try:  # Imports exist in the Cloudflare Python runtime, not local CPython.
        from js import FormData, Object, fetch  # type: ignore[import-not-found]
        from pyodide.ffi import to_js  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - Cloudflare runtime boundary
        raise DeliveryConfigurationError(
            "HTTP email delivery runtime unavailable"
        ) from exc

    form_data = FormData.new()
    for name, value in magic_link_message(recipient, sender, link).items():
        form_data.append(name, value)
    options = to_js(
        {
            "method": "POST",
            "headers": {
                "authorization": mailgun_authorization(api_key),
            },
            "body": form_data,
        },
        dict_converter=Object.fromEntries,
    )
    response = await fetch(endpoint, options)
    if not bool(response.ok):
        raise RuntimeError(f"Email delivery failed with status {response.status}")
