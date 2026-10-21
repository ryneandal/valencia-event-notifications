import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cloudflare" / "worker" / "src"))

from worker_jev_questions import QUESTION_DEFINITIONS  # noqa: E402
from worker_relevance import fallback_score, score_answers  # noqa: E402

EXAMPLES = json.loads(
    (ROOT / "cloudflare/shared/jev-preview.examples.json").read_text()
)


def answers_for(selected, values):
    return {
        f"event_type:{name}": {"type": "noul", "noul": value}
        for name, value in zip(selected, values, strict=True)
    }


@pytest.mark.parametrize("name", list(EXAMPLES))
def test_scores_match_shared_frontend_examples(name):
    example = EXAMPLES[name]
    selected = example["selected_event_types"]
    if name == "fallback":
        actual = fallback_score(selected, "provider_unavailable")
    else:
        actual = score_answers(
            selected,
            answers_for(selected, [c["p_yes"] for c in example["components"]]),
            example["threshold"],
        )
    assert actual == {key: example[key] for key in actual}


def test_any_match_wins_among_all_twelve_selected_categories():
    selected = list(QUESTION_DEFINITIONS)
    result = score_answers(selected, answers_for(selected, [0.8] + [0.0] * 11))
    assert result["decision"] == "eligible"
    assert result["irrelevance_score"] == 0
    assert len(result["components"]) == 12
    assert all(item["contribution"] == 0 for item in result["components"])


@pytest.mark.parametrize("count", [1, 2, 3, 6, 7, 9, 12])
def test_decimal_threshold_equality_does_not_reject(count):
    selected = list(QUESTION_DEFINITIONS)[:count]
    result = score_answers(selected, answers_for(selected, [0.2] * count))
    assert result["decision"] == "eligible"
    assert result["irrelevance_score"] == 0.6
    assert sum(c["contribution"] for c in result["components"]) == pytest.approx(0.6)


def test_strict_threshold_and_probability_precision():
    selected = ["film"]
    result = score_answers(selected, answers_for(selected, [0.199999999999]))
    assert result["decision"] == "irrelevant"
    result = score_answers(selected, answers_for(selected, [0.200000000001]))
    assert result["status"] == "uncertain"
    assert result["decision"] == "unknown"
    assert result["irrelevance_score"] is None
    assert result["components"][0]["contribution"] is None


@pytest.mark.parametrize(
    "value",
    [True, False, None, "0.05", float("nan"), float("inf"), -0.01, 1.01, 10**400],
)
def test_invalid_numbers_never_become_confident_exclusions(value):
    result = score_answers(["film"], answers_for(["film"], [value]))
    assert result["status"] == "fallback"
    assert result["decision"] == "unknown"
    assert result["error_code"] == "invalid_provider_response"
    assert result["irrelevance_score"] is None


@pytest.mark.parametrize(
    "answers",
    [
        {},
        [],
        {"event_type:film": {"type": "score", "noul": 0}},
        {"event_type:film": {"type": "noul"}},
        {"event_type:film": {"type": "noul", "noul": 0, "confidence": 1}},
        {"event_type:film": {"type": "noul", "noul": 0}, "unexpected": {}},
        {"event_type:film": True},
    ],
)
def test_partial_wrong_type_extra_answers_are_invalid(answers):
    assert score_answers(["film"], answers)["error_code"] == "invalid_provider_response"


@pytest.mark.parametrize(
    "selected", [[], ["film", "film"], ["unknown"], "film", [None], None]
)
def test_invalid_selections_return_schema_shaped_fallback(selected):
    result = score_answers(selected, {})
    assert result["error_code"] == "invalid_preferences"
    assert result["selected_event_types"] == []
    assert result["components"] == []
    assert result["decision"] == "unknown"


def test_selection_change_recomputes_instead_of_reusing_user_score():
    result = score_answers(["live_music"], answers_for(["live_music"], [0.94]))
    assert result["decision"] == "eligible"
    result = score_answers(["food_drink"], answers_for(["food_drink"], [0.08]))
    assert result["decision"] == "irrelevant"
