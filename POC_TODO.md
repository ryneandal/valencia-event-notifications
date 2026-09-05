# València Events PoC Completion Checklist

This checklist is the durable execution record for the current PoC. When older
documentation conflicts with the current conversation, the decisions below are
authoritative until deliberately revised.

## Current architecture decisions

- [x] Use a React SPA on Cloudflare Pages for registration and onboarding.
- [x] Use the Mediterranean/València design direction from `cloudflare/design-poc/`.
- [x] Treat “Brisa” as a working product/guide name; it means “breeze” in Spanish.
- [x] The onboarding form must produce the profile shape consumed by
  `src/valencia_events/personalization.py`.
- [x] Use the Python Cloudflare Worker for interactive account/profile APIs.
- [x] Use Cloudflare D1 as the canonical production subscriber store.
- [x] Keep the complete production runtime on Cloudflare: use a Cron-triggered
  Worker for scraping, per-user LLM ranking, email rendering, and delivery.
- [x] Treat the existing GitHub Actions digest workflow as legacy infrastructure
  to retire, not part of the target platform.
- [x] Support Gemini, Mistral, and OpenRouter for LLM ranking; default to
  OpenRouter with `nvidia/nemotron-3-ultra-550b-a55b:free`, while environment
  values take precedence over `.env` values locally.

## Foundation completed

- [x] Confirm the Cloudflare Pages Git integration is active with `main` as the
  production branch and branch preview deployments enabled.
- [x] Create and initialize the `valencia-events` D1 database.
- [x] Deploy the Python Worker API with its D1 binding.
- [x] Add and deploy a Pages Function proxy for same-origin `/api/*` requests.
- [x] Verify registration, session lookup, preference update, and logout against
  the production Pages hostname; remove the disposable verification account.
- [x] Add OpenRouter provider support and configuration documentation.
- [x] Produce the approved Mediterranean onboarding design PoC.

## Track A — React onboarding SPA (owner: primary agent)

- [x] Replace generic demo fields with the authoritative personalization fields:
  `audience`, `location_scope`, `top_interest_clusters`,
  `strong_positive_signals`, `strong_negative_signals`, and
  `seasonal_anchors`.
- [x] Serialize the profile into `preferences_blob` without lossy renaming.
- [x] Support new registration, resuming an existing session, editing a saved
  profile, and an explicit completion state.
- [x] Support pausing/unsubscribing from the onboarding account UI. The live
  account screen preserves the profile and session and can resume delivery.
