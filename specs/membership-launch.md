# Paid membership launch

Prepared on 2026-10-22. The repository includes Stripe-hosted Checkout, customer
portal access, and webhook synchronization. Billing remains closed with
`BILLING_ENABLED=false`; no Stripe purchase, live charge, or payment lifecycle
test has been completed as part of this implementation. Deployment and external
verification remain separate work, tracked in [task.md](../task.md).

All 328 Python and 217 frontend tests pass, including 21 offline billing cases;
Ruff checks/formatting and the Worker bundle pass. The three additive
migrations were checked against the deployed schema baseline: existing rows
survived, and the result matched the fresh schema's 16 tables and columns.
Native-browser verification was blocked by the local automation environment;
no visual check is claimed. A production secret-name check found no `STRIPE_*`
secrets, so credentials and external Stripe checks remain launch prerequisites.

The prepared offer is **EUR 3 per month to support continued development of
Brisa**. Planning tools remain available during beta. Membership includes no
event tickets and makes no promise of exclusive features, daily listings, or
complete coverage. Confirm this price before activation: the Worker currently
accepts only a EUR 3 monthly recurring Price, so a different price needs matching
code, tests, and customer copy.

`DIGEST_DELIVERY_ENABLED` stays `false`. Billing setup doesn't change the Mailgun
sandbox, recipient restrictions, or the separate digest-delivery smoke test.

## Configuration and runtime

