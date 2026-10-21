# Jev code release — 2026-10-21

The bounded selector, Worker validation, Jev integration, and preview UI are
deployed at [Brisa](https://valencia-event-notifications.pages.dev/). Jev is off
pending its API secret and provider validation. Digest sending remains disabled.

## Release evidence

| Item | Result |
| --- | --- |
| Source release | [PR #55](https://github.com/ryneandal/valencia-event-notifications/pull/55), merged as `6579153a26f21f77a0a6f960d83605d511540054` |
| PR CI | [Passed](https://github.com/ryneandal/valencia-event-notifications/actions/runs/39592472631): 247 Python tests on 3.11.17, 101 frontend tests, lint/format, Worker bundle |
| Production CI | [Passed](https://github.com/ryneandal/valencia-event-notifications/actions/runs/39593878560) |
| D1 migration | `0001_jev_evaluations.sql`: five queries succeeded; both Jev tables and all three indexes verified afterward |
| Worker release | `7bc0e38e-c01e-4e90-a69a-b3b4f4b307aa`, deployed at 100% on 2026-10-21 at 11:41 UTC |
| Previous Worker | `a54c1988-3718-480f-8d23-8be0ca95461f` |
| Pages production deployment | `dc62ee00-90c9-403c-9c47-a6454d457886`, from the merged release commit |
| Public build verification | JavaScript `index-D3WoHbOk.js` and CSS `index-CLEtb_iq.css` both exactly match the verified local build by SHA-256 |
| Direct Worker and Pages proxy health | HTTP 200, `{"ok": true}` |
| Unauthenticated account route | HTTP 401, as expected |
| Production switches | `JEV_MODE=off`, `JEV_MODEL=jev-1.13.0`, `DIGEST_DELIVERY_ENABLED=false` |
| Cron | Daily `0 8 * * *`, retained by the deployed Worker |

The release order was D1 migration, Worker deployment and health checks, then
merge to `main` and the Git-connected Pages build. Existing Mailgun and
OpenRouter secrets were preserved. No TypeSafe key was present, and this release
made no live Jev calls or email sends.

## Runtime state checked

Authenticated D1 queries showed the three most recent digest dates, October 20,
21, and 22, all completed with one event, zero failures, and zero emails sent.
Their completion timestamps correspond to the October 19–21 morning schedule.
These runs predate the new Worker release and confirm the prior dry-run schedule
was operating; they do not validate the newly deployed provider integration.

The new Jev tables were empty at release. Local browser verification covers the
new preview/scoring behavior with fake providers; see
[the verification record](jev-verification-2026-10-21.md).

## Activation still required

1. Add `TYPESAFE_API_KEY` as an encrypted Worker secret, never a Pages variable
   or plaintext repository value.
2. Enable `shadow` for a controlled authenticated preview, verify the pinned
   model response and decision breakdown, and compare results with labeled events.
3. Enable `filter` only after checking false exclusions. Preserve strict score
   direction: values above 0.6 are irrelevant; equality stays eligible.
4. Keep email delivery disabled until its separate intended-recipient smoke
   succeeds and the sending domain is ready.

See [Cloudflare secret setup](https://developers.cloudflare.com/workers/configuration/secrets/#via-the-dashboard)
and [the repository deployment guide](../cloudflare/README.md#worker-and-d1).
Code rollback can retain the additive Jev tables; do not remove user or digest
data as part of a rollback.
