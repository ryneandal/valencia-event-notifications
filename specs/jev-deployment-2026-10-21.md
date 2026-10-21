# Jev code release — 2026-10-21

The bounded selector, Worker validation, Jev integration, and preview UI are
deployed at [Brisa](https://valencia-event-notifications.pages.dev/). Jev filtering
is active with its encrypted API secret configured. Three live labeled fixtures
and authenticated production previews passed. Digest sending remains disabled.

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
| Initial release switches | `JEV_MODE=off`, `JEV_MODEL=jev-1.13.0`, `DIGEST_DELIVERY_ENABLED=false` |
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

## Live provider verification and shadow deployment

After the initial release, `TYPESAFE_API_KEY` was uploaded as an encrypted Worker
secret and its `secret_text` binding was verified. Plaintext key entries were
removed from the local tracked configuration before committing. No key value
was committed or printed.

Three synthetic event fixtures were sent to the live TypeSafe API using the
production question builder, response validator, and scoring function. Each
request selected `live_music` and `film` and requested `jev-1.13.0`.

| Fixture | Music p(yes) | Film p(yes) | Irrelevance score | Result |
| --- | --- | --- | --- | --- |
| Live jazz concert | 0.99 | 0.02 | 0 | Eligible |
| Cinema screening | 0.02 | 0.99 | 0 | Eligible |
| Road running race | 0.02 | 0.01 | 0.97 | Irrelevant |

All requests returned HTTP 200 and the expected decisions. These checks validate
live provider compatibility and the score direction; they are not a broad
quality evaluation or an authenticated production preview.

Worker version `6c872217-6c39-4fe3-a83e-1d776f2a2ae7` was deployed with
`JEV_MODE=shadow`, `JEV_MODEL=jev-1.13.0`, and
`DIGEST_DELIVERY_ENABLED=false`. The deployed version retains the encrypted
TypeSafe secret. Direct Worker and Pages-proxy health both return `{"ok": true}`.
Shadow mode records decisions without excluding events.

## Production preview repair and filtering activation

The first authenticated preview reached Jev but failed while saving its audit
row, showing “Brisa could not finish this preview. Please try again.” The Worker
reported `D1_TYPE_ERROR` for an `undefined` value. Pyodide converts Python `None`
to JavaScript `undefined`, while D1 requires `null` for SQL NULL. The fix binds
`pyodide.ffi.jsnull` for nullable Jev fields and the optional delivery provider ID,
retaining Python `None` in offline SQLite tests. See
[Pyodide type conversions](https://github.com/pyodide/pyodide/blob/main/docs/usage/type-conversions.md)
and [D1 supported types](https://developers.cloudflare.com/d1/worker-api/).

[PR #58](https://github.com/ryneandal/valencia-event-notifications/pull/58)
includes four regression cases that reproduced the exact failure before the fix:
evaluated, uncertain, and fallback Jev results, and delivery without a provider
ID. After the fix, all 251 Python tests and 103 frontend tests passed, along with
lint, formatting, and Worker bundle checks.

| Check | Result |
| --- | --- |
| Corrected shadow Worker | `5c211b99-753b-4fe8-bb52-42b6eabe5481`; authenticated preview completed at 12:34 UTC with zero failures and no email sent |
| Decision inspection | Pinned `jev-1.13.0` response, per-type probabilities/confidence/contributions, and the resulting score were visible; source event evidence supported the classification |
| Filter Worker | `d20996c6-95ed-4d61-b9c9-a861a4161301`, with `JEV_MODE=filter`, `JEV_MODEL=jev-1.13.0`, and `DIGEST_DELIVERY_ENABLED=false` |
| Filtered authenticated preview | Completed at 12:45 UTC with one evaluated event, zero failures, and no email sent; the irrelevant candidate was removed from recommendations while its explanation remained visible |
| D1 verification | The evaluation persisted with a null error code; the filtered run had zero recommendation rows |

The browser showed “Tomorrow’s preview” and the completed classification instead
of the failure message. These checks cover live provider compatibility and the
complete authenticated preview path, not classification accuracy across all
event types. Private account preferences and per-user scores are omitted here.

Filtering retains the strict score direction: values above 0.6 are irrelevant;
equality stays eligible. To stop exclusions, redeploy with `JEV_MODE=shadow`; to
stop Jev calls, use `off`. Keep email delivery disabled until its separate
intended-recipient smoke succeeds and the sending domain is ready.

See [Cloudflare secret setup](https://developers.cloudflare.com/workers/configuration/secrets/#via-the-dashboard)
and [the repository deployment guide](../cloudflare/README.md#worker-and-d1).
Code rollback can retain the additive Jev tables; do not remove user or digest
data as part of a rollback.
