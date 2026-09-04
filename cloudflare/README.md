# Cloudflare Onboarding Application

This directory contains the production web stack for subscriber registration
and personalization:

- `pages/src/`: React/Vite single-page application source.
- `pages/public/`: static assets and Vite build output deployed by Cloudflare
  Pages.
- `pages/functions/api/[[path]].js`: same-origin `/api/*` proxy to the Worker.
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
| Static Pages dashboard and same-origin API proxy | Deployed |
| Python Worker with D1 binding | Deployed |
| React personalization onboarding SPA | Implemented and passing frontend contract tests; production deploy pending |
| Email-only register/login sessions | Implemented for development, but not safe for public authentication |
| Verified email magic links | Worker deployed with Mailgun and migrated D1; compatible React Pages deploy pending |
| Scheduled job reads active D1 subscribers | Implemented and tested; production configuration/run pending |

Do not infer that an in-progress capability is available merely because its
schema or partial endpoint exists.

The currently deployed magic-link Worker requires the React SPA contract. Until
the Git-connected `main` branch or a credentialed direct Pages deployment ships
the React build, the older static Pages dashboard is not a usable registration
client.

## Request and data flow

```text
Browser
  -> Cloudflare Pages frontend
  -> same-origin /api/* Pages Function
  -> Python Worker
  -> D1 (subscriber, profile, session/auth state)

Scheduled GitHub Actions job
  -> authenticated Cloudflare D1 HTTP query API (implemented; activation pending)
  -> scrape and normalize events into cached SQLite
  -> rank each subscriber's events via Gemini, Mistral, or OpenRouter
  -> render and send HTML email through SMTP
```

The React rework stores the structured profile documented in
[`../specs/user_management.md`](../specs/user_management.md). D1 is canonical
for subscribers; cached SQLite remains the scheduled job's event/deduplication
store. See [`../specs/architecture.md`](../specs/architecture.md) for the full
source-of-truth boundaries.

## API surface

Currently deployed Worker routes:

- `GET /api/health`
- `POST /api/register`
- `POST /api/login`
- `POST /api/logout`
- `GET /api/me`
- `PATCH /api/preferences`

Authenticated routes use an `HttpOnly` session cookie. The register/login routes
currently trust possession of an email string and are development-only.

The locally implemented and tested replacement contract is:

- `POST /api/register` with `{email, preferences_blob}` returns a generic `202`
  and sends a link for a new inactive user;
- `POST /api/login` with `{email}` returns the same generic `202` and sends a
  link only for an active user;
- the link is `APP_BASE_URL/auth/verify?token=...`;
- `POST /api/auth/verify` accepts the token and returns `200` with `{user}` and
  the session cookie; invalid, expired, or replayed tokens return `401`; and
- `/api/me`, `/api/preferences`, and `/api/logout` retain their existing
  authenticated behavior.

The Worker auth code and Wrangler dry-run pass, and the additive D1 migration is
applied. This contract is not live until email provider configuration and Worker
deployment are completed. Subscription pause/resume remains planned.

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

The separate scheduled digest workflow requires SMTP secrets and one optional
LLM provider API key. Provider/backend/model configuration is documented in the
root [`README.md`](../README.md) and `.env.example`.

For its direct, read-only D1 subscriber source, the scheduled workflow uses:

- `SUBSCRIBER_BACKEND=d1` (explicit backend selection);
- `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_D1_DATABASE_ID` as GitHub repository
  variables; and
- a least-privilege `CLOUDFLARE_API_TOKEN` as a GitHub repository secret.

`SUBSCRIBER_BACKEND=sqlite` remains available only for explicit local/test use
and is the only mode in which `RECIPIENT_EMAIL` may be used as a fallback.

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
uv run pytest tests/test_cloudflare_worker.py
```

For a local Worker/D1 session, install or invoke Wrangler, apply the schema to
the local D1 database, and start the Worker:

```bash
cd cloudflare
npx wrangler d1 execute valencia-events --local \
  --file=worker/src/schema.sql --config=worker/wrangler.toml
npx wrangler dev --config=worker/wrangler.toml
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

Before deploying the magic-link implementation, configure `APP_BASE_URL`,
`MAILGUN_DOMAIN`, `MAILGUN_REGION`, and `EMAIL_FROM`, then store
`MAILGUN_API_KEY` as a Worker secret. The additive `magic_links` migration shown
above is already applied in production.
Deploying the Worker without a real delivery provider does not produce a usable
public sign-in flow.

## Rollback

- **Pages:** select and roll back to a known-good deployment in the Cloudflare
  Pages dashboard, or revert the responsible commit on `main`.
- **Worker:** use Wrangler/Cloudflare deployment history to roll back to the
  preceding Worker version.
- **D1:** schema changes should be backward-compatible and forward-only. Take an
  export/backup before destructive migration; rolling back Worker code does not
  reverse a D1 migration.

After any rollback, verify `/api/health`, the Pages proxy, authentication/session
handling, profile round-tripping, and that the scheduled subscriber loader still
matches the deployed D1 schema.
