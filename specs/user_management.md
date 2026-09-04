# Feature Specification: User Registration and Personalization

## Status (2026-09-04)

The production direction is decided: Cloudflare is the interactive web stack.
The Git-connected Pages project serves the React/Vite onboarding SPA and
same-origin API proxy. The Python Worker, D1 database, single-use magic links,
and Mailgun sandbox delivery are also deployed.

The complete registration, magic-link, session, and profile round-trip is live.
Production D1 contains a verified active profile with all six authoritative
personalization keys. The remaining product work is the Cloudflare-native
scheduled digest runtime and pause/unsubscribe support.

The older FastAPI/SQLite onboarding implementation under `src/valencia_events/`
is retained for now, but it is not the production web architecture. New web
features should target Pages, the Worker, and D1.

See [architecture.md](architecture.md) for component ownership and the full
data flow.

## Product scope

The onboarding application lets a person:

1. provide and verify the email address that will receive the digest;
2. describe who the recommendations are for;
3. select acceptable travel distance and event interests;
4. identify strong positive and negative ranking signals;
5. opt into seasonal València event anchors;
6. review and save the profile; and
7. later resume the account, edit the profile, pause the subscription, or log
   out.

Completing onboarding stores the profile in D1. It does not run scrapers or an
LLM request synchronously in the browser. A Cron-triggered Cloudflare Worker
will perform that work and send the resulting HTML digest by email.

## Personalization profile contract

`src/valencia_events/personalization.py` is the source of truth for the profile
shape consumed by ranking. The SPA must serialize this shape as JSON in the D1
`users.preferences_blob` field:

```json
{
  "audience": "family_with_school_age_kids",
  "location_scope": ["Valencia city"],
  "top_interest_clusters": [
    {
      "name": "parks_and_play",
      "includes": ["destination playgrounds", "picnics"]
    }
  ],
  "strong_positive_signals": ["outdoors", "daytime", "near_transit"],
  "strong_negative_signals": ["starts_after_20", "crowd_extreme"],
  "seasonal_anchors": [
    {
      "name": "Fallas",
      "months": ["Feb", "Mar"],
      "notes": "daytime monument walks; mascleta/fireworks are loud"
    }
  ]
}
```

The current UI vocabulary is maintained in `cloudflare/pages/src/profile.js`
and maps to those fields. The form should make structured choices easy while
retaining the complete stored JSON needed by the ranker. Email, session tokens,
and authentication metadata are not part of the personalization profile and
must never be included in an LLM prompt.

## User experience requirements

- Use a responsive React SPA hosted by Cloudflare Pages.
- Preserve the approved Mediterranean/València visual direction from
  `cloudflare/design-poc/`.
- Use a short, multi-step flow with progress, back/next navigation, validation,
  and a final review screen.
- Persist only after explicit submission; explain that selections can be
  changed later.
- Restore an existing saved profile when an authenticated user returns.
- Make keyboard focus, labels, error messages, contrast, reduced motion, and
  mobile layouts part of acceptance testing.
- Do not expose API credentials or raw session tokens to browser JavaScript.

## Authentication

The PoC authentication target is a verified, passwordless email magic link.
Google OAuth and Passkeys are possible later additions, not requirements for
this PoC.

The deployed magic-link flow:

- returns a generic `202` from registration/login so account state is not
  disclosed;
- leaves a newly registered user inactive until verification;
- sends login links only for active users while preserving the generic response;
- stores only SHA-256 token hashes and defaults to a 15-minute lifetime;
- accepts each token once; invalid, expired, and replayed tokens return `401`;
- establishes an `HttpOnly`, `Secure`, `SameSite=Lax` session cookie only after
  successful verification; and
- builds a same-origin verification link from the configured application URL.

This behavior is deployed and its Mailgun delivery and D1 persistence have been
verified with a controlled production account.

## Data model and source-of-truth boundaries

### D1: subscriber identity and profile

D1 is canonical for:

- unique email address;
- serialized personalization profile;
- verified-account state in `users.is_active`;
- reversible delivery state in `subscriptions.is_subscribed`;
- sessions; and
- magic-link verification records once implemented.

### D1: scheduled event processing

The scheduled Cloudflare Worker will store normalized events, deduplication
state, recommendations, and delivery history in D1. The existing SQLite and D1
HTTP subscriber-loader implementations remain local migration references, not
production runtime components.

## API boundary

The browser calls same-origin `/api/*` URLs. A Pages Function forwards those
requests to the Python Worker, so the browser does not need cross-origin Worker
URLs or credentials.

The deployed Worker contract is:

- `POST /api/register` with `{email, preferences_blob}` returns a generic `202`
  and sends a verification link for a new inactive user;
- `POST /api/login` with `{email}` returns the same generic `202`, sending a
  link only for an active user;
- the link targets `APP_BASE_URL/auth/verify?token=...`;
- the SPA posts the token to `POST /api/auth/verify`, which returns `200` with
  `{user}` plus the session cookie or `401` for an invalid/replayed/expired
  token; and
- `/api/me`, `/api/preferences`, and `/api/logout` retain their existing
  authenticated behavior; and
- authenticated `PATCH /api/subscription` accepts `{subscribed: boolean}`.

Pausing is the PoC's unsubscribe behavior: it excludes the address from digest
selection but preserves the verified account, session, and personalization
profile. Resuming restores delivery without repeating onboarding. Permanent
account/profile deletion is outside the PoC and must be designed separately.

## Privacy and LLM boundary

The scheduled Cloudflare Worker may send event details and the personalization profile to the
configured Gemini, Mistral, or OpenRouter model. It must not send the subscriber
email, session data, magic-link data, Cloudflare credentials, or SMTP
credentials. Provider calls fall back to deterministic ranking when unavailable.

## PoC acceptance criteria

- A new user can verify an email address and complete the full personalization
  profile through the SPA.
- D1 contains one canonical subscriber record and the saved profile can be
  restored and edited.
- An active D1 subscriber is included in a scheduled digest run without copying
  account records into source control.
- The ranker receives the stored profile shape and never receives identity or
  authentication data.
- A personalized HTML email is sent to the verified address.
- A paused subscriber is excluded from subsequent runs.
- Unit and integration tests use fake credentials and no live provider calls.

## Delivery checklist

- [x] Select Cloudflare Pages + Python Worker + D1 as the production web stack.
- [x] Deploy the Pages project, static dashboard, API proxy, Worker, and D1.
- [x] Implement and validate the React personalization onboarding SPA.
- [x] Deploy the React personalization onboarding SPA to production Pages.
- [x] Implement and test verified magic-link authentication.
- [x] Configure email delivery, migrate production D1, and deploy magic-link auth.
- [x] Verify the live profile round-trip and exact D1 personalization shape.
- [ ] Implement and deploy the Cron-triggered Cloudflare digest Worker.
- [x] Retire the GitHub Actions digest schedule during Cloudflare migration.
- [ ] Add pause/resume subscription controls.
- [ ] Record per-user send/relevance history after a digest succeeds.
- [ ] Remove or clearly deprecate the legacy FastAPI onboarding surface after
  production parity is verified.
