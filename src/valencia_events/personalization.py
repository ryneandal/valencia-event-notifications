"""LLM-based event personalization and ranking."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from .filters import rank_and_limit_events
from .logger import get_logger
from .models import Event

logger = get_logger(__name__)

DEFAULT_FAMILY_PROFILE: dict[str, Any] = {
    "audience": "family_with_school_age_kids",
    "location_scope": [
        "Valencia city",
        "Valencia metro area",
        "easy day trips (<=60-90 min)",
    ],
    "top_interest_clusters": [
        {
            "name": "local_festivals_spectacle",
            "includes": [
                "parades",
                "fireworks",
                "street art/monuments",
                "processions",
                "flower battles",
            ],
        },
        {
            "name": "hands_on_learning",
            "includes": [
                "science museum",
                "interactive exhibits",
                "kids workshops",
                "aquarium/planetarium/IMAX-style shows",
            ],
        },
        {
            "name": "animals_and_nature",
            "includes": [
                "zoo/animal park",
                "keeper talks",
                "boat trips",
                "wetlands/birding",
                "sunset nature",
            ],
        },
        {
            "name": "parks_and_play",
            "includes": [
                "destination playgrounds",
                "Turia-style park events",
                "picnics",
                "bike-friendly outings",
            ],
        },
        {
            "name": "kid-friendly_culture",
            "includes": [
                "craft markets",
                "family theatre/puppets",
                "street performances",
                "museum family days",
            ],
        },
    ],
    "strong_positive_signals": [
        "kid_focused",
        "interactive",
        "workshop",
        "animals",
        "outdoors",
        "park",
        "daytime",
        "stroller_friendly",
        "accessible",
        "near_transit",
        "short_duration_or_drop_in",
    ],
    "strong_negative_signals": [
        "starts_after_20",
        "adult_nightlife",
        "very_loud_no_family_area",
        "crowd_extreme",
        "long_static_format",
    ],
    "seasonal_anchors": [
        {
            "name": "Fallas",
            "months": ["Feb", "Mar"],
            "notes": "daytime monument walks; mascleta/fireworks are loud",
        },
        {
            "name": "Semana_Santa_Marinera",
            "months": ["Mar", "Apr"],
            "notes": "processions in maritime districts",
        },
        {
            "name": "Gran_Feria_de_Julio",
            "months": ["Jul"],
            "notes": "citywide summer culture nights + finale events",
        },
        {
            "name": "La_Tomatina_Bunol_day_trip",
            "months": ["Aug"],
            "notes": "ticketed; huge crowds; messy novelty",
        },
    ],
}


class GeminiRankingResponse(BaseModel):
    """Structured output expected from the LLM ranking pass."""

    summary: str = Field(..., description="Why the selected events fit this family.")
    selected_events: list[GeminiRankedEvent] = Field(
        default_factory=list,
        description="Ordered selected events with concise rationale.",
    )
    selected_event_hashes: list[str] = Field(
        default_factory=list,
        description="Ordered list of best-matching event hashes.",
    )


class GeminiRankedEvent(BaseModel):
    """Single ranked event feedback item from Gemini."""

    event_hash: str
    reason: str = Field(
        default="",
        description="One concise reason this event matches the family profile.",
    )


@dataclass
class PersonalizedSelection:
    """Personalized result set for digest generation."""

    events: list[Event]
    summary: str | None
    feedback_by_hash: dict[str, str]
    used_llm: bool


class GeminiEventRanker:
    """Rank events with Gemini via LangChain structured output."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        fallback_model: str = "gemini-2.5-pro",
    ):
        self.api_key = api_key
        self.model = model
        self.fallback_model = fallback_model

    @classmethod
    def from_env(cls) -> GeminiEventRanker | None:
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            return None
        model = os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview")
        fallback_model = os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-2.5-pro")
        return cls(
            api_key=api_key,
            model=model,
            fallback_model=fallback_model,
        )

    def _invoke_model(
        self,
        *,
        model: str,
        family_profile: dict[str, Any],
        event_payload: list[dict[str, str]],
        limit: int,
    ) -> GeminiRankingResponse:
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_google_genai import ChatGoogleGenerativeAI

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    (
                        "You are a family event curator for Valencia. "
                        "Use the provided family profile to rank events. "
                        "Return a concise summary and ordered event hashes."
                    ),
                ),
                (
                    "human",
                    (
                        "Family profile JSON:\n{family_profile_json}\n\n"
                        "Candidate events JSON:\n{events_json}\n\n"
                        "Select up to {limit} events and return ranked output. "
                        "Include selected_events with event_hash and reason. "
                        "Reasons should be short and family-focused."
                    ),
                ),
            ]
        )

        llm = ChatGoogleGenerativeAI(
            model=model,
            google_api_key=self.api_key,
            temperature=0,
        )
        chain = prompt | llm.with_structured_output(GeminiRankingResponse)
        return chain.invoke(
            {
                "family_profile_json": json.dumps(
                    family_profile, ensure_ascii=False, indent=2
                ),
                "events_json": json.dumps(event_payload, ensure_ascii=False, indent=2),
                "limit": str(limit),
            }
        )

    def rank(
        self,
        events: list[Event],
        family_profile: dict[str, Any],
        limit: int,
    ) -> PersonalizedSelection:
        try:
            import langchain_google_genai  # noqa: F401
            from langchain_core.prompts import ChatPromptTemplate  # noqa: F401
        except ImportError as exc:
            raise RuntimeError("LangChain Gemini dependencies are missing") from exc

        event_payload: list[dict[str, str]] = []
        for event in events:
            event_hash = event.event_hash or ""
            if not event_hash:
                continue
            event_payload.append(
                {
                    "event_hash": event_hash,
                    "title": event.title,
                    "start": event.start.isoformat(),
                    "url": str(event.url),
                    "description": event.description,
                    "source": event.source,
                }
            )

        if not event_payload:
            return PersonalizedSelection(
                events=rank_and_limit_events(events, limit=limit),
                summary=None,
                feedback_by_hash={},
                used_llm=False,
            )
        models_to_try = [self.model]
        if self.fallback_model and self.fallback_model != self.model:
            models_to_try.append(self.fallback_model)

        result: GeminiRankingResponse | None = None
        last_exc: Exception | None = None
        for idx, model_name in enumerate(models_to_try):
            try:
                result = self._invoke_model(
                    model=model_name,
                    family_profile=family_profile,
                    event_payload=event_payload,
                    limit=limit,
                )
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if idx < len(models_to_try) - 1:
                    logger.warning(
                        f"LLM model {model_name} failed; "
                        f"retrying with fallback {models_to_try[idx + 1]}: {exc}"
                    )
                else:
                    raise
        if result is None:
            raise RuntimeError("LLM ranking failed") from last_exc

        selected_items = result.selected_events or [
            GeminiRankedEvent(event_hash=event_hash, reason="")
            for event_hash in result.selected_event_hashes
        ]
        selected_hashes = [item.event_hash for item in selected_items]
        feedback_by_hash = {
            item.event_hash: item.reason.strip()
            for item in selected_items
            if item.reason and item.reason.strip()
        }

        by_hash = {
            event.event_hash: event
            for event in events
            if event.event_hash and event.event_hash in selected_hashes
        }
        ranked_events = [
            by_hash[event_hash]
            for event_hash in selected_hashes
            if event_hash in by_hash
        ]
        if len(ranked_events) < limit:
            remaining = [
                event
                for event in rank_and_limit_events(events, limit=limit)
                if event.event_hash not in selected_hashes
            ]
            ranked_events.extend(remaining[: max(limit - len(ranked_events), 0)])

        return PersonalizedSelection(
            events=ranked_events[:limit],
            summary=result.summary,
            feedback_by_hash=feedback_by_hash,
            used_llm=True,
        )


