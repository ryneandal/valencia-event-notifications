# Feature Specification: User Management

## Status (2026-06-10)
Partially implemented. There are currently **two parallel implementations**:

- **FastAPI** (`src/valencia_events/web.py` + `onboarding.py` + `storage.py`): `/onboarding/*` routes, bearer-token sessions, SQLite `events.db`.
- **Cloudflare** (`cloudflare/worker/src/` + `cloudflare/pages/public/`): `/api/*` routes, HttpOnly cookie sessions (SHA-256 hashed tokens), D1.

The Pages frontend talks only to the Worker. Open decisions: hosting/DB strategy, consolidating to one stack, and real authentication — **login is currently email-only with no verification** (passwordless per the spirit of this spec, but with no proof of email ownership). Google OAuth and Passkeys are not implemented.

## Overview
Implement a user authentication system and profile management to allow users to customize their event notifications.

## Requirements
1.  **Passwordless Authentication**: Users must sign in using Google OAuth2 or Passkeys. No traditional password storage.
2.  **User Profile**:
    - Store user email (unique identifier).
    - Store a "Preferences" free-text field (e.g., "Family of 5, likes hiking...").
    - Store subscription status (Active/Paused).
3.  **UI/UX**:
    - Simple landing page with "Sign in with Google" / "Sign in with Passkey".
    - Account dashboard to view/edit preferences and subscription status.

## Technical Architecure
*Since the current project is a collection of scripts run by a runner, we need to introduce a web server component for user interaction.*

- **Web Framework**: FastAPI (lightweight, async, great for Pydantic integration).
- **Database**: Expand existing SQLite `events.db`.
    - `users` table:
        - `id` (INTEGER PK AUTOINCREMENT)
        - `email` (TEXT UNIQUE NOT NULL)
        - `preferences` (TEXT) - Natural language string
        - `is_active` (BOOLEAN DEFAULT 1)
        - `created_at` (TIMESTAMP)
    - `users_events` table (Join Table):
        - `user_id` (INTEGER FK -> users.id)
        - `event_hash` (TEXT FK -> events.event_hash)
        - `is_sent` (BOOLEAN) - Track if emailed
        - `relevance_score` (FLOAT) - From LLM
        - `relevance_reason` (TEXT) - From LLM
        - Primary Key: `(user_id, event_hash)`
- **Auth Provider**:
    - Use `authlib` or similar for Google OAuth.
    - Research libraries for Passkey support (WebAuthn).
- **Hosting**:
    - The web app will need to be deployed (e.g., Vercel, Railway, or a VPS) to handle logins and profile management.
    - *Constraint*: If this runs solely on GHA currently, we need to decide where the user database lives.
        - **Decision**: For development/MVP, we will use the local SQLite file. For production, we will likely need a managed database or a volume mount if running in a container.

## Tasks
- [ ] Research & Select Hosting/DB solution for persistent user data (SQLite on GHA is ephemeral unless committed; Cloudflare D1 is the current candidate).
- [x] Implement FastAPI app skeleton (`src/valencia_events/web.py`).
- [x] Implement User Model & Database schema (`users`, `user_sessions`, `users_events` in `storage.py`; D1 mirror in `cloudflare/worker/src/schema.sql`).
- [x] Basic profile UI (Cloudflare Pages static frontend, `cloudflare/pages/public/` — plain HTML/JS, not Tailwind/Jinja2).
- [ ] Implement verified authentication (minimum: email magic-link; target: Google OAuth2 and/or Passkeys).
- [ ] Consolidate FastAPI and Cloudflare Worker stacks into one (unify routes, session model, and `preferences` vs `preferences_blob` field naming).
- [ ] Populate `users_events` during digest sends (table exists, never written).
