import json
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any
from urllib.parse import urljoin

from worker_runtime import env_value
from worker_storage import upsert_event
from worker_time import localize_madrid, madrid_noon, to_madrid

FETCH_TIMEOUT_MS = 10_000
USER_AGENT = "BrisaEventDigest/0.1 (+https://valencia-event-notifications.pages.dev)"


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    parser: Callable[[str, str], list[dict[str, str]]]


def _clean_text(value: Any) -> str:
    text = unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.split())


def normalize_start(value: str) -> str:
    """Normalize supported source dates to an aware Europe/Madrid ISO value."""
    raw = _clean_text(value)
    if not raw:
        raise ValueError("missing_start")

    if raw.isdigit():
        timestamp = int(raw)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        return to_madrid(datetime.fromtimestamp(timestamp, UTC)).isoformat()

    range_match = re.search(r"(\d{1,2})[/.](\d{1,2})[/.](\d{2,4})", raw)
    if range_match:
        day, month, year = (int(part) for part in range_match.groups())
        if year < 100:
            year += 2000
        return madrid_noon(date(year, month, day)).isoformat()

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return madrid_noon(date.fromisoformat(raw)).isoformat()

    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        parsed = None

    if parsed is None:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("unsupported_start") from exc

    if parsed.tzinfo is None:
        parsed = localize_madrid(parsed)
    return to_madrid(parsed).isoformat()


def parse_rss(text: str, source_url: str) -> list[dict[str, str]]:
    """Parse RSS or Atom items without a Scrapy/Twisted dependency."""
    del source_url
    root = ET.fromstring(text)
    events: list[dict[str, str]] = []
    for node in root.iter():
        if node.tag.split("}")[-1] not in {"item", "entry"}:
            continue
        children = {child.tag.split("}")[-1]: child for child in node}

        def child_text(*names: str) -> str:
            for name in names:
                child = children.get(name)
                if child is not None:
                    if name == "link" and child.attrib.get("href"):
                        return str(child.attrib["href"])
                    if child.text:
                        return str(child.text)
            return ""

        title = _clean_text(child_text("title"))
        url = _clean_text(child_text("link"))
        raw_start = child_text("pubDate", "published", "updated", "date")
        if not title or not url or not raw_start:
            continue
        try:
            start_at = normalize_start(raw_start)
        except ValueError:
            continue
        events.append(
            {
                "title": title,
                "start_at": start_at,
                "url": url,
                "description": _clean_text(
                    child_text("description", "summary", "content", "encoded")
                ),
            }
        )
    return events


EVENTOS_RE = re.compile(r"var\s+eventosInicio\s*=\s*(\[[\s\S]*?\]);")


def parse_ajuntament_agenda(text: str, source_url: str) -> list[dict[str, str]]:
    """Parse the city agenda's embedded JSON event collection."""
    match = EVENTOS_RE.search(text)
    if not match:
        raise ValueError("missing_event_payload")
    payload = json.loads(match.group(1))
    if not isinstance(payload, list):
        raise ValueError("invalid_event_payload")

    events: list[dict[str, str]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        title = _clean_text(item.get("content"))
        raw_start = str(item.get("startDateSort") or item.get("startDate") or "")
        relative_url = str(item.get("editURL") or item.get("url") or "").strip()
        if relative_url and not relative_url.startswith(("http://", "https://", "/")):
            relative_url = f"/cas/agenda-de-la-ciudad/-/content/{relative_url}"
        if not title or not raw_start or not relative_url:
            continue
        try:
            start_at = normalize_start(raw_start)
        except ValueError:
            continue
        category = _clean_text(item.get("categoria"))
        description = _clean_text(item.get("description"))
        events.append(
            {
                "title": title,
                "start_at": start_at,
                "url": urljoin(source_url, relative_url),
                "description": ". ".join(
                    part for part in (category, description) if part
                ),
            }
        )
    return events


SOURCES = (
    Source(
        "ajuntament_agenda",
        "https://www.valencia.es/cas/agenda-de-la-ciudad",
        parse_ajuntament_agenda,
    ),
    Source(
        "elperiodic_rss",
        "https://www.elperiodic.com/feed/rss_valencia.xml",
        parse_rss,
    ),
)


async def fetch_source(env: Any, source: Source) -> str:
    """Fetch one source with a bounded timeout and an identifying user agent."""
    fake = env_value(env, "EVENT_FETCH")
    if callable(fake):
        return str(await fake(source.url, USER_AGENT, FETCH_TIMEOUT_MS))

    try:  # Imports are provided by the Cloudflare Python runtime.
        from js import AbortSignal, Object, fetch  # type: ignore[import-not-found]
        from pyodide.ffi import to_js  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - Cloudflare runtime boundary
        raise RuntimeError("fetch_runtime_unavailable") from exc

    options = to_js(
        {
            "headers": {
                "accept": "text/html, application/xml",
                "user-agent": USER_AGENT,
            },
            "signal": AbortSignal.timeout(FETCH_TIMEOUT_MS),
        },
        dict_converter=Object.fromEntries,
    )
    response = await fetch(source.url, options)
    if not bool(response.ok):
        raise RuntimeError(f"http_{int(response.status)}")
    return str(await response.text())


def _error_code(error: Exception) -> str:
    value = "_".join(str(error).strip().lower().split())
    if re.fullmatch(r"[a-z0-9_]{1,64}", value):
        return value
    return error.__class__.__name__.lower()[:64]


async def collect_events(
    env: Any,
    target_date: date,
    sources: tuple[Source, ...] = SOURCES,
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """Collect tomorrow's events while isolating each source failure."""
    matching: list[dict[str, str]] = []
    diagnostics: list[dict[str, Any]] = []
    for source in sources:
        try:
            text = await fetch_source(env, source)
            parsed = source.parser(text, source.url)
            selected = [
                {**event, "source": source.name}
                for event in parsed
                if datetime.fromisoformat(event["start_at"]).date() == target_date
            ]
            matching.extend(selected)
            diagnostics.append(
                {
                    "source": source.name,
                    "status": "ok",
                    "parsed": len(parsed),
                    "matched": len(selected),
                }
            )
        except Exception as error:
            diagnostics.append(
                {
                    "source": source.name,
                    "status": "failed",
                    "error_code": _error_code(error),
                }
            )
    return matching, diagnostics


async def persist_events(db: Any, events: list[dict[str, str]]) -> int:
    """Idempotently persist collected normalized events and return unique count."""
    keys: set[str] = set()
    for event in events:
        keys.add(await upsert_event(db, **event))
    return len(keys)
