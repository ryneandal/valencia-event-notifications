"""Bounded native Worker transport for identity-free Jev event classification."""

import asyncio
import hashlib
import json
import math
import re
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

from worker_jev_questions import (
    QUESTION_DEFINITIONS,
    QUESTION_VERSION,
    TAXONOMY_VERSION,
)
from worker_relevance import (
    DEFAULT_THRESHOLD,
    fallback_score,
    score_answers,
    validate_answers,
    validate_selections,
)
from worker_runtime import env_value, to_python
from worker_storage import load_jev_answers, save_jev_answers

JEV_URL = "https://api.typesafe.ai/v1/systemone"
DEFAULT_MODEL = "jev-1.13.0"
ATTEMPT_TIMEOUT_SECONDS = 5.0
EVALUATION_BUDGET_SECONDS = 30.0
MAX_CONCURRENT_REQUESTS = 2
RETRY_DELAY_SECONDS = 0.25
MAX_ATTEMPTS = 2


class ProviderHTTPError(Exception):
    """Safe transport metadata; never carry a provider error body."""

    def __init__(self, status: int, retry_after: float | None = None):
        super().__init__("provider_unavailable")
        self.status = status
        self.retry_after = retry_after


class InvalidResponseError(Exception):
    pass


def jev_mode(env: Any) -> str:
    value = env_value(env, "JEV_MODE", "off")
    return value if value in ("off", "shadow", "filter") else "off"


def selected_types(preferences_blob: str | None) -> list[str]:
    """Use only saved catalog IDs, never client-supplied question text."""
    try:
        profile = json.loads(preferences_blob or "{}")
        clusters = profile["top_interest_clusters"]
        if not isinstance(clusters, list):
            raise ValueError("invalid_preferences")
        return validate_selections([cluster["name"] for cluster in clusters])
    except (ValueError, TypeError, KeyError, RecursionError):
        return []


def build_questions(selected_ids: list[str]) -> dict[str, Any]:
    questions = {}
    for name in validate_selections(selected_ids):
        instructions, positive, negative = QUESTION_DEFINITIONS[name]
        questions[f"event_type:{name}"] = {
            "type": "noul",
            "instructions": instructions,
            "criteria": {"true": positive, "false": negative},
        }
    return questions


def build_request(
    event: dict[str, Any], questions: dict[str, Any], model: str
) -> dict[str, Any]:
    """Whitelist event evidence; identities, URLs, and profile text stay local."""
    if not isinstance(model, str) or not re.fullmatch(r"jev-\d+\.\d+\.\d+", model):
        raise ValueError("invalid_model")
    selected = [key.removeprefix("event_type:") for key in questions]
    if questions != build_questions(selected):
        raise ValueError("invalid_questions")
    evidence = {}
    for field, limit in (
        ("title", 500),
        ("description", 8_000),
        ("start_at", 64),
        ("timezone", 64),
        ("source", 200),
        ("venue", 500),
        ("category", 500),
    ):
        value = event.get(field)
        if isinstance(value, str):
            evidence[field] = value.strip()[:limit]
    if "start_at" in evidence and not evidence.get("timezone"):
        # Stored collector events have an aware ISO start but no timezone column.
        # Retain its actual offset when an explicit zone name is unavailable.
        evidence.pop("timezone", None)
        try:
            start = datetime.fromisoformat(evidence["start_at"])
        except ValueError:
            pass
        else:
            if start.tzinfo is not None:
                evidence["timezone"] = start.tzname()
    if not evidence.get("title"):
        raise ValueError("invalid_event")
    return {"model": model, "state": {"event": evidence}, "questions": questions}


