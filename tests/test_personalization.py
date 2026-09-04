"""Tests for LLM personalization layer."""

import json
from datetime import datetime

import pytz

from valencia_events.models import Event
from valencia_events.personalization import (
    DEFAULT_LLM_BACKEND,
    DEFAULT_MISTRAL_MODEL,
    DEFAULT_OPENROUTER_MODEL,
    GeminiEventRanker,
    MistralEventRanker,
    OpenRouterEventRanker,
    PersonalizedSelection,
    _ranker_from_env,
    load_family_profile,
    rank_events_for_family,
)

TZ = pytz.timezone("Europe/Madrid")


def _event(title: str, event_hash: str, hour: int = 10) -> Event:
    return Event(
        title=title,
        start=TZ.localize(datetime(2025, 10, 20, hour, 0)),
        url=f"https://example.com/{event_hash}",
        description="",
        source="test",
        event_hash=event_hash,
    )


class FakeRanker(GeminiEventRanker):
    """Fake ranker to avoid network calls."""

    def __init__(self):
        super().__init__(api_key="x", model="m")

    def rank(self, events, family_profile, limit):  # noqa: ANN001
        del family_profile
        return PersonalizedSelection(
            events=list(reversed(events))[:limit],
            summary="Picked family-friendly options.",
            feedback_by_hash={"b": "Daytime, interactive, and easy to access."},
            used_llm=True,
        )


def test_load_family_profile_from_env(monkeypatch):
    monkeypatch.setenv("FAMILY_PROFILE_JSON", json.dumps({"audience": "test_family"}))
    profile = load_family_profile()
    assert profile["audience"] == "test_family"


