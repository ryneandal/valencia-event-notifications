# Feature Specification: LLM Filtering

## Status (2026-09-04)
The production Cloudflare Worker directly calls OpenRouter and defaults to
`nvidia/nemotron-3-ultra-550b-a55b:free`. It schema-validates the response,
falls back deterministically, and stores ordered recommendations and reasons in
D1. The local reference pipeline still supports Gemini, Mistral, and OpenRouter
through LangChain in `src/valencia_events/personalization.py`.

## Overview
Use an LLM (Gemini, Mistral, or an OpenRouter model) to filter and rank daily events based on a user's natural language preferences.

## Requirements
1.  **Input**:
    - Top N events (e.g., 20-50) collected for the day.
    - User's preference string (e.g., "Family of 5...").
2.  **Process**:
    - Send event data (JSON) + user preferences to the configured LLM provider.
    - Ask LLM to:
        - Select events that match the user's interests.
        - Explain *why* it fits (1-sentence rationale).
        - Rank them by relevance.
3.  **Output**:
    - A filtered list of events with personalized descriptions.
4.  **Integration**:
    - Run from a daily Cloudflare Cron Trigger.
    - Iterate through all active D1 users, generating a custom email for each.

## Technical Architecture
- **Production model**: OpenRouter by default using
  `nvidia/nemotron-3-ultra-550b-a55b:free`; `OPENROUTER_MODEL` can override it.
- **Local reference models**: Gemini, Mistral, and OpenRouter through LangChain.
- **Failure behavior**: provider/model failures must use the deterministic rank-and-limit fallback; tests must not call live provider APIs.
- **Pipeline**:
    1.  The scheduled Worker fetches tomorrow's events once.
    2.  It loads verified, subscribed D1 users through its direct binding.
    3.  For each user:
        - Construct prompt: `System: You are an event curator. User: {prefs}. Events: {events_json}. Task: Pick top 5...`
        - Call API.
        - Parse JSON response.
        - Generate HTML email with personalized content.
        - Send email.

## Tasks
- [x] Add LLM dependencies (LangChain: `langchain-google-genai`, `langchain-mistralai`, `langchain-openrouter`).
- [x] Define LLM Prompt Template.
- [x] Implement ranking logic (`rank_events_for_family` in `src/valencia_events/personalization.py`).
- [x] Update `src/valencia_events/cli.py` to loop through active users as migration
  reference behavior.
- [x] Port ranking orchestration to the scheduled Cloudflare Worker.
- [x] Persist ordered reasons, model ID, and fallback state to D1
  `recommendations` rows.
- [x] Configure the production `OPENROUTER_API_KEY` Worker secret.
- [ ] Complete an authenticated provider preview and one controlled live smoke
  before enabling digest delivery.
