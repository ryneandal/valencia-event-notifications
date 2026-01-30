# Feature Specification: User Management

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
- [ ] Research & Select Hosting/DB solution for persistent user data (SQLite on GHA is ephemeral unless committed).
- [ ] Implement FastAPI app skeleton.
- [ ] Implement Google OAuth2 login flow.
- [ ] Implement User Model & Database migration.
- [ ] Create Profile Page (HTML/Tailwind/Jinja2).
