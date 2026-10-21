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

See the [2026-10-21 status check](../specs/project-status-2026-10-21.md) for live
public endpoint results and the limits of verification without authenticated
Cloudflare access. The [later production release](../specs/jev-deployment-2026-10-21.md)
includes authenticated deployment, D1, and Cron checks. The deployed selector uses 12 fixed event types from
`shared/event-types.json`; `worker_preferences.py` enforces valid selections and
trusted definitions on registration/profile updates. Jev classification, scoring,
private D1 history, and the frontend decision breakdown are deployed after local
and CI verification against the [shared contract](../specs/jev-integration-plan.md).
The Jev D1 migration was applied before the Worker and matching Pages release.
`JEV_MODE=filter` is active with the encrypted TypeSafe secret configured.
Three live labeled fixtures and an authenticated Worker preview passed before
filtering was enabled. Digest delivery remains disabled.

| Capability | State |
| --- | --- |
| Git-connected Cloudflare Pages project | Deployed; `main` is production and other branches can receive previews |
| React personalization onboarding SPA and same-origin API proxy | Deployed from Git-connected `main` |
| Python Worker with D1 binding | Deployed |
| D1 event, digest-run, recommendation, and delivery state | Migrated and verified in production |
| Email-only register/login sessions | Superseded in production; retained only in older local tooling |
| Verified email magic links | Deployed with Mailgun and migrated D1; controlled delivery smoke passed |
| Cloudflare Cron digest Worker | Full safe pipeline implemented; deployed with delivery disabled pending controlled smoke |
| Bounded event types and Jev preview/scoring | Filtering enabled with migrated D1 and encrypted secret; live fixtures and authenticated preview passed |
| Shorter onboarding, planning shortlist, date choices, and saved plans | Deployed with D1 migrations and 545 passing automated tests; interactive browser check pending |
| Delivery-day controls, coverage history, and voluntary study feedback | Deployed; global delivery remains disabled |
| Stripe-hosted membership and customer portal | Prepared at EUR 3/month; billing disabled, external setup and payment lifecycle checks pending |

Do not infer that an in-progress capability is available merely because its
schema or partial endpoint exists.

The deployed React SPA, repository-root Pages Function proxy, magic-link Worker,
and Mailgun sandbox now share the production contract. A controlled registration
returned `202`, and Mailgun reported both `accepted` and `delivered`.

The pending [planning release](../specs/planning-experience-contract.md) leads
returning accounts to a shortlist for tomorrow, with dates through the coming
seven days in Europe/Madrid. It distinguishes empty results, rejected listings,
and source failures. Users can save a plan, copy its public details, or export a
calendar entry when the source's date is sufficiently precise. New onboarding
asks for an audience explicitly, offers optional refinements, and shows readable
preferences before saving. Collection currently covers València city through
the sources listed below; saved preferences for wider areas do not establish
coverage there.

New accounts in this release start with email digests paused. Users can verify
their email, sign in, and use planning tools before explicitly enabling digests
in account email preferences. Existing accounts retain their saved subscription
state and legacy defaults. The global delivery switch remains disabled.

Paid membership supports continued development. Planning tools remain available
during beta, without exclusive-feature, ticket, or coverage promises. Follow the
[membership launch guide](../specs/membership-launch.md) for the prepared EUR
3/month offer and the remaining Stripe setup and verification. Billing and
digest delivery remain separate, disabled switches.

## Request and data flow

```text
Browser
  -> Cloudflare Pages frontend
  -> same-origin /api/* Pages Function
  -> Python Worker
  -> D1 (subscriber, profile, session/auth state)

Cloudflare Cron Trigger [deployed; dry-run by default]
  -> lightweight scheduled Worker dispatcher
  -> Python `DigestCoordinator` Durable Object
  -> fetch and normalize events into D1
  -> load active subscriber profiles directly from D1
  -> rank with OpenRouter/Nemotron by default
  -> render and send through Mailgun's HTTP API
```

The React rework stores the structured profile documented in
[`../specs/user_management.md`](../specs/user_management.md). D1 is canonical
for subscribers and production event and delivery history. Cached
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

The deployed Jev implementation extends `POST /api/digest/dry-run` with
`{contract_version: "jev-preview-v1", summary, evaluations}`. It accepts no event
or profile data from the browser: the Worker loads the session user's saved
profile and collected events. Active accounts can preview while delivery is
paused. Evaluations include rejected events and their per-type contributions;
scheduled responses expose aggregate counts only. The UI rejects failed runs,
offers retry, and discards stale previews after profile edits or sign-out.

