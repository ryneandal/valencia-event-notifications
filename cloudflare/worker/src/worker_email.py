from base64 import b64encode
from collections.abc import Awaitable, Callable
from html import escape
from typing import Any
from urllib.parse import quote

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


def magic_link_message(recipient: str, sender: str, link: str) -> dict[str, str]:
    return {
        "from": sender,
        "to": recipient,
        "subject": "Your València Events sign-in link",
        "text": f"Open this link to continue: {link}",
        "html": (
            f'<p><a href="{escape(link, quote=True)}">'
            "Continue to València Events</a></p>"
        ),
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
