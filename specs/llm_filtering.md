# Feature Specification: LLM Filtering

## Overview
Use an LLM (Gemini) to filter and rank daily events based on a user's natural language preferences.

## Requirements
1.  **Input**:
    - Top N events (e.g., 20-50) collected for the day.
    - User's preference string (e.g., "Family of 5...").
2.  **Process**:
    - Send event data (JSON) + User Preferences to Gemini API.
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
- **Model**: Gemini (likely `gemini-pro` via `google-generativeai` SDK).
- **Pipeline**:
    1.  `runner.py` fetches tomorrow's events.
    2.  `runner.py` loads active users.
    3.  For each user:
        - Construct prompt: `System: You are an event curator. User: {prefs}. Events: {events_json}. Task: Pick top 5...`
        - Call API.
        - Parse JSON response.
        - Generate HTML email with personalized content.
        - Send email.

## Tasks
- [ ] Add `google-generativeai` dependency.
- [ ] Define LLM Prompt Template.
- [ ] Implement `LLMFilter` class in `filters.py` (new).
- [ ] Update `runner.py` to loop through users.