The pending planning release preserves that contract and adds `plans`, containing
the actual ranked shortlist, public event details, source-check status, and
service state. An optional `{date: "YYYY-MM-DD"}` body selects tomorrow through
seven days from today in Europe/Madrid; invalid dates fail before collection.
Omitting the date retains tomorrow behavior. A date, account, or saved-profile
change discards any earlier response.

These implemented routes await the matching D1 migrations and Worker release:

| Route | Purpose |
| --- | --- |
| `GET /api/planning` | Available dates, delivery state/days, saved plans, study consent, and public coverage history. |
| `PATCH /api/planning/delivery` | Explicitly save event-day choices and pause/resume state. |
| `POST` / `DELETE /api/planning/saved` | Save or remove a canonical event for the session account, up to 50 saved plans. |
| `PUT /api/planning/pilot` | Opt into the 30-day planning study or opt out and delete its feedback. |
| `POST /api/planning/feedback` | Submit voluntary result/action feedback with unexpired consent. |
| `GET /api/billing`; `POST /api/billing/checkout` / `portal` | Read membership state or open account-specific Stripe-hosted Checkout/customer portal. |
| `POST /api/billing/webhook` | Accept Stripe subscription snapshot events with a verified raw-body signature. |

Planning and billing account routes use the existing session. The webhook uses
Stripe's signature instead of a session cookie. Account IDs, Stripe customers,
Prices, and billing return URLs are selected by the Worker, never the browser.
Checkout validates cached session status and starts a fresh session after
cancellation. Webhook synchronization ignores unrelated products before claiming
an update and reads current customer subscriptions, so an older cancellation or
delayed response cannot overwrite a replacement membership. The
[contract](../specs/planning-experience-contract.md) records the revision guard
and matching billing-schema columns.

## Configuration

### Worker runtime

- `DB`: required D1 binding named `valencia-events`.
- `DIGEST_COORDINATOR`: SQLite-backed Durable Object binding. Cron and the
  authenticated preview route dispatch to the stable `daily-digest` instance so
  scraping/parsing does not run inside the Free-plan HTTP/Cron CPU boundary.
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
- `TYPESAFE_API_KEY`: Jev credential, configured only as a Worker secret with
  `wrangler secret put TYPESAFE_API_KEY --config worker/wrangler.toml` from this
  directory. Never place it in Pages variables or browser code.
- `JEV_MODEL`: pinned stable Jev version; defaults to `jev-1.13.0`. Aliases are
  rejected, and the response model must match the requested version.
- `JEV_MODE`: `off` skips Jev calls; `shadow` evaluates and stores decisions
  without excluding events; `filter` excludes evaluated scores strictly above
  `0.6`. Uncertain or unavailable decisions keep the usual ranking path. The
  checked-in Wrangler configuration selects `filter`. A missing or invalid
  runtime value falls back to `off`. OpenRouter still ranks the remaining
  candidates using the other saved preferences.
- `DIGEST_DELIVERY_ENABLED`: fail-closed production switch. Its checked-in value
  is `false`; set it to `true` only after the controlled end-to-end smoke.
- `BILLING_ENABLED`: separately gates new paid Checkout sessions; checked-in
  value and missing-variable fallback are `false`. Keep it disabled through
  Stripe setup and test-mode verification.
- `STRIPE_PRICE_ID`: non-secret reviewed Price ID for EUR 3 every month, in the
  same Stripe mode as the key. No placeholder Price is configured for deployment.
- `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET`: encrypted Worker secrets for
  Stripe requests and webhook signatures. Never expose either in Pages variables
  or browser code. `worker_billing.py` pins API version `2025-09-30.clover`; the
  [launch guide](../specs/membership-launch.md) covers endpoint version and setup.

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

For the PoC, the interactive API, daily scheduler, and Durable Object share the
existing Python Worker deployment, secrets, and D1 binding. The configured
`0 8 * * *` trigger runs at 08:00 UTC, which is 09:00 CET or 10:00 CEST in
València. The Cron handler only dispatches to the stable `daily-digest` Durable
Object; that object runs collection, ranking, rendering, and optional delivery.
The authenticated preview uses the same boundary and remains targeted and
delivery-disabled. D1 idempotency protects against overlapping/repeated
invocations. Move per-subscriber work to a Queue consumer only when fan-out or
execution limits justify another component. Current limits:
<https://developers.cloudflare.com/durable-objects/platform/limits/>.

