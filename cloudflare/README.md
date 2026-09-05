# Cloudflare Onboarding Application

This directory contains the production web stack for subscriber registration
and personalization:

- `pages/src/`: React/Vite single-page application source.
- `pages/public/`: static assets and Vite build output deployed by Cloudflare
  Pages.
- `../functions/api/[[path]].js`: same-origin `/api/*` proxy to the Worker. It
  lives at the repository root because the Pages Git integration uses `/` as
  its root directory.
- `worker/src/`: Python Cloudflare Worker API.
- `worker/src/schema.sql`: D1 schema.
- `terraform/`: optional Cloudflare resource configuration. Worker code remains
  deployed with Wrangler rather than Terraform.
- `tests/`: browser-side and proxy integration tests.

The approved visual exploration lives in `design-poc/`; it is a design reference,
not a separately deployed application.

## Current versus upcoming behavior

| Capability | State |
| --- | --- |
| Git-connected Cloudflare Pages project | Deployed; `main` is production and other branches can receive previews |
| React personalization onboarding SPA and same-origin API proxy | Deployed from Git-connected `main` |
| Python Worker with D1 binding | Deployed |
| D1 event, digest-run, recommendation, and delivery state | Migrated and verified in production |
| Email-only register/login sessions | Superseded in production; retained only in older local tooling |
| Verified email magic links | Deployed with Mailgun and migrated D1; controlled delivery smoke passed |
| Cloudflare Cron digest Worker | Full safe pipeline implemented; deployed with delivery disabled pending controlled smoke |

Do not infer that an in-progress capability is available merely because its
schema or partial endpoint exists.

The deployed React SPA, repository-root Pages Function proxy, magic-link Worker,
and Mailgun sandbox now share the production contract. A controlled registration
returned `202`, and Mailgun reported both `accepted` and `delivered`.

## Request and data flow

```text
Browser
  -> Cloudflare Pages frontend
  -> same-origin /api/* Pages Function
  -> Python Worker
  -> D1 (subscriber, profile, session/auth state)

Cloudflare Cron Trigger [deployed; dry-run by default]
  -> scheduled Worker
  -> fetch and normalize events into D1
  -> load active subscriber profiles directly from D1
  -> rank with OpenRouter/Nemotron by default
  -> render and send through Mailgun's HTTP API
```

The React rework stores the structured profile documented in
[`../specs/user_management.md`](../specs/user_management.md). D1 is canonical
for subscribers and will also own production event and delivery history. Cached
SQLite remains local migration/reference state only. See
[`../specs/architecture.md`](../specs/architecture.md) for the full
source-of-truth boundaries.

## API surface

Currently deployed Worker routes:

- `GET /api/health`
- `POST /api/register`
- `POST /api/login`
- `POST /api/auth/verify`
- `POST /api/logout`
- `GET /api/me`
- `PATCH /api/preferences`
- `PATCH /api/subscription`
- `POST /api/digest/dry-run`

Authenticated routes use an `HttpOnly` session cookie. The deployed contract is:

- `POST /api/register` with `{email, preferences_blob}` returns a generic `202`
  and sends a link for a new inactive user;
- `POST /api/login` with `{email}` returns the same generic `202` and sends a
  link only for an active user;
- the link is `APP_BASE_URL/auth/verify?token=...`;
- `POST /api/auth/verify` accepts the token and returns `200` with `{user}` and
  the session cookie; invalid, expired, or replayed tokens return `401`; and
- `/api/me`, `/api/preferences`, `/api/subscription`, and `/api/logout` retain
  their authenticated behavior. `PATCH /api/subscription` accepts
  `{subscribed: boolean}` and preserves the account, session, and profile; and
- `POST /api/digest/dry-run` targets the current session user, returns aggregate
  counts plus a correlation ID, and is structurally unable to call Mailgun.

The Worker auth code, additive D1 migration, email provider configuration, and
deployment are live.

## Configuration

### Worker runtime

- `DB`: required D1 binding named `valencia-events`.
- `SESSION_TTL_HOURS`: non-secret session lifetime; defaults to `24` in the
  checked-in Wrangler configuration.
