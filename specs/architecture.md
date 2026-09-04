# System Architecture and Data Flow

## PoC target

The PoC runs entirely on Cloudflare in production:

```text
Interactive web plane
=====================
Browser
  -> React/Vite SPA on Git-connected Cloudflare Pages [deployed]
  -> same-origin Pages Function (/api/*) [deployed]
  -> Python Cloudflare Worker [deployed]
  -> D1 [deployed]
       subscriber email
       personalization profile
       active/paused state
       session and verification records

Scheduled digest plane [upcoming]
=================================
Cloudflare Cron Trigger
  -> scheduled Cloudflare Worker
  -> fetch and normalize event sources
  -> D1 event and delivery history
  -> active D1 subscribers and their profiles
  -> per-subscriber OpenRouter ranking with deterministic fallback
  -> Mailgun HTTP API to the verified subscriber
```

The existing Python/Scrapy/SQLite command remains useful for local development
and as migration reference code. The GitHub Actions digest schedule is legacy
infrastructure and is not part of the target production platform. The
Cloudflare runtime plan must provide enough Cron CPU for parsing and
orchestration; network wait time does not consume CPU, but the Free plan's CPU
allowance is not a safe production assumption for this workload.

## Delivery state

### Deployed/available

- Cloudflare Pages project connected to GitHub (`main` production, branch
  previews available), currently serving the static dashboard.
- Python Worker service and D1 database.
- Pages Function that proxies browser `/api/*` requests to the Worker.
- D1-backed subscriber/profile and cookie-session operations.
- Gemini, Mistral, and OpenRouter ranking backends with deterministic fallback.
- A verified active production profile containing all six personalization keys.

### Implemented, pending production activation or final smoke

- A Cloudflare scheduled Worker, Cron Trigger, Worker-compatible event collectors,
  D1 event/delivery history, per-user ranking, and digest delivery.
- The React onboarding SPA, repository-root Pages Function, single-use magic-link
  Worker, D1 migration, branded verification email, and Mailgun delivery are live.

### Later hardening

- Pause/resume UX and complete account lifecycle.
- Per-user event recommendation/send history.
- Removal or explicit deprecation of the legacy FastAPI/SQLite onboarding path.
- Operational alerts, retention policy, and recovery exercises.

## Sources of truth

| Data | Canonical store/code | Notes |
| --- | --- | --- |
| Subscriber identity and verified email | D1 | Never source control or the cached SQLite user table |
| Personalization profile | D1 `users.preferences_blob` | JSON shape defined by `src/valencia_events/personalization.py`; UI mapping in `cloudflare/pages/src/profile.js` |
| Subscription state | D1 | Only active subscribers are exported to the digest job |
| Sessions and email verification | D1 | Private to the Worker; never exported to the batch job |
| Scraped events and deduplication state | D1 (upcoming schema) | SQLite remains local migration/reference state only |
| Recommendation and send history | D1 (upcoming schema) | Required for idempotent delivery and feedback |
| Ranking behavior and provider fallback | Scheduled Worker; Python implementation is the migration reference | OpenRouter/Nemotron by default, then deterministic fallback |
| PoC work status | `POC_TODO.md` | Update as implementation and validation finish |
| General backlog | `task.md` | Must agree with implementation/tests, not supersede them |

The legacy FastAPI onboarding and SQLite `users` tables may remain during the
transition, but they are not allowed to become a second production subscriber
source.

## Trust boundaries

1. The browser sends onboarding and account requests only to same-origin
   `/api/*` paths.
2. The Pages Function knows the Worker origin and forwards required request and
   response headers; it does not own subscriber data.
3. The Worker validates input, owns authentication, and is the only public
   writer to D1.
4. The scheduled Worker reads subscribers and events through direct D1 bindings;
   no browser or cross-cloud subscriber export is involved.
5. The ranking provider receives only event candidates and profile fields. It
   must not receive email addresses, cookies, session/verification records,
   SMTP credentials, or Cloudflare credentials.
6. Mailgun receives the rendered message and verified destination only after
   ranking succeeds or deterministic fallback completes.

## Failure behavior

- If the LLM is missing or fails, deterministic ranking keeps the digest path
  available.
- If D1 fails, the scheduled Worker fails closed and must not use a fallback
  recipient or stale subscriber export.
- A failure for one subscriber should be isolated and reported without exposing
  their full profile in logs.
- Pages/Worker rollback must not assume a D1 schema migration was reversed.

## Configuration ownership

- Interactive Cloudflare Worker: D1 `DB` binding; `SESSION_TTL_HOURS`; magic-link
  `APP_BASE_URL`, `MAILGUN_DOMAIN`, `MAILGUN_REGION`, `EMAIL_FROM`; optional
  `MAGIC_LINK_TTL_MINUTES`; and secret `MAILGUN_API_KEY`.
- Scheduled Cloudflare Worker: D1 binding, Cron Trigger, `LLM_BACKEND` defaulting
  to `openrouter`, `OPENROUTER_MODEL` defaulting to
  `nvidia/nemotron-3-ultra-550b-a55b:free`, and Worker secrets for OpenRouter and
  Mailgun.
- Pages Function: non-secret `API_BASE_URL` when the Worker is not same-origin.
- GitHub Actions has no production runtime ownership. The old scheduled digest
  workflow has been removed.

Cloudflare runtime and deployment configuration is documented in
`cloudflare/README.md`.
