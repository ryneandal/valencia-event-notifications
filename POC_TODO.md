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
- [x] Keep scraping, per-user LLM ranking, email rendering, and delivery in the
  scheduled Python/GitHub Actions job for this PoC.
- [x] Support Gemini, Mistral, and OpenRouter for LLM ranking; environment values
  take precedence over `.env` values locally.

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
- [ ] Support pausing/unsubscribing from the onboarding account UI.
- [ ] Add field-level validation, accessible keyboard/focus behavior, responsive
  layouts, reduced-motion support, and useful API error states.
- [x] Add deterministic frontend tests for profile construction and API payloads.
- [x] Build the React SPA for the existing Pages project.
- [ ] Deploy the React SPA to the existing Pages project.
- [ ] Verify the live SPA writes the expected profile JSON to D1.

## Track B — Production subscriber bridge (owner: delegated agent)

- [x] Make the nightly Python process load active production subscribers from D1
  through a narrowly scoped, authenticated interface.
- [x] Preserve SQLite as an explicit local/test fallback, not a competing
  production source of truth.
- [x] Map D1 `preferences_blob` losslessly to the Python `User.preferences` field.
- [x] Configure the nightly workflow to consume non-secret D1 identifiers and a
  least-privilege secret token.
- [x] Test pagination, empty subscriber sets, invalid responses, timeouts, and
  fallback behavior without network calls.
- [ ] Set the production repository variables `CLOUDFLARE_ACCOUNT_ID` and
  `CLOUDFLARE_D1_DATABASE_ID`, plus a least-privilege `CLOUDFLARE_API_TOKEN`
  secret.

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
- [x] Store `MAILGUN_API_KEY` as an encrypted Worker secret.
- [x] Deploy the verified magic-link Worker with Mailgun configuration.
- [ ] Deploy the compatible React SPA. The direct Pages upload needs an explicit
  Cloudflare API token, or the current changes must be committed and pushed to
  the Git-connected `main` production branch.

## Track D — Digest completion

- [ ] Scrape and normalize tomorrow’s events once per scheduled run.
- [ ] Load all active D1 subscribers and build each exact personalization profile.
- [ ] Rank candidates per subscriber through the configured LLM backend.
- [ ] Render ranked events and concise fit reasons into the existing HTML email.
- [ ] Send to each verified active subscriber and isolate per-user failures.
- [ ] Record delivery/event history sufficiently to avoid duplicate sends.
- [ ] Add a safe dry-run/manual workflow that cannot accidentally email everyone.
- [ ] Run one controlled end-to-end test from onboarding through rendered email.

## Track E — Documentation, operations, and handoff

- [x] Rewrite stale user-management and Cloudflare documentation around the
  chosen Pages + Worker + D1 + GitHub Actions architecture.
- [x] Document local development, tests, migrations, deployment, rollback, and
  required secrets/variables.
- [x] Add a concise architecture/data-flow diagram and source-of-truth statement.
- [x] Reconcile `task.md`, README files, examples, and obsolete FastAPI/SQLite
  claims without deleting still-useful local tooling.
- [ ] Ensure all implementation changes are committed and pushed so a future
  Git-triggered Pages deployment cannot overwrite the live manual deployment.
- [ ] Run Python tests, Ruff, frontend tests/build, Wrangler dry-run, live health,
  and end-to-end smoke checks; record final evidence here.
  - [x] Local verification (2026-09-04): 82 Python tests and 7 frontend tests
    pass; Ruff check/format, Vite production build, `git diff --check`, and the
    Wrangler Worker bundle dry-run pass (21.00 KiB upload, 4.82 KiB gzip).
  - [ ] Repeat health and end-to-end smoke checks after the React SPA and
    magic-link Worker are deployed together.

## Final acceptance

- [ ] A new user can verify their email, complete the personalization UI, and see
  a clear subscription confirmation.
- [ ] The exact profile is persisted in D1 and can be edited or paused.
- [ ] The scheduled job reads that subscriber, finds tomorrow’s events, obtains a
  structured LLM-ranked selection, renders it, and sends the intended email.
- [ ] No browser bundle, repository file, log, or test fixture contains a secret.
- [ ] The production Pages and Worker deployments are reproducible from the
  committed repository and documented configuration.
