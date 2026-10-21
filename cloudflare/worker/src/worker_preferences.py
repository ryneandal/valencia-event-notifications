"""Validate bounded event interests before persisting a subscriber profile."""

import json
from typing import Any, NoReturn

MAX_PREFERENCES_BYTES = 16_384

# Mirror shared/event-types.json for the Python Worker bundle. The catalog parity
# test requires identical IDs and definitions without runtime filesystem access.
EVENT_TYPE_INCLUDES = {
    "local_festivals_spectacle": [
        "parades",
        "fireworks",
        "street art/monuments",
        "processions",
        "flower battles",
    ],
    "hands_on_learning": [
        "science museum",
        "interactive exhibits",
        "kids workshops",
        "aquarium/planetarium/IMAX-style shows",
    ],
    "animals_and_nature": [
        "zoo/animal park",
        "keeper talks",
        "boat trips",
        "wetlands/birding",
        "sunset nature",
    ],
    "parks_and_play": [
        "destination playgrounds",
        "Turia-style park events",
        "picnics",
        "bike-friendly outings",
    ],
    "kid-friendly_culture": [
        "craft markets",
        "family theatre/puppets",
        "street performances",
        "museum family days",
    ],
    "live_music": ["concerts", "live bands", "jazz", "classical music", "DJ sets"],
    "performing_arts": ["theatre", "dance performances", "opera", "comedy", "circus"],
    "art_exhibitions": [
        "art exhibitions",
        "gallery openings",
        "photography",
        "design",
        "museum exhibitions",
    ],
    "film": ["film screenings", "open-air cinema", "film festivals", "documentaries"],
    "food_drink": ["food festivals", "food markets", "tastings", "cooking classes"],
    "sports_active": [
        "sports matches",
        "running events",
        "cycling events",
        "group fitness",
        "guided hikes",
    ],
    "tours_heritage": [
        "guided city walks",
        "heritage tours",
        "historic sites",
        "architecture tours",
    ],
}


def _reject_non_finite_number(_value: str) -> NoReturn:
    raise ValueError("Preferences must contain finite JSON numbers.")


def normalize_preferences_blob(blob: Any) -> str:
    """Require supported, unique selections and restore trusted definitions."""
    if not isinstance(blob, str) or len(blob.encode("utf-8")) > MAX_PREFERENCES_BYTES:
        raise ValueError("Preferences must be a JSON string of at most 16384 bytes.")
    try:
        profile = json.loads(blob, parse_constant=_reject_non_finite_number)
    except (ValueError, RecursionError) as exc:
        raise ValueError("Preferences must contain a JSON object.") from exc
    if not isinstance(profile, dict):
        raise ValueError("Preferences must contain a JSON object.")
    interests = profile.get("top_interest_clusters")
    if not isinstance(interests, list) or not 1 <= len(interests) <= len(
        EVENT_TYPE_INCLUDES
    ):
        raise ValueError("Choose at least one event type from the list.")
    selected: set[str] = set()
    for item in interests:
        name = item.get("name") if isinstance(item, dict) else None
        if (
            not isinstance(name, str)
            or name not in EVENT_TYPE_INCLUDES
            or name in selected
        ):
            raise ValueError("Event types must be unique choices from the list.")
        selected.add(name)
    profile["top_interest_clusters"] = [
        {"name": name, "includes": includes}
        for name, includes in EVENT_TYPE_INCLUDES.items()
        if name in selected
    ]
    try:
        normalized = json.dumps(
            profile, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        )
        normalized_size = len(normalized.encode("utf-8"))
    except (ValueError, RecursionError) as exc:
        raise ValueError(
            "Preferences must contain valid JSON with finite numbers."
        ) from exc
    if normalized_size > MAX_PREFERENCES_BYTES:
        raise ValueError(
            "Preferences must be at most 16384 bytes after event types are normalized."
        )
    return normalized
