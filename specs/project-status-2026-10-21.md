# Project status checked on 2026-10-21

This records the initial pre-deployment check. The subsequent
[production release](jev-deployment-2026-10-21.md) applied the Jev migration,
deployed Worker and Pages, and completed authenticated deployment/D1/Cron checks.
TypeSafe provider activation and digest delivery remain pending.

The public Cloudflare Pages frontend and Python Worker API are running. These
checks do not prove that scheduled digests collect, rank, and deliver
successfully. Checked-in configuration keeps digest delivery disabled.

| Check | Observed result |
| --- | --- |
| [Pages frontend](https://valencia-event-notifications.pages.dev/) | HTTP 200; Brisa HTML and JavaScript entry point; Cloudflare response headers |
| [Pages API proxy health](https://valencia-event-notifications.pages.dev/api/health) | HTTP 200, `{"ok": true}` |
| [Direct Worker health](https://valencia-events-api.ryne.workers.dev/api/health) | HTTP 200, `{"ok": true}` |
| Unauthenticated `/api/me` on both origins | HTTP 401, `{"error": "Unauthorized"}` |
| Repository base and remote `main` | Both point to `bea8f1f65f67f4a1d8c6e11e3bcffaa0210349bd`, dated 2026-09-05; initial working tree clean |
| CI for that `main` commit | [Passed](https://github.com/ryneandal/valencia-event-notifications/actions/runs/33980642984) |
| Most recent returned CI run, on another commit | [Passed on 2026-10-21](https://github.com/ryneandal/valencia-event-notifications/actions/runs/39556724085); not evidence of a new production deployment |

The health handler returns a static response. It establishes that routing and
Worker execution work; it does not query D1 or call a model or email provider.
These checks created no accounts, sent no email, and changed no production state.

## Runtime and outstanding production checks

The implemented platform comprises React/Vite on Pages, a same-origin API proxy,
a Python Worker with D1, email magic-link sessions, subscription controls, and
a digest pipeline dispatched through a Durable Object. It collects events, calls
OpenRouter with deterministic fallback, renders digests, and stores history.
The local Python/Scrapy pipeline is reference tooling.

`cloudflare/worker/wrangler.toml` specifies daily Cron `0 8 * * *` (08:00 UTC,
10:00 in València on this check date), D1 and Durable Object bindings, and
`DIGEST_DELIVERY_ENABLED="false"`. Mailgun configuration still uses a sandbox
domain. Existing documentation requires an authenticated provider preview and
a controlled delivery smoke before delivery cutover.

Wrangler's read-only deployment query failed because this session has no
authenticated Cloudflare account/API token. The deployed version, live
environment values/secrets, current Cron configuration, recent invocations,
D1 state, and provider/email delivery therefore remain unverified in this check.

With authenticated Cloudflare access, inspect the Worker deployment and Cron,
query aggregate recent `digest_runs`/`deliveries` status, and run the existing
authenticated dry-run for a controlled subscriber. Confirm `sent_count=0` and
inspect provider/fallback counts before considering delivery cutover.

## Changes prepared locally

The interest step now offers 12 bounded checkbox choices, including music,
performing arts, exhibitions, cinema, food, sport, and guided walks alongside
the five existing groups. It preserves saved IDs and the six-field profile.
The Worker validates selections before writing to D1 or sending a sign-in link,
and replaces client definitions with trusted catalog definitions.

The [Jev plan](jev-integration-plan.md) and [API research](jev-api-research.md)
provide a shared response schema, examples, confidence-aware additive scoring,
and separate frontend/backend agent assignments. Both agents have completed
transport, scoring, cache/history, and response-driven UI; integration review
and offline browser verification are complete.

Local validation passed: 247 Python tests and 101 frontend tests. The
[verification record](jev-verification-2026-10-21.md) records build, schema,
bundle, lint, and browser checks. The local Python environment is 3.12.9; CI
targets Python 3.11. No project dependency changes were needed. The new
`0001_jev_evaluations.sql` migration must be applied before deployment, even with
Jev off. The frontend and Worker changes have not been deployed; the public
checks exercised the existing deployment.
