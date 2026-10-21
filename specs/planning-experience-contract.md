# Brisa planning experience contract

Implementation scope: the usable shortlist, honest collection states, shorter
onboarding, readable review, optional explanations, returning-user planning,
delivery-day preferences, coverage history, calendar/copy/save actions, a
seven-day date chooser, voluntary study feedback, and Stripe-hosted paid
membership preparation. Membership supports continued development at the
prepared price of EUR 3/month; planning tools remain available during beta.
It promises neither exclusive features nor event tickets or daily coverage.
The implementation keeps `BILLING_ENABLED=false` and
`DIGEST_DELIVERY_ENABLED=false`. Stripe configuration, payment lifecycle checks,
and live activation remain pending; follow the [launch runbook](membership-launch.md).

## Preview extension

Keep `contract_version: "jev-preview-v1"`, `summary`, and `evaluations` compatible.
Add `plans` to authenticated preview responses only:

```json
{
  "version": "brisa-plans-v1",
  "date": "2026-10-22",
  "checked_at": "2026-10-21T20:00:00+00:00",
  "delivery_enabled": false,
  "coverage": {
    "state": "complete",
    "collected_count": 1,
    "sources": [
      {"name": "ajuntament_agenda", "status": "ok", "fetched_count": 8,
       "event_count": 1, "checked_at": "2026-10-21T20:00:00+00:00"}
    ]
  },
  "recommendations": [
    {"id": 7, "event_key": "canonical-key", "title": "Example screening",
     "url": "https://example.org/event", "start_at": "2026-10-22T19:00:00+02:00",
     "end_at": null, "time_precision": "datetime", "location": "",
     "description": "Public event description", "source": "ajuntament_agenda",
     "position": 1, "reason": "Suggested from your saved choices.",
     "used_fallback": false, "type_decision": "eligible"}
  ],
  "excluded_count": 0
}
```

Recommendations come from the actual ranker, in its order, never from frontend
interpretation of eligibility. Other checked listings stay available in a
disclosure. Sharing copies public title/date/link only, never reasons, scores,
account URLs, or profile data.

`coverage.state` is `complete` when all sources succeeded, `partial` when only
some did, and `unavailable` when none did. Successful empty sources count as
checked. Persist public source counts/status/check times to `source_checks` for
later coverage inspection. No account identity is attached to those checks.

Event `time_precision` is `datetime`, `date`, or `unverified`. Date-only sources
must not present the collector's synthetic noon as an event time. Publication
timestamps from RSS are unverified event times. Legacy stored events default to
`unverified`. Do not invent locations or booking information. Date-only calendar
exports are clearly labeled as saving the date; unverified dates cannot be
exported. Timed exports may offer an explicit optional one-hour reminder.

`POST /api/digest/dry-run` accepts an optional JSON `date` (`YYYY-MM-DD`), limited
to tomorrow through seven days from today in Europe/Madrid. A missing date
retains tomorrow behavior. Invalid/out-of-range dates return 422 before collection.
Carry the chosen date through the Durable Object; scheduled runs keep tomorrow.

## Account planning API

All endpoints below require the existing session. Account IDs come only from
that session; request bodies cannot select another account. The API
dispatcher calls `handle_planning_request(env, request, user, path, method)` for
`/api/planning` and its subpaths after resolving the session; it returns an
`AppResponse` or 404. `worker_planning.py` owns these routes;
`PlanningTools.jsx` provides the account controls.

`GET /api/planning` returns:

```json
{
  "version": "brisa-planning-v1",
  "today": "2026-10-21",
  "available_dates": ["2026-10-22", "2026-10-23", "2026-10-24", "2026-10-25", "2026-10-26", "2026-10-27", "2026-10-28"],
  "delivery_enabled": false,
  "delivery_days": [0,1,2,3,4,5,6],
  "subscribed": false,
  "saved_events": [],
  "pilot": {"consented": false, "expires_at": null},
  "coverage_history": []
}
```

The example shows a new account. Registration creates its email subscription
paused, and magic-link verification returns `is_subscribed: false`. The user
enables digests explicitly through account email preferences. Verification links
still work while digests are paused. Existing accounts retain their subscription
state, including the existing default for legacy accounts without a row.

Weekdays use Monday=0 through Sunday=6. New day choices affect scheduled delivery,
never previews.
Days refer to the event day; a digest goes out the preceding day. An active
subscription requires at least one selected day. Global delivery remains
disabled. Every change uses explicit submission.

- `PATCH /api/planning/delivery`: `{days: [0,5], subscribed: true}`; validate
  unique bounded days and Boolean subscription, update account schedule and the
  existing subscription row, return `{delivery_days, subscribed}`.
- `POST /api/planning/saved`: `{event_id: 7}`; save a canonical existing event,
  idempotently, max 50 per account. Return `{saved_events}` using the public event
  fields above (without ranking reasons/position/decisions).
- `DELETE /api/planning/saved`: `{event_id: 7}`; remove only this account's saved
  item and return `{saved_events}`. No event or other account data is deleted.
- `PUT /api/planning/pilot`: `{consented: true|false}`; create an expiring random
  study code linked separately to the account. Opt-out removes that link and
  associated feedback. Return `{pilot}`. No passive tracking before consent.
- `POST /api/planning/feedback`: `{date, result_state, useful, action}`. Date is
  a bounded valid preview date; result_state is `recommendations`, `empty`,
  `filtered`, `partial`, or `unavailable`; useful is Boolean or null; action is
  null, `organizer`, `save`, `copy`, or `calendar`. Requires unexpired consent.
  No event names, preferences, emails, or free text are stored in feedback.
  Return `{ok: true}`. Feedback is voluntary, not automatic link tracking.