def load_family_profile() -> dict[str, Any]:
    """Load family profile from env override or default profile."""
    raw = os.environ.get("FAMILY_PROFILE_JSON")
    if not raw:
        return DEFAULT_FAMILY_PROFILE

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        logger.warning("Invalid FAMILY_PROFILE_JSON; using default family profile")
    return DEFAULT_FAMILY_PROFILE


def rank_events_for_family(
    events: list[Event],
    *,
    limit: int = 20,
    ranker: GeminiEventRanker | None = None,
) -> PersonalizedSelection:
    """Rank events using Gemini when configured; fall back deterministically."""
    if not events:
        return PersonalizedSelection(
            events=[],
            summary=None,
            feedback_by_hash={},
            used_llm=False,
        )

    family_profile = load_family_profile()
    ranker = ranker or GeminiEventRanker.from_env()

    if not ranker:
        return PersonalizedSelection(
            events=rank_and_limit_events(events, limit=limit),
            summary=None,
            feedback_by_hash={},
            used_llm=False,
        )

    try:
        return ranker.rank(events, family_profile=family_profile, limit=limit)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"LLM ranking failed, falling back to default ranking: {exc}")
        return PersonalizedSelection(
            events=rank_and_limit_events(events, limit=limit),
            summary=None,
            feedback_by_hash={},
            used_llm=False,
        )
