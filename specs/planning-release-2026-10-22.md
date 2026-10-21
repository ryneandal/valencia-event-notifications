# Planning release — 2026-10-22

The implementation from PR [#60](https://github.com/ryneandal/valencia-event-notifications/pull/60)
is deployed on [Brisa](https://valencia-event-notifications.pages.dev/).
Release code: `92d3946`. Worker version:
`dade0974-c9fa-4789-b9e1-0a90953e3250`. Initial matching Pages deployment:
[df6b8930](https://df6b8930.valencia-event-notifications.pages.dev/).

The release includes four-step onboarding, explicit audience/event types,
editable review, actual ranked plans, seven-day date selection, conservative
event times, source coverage history, saved plans, public sharing, calendar
exports, delivery-day controls, and voluntary feedback with 30-day retention.
New accounts start with digest emails paused; existing subscription choices
remain intact.

The payment implementation includes hosted Stripe Checkout, a customer portal,
signature verification, test/live isolation, idempotent requests, and guarded
membership synchronization. Billing stays disabled because Stripe credentials,
Price, portal, and webhook configuration have not been connected or exercised.
No paid lifecycle check or charge has occurred. The EUR 3/month offer supports
continued development; planning tools remain available during beta.

## Verification

- 328 Python and 217 frontend tests pass (545 total), including 21 billing cases.
- Ruff check and formatting pass for 77 Python files. Frontend production build
  and Cloudflare Worker dry-run bundle pass.
- Both CI jobs and the Cloudflare preview check passed for the implementation
  commit before production deployment.
- Applied forward migrations 0002–0004 and adopted the existing idempotent 0001
  in D1 migration tracking. Offline migration checks preserved seeded users and
  events and matched the fresh schema columns across 16 tables.
- Production Worker and Pages `/api/health` return 200. Unauthenticated
  `/api/planning` and `/api/billing` return 401. Unsigned billing webhook requests
  return 400 through both the Worker URL and Pages proxy.
- The production HTML serves `index-BhL6L3uf.js` and `index-zGFE0zjH.css`, matching
  the tested build. The compiled stylesheet retains the higher-specificity
  review wrapping rule.

The two implementation reviewers' accepted findings were fixed: truncated
review labels, resume with no delivery days, implicit new-user email enrollment,
same-second webhook races, unrelated-product watermark interference, old
cancellations overwriting a new membership, completed checkout reuse, and
checkout completing during retry. Automated regressions cover the behavioral
cases; compiled CSS inspection covers the wrapping fix.

Native visual inspection could not run because the computer-use service
returned `cgWindowNotFound` for both Safari and Chrome. The authenticated
production account flow therefore remains an explicit follow-up, despite the
passing offline UI and API tests. No session was fabricated or bypassed.

## Operational state

`JEV_MODE=filter`, `JEV_MODEL=jev-1.13.0`,
`DIGEST_DELIVERY_ENABLED=false`, and `BILLING_ENABLED=false`.
The encrypted TypeSafe secret and existing Mailgun settings remain in place.
The production secret-name inventory contains no `STRIPE_*` entries.

Follow the [membership launch runbook](membership-launch.md) to configure and
verify Stripe before accepting payments. Digest delivery has its separate
sender/recipient and delivery smoke checks; a membership does not enable it.