- [x] [RYN-122](https://linear.app/ryneandal/issue/RYN-122/harden-onboarding-validation-accessibility-and-mobile-behavior): add field-level validation, accessible keyboard/focus behavior, responsive
  layouts, reduced-motion support, and useful API error states.
  - [x] Repair the registered-account completion layout so its heading, status,
    actions, and notes stack vertically and remain centered while actions wrap.
  - [x] Separate registered-account actions into a two-column hierarchy: profile
    editing and safe preview first, then subscription state and sign-out; collapse
    to one action per row on small screens.
  - [x] Associate required-field errors with their controls, move focus after
    validation and step transitions, expose semantic progress, and support Enter
    submission through a real form.
  - [x] Verify 375 px and 320 px Chromium viewports have no document overflow;
    details are recorded in `cloudflare/pages/ACCESSIBILITY.md`.
- [x] Add deterministic frontend tests for profile construction and API payloads.
- [x] Build the React SPA for the existing Pages project.
- [x] Deploy the React SPA to the existing Pages project from the Git-connected
  `main` branch.
- [x] Verify the live SPA writes the expected profile JSON to D1. Production D1
  contains an active profile with all six authoritative personalization keys.

## Track B — Cloudflare-native digest runtime

- [x] Prove lossless mapping between D1 `preferences_blob` and the six-field
  Worker ranking profile through storage and orchestrator tests.
- [x] Route Cron and authenticated preview runs through a SQLite-backed Python
  Durable Object so collection/parsing uses the Durable Object execution budget;
  keep the Cron entrypoint as a small dispatcher and D1 as canonical storage.
- [x] Add a Cloudflare `scheduled()` handler and daily Cron Trigger.
- [x] Port event collection and normalization to Worker-compatible asynchronous
  fetch/parsing; Scrapy and cached SQLite remain local migration references only.
- [x] Add D1 event, recommendation, and delivery-history tables with idempotent
  writes and retention rules. The additive schema was applied to production D1
  and all four batch tables were verified on 2026-09-04.
- [x] Read active subscribers directly from the Worker's D1 binding, excluding
  both unverified and paused users without exporting account data.
- [x] Call OpenRouter from the scheduled Worker, defaulting to
  `nvidia/nemotron-3-ultra-550b-a55b:free`, request JSON-object output with
  response healing, retry transient/provider-validation failure once, and
  validate its JSON response before accepting a ranking.
- [x] Store `OPENROUTER_API_KEY` as an encrypted production Worker secret; only
  the secret name was verified and no value was logged.
- [x] Render digest email and implement bounded Mailgun HTTP delivery. Production
  digest sending remains disabled pending the controlled smoke.
- [x] Add an authenticated dry-run path and per-user failure isolation.
- [x] Disable and remove the GitHub Actions digest schedule so it cannot send
  during the Cloudflare migration.
- [x] Deploy and validate the Cron-triggered Worker. Current production version
  `a54c1988-3718-480f-8d23-8be0ca95461f` is healthy, has the encrypted OpenRouter
  secret, keeps delivery disabled, and is registered with `0 8 * * *` UTC as of
  2026-09-05.
- [x] Deploy the SQLite-backed `DigestCoordinator` Durable Object with the
  scheduled and authenticated-preview dispatch paths.
  - [x] Local runtime smoke (2026-09-05): Wrangler instantiated the Python object,
    dispatched the scheduled RPC, fetched both sources, matched four events for
    2026-09-06, completed with zero failures, and sent no email.
  - [x] Production deployment (2026-09-05): Cloudflare created the
    `DigestCoordinator` export, attached its binding, retained the daily Cron,
    and activated version `a54c1988-3718-480f-8d23-8be0ca95461f`; health is 200
    and delivery remains disabled.
- [ ] Confirm an authenticated production preview emits
  `digest.coordinator.started` before the normal run events.

## Track C — Verified magic-link authentication (owner: delegated agent)

- [x] Replace email-only impersonation with expiring, one-time magic-link tokens.
- [x] Store only token hashes; add expiry, consumption, and replay protection.
- [x] Keep new subscriptions inactive until email ownership is verified.
- [x] Add request/verify/logout flows and abuse controls suitable for the PoC.
- [x] Define the transactional email provider boundary and required secrets
  without exposing tokens to Pages/browser code.
- [x] Add deterministic tests for expiry, replay, invalid tokens, and activation.
- [x] Integrate the React SPA with request-link and verification states.
- [x] Apply the additive `magic_links` migration to production D1.
- [x] Select Mailgun as the transactional email provider and implement its
  authenticated HTTP API adapter.
- [x] Configure the Mailgun US sandbox domain, region, and sender in Wrangler.
- [x] Add and verify a Mailgun sandbox Authorized Recipient.
- [ ] Configure a verified custom Mailgun sending domain before accepting
  arbitrary public registrations; the sandbox can email only authorized recipients.
- [x] Store `MAILGUN_API_KEY` as an encrypted Worker secret.
- [x] Deploy the verified magic-link Worker with Mailgun configuration.
- [x] Deploy the compatible React SPA and repository-root Pages Function proxy
  from the Git-connected `main` production branch.
- [x] Format the verification email with the Brisa visual system, accessible
  fallback text, a prominent call to action, and a visible fallback URL.
- [x] Generate and install a placeholder Brisa logo for the SPA header,
  verification email, favicon, and Apple touch icon.

## Track D — Digest completion and controlled cutover

- [x] Scrape and normalize tomorrow’s events once per Cloudflare Cron run.
- [x] Load all active D1 subscribers and build each exact personalization profile.
- [x] Rank candidates per subscriber through OpenRouter or deterministic fallback.
- [x] Render ranked events and concise fit reasons into the Brisa HTML email.
- [x] Implement verified-subscriber delivery with per-user failure isolation; keep
  the production delivery switch off until the controlled smoke.
- [x] Record delivery/event history sufficiently to avoid duplicate sends.
- [x] Bound failed delivery retries to three attempts with 5- and 15-minute
  backoff windows and retain only sanitized failure codes.
- [x] Add a safe dry-run/manual Worker path that cannot accidentally email everyone.
- [ ] Run one controlled end-to-end test from onboarding through rendered email.

## Track E — Documentation, operations, and handoff

- [x] Rewrite stale user-management and Cloudflare documentation around the
  chosen Pages + Workers + D1 architecture.
- [x] Document local development, tests, migrations, deployment, rollback, and
  required secrets/variables.
- [x] Add a concise architecture/data-flow diagram and source-of-truth statement.
- [x] Reconcile `task.md`, README files, examples, and obsolete FastAPI/SQLite
  claims without deleting still-useful local tooling.
- [x] Remove the unused FastAPI onboarding surface, D1 HTTP subscriber export,
  local bearer-session code, and unpopulated `users_events` table.
- [x] [RYN-135](https://linear.app/ryneandal/issue/RYN-135/resolve-the-legacy-sala-russafa-scraper-and-validation-pipeline):
  retire the synthetic Sala Russafa placeholder and remove the duplicate Scrapy
  item-validation pipeline; `source_filters.py` now owns raw validation for local
  reference runs.
- [x] Ensure all implementation changes are committed and pushed so a future
  Git-triggered Pages deployment cannot overwrite the live manual deployment.
- [x] [RYN-131](https://linear.app/ryneandal/issue/RYN-131/align-terraform-with-the-deployed-pages-and-worker-configuration): align Terraform's Pages build and compatibility settings with the deployed architecture.
- [ ] Run Python tests, Ruff, frontend tests/build, Wrangler dry-run, live health,
  and end-to-end smoke checks; record final evidence here.
  - [x] Local verification (2026-09-05): 94 Python tests and 10 frontend tests
    pass; Ruff check/format, Vite production build, `git diff --check`, and the
    Wrangler Worker bundle dry-run pass (78.47 KiB upload, 18.26 KiB gzip).
  - [x] Dependency security review (2026-09-05): integrated Dependabot PRs
    #40–#47, applied #39's LangChain update to the current dependency graph,
    and superseded obsolete Starlette PR #37 because Starlette is no longer a
    project dependency. `pip-audit` and `pnpm audit` both report zero known
    vulnerabilities; frozen lock installs and the full local checks pass.
  - [x] Production health smoke (2026-09-04): React assets and the same-origin
    Pages Function proxy are live; registration returned `202`; Mailgun reported
    both `accepted` and `delivered` without exposing the recipient or token.
  - [x] Production D1 profile smoke (2026-09-04): one verified active subscriber
    has a stored profile containing the six authoritative personalization keys.
  - [x] Production Worker smoke (2026-09-05): version
    `a54c1988-3718-480f-8d23-8be0ca95461f` starts without external tzdata,
    exposes the `DigestCoordinator`, `/api/health` returns `200`, unauthenticated
    digest preview returns `401`, and Cron delivery remains disabled.
  - [x] Live source probe (2026-09-04): the City agenda parsed 75 records and the
    corrected active-range policy found two candidates for 2026-09-05; the
    ElPeriodic feed parsed 30 records and found zero. Short active ranges and a
    longer event's closing day are eligible, while generic year-long programme
    pages are excluded.
  - [x] Production persistence trace (2026-09-04): D1 contained both matched City
    events with their truthful original start timestamps. The digest now reloads
    the collector-selected batch by stable event keys, preventing active ranges
    from being discarded by a second start-date filter.
  - [x] Authenticated production preview (2026-09-04): the registered user
    confirmed the safe preview found two events for 2026-09-05 and sent no email,
    proving the collection, D1 handoff, targeting, ranking, and rendering path.
    D1 showed that run used deterministic fallback. OpenRouter hardening was
    deployed on 2026-09-05 and awaits one authenticated preview confirmation
    showing the named Nemotron model instead of fallback.

## Post-PoC

- [ ] [RYN-130](https://linear.app/ryneandal/issue/RYN-130/generate-dynamic-related-onboarding-tags-with-an-llm): generate related
  onboarding tags through a privacy-bounded Worker/LLM endpoint and show them as
  optional accessible chips. Debounce/cache requests, validate and deduplicate
  suggestions, preserve deterministic fallbacks, and keep the six-field profile
  contract unchanged.

## Final acceptance

- [ ] A new user can verify their email, complete the personalization UI, and see
  a clear subscription confirmation.
- [ ] The exact profile is persisted in D1 and can be edited or paused.
- [ ] The scheduled Cloudflare Worker reads that subscriber, finds tomorrow’s
  events, obtains a validated LLM-ranked selection, renders it, and sends the
  intended email.
- [ ] No browser bundle, repository file, log, or test fixture contains a secret.
- [ ] The production Pages and Workers deployments are reproducible from the
  committed repository and documented configuration.