`cloudflare/worker/src/worker_billing.py` is the implementation reference.
Requests pin `Stripe-Version: 2025-09-30.clover`; configure the webhook endpoint
to use the same version. Stripe versions webhook payloads separately from API
requests. [Stripe API versioning](https://docs.stripe.com/api/versioning?api-version=2025-09-30.clover)

| Setting | Where it belongs | Requirement |
| --- | --- | --- |
| `BILLING_ENABLED` | Worker variable | Checked-in value `false`; gates new Checkout sessions. |
| `STRIPE_PRICE_ID` | Worker variable | The actual reviewed Price from the same Stripe mode as the key. No placeholder Price is deployed. |
| `STRIPE_SECRET_KEY` | Encrypted Worker secret | Stripe secret or suitably permitted restricted key for the selected mode. |
| `STRIPE_WEBHOOK_SECRET` | Encrypted Worker secret | Signing secret for this endpoint and mode. |
| `APP_BASE_URL` | Worker variable | HTTPS Pages origin for authenticated account return URLs. |

The browser never chooses a Stripe customer, Price, or return URL. The Worker
associates a customer with the session account and keeps test/live billing rows
separate. It sends Stripe the email and an internal account ID, without event
preferences or study feedback. Card details stay on Stripe's hosted pages.

Authenticated `GET /api/billing` reports availability and synchronized membership
state. `POST /api/billing/checkout` and `POST /api/billing/portal` return hosted
URLs. The unauthenticated `POST /api/billing/webhook` instead requires a valid
Stripe signature over the original request body. A `?billing=success` redirect
doesn't establish payment status.

Checkout rechecks a stored session with Stripe before reusing it. Completed or
expired sessions get a fresh idempotency key, so a canceled member can subscribe
again immediately. Webhooks validate the candidate's product before claiming a
revision, then fetch the customer's current subscriptions. Revision-guarded
updates prevent delayed responses or older cancellations from replacing a newer
membership; unrelated products cannot advance its event watermark. These cases
are covered by offline tests, not a live payment claim.

## Prepare Stripe

Use a separate test Worker and D1 database for payment lifecycle checks. The
checked-in Wrangler configuration points at the production database; don't use
it as a disposable test deployment. Stripe test and live modes need their own
keys, Price IDs, portal settings, and webhook signing secrets.

1. In Stripe's test environment, create the Brisa membership Product and a
   fixed recurring Price with `currency=eur`, `unit_amount=300`,
   `recurring.interval=month`, and `recurring.interval_count=1`. Keep the Price
   active. Set its tax behavior to `inclusive` so the prepared customer price
   remains EUR 3 when an applicable tax calculation is configured; this setting
   doesn't determine tax obligations or enable Stripe Tax. Confirm the amount
   displayed in Checkout before accepting payments.
   [Stripe Price configuration](https://docs.stripe.com/api/prices/create?api-version=2025-09-30.clover)
2. Configure the customer portal to allow subscription cancellation and payment
   method updates. Keep plan switching and quantity changes off for this single
   membership offer. Set the portal return destination to the Brisa account
   page. Use Stripe's default `checkout.stripe.com` and `billing.stripe.com`
   hosts, which the Worker and browser accept.
   [Customer portal settings](https://docs.stripe.com/customer-management/configure-portal)
3. Optionally enable Stripe's one-subscription limit as an additional account
   setting. The Worker already checks for an open subscription before creating
   Checkout and reuses idempotent customer/session requests.
   [Limit customers to one subscription](https://docs.stripe.com/payments/checkout/limit-subscriptions)
4. In Workbench, add a webhook destination for **your account**, using
   **snapshot** events and API version `2025-09-30.clover`. Its HTTPS URL is the
   deployed Worker's `/api/billing/webhook` route. Subscribe to
   `checkout.session.completed`, `customer.subscription.created`,
   `customer.subscription.updated`, and `customer.subscription.deleted`.
   Save that endpoint's signing secret through the Worker secret mechanism.
   [Stripe webhook setup and signatures](https://docs.stripe.com/webhooks)

The integration uses [hosted subscription Checkout](https://docs.stripe.com/payments/checkout/build-subscriptions).
The Worker fetches current subscription state when processing supported events;
delivery order and a browser redirect aren't the source of membership truth.

## Apply schema and install secrets

For an existing database with the Jev tables already present, apply the
forward-only migrations before deploying the updated Worker. Wrangler's
migration tracking safely adopts idempotent `0001_jev_evaluations.sql` and then
applies `0002_event_planning.sql`, `0003_account_planning.sql`, and
`0004_membership_billing.sql` once, in order.
The billing migration includes the synchronization revision and cached Checkout
session ID columns (`sync_version` and `checkout_session_id`).
Use the configuration for the intended environment. The commands below show the
production configuration; replace that path for an isolated test deployment.

```bash
cd cloudflare
npx wrangler d1 migrations list valencia-events --remote --config=worker/wrangler.toml
npx wrangler d1 migrations apply valencia-events --remote --config=worker/wrangler.toml
```

A fresh database uses `worker/src/schema.sql` instead of replaying these
migrations over that schema. Review the schema and pending migration list first;
don't re-run the event-column migration as an untracked SQL file.

Enter credentials directly in Cloudflare's encrypted Worker secrets UI, or use
the interactive prompts below. Don't put values in chat, documentation, shell
arguments, Pages variables, or tracked files.

```bash
npx wrangler secret put STRIPE_SECRET_KEY --config=worker/wrangler.toml
npx wrangler secret put STRIPE_WEBHOOK_SECRET --config=worker/wrangler.toml
```

Set the reviewed `STRIPE_PRICE_ID` as a Worker variable and retain
`BILLING_ENABLED=false` for the initial production deployment. Local Worker
development uses an untracked `.dev.vars`; the example file lists the required
names without credentials. Deploy the Worker before the matching Pages build
so the UI can read both planning and billing endpoints.

## Verify test mode, then activate live checkout

Run offline checks before using Stripe. These commands mock payment and provider
calls and require no credentials:

```bash
uv run pytest tests/test_worker_billing.py tests/test_worker_planning.py
pnpm --dir cloudflare test
uv run ruff check .
uv run ruff format --check .
```

On the isolated test deployment, configure test values and set its
`BILLING_ENABLED=true`. Confirm that `/api/billing` reports `available: true`
and `livemode: false`, and that the UI labels Checkout as a test. Complete a test
subscription through the signed-in account. Verify that a signed webhook updates
that same account, returning from Checkout alone doesn't claim payment, and
retrying Checkout doesn't create a second open subscription. Use the portal to
change a payment method and cancel; check both cancellation-at-period-end and
the final canceled status. After cancellation takes effect, confirm a fresh
Checkout opens immediately and a new membership survives replay of the older
cancellation event. Confirm that an expired session or another account
cannot open the first account's billing portal.

Next, create and review the equivalent live Product/Price, portal, and webhook
configuration. Keep the production flag off while confirming the live key,
Price mode, amount, webhook destination/version, and endpoint secret. An
authenticated billing read must still report `available: false`; a signed
webhook delivery check verifies the endpoint without proving a paid membership.
Record the environment and results without secrets or customer payment details.

After those checks pass, change production `BILLING_ENABLED` to `true` and deploy
the Worker. Confirm the UI shows the live EUR 3/month offer and the final hosted
Checkout amount. A controlled live purchase, webhook update, and portal
cancellation complete the launch verification; this document doesn't claim they
have happened. Keep digest delivery disabled throughout.

## Activation record

- [ ] Confirm the EUR 3/month offer and review the customer-facing copy.
- [ ] Apply migrations 0002–0004 to the intended database and deploy Worker/Pages.
- [ ] Check the signed-in planning and billing controls in a browser.
- [ ] Complete the isolated Stripe test-mode checkout, webhook, retry, and portal lifecycle.
- [ ] Verify the live Price, credentials, portal, endpoint, and API version with production checkout still disabled.
- [ ] Enable production billing and record the controlled live purchase, synchronization, and cancellation results.

To stop accepting new memberships, set `BILLING_ENABLED=false`. That flag doesn't
cancel existing Stripe subscriptions. Retain the configured Price and secrets
so webhooks and customer-portal access can continue; members cancel through the
portal. Record any activation or rollback evidence in [task.md](../task.md).