def test_rank_events_for_family_fallback_without_api_key(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    events = [_event("B", "b", 11), _event("A", "a", 10)]

    selection = rank_events_for_family(events, limit=1)

    assert len(selection.events) == 1
    assert selection.used_llm is False


def test_rank_events_for_family_with_custom_ranker():
    events = [_event("A", "a"), _event("B", "b")]
    selection = rank_events_for_family(events, limit=2, ranker=FakeRanker())
    assert selection.used_llm is True
    assert selection.summary == "Picked family-friendly options."
    assert [event.title for event in selection.events] == ["B", "A"]


def test_gemini_ranker_falls_back_to_secondary_model(monkeypatch):
    from valencia_events.personalization import GeminiRankedEvent, GeminiRankingResponse

    ranker = GeminiEventRanker(
        api_key="x",
        model="gemini-3-flash-preview",
        fallback_model="gemini-2.5-pro",
    )
    events = [_event("A", "a"), _event("B", "b")]
    calls: list[str] = []

    def fake_invoke_model(*, model, family_profile, event_payload, limit):  # noqa: ANN001
        del family_profile, event_payload, limit
        calls.append(model)
        if model == "gemini-3-flash-preview":
            raise RuntimeError("503")
        return GeminiRankingResponse(
            summary="Fallback model worked.",
            selected_events=[
                GeminiRankedEvent(event_hash="b", reason="Better fit."),
                GeminiRankedEvent(event_hash="a", reason="Also suitable."),
            ],
            selected_event_hashes=["b", "a"],
        )

    monkeypatch.setattr(ranker, "_invoke_model", fake_invoke_model)
    selection = ranker.rank(events, family_profile={"audience": "test"}, limit=2)

    assert calls == ["gemini-3-flash-preview", "gemini-2.5-pro"]
    assert selection.used_llm is True
    assert [event.title for event in selection.events] == ["B", "A"]


def test_mistral_ranker_from_env_uses_default_model(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    monkeypatch.delenv("MISTRAL_MODEL", raising=False)
    monkeypatch.delenv("MISTRAL_FALLBACK_MODEL", raising=False)

    ranker = MistralEventRanker.from_env()

    assert ranker is not None
    assert ranker.model == DEFAULT_MISTRAL_MODEL
    assert ranker.fallback_model == ""


def test_openrouter_ranker_from_env_uses_default_model(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    monkeypatch.delenv("OPENROUTER_FALLBACK_MODEL", raising=False)

    ranker = OpenRouterEventRanker.from_env()

    assert ranker is not None
    assert DEFAULT_LLM_BACKEND == "openrouter"
    assert DEFAULT_OPENROUTER_MODEL == "nvidia/nemotron-3-ultra-550b-a55b:free"
    assert ranker.model == DEFAULT_OPENROUTER_MODEL
    assert ranker.fallback_model == ""


def test_openrouter_ranker_loads_dotenv_when_environment_key_is_missing(
    monkeypatch,
    tmp_path,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    monkeypatch.delenv("OPENROUTER_FALLBACK_MODEL", raising=False)
    (tmp_path / ".env").write_text(
        "OPENROUTER_API_KEY=dotenv-key\n"
        "OPENROUTER_MODEL=google/gemini-2.5-flash\n"
        "OPENROUTER_FALLBACK_MODEL=openrouter/auto\n",
        encoding="utf-8",
    )

    ranker = OpenRouterEventRanker.from_env()

    assert ranker is not None
    assert ranker.api_key == "dotenv-key"
    assert ranker.model == "google/gemini-2.5-flash"
    assert ranker.fallback_model == "openrouter/auto"


def test_openrouter_ranker_prefers_environment_over_dotenv(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "environment-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "openai/gpt-5")
    (tmp_path / ".env").write_text(
        "OPENROUTER_API_KEY=dotenv-key\nOPENROUTER_MODEL=google/gemini-2.5-flash\n",
        encoding="utf-8",
    )

    ranker = OpenRouterEventRanker.from_env()

    assert ranker is not None
    assert ranker.api_key == "environment-key"
    assert ranker.model == "openai/gpt-5"


def test_openrouter_ranker_uses_dedicated_structured_output_client(monkeypatch):
    import langchain_core.prompts
    import langchain_openrouter

    from valencia_events.personalization import GeminiRankingResponse

    calls = {}
    expected = GeminiRankingResponse(summary="Selected events.")

    class FakeChain:
        def invoke(self, payload):  # noqa: ANN001
            calls["payload"] = payload
            return expected

    class FakePrompt:
        def __or__(self, structured_model):  # noqa: ANN001
            calls["structured_model"] = structured_model
            return FakeChain()

    class FakePromptTemplate:
        @classmethod
        def from_messages(cls, messages):  # noqa: ANN001
            calls["messages"] = messages
            return FakePrompt()

    class FakeChatOpenRouter:
        def __init__(self, **kwargs):  # noqa: ANN003
            calls["client_kwargs"] = kwargs

        def with_structured_output(self, schema, **kwargs):  # noqa: ANN001, ANN003
            calls["schema"] = schema
            calls["structured_output_kwargs"] = kwargs
            return "structured-model"

    monkeypatch.setattr(
        langchain_core.prompts,
        "ChatPromptTemplate",
        FakePromptTemplate,
    )
    monkeypatch.setattr(
        langchain_openrouter,
        "ChatOpenRouter",
        FakeChatOpenRouter,
    )
    ranker = OpenRouterEventRanker(api_key="test-key", model="openrouter/auto")

    result = ranker._invoke_model(
        model="openrouter/auto",
        family_profile={"audience": "test"},
        event_payload=[{"event_hash": "a", "title": "A"}],
        limit=1,
    )

    assert result is expected
    assert calls["client_kwargs"] == {
        "model": "openrouter/auto",
        "api_key": "test-key",
        "temperature": 0,
        "openrouter_provider": {"require_parameters": True},
    }
    assert calls["schema"] is GeminiRankingResponse
    assert calls["structured_output_kwargs"] == {"method": "json_schema"}
    assert json.loads(calls["payload"]["family_profile_json"]) == {"audience": "test"}
    assert json.loads(calls["payload"]["events_json"]) == [
        {"event_hash": "a", "title": "A"}
    ]
    assert calls["payload"]["limit"] == "1"


def test_openrouter_default_model_parses_plain_json(monkeypatch):
    import langchain_core.prompts
    import langchain_openrouter

    calls = {}

    class FakeResponse:
        content = (
            "Here is the result:\n"
            '{"summary":"A strong fit.","selected_events":['
            '{"event_hash":"a","reason":"Interactive."}],'
            '"selected_event_hashes":["a"]}'
        )

    class FakeChain:
        def invoke(self, payload):  # noqa: ANN001
            calls["payload"] = payload
            return FakeResponse()

    class FakePrompt:
        def __or__(self, llm):  # noqa: ANN001
            calls["llm"] = llm
            return FakeChain()

    class FakePromptTemplate:
        @classmethod
        def from_messages(cls, messages):  # noqa: ANN001
            calls["messages"] = messages
            return FakePrompt()

    class FakeChatOpenRouter:
        def __init__(self, **kwargs):  # noqa: ANN003
            calls["client_kwargs"] = kwargs

    monkeypatch.setattr(
        langchain_core.prompts,
        "ChatPromptTemplate",
        FakePromptTemplate,
    )
    monkeypatch.setattr(
        langchain_openrouter,
        "ChatOpenRouter",
        FakeChatOpenRouter,
    )
    ranker = OpenRouterEventRanker(
        api_key="test-key",
        model=DEFAULT_OPENROUTER_MODEL,
    )

    result = ranker._invoke_model(
        model=DEFAULT_OPENROUTER_MODEL,
        family_profile={"audience": "test"},
        event_payload=[{"event_hash": "a", "title": "A"}],
        limit=1,
    )

    assert result.summary == "A strong fit."
    assert result.selected_events[0].reason == "Interactive."
    assert calls["client_kwargs"] == {
        "model": DEFAULT_OPENROUTER_MODEL,
        "api_key": "test-key",
        "temperature": 0,
    }


def test_ranker_from_env_defaults_to_openrouter(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-key")
    monkeypatch.setenv("MISTRAL_API_KEY", "mistral-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")

    ranker = _ranker_from_env()

    assert isinstance(ranker, OpenRouterEventRanker)
    assert ranker.model == DEFAULT_OPENROUTER_MODEL


def test_ranker_from_env_can_select_gemini(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "gemini")
    monkeypatch.setenv("MISTRAL_API_KEY", "mistral-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")

    ranker = _ranker_from_env()

    assert isinstance(ranker, GeminiEventRanker)
    assert not isinstance(ranker, MistralEventRanker)


def test_ranker_from_env_can_select_openrouter(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LLM_BACKEND", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.5")

    ranker = _ranker_from_env()

    assert isinstance(ranker, OpenRouterEventRanker)
    assert ranker.model == "anthropic/claude-sonnet-4.5"