Study consent expires after 30 days. Cleanup deletes expired study links and
feedback; opting out deletes the link and its feedback. Saved events remain
private to the account and protect their source event rows from history cleanup
until removed. Coverage history contains public counts and check times, with up
to 40 checks from the past 14 days in the account response.

## Paid membership API

`worker_billing.py` handles the authenticated `/api/billing` routes. It uses
Stripe-hosted Checkout and the customer portal; no payment details pass through
the Brisa frontend. The Worker sends Stripe the account email and internal user
ID to associate a billing customer, but sends no event preferences or study
feedback. Billing state separates test and live customers by account and mode.

| Route | Behavior |
| --- | --- |
| `GET /api/billing` | Returns `{membership}` with `available`, `livemode`, `price_eur`, `interval`, `status`, `active`, `can_manage`, `cancel_at_period_end`, and `current_period_end`. |
| `POST /api/billing/checkout` | Creates or reuses a hosted subscription Checkout URL for the session account and configured Price. Returns `{url}`; accepts no client-selected customer, price, or return URL. |
| `POST /api/billing/portal` | Returns `{url}` for that account's Stripe customer portal. Existing members can manage billing while new checkout is closed. |
| `POST /api/billing/webhook` | Receives Stripe snapshot events without a session cookie. Verifies the raw body signature and timestamp, checks mode/product relevance, and loads the customer's current subscriptions before updating local status. |

The Worker pins Stripe API requests to `2025-09-30.clover`. Checkout requires an
active recurring Price for 300 euro cents (EUR 3) every month in the key's mode, both
Worker secrets, an HTTPS `APP_BASE_URL`, and `BILLING_ENABLED=true`. The server
rejects a second open subscription and uses idempotency keys for customer and
Checkout creation. It stores the Checkout session ID and queries Stripe before
reusing a cached session. Completed or expired sessions receive a fresh key,
allowing a canceled member to subscribe again without waiting an hour. The
browser accepts only the expected Stripe HTTPS hosts.
The success return page never establishes payment status; verified subscription
state does. Configuring the Price and portal, checking signatures and retries,
and testing payment/cancellation remain launch work.

Webhook synchronization validates the event's candidate subscription before
claiming a revision, so another product cannot advance the account's event
watermark. It then fetches the customer's current subscriptions and chooses the
current membership, preferring an active/trialing subscription. A
compare-and-swap update publishes only the newest claimed revision. Delayed or
same-second events therefore cannot overwrite a newer state, and an older
cancellation cannot revoke a replacement membership.

Apply forward-only migrations before deploying the updated Worker:
`0002_event_planning.sql` for public event metadata and checks,
`0003_account_planning.sql` for private planning state, and
`0004_membership_billing.sql` for billing accounts, including `sync_version` and
`checkout_session_id`. Fresh databases use the
synchronized `schema.sql` instead. Existing Jev installations already need
`0001_jev_evaluations.sql`.

## Frontend integration

App owns the selected preview date and sends `{date}` when present. Keep stale
response cancellation when the account, saved profile, or selected date changes.
Its account screen leads with the planning action and keeps profile editing and
pause/resume accessible. Read service state from `/api/planning`; never promise
emails while delivery is disabled.

`DigestPreview` retains its existing props and additionally accepts
`onEditPreferences`, `onSaveEvent(eventId)`, and `onFeedback({date, result_state,
useful, action})`. Actions remain usable if optional callbacks are absent.
It exports/reuses public planning helpers from `planning.js` for calendar and
copy actions. Add `plans` validation to the preview parser without breaking
older responses; older responses may show legacy explanations but never pretend
to contain final recommendations.

`PlanningTools` accepts props `user`, `onUserChange(user)`,
`onPlanningChange(data)`, and `refreshKey`. It loads account planning state,
renders saved plans, schedule controls, explicit pilot consent, and hosted
checkout/customer-portal actions. Billing failure doesn't disable planning.
App increments `refreshKey` after saving an event or changing subscription state.
App passes account planning state to date controls and can call the APIs through
the existing `apiFetch` helper. Failed planning loads report `null`; successful
refreshes preserve the selected date. `planning.css` contains the added styles.

Onboarding uses four steps: audience and current coverage, event types,
optional refinements, then account access and review. New users start without
an audience, selected types, or family presets. Review shows the actual saved
preference labels and section edit actions; previously saved area preferences
remain editable without promising broader source coverage. The account view
leads with plans and offers server-provided dates, including weekend and Monday
shortcuts. Date, account, or saved-profile changes cancel stale requests.

## Verification

Offline regression tests cover ordered recommendations, source failures versus
empty/all-filtered results, date bounds/time zones, conservative time precision,
auth/ownership, explicit consent and expiry, subscription weekdays, public-only
sharing, calendar escaping, onboarding defaults and edits, cancellation, and
legacy response compatibility. Billing tests mock Stripe transport and cover
authentication, Price validation, test/live separation, hosted URL checks,
idempotency, signed webhooks, concurrent synchronization, unrelated-product
events, replacement subscriptions, and immediate checkout after cancellation.
Signup regressions verify paused new accounts and retained legacy state. No test needs
real credentials or a charge. Full Python/frontend tests, Ruff, Worker bundle,
browser checks, additive D1 migrations, and live health checks precede release;
the [membership launch checklist](membership-launch.md) separately tracks
external Stripe checks and activation.
