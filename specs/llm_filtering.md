# Feature Specification: LLM Filtering

## Status (2026-09-04)
Mostly implemented, with one architectural difference from the original plan: the integration uses
**LangChain** provider integrations for Gemini, Mistral, and OpenRouter instead of the raw
`google-generativeai` SDK, and the logic lives in `src/valencia_events/personalization.py` rather than an
`LLMFilter` class in `filters.py` (`filters.py` holds the deterministic tomorrow-filter and rank/limit
fallback). Backend selection via `LLM_BACKEND` env var with model fallbacks. The multi-user loop in
`cli.py` is done. Remaining: persist relevance scores/reasons to `users_events`.

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
    - Run as part of the daily GHA workflow.
    - Iterate through all active users, generating a custom email for each.

## Technical Architecture
- **Model**: Gemini, Mistral, or OpenRouter via LangChain (`langchain-google-genai`, `langchain-mistralai`, or `langchain-openrouter`), with configurable primary and fallback models.
- **Failure behavior**: provider/model failures must use the deterministic rank-and-limit fallback; tests must not call live provider APIs.
- **Pipeline**:
    1.  `cli.py` fetches tomorrow's events.
    2.  `cli.py` loads active users.
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
- [x] Update `src/valencia_events/cli.py` to loop through active users.
- [ ] Persist `relevance_score` / `relevance_reason` to the `users_events` table.
