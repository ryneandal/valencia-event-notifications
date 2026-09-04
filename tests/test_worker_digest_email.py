import asyncio
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

WORKER_DIR = Path(__file__).resolve().parents[1] / "cloudflare" / "worker" / "src"
sys.path.insert(0, str(WORKER_DIR))

spec = importlib.util.spec_from_file_location(
    "cloudflare_worker_email", WORKER_DIR / "worker_email.py"
)
email = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(email)


def ranked_events() -> list[dict]:
    return [
        {
            "title": "Música & <script>alert(1)</script> cerámica 🎨",
            "start_at": "2026-09-05T11:00:00+02:00",
            "url": "javascript:alert(1)",
            "description": "Taller para niñas, niños y familias " + "x" * 300,
            "relevance_reason": "Encaja con arte y planes familiares.",
        }
    ]


def test_digest_message_is_branded_escaped_and_has_plain_text():
    message = email.digest_message(
        "reader@example.com",
        "Brisa <hello@example.com>",
        "https://events.example.com",
        "2026-09-05",
        ranked_events(),
    )

    assert message["subject"] == "Brisa picks for València · 2026-09-05"
    assert "BRISA" in message["html"]
    assert "brisa-mark.png" in message["html"]
    assert "Why it fits:" in message["html"]
    assert "&lt;script&gt;" in message["html"]
    assert "<script>alert(1)</script>" not in message["html"]
    assert 'href="#"' in message["html"]
    assert "cerámica 🎨" in message["text"]
    assert "Manage your digest" in message["text"]


def test_digest_message_rejects_empty_selection():
    with pytest.raises(ValueError, match="empty digest"):
        email.digest_message(
            "reader@example.com",
            "Brisa <hello@example.com>",
            "https://events.example.com",
            "2026-09-05",
            [],
        )


def test_digest_delivery_uses_injected_adapter_without_network():
    delivered = []

    async def fake_delivery(recipient, message):
        delivered.append((recipient, message))
        return "provider-id"

    provider_id = asyncio.run(
        email.deliver_digest(
            SimpleNamespace(
                EMAIL_FROM="Brisa <hello@example.com>",
                APP_BASE_URL="https://events.example.com",
                DIGEST_DELIVERY=fake_delivery,
            ),
            "reader@example.com",
            "2026-09-05",
            ranked_events(),
        )
    )

    assert provider_id == "provider-id"
    assert delivered[0][0] == "reader@example.com"
    assert delivered[0][1]["to"] == "reader@example.com"