- `APP_BASE_URL`: public Pages origin used to construct
  `/auth/verify?token=...` links.
- `MAILGUN_DOMAIN`: Mailgun sending domain. The PoC currently uses the account's
  US sandbox domain.
- `MAILGUN_REGION`: `us` or `eu`; selects Mailgun's regional API hostname.
- `EMAIL_FROM`: sender address used for magic-link messages.
- `MAGIC_LINK_TTL_MINUTES`: optional token lifetime; defaults to `15`.
- `MAILGUN_API_KEY`: required Mailgun domain sending key or private API key,
  configured with `wrangler secret put` rather than `[vars]`.
- `OPENROUTER_MODEL`: optional model override; defaults to
  `nvidia/nemotron-3-ultra-550b-a55b:free`.
- `OPENROUTER_API_KEY`: OpenRouter credential, configured only as a Worker secret.
- `DIGEST_DELIVERY_ENABLED`: fail-closed production switch. Its checked-in value
  is `false`; set it to `true` only after the controlled end-to-end smoke.

Mailgun sandbox domains can deliver only to verified Authorized Recipients. Add
and verify the PoC test address in Mailgun before the production smoke test.

### Pages runtime

- `API_BASE_URL`: Worker origin used only by the Pages Function proxy. Leave it
  empty when routing is configured at the same origin; otherwise set the Worker
  or Worker custom-domain origin. It is not a browser secret.

### Deployment credentials

Interactive local deployments may use `wrangler login`. CI/Terraform should use
a narrowly scoped `CLOUDFLARE_API_TOKEN` and the appropriate Cloudflare account
and zone IDs. Never commit `terraform.tfvars`, `.dev.vars`, or real tokens.

The scheduled Worker uses a Cron Trigger and direct D1 binding. Store
`OPENROUTER_API_KEY` and the Mailgun credential as Worker secrets. Its default
provider/model are OpenRouter and
`nvidia/nemotron-3-ultra-550b-a55b:free`. Provider/backend/model configuration
for the local migration reference is documented in the root
[`README.md`](../README.md) and `.env.example`.

The Worker requests non-streaming `json_object` output and enables OpenRouter's
`response-healing` plugin. Provider or validation failures receive one bounded
retry, except authentication, client, routing, and rate-limit errors. A final
failure uses deterministic ranking and reports only aggregate sanitized reason
codes; provider bodies and profile values are never logged. Do not set
`provider.require_parameters` for the default free Nemotron route: it does not
advertise structured-output support and becomes unroutable when that constraint
is required.

For the PoC, the interactive API and daily scheduler share the existing Python
Worker and D1 binding. This keeps deployment and secrets in one place while the
subscriber count is small. The configured `0 8 * * *` trigger runs at 08:00 UTC,
which is 09:00 CET or 10:00 CEST in València. Move per-subscriber work to a Queue
consumer only when fan-out or execution limits justify the additional component.
Free Workers allow only 10 ms of CPU for both HTTP and Cron invocations. An HTTP
request may remain open while awaiting network I/O, but that unlimited wall time
does not increase its CPU allowance; Cron invocations instead have a 15-minute
wall-time ceiling. Confirm Workers Paid before relying on Python parsing in the
daily schedule. Current limits: <https://developers.cloudflare.com/workers/platform/limits/>.

### D1 batch-processing state

The forward-only schema keeps normalized `events`, one `digest_runs` row per
València digest date, per-user ranked `recommendations`, and one `deliveries`
state row per run/user pair. Event identity is the SHA-256 of normalized title,
start, and URL. A failed delivery can be claimed again after 5 then 15 minutes,
with a maximum of three attempts; a pending or sent row cannot be claimed twice.
Provider message IDs and sanitized failure codes are retained without
credentials or response bodies.

The scheduled cleanup policy is to retain digest, recommendation, and delivery
history for 90 days. Events unseen for 30 days may be removed only after no
retained recommendation references them. `delete_expired_history()` performs
deletion in dependency order; the orchestrator must supply UTC ISO/date cutoffs
and report only aggregate row counts.