def cache_key(request: dict[str, Any]) -> str:
    """Selection-independent key; per-question entries share the same evidence."""
    identity = {
        "state": request["state"],
        "model": request["model"],
        "taxonomy_version": TAXONOMY_VERSION,
        "question_version": QUESTION_VERSION,
        "questions": build_questions(list(QUESTION_DEFINITIONS)),
    }
    return hashlib.sha256(
        json.dumps(identity, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def attach_event(
    event: dict[str, Any], score: dict[str, Any], model: str | None = None
) -> dict[str, Any]:
    return {
        "event": {name: event[name] for name in ("event_key", "title", "url")},
        **score,
        "model": model,
        "evaluated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


def fallback_evaluation(
    event: dict[str, Any], selected_ids: list[str], error_code: str
) -> dict[str, Any]:
    return attach_event(event, fallback_score(selected_ids, error_code))


def _retry_after(headers: Any) -> float | None:
    if headers is None:
        return None
    value = headers.get("retry-after-ms")
    seconds = headers.get("retry-after")
    try:
        if value is not None:
            delay = float(value) / 1000
        elif seconds is not None:
            try:
                delay = float(seconds)
            except ValueError:
                delay = (
                    parsedate_to_datetime(seconds) - datetime.now(UTC)
                ).total_seconds()
        else:
            return None
        return max(0, delay) if math.isfinite(delay) else None
    except (TypeError, ValueError, OverflowError):
        return None


async def _call_provider(env: Any, body: dict[str, Any], timeout: float) -> Any:
    fake = env_value(env, "JEV_FETCH")
    if callable(fake):
        response = await fake(body)
        if isinstance(response, dict):
            return response
    else:
        api_key = str(env_value(env, "TYPESAFE_API_KEY", "")).strip()
        if not api_key:
            raise ProviderHTTPError(401)
        from js import AbortSignal, Object, fetch  # type: ignore[import-not-found]
        from pyodide.ffi import to_js  # type: ignore[import-not-found]

        response = await fetch(
            JEV_URL,
            to_js(
                {
                    "method": "POST",
                    "headers": {
                        "authorization": f"Bearer {api_key}",
                        "content-type": "application/json",
                    },
                    "body": json.dumps(body, ensure_ascii=False, allow_nan=False),
                    "signal": AbortSignal.timeout(max(1, math.ceil(timeout * 1000))),
                },
                dict_converter=Object.fromEntries,
            ),
        )
    if response is None or not hasattr(response, "status"):
        raise InvalidResponseError()
    status = int(response.status)
    if not 200 <= status < 300:
        raise ProviderHTTPError(
            status, _retry_after(getattr(response, "headers", None))
        )
    try:
        return to_python(await response.json())
    except Exception as exc:
        raise InvalidResponseError() from exc


async def _fetch_answers(
    env: Any, body: dict[str, Any], selected_ids: list[str], deadline: float
) -> dict[str, Any]:
    for attempt in range(MAX_ATTEMPTS):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError()
        try:
            timeout = min(ATTEMPT_TIMEOUT_SECONDS, remaining)
            response = await asyncio.wait_for(
                _call_provider(env, body, timeout), timeout
            )
            if not isinstance(response, dict) or response.get("model") != body["model"]:
                raise InvalidResponseError()
            try:
                answers = response["answers"]
                validate_answers(selected_ids, answers)
            except (KeyError, ValueError, OverflowError) as exc:
                raise InvalidResponseError() from exc
            return answers
        except InvalidResponseError:
            raise
        except Exception as exc:
            retryable = not isinstance(exc, ProviderHTTPError) or (
                exc.status in (408, 429) or 500 <= exc.status < 600
            )
            if not retryable or attempt == MAX_ATTEMPTS - 1:
                raise
            delay = RETRY_DELAY_SECONDS
            if isinstance(exc, ProviderHTTPError) and exc.retry_after is not None:
                delay = max(delay, exc.retry_after)
            if delay >= deadline - time.monotonic():
                raise TimeoutError() from None
            await asyncio.sleep(delay)
    raise RuntimeError("provider_unavailable")  # pragma: no cover


async def _evaluate_event(
    env: Any, event: dict[str, Any], selected_ids: list[str], deadline: float
) -> dict[str, Any]:
    if jev_mode(env) == "off":
        return fallback_evaluation(event, selected_ids, "feature_disabled")
    try:
        questions = build_questions(selected_ids)
    except ValueError:
        return fallback_evaluation(event, selected_ids, "invalid_preferences")
    model = env_value(env, "JEV_MODEL", DEFAULT_MODEL)
    try:
        body = build_request(event, questions, model)
    except ValueError:
        return fallback_evaluation(event, selected_ids, "provider_unavailable")
    key = cache_key(body)
    db = env_value(env, "DB")
    answers: dict[str, Any] = {}
    if db is not None:
        try:
            cached = await load_jev_answers(db, key, model)
            for question_id, answer in cached.items():
                if question_id in questions:
                    validate_answers(
                        [question_id.removeprefix("event_type:")], {question_id: answer}
                    )
                    answers[question_id] = answer
        except Exception:
            # Cache failures cannot fabricate a classification or expose D1 errors.
            answers = {}
    missing = [name for name in selected_ids if f"event_type:{name}" not in answers]
    if missing:
        request = {**body, "questions": build_questions(missing)}
        try:
            fresh = await _fetch_answers(env, request, missing, deadline)
        except InvalidResponseError:
            return fallback_evaluation(event, selected_ids, "invalid_provider_response")
        except Exception:
            error_code = (
                "budget_exhausted"
                if time.monotonic() >= deadline
                else "provider_unavailable"
            )
            return fallback_evaluation(event, selected_ids, error_code)
        answers.update(fresh)
        if db is not None:
            try:
                await save_jev_answers(db, key, model, fresh)
            except Exception:
                pass  # A valid response remains useful when the optional cache fails.
    return attach_event(
        event, score_answers(selected_ids, answers, DEFAULT_THRESHOLD), model
    )


async def evaluate_event(
    env: Any,
    event: dict[str, Any],
    selected_ids: list[str],
    *,
    deadline: float | None = None,
) -> dict[str, Any]:
    end = (
        deadline
        if deadline is not None
        else time.monotonic() + EVALUATION_BUDGET_SECONDS
    )
    remaining = end - time.monotonic()
    if remaining <= 0:
        return fallback_evaluation(event, selected_ids, "budget_exhausted")
    try:
        return await asyncio.wait_for(
            _evaluate_event(env, event, selected_ids, end), remaining
        )
    except TimeoutError:
        return fallback_evaluation(event, selected_ids, "budget_exhausted")


async def evaluate_events(
    env: Any, events: list[dict[str, Any]], selected_ids: list[str]
) -> list[dict[str, Any]]:
    """One shared budget and at most two in-flight event evaluations."""
    deadline = time.monotonic() + EVALUATION_BUDGET_SECONDS
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    async def one(event: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            return await evaluate_event(env, event, selected_ids, deadline=deadline)

    return list(await asyncio.gather(*(one(event) for event in events)))