### D1 batch-processing state

The forward-only schema keeps normalized `events`, one `digest_runs` row per
València digest date, per-user ranked `recommendations`, and one `deliveries`
state row per run/user pair. Event identity is the SHA-256 of normalized title,
start, and URL. A failed delivery can be claimed again after 5 then 15 minutes,
with a maximum of three attempts; a pending or sent row cannot be claimed twice.
Provider message IDs and sanitized failure codes are retained without
credentials or response bodies.

The scheduled cleanup policy is to retain digest, recommendation, and delivery
history for 90 days. With the planning migration, events unseen for 30 days may
be removed only after no retained recommendation, Jev evaluation, or saved plan
references them. `delete_expired_history()` performs
deletion in dependency order; the orchestrator must supply UTC ISO/date cutoffs
and report only aggregate row counts.

The planning release stores saved plans privately for the session account until
removed. Public source checks contain source names, counts, and timestamps; the
account screen exposes up to 40 checks from the past 14 days. Delivery-day
preferences describe the event day, with its digest scheduled the preceding
day, and do not affect manual previews.

The optional study requires explicit consent and separately submitted feedback;
opening a listing or using a plan action does not record feedback automatically.
A random study code is linked separately to the account. Consent expires after
30 days; cleanup removes expired study links and feedback, and opting out deletes
both immediately. Feedback stores only the date, result category, usefulness,
and chosen action category, without event names, email, or profile data. No
study feedback is sent to ranking providers or Stripe. Billing sends Stripe
only the account email and internal ID needed to associate its customer;
test/live billing state is separate and card details remain with Stripe.

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
must not send email, call an LLM, or contact Stripe. Offline billing tests mock
the Stripe transport. Live payment checks are a separate launch activity.

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

The Jev tables from `0001_jev_evaluations.sql` were created in production on
2026-10-21 before Wrangler migration tracking was adopted. Existing databases
require the planning and billing
migrations before this Worker, **even when billing and digest delivery are
disabled**, because account reads and cleanup use their tables. Use Wrangler's
migration tracking: it can safely adopt the idempotent `0001` and apply
`0002`–`0004` once, in order. Check the schema and pending migration list before
applying them. These three new migrations have not yet been applied to
production as part of this work.
For a fresh database, initialize `worker/src/schema.sql` instead of replaying
migrations over that schema.

```bash
cd cloudflare
npx wrangler d1 migrations list valencia-events --remote --config=worker/wrangler.toml
npx wrangler d1 migrations apply valencia-events --remote --config=worker/wrangler.toml
npx wrangler deploy --config=worker/wrangler.toml
```

The real D1 database ID is checked into `worker/wrangler.toml`; treat changes to
that binding as production infrastructure changes. Terraform may own the Pages,
D1, domain, and route resources, but it intentionally does not upload Worker
code. Deploy the updated Worker before Pages. Keep `BILLING_ENABLED=false`;
Stripe test setup, live configuration, and activation have their own
[launch checklist](../specs/membership-launch.md).

Deploying `worker/wrangler.toml` also updates the daily Cron Trigger. Cloudflare
Cron changes can take several minutes to propagate. Confirm the trigger and its
first structured `digest.schedule.triggered` log event after deployment. Leave
`DIGEST_DELIVERY_ENABLED=false` until a controlled authenticated preview and one
intended-recipient send have passed. The preview button in the signed-in account
screen exercises the safe path.

For a fresh installation, keep `JEV_MODE=off` for its first deployment. After
configuring the TypeSafe secret, use `shadow` for controlled previews and compare decisions with labeled
local events. Only then enable `filter`; production already completed these
checks, and delivery remains a separate switch.
Per-type cached answers contain public event evidence only. Private evaluations
retain selected types, probabilities, contributions, model/version provenance,
and decisions under the existing 90-day digest retention policy.

The magic-link implementation is already deployed with `APP_BASE_URL`,
`MAILGUN_DOMAIN`, `MAILGUN_REGION`, `EMAIL_FROM`, and the encrypted
`MAILGUN_API_KEY`. The additive `magic_links` migration is already
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