### Event sources

Production collection currently reads the Ajuntament de València embedded
agenda and the ElPeriodic València RSS feed. Each request identifies Brisa,
times out after 10 seconds, and runs once per digest date. Adapters are
fixture-tested without network calls, one source failure does not discard other
results, and diagnostics record only source names, counts, and sanitized error
codes. City events are eligible on their start date, throughout active ranges up
to 14 days, or on the closing day of a longer run; this retains useful festivals
and final-chance exhibitions without repeating generic year-long programme pages
every day. After persistence, the orchestrator reloads the exact collector batch
by stable event keys rather than filtering on the events' original start dates;
ongoing events therefore retain accurate source dates without disappearing from
the digest. Operators must continue to honor each publisher's robots policy and
avoid raising the daily request frequency without review.

## Local development

Install and run the SPA from the repository root:

```bash
pnpm --dir cloudflare install --frozen-lockfile
pnpm --dir cloudflare dev
```

Build and test it:

```bash
pnpm --dir cloudflare build
pnpm --dir cloudflare test
uv run pytest tests/test_cloudflare_worker.py tests/test_worker_*.py
```

For a local Worker/D1 session, install or invoke Wrangler, apply the schema to
the local D1 database, and start the Worker:

```bash
cd cloudflare
npx wrangler d1 execute valencia-events --local \
  --file=worker/src/schema.sql --config=worker/wrangler.toml
npx wrangler dev --test-scheduled --config=worker/wrangler.toml
# In another terminal, invoke the local scheduled handler:
curl "http://localhost:8787/cdn-cgi/handler/scheduled?format=json"
```

Configure the Pages Function to proxy to the local Worker when exercising the
complete browser flow. Use fake delivery/provider credentials in tests; tests
must not send email or call an LLM.

## Deployment

### Pages

The Cloudflare Pages project is connected to GitHub. The intended build settings
are:

- production branch: `main`;
- build command: `pnpm --dir cloudflare install --frozen-lockfile && pnpm --dir cloudflare build`;
- output directory: `cloudflare/pages/public`.

A push to `main` creates a production deployment. Pull-request or feature-branch
pushes can create preview deployments and should be used for acceptance testing
before merge.

### Worker and D1

Apply additive schema changes before deploying Worker code that requires them:

```bash
cd cloudflare
npx wrangler d1 execute valencia-events --remote \
  --file=worker/src/schema.sql --config=worker/wrangler.toml
npx wrangler deploy --config=worker/wrangler.toml
```

The real D1 database ID is checked into `worker/wrangler.toml`; treat changes to
that binding as production infrastructure changes. Terraform may own the Pages,
D1, domain, and route resources, but it intentionally does not upload Worker
code.

Deploying `worker/wrangler.toml` also updates the daily Cron Trigger. Cloudflare
Cron changes can take several minutes to propagate. Confirm the trigger and its
first structured `digest.schedule.triggered` log event after deployment. Leave
`DIGEST_DELIVERY_ENABLED=false` until a controlled authenticated preview and one
intended-recipient send have passed. The preview button in the signed-in account
screen exercises the safe path.

The magic-link implementation is already deployed with `APP_BASE_URL`,
`MAILGUN_DOMAIN`, `MAILGUN_REGION`, `EMAIL_FROM`, and the encrypted
`MAILGUN_API_KEY`. The additive `magic_links` migration shown above is already
applied in production. Public registration beyond authorized Mailgun sandbox
recipients still requires a verified custom sending domain.

## Rollback

- **Pages:** select and roll back to a known-good deployment in the Cloudflare
  Pages dashboard, or revert the responsible commit on `main`.
- **Worker:** use Wrangler/Cloudflare deployment history to roll back to the
  preceding Worker version.
- **D1:** schema changes should be backward-compatible and forward-only. Take an
  export/backup before destructive migration; rolling back Worker code does not
  reverse a D1 migration.

After any rollback, verify `/api/health`, the Pages proxy,
authentication/session handling, profile round-tripping, and that the scheduled
Worker still matches the deployed D1 schema.
