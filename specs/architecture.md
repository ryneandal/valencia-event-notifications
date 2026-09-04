# System Architecture and Data Flow

## PoC target

The PoC has two execution planes joined through a narrow subscriber interface:

```text
Interactive web plane
=====================
Browser
  -> React/Vite SPA on Git-connected Cloudflare Pages [implemented; deploy pending]
  -> same-origin Pages Function (/api/*) [deployed]
  -> Python Cloudflare Worker [deployed]
  -> D1 [deployed]
       subscriber email
       personalization profile
       active/paused state
       session and verification records

Scheduled digest plane
======================
GitHub Actions schedule/manual dispatch
  -> authenticated active-subscriber query through Cloudflare D1 HTTP API
       [implemented; production activation pending]
  -> Scrapy sources
  -> normalize and deduplicate events in cached SQLite
  -> per-subscriber ranking
       Gemini | Mistral | OpenRouter | deterministic fallback
  -> Jinja2 HTML email
  -> SMTP to the verified subscriber
```

Cloudflare serves interactive, low-latency account operations. GitHub Actions
runs the batch workload so the existing Python scraping, ranking, and email
pipeline remains reusable.

## Delivery state

### Deployed/available

- Cloudflare Pages project connected to GitHub (`main` production, branch
  previews available), currently serving the static dashboard.
- Python Worker service and D1 database.
- Pages Function that proxies browser `/api/*` requests to the Worker.
- D1-backed subscriber/profile and cookie-session operations.
- Scheduled Python scraping, normalization, ranking, email rendering, and SMTP
  delivery.
- Gemini, Mistral, and OpenRouter ranking backends with deterministic fallback.

### Implemented, pending production deployment

- React multi-step onboarding UI that captures the complete personalization
  profile and replaces the static dashboard. Its build and frontend contract
  tests pass.
- Direct D1 HTTP subscriber loader for the scheduled job. Its tests pass; GitHub
  credentials/IDs and a successful production run are still pending.
- Single-use magic-link Worker authentication. Its tests and Wrangler dry-run
  pass and the additive D1 migration is applied; email-provider configuration
  and production deployment are still pending.

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
| Scraped events and deduplication state | Cached `events.db` in GitHub Actions | Batch-processing state, not the subscriber directory |
| Ranking behavior and provider fallback | `src/valencia_events/personalization.py` | Gemini, Mistral, OpenRouter, then deterministic fallback |
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
4. The scheduled job uses a least-privilege Cloudflare API token to query active
   users directly through the D1 HTTP API. It reads only the subscriber fields
   mapped by the Python `User` model and fails closed instead of using a fallback
   recipient when D1 is unavailable or empty.
5. The ranking provider receives only event candidates and profile fields. It
   must not receive email addresses, cookies, session/verification records,
   SMTP credentials, or Cloudflare credentials.
6. SMTP receives the rendered message and verified destination only after
   ranking succeeds or deterministic fallback completes.

## Failure behavior

- If the LLM is missing or fails, deterministic ranking keeps the digest path
  available.
- If the subscriber loader fails, the job fails closed for D1 recipients;
  it must not silently use stale or unverified account data.
- A failure for one subscriber should be isolated and reported without exposing
  their full profile in logs.
- Pages/Worker rollback must not assume a D1 schema migration was reversed.

## Configuration ownership

- Cloudflare Worker: D1 `DB` binding; `SESSION_TTL_HOURS`; magic-link
  `APP_BASE_URL`, `MAILGUN_DOMAIN`, `MAILGUN_REGION`, `EMAIL_FROM`; optional
  `MAGIC_LINK_TTL_MINUTES`; and secret `MAILGUN_API_KEY`.
- Pages Function: non-secret `API_BASE_URL` when the Worker is not same-origin.
- GitHub Actions secrets: SMTP credentials, optional local-mode recipient
  fallback, selected LLM API key, and least-privilege `CLOUDFLARE_API_TOKEN`.
- GitHub Actions variables: `CLOUDFLARE_ACCOUNT_ID`,
  `CLOUDFLARE_D1_DATABASE_ID`, `LLM_BACKEND`, provider model/fallback model, and
  optional OpenRouter attribution values. Production sets
  `SUBSCRIBER_BACKEND=d1`; local/test runs may explicitly use `sqlite`.

Exact batch-workflow names are in `.env.example` and
`.github/workflows/nightly_digest.yml`. Cloudflare runtime and deployment
configuration is documented in `cloudflare/README.md`.
