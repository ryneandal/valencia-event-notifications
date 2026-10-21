"""Pure, conservative scoring of independent event-type answers."""

import math
from decimal import Decimal
from typing import Any

from worker_jev_questions import (
    QUESTION_DEFINITIONS,
    QUESTION_VERSION,
    TAXONOMY_VERSION,
)

SCORING_VERSION = "noul-any-type-v1"
DEFAULT_THRESHOLD = 0.6
ERROR_CODES = {
    "provider_unavailable",
    "invalid_provider_response",
    "invalid_preferences",
    "budget_exhausted",
    "feature_disabled",
}


def validate_selections(selected_ids: Any) -> list[str]:
    if (
        not isinstance(selected_ids, list)
        or not 1 <= len(selected_ids) <= len(QUESTION_DEFINITIONS)
        or any(not isinstance(item, str) for item in selected_ids)
        or len(set(selected_ids)) != len(selected_ids)
        or any(item not in QUESTION_DEFINITIONS for item in selected_ids)
    ):
        raise ValueError("invalid_preferences")
    return list(selected_ids)


def probability(value: Any) -> Decimal:
    """JSON numbers only: bool, strings, NaN, and infinities are invalid."""
    if (
        type(value) not in (int, float)
        or not math.isfinite(value)
        or not 0 <= value <= 1
    ):
        raise ValueError("invalid_provider_response")
    return Decimal(str(value))


def validate_answers(selected_ids: list[str], answers: Any) -> dict[str, Decimal]:
    expected = {f"event_type:{name}" for name in selected_ids}
    if not isinstance(answers, dict) or set(answers) != expected:
        raise ValueError("invalid_provider_response")
    probabilities = {}
    for name in selected_ids:
        answer = answers[f"event_type:{name}"]
        if (
            not isinstance(answer, dict)
            or set(answer) != {"type", "noul"}
            or answer["type"] != "noul"
        ):
            raise ValueError("invalid_provider_response")
        probabilities[name] = probability(answer["noul"])
    return probabilities


def fallback_score(
    selected_ids: Any,
    error_code: str,
    threshold: float = DEFAULT_THRESHOLD,
) -> dict[str, Any]:
    try:
        selected = validate_selections(selected_ids)
    except ValueError:
        selected = []
    try:
        safe_threshold = float(probability(threshold))
    except (ValueError, OverflowError):
        safe_threshold = DEFAULT_THRESHOLD
    return {
        "selected_event_types": selected,
        "taxonomy_version": TAXONOMY_VERSION,
        "question_version": QUESTION_VERSION,
        "scoring_version": SCORING_VERSION,
        "status": "fallback",
        "decision": "unknown",
        "irrelevance_score": None,
        "threshold": safe_threshold,
        "components": [],
        "error_code": error_code
        if error_code in ERROR_CODES
        else "provider_unavailable",
    }


def score_answers(
    selected_ids: list[str],
    answers: dict[str, Any],
    threshold: float = DEFAULT_THRESHOLD,
) -> dict[str, Any]:
    """Return scoring fields; the adapter attaches canonical event provenance."""
    result = fallback_score(selected_ids, "invalid_preferences", threshold)
    try:
        selected = validate_selections(selected_ids)
        cutoff = probability(threshold)
    except (ValueError, OverflowError):
        return result
    try:
        probabilities = validate_answers(selected, answers)
    except (ValueError, OverflowError):
        return fallback_score(selected, "invalid_provider_response", threshold)

    matched = any(p >= Decimal("0.8") for p in probabilities.values())
    nonmatches = all(p <= Decimal("0.2") for p in probabilities.values())
    evaluated = matched or nonmatches
    weight = Decimal(1) / len(selected)
    components = []
    confidences = []
    for name, p_yes in probabilities.items():
        confidence = abs(2 * p_yes - 1)
        confidences.append(confidence)
        contribution = (
            Decimal(0) if matched else weight * confidence if nonmatches else None
        )
        components.append(
            {
                "question_id": f"event_type:{name}",
                "event_type": name,
                "p_yes": float(p_yes),
                "confidence": float(confidence),
                "weight": float(weight),
                "contribution": float(contribution)
                if contribution is not None
                else None,
            }
        )
    # Divide once so repeating weights cannot turn exact equality into rejection.
    score = Decimal(0) if matched else sum(confidences) / len(selected)
    result.update(
        status="evaluated" if evaluated else "uncertain",
        decision=("irrelevant" if score > cutoff else "eligible")
        if evaluated
        else "unknown",
        irrelevance_score=float(score) if evaluated else None,
        components=components,
        error_code=None,
    )
    return result
