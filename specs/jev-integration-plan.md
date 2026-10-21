# Jev relevance implementation plan

Status: implemented by parallel frontend and backend agents, verified locally
and in CI, and deployed with its D1 migration on 2026-10-21. The TypeSafe secret
and provider validation remain pending; production `JEV_MODE=off`. See the
[release record](jev-deployment-2026-10-21.md). This plan follows the user's rule: **a score above the threshold means
the event is irrelevant**. Use `irrelevance_score` in code to make that direction
explicit. Dates and API facts were checked on 2026-10-21.

## Contract to agree before splitting work

The frontend and backend depend on shared data, not on each other's completion.
The initial contract and examples live in:

- `cloudflare/shared/event-types.json`: the 12 allowed event types, stable IDs,
  labels, and definitions. Keep the five original IDs compatible with saved
  profiles, including `kid-friendly_culture`.
- `cloudflare/shared/jev-preview.schema.json`: version 1 per-event evaluation
  response. Both implementations must validate against this schema.
- `cloudflare/shared/jev-preview.examples.json`: offline examples for matched,
  irrelevant, uncertain, provider failure, and threshold equality states.
- `specs/jev-api-research.md`: verified provider request/response shape and sources.

Treat these as version 1. An integration owner reviews contract changes before
either parallel branch adopts them. Do not silently change IDs, field meanings,
score direction, or fixture values. The fixtures describe application
behavior, not recorded Jev results.

The existing profile remains JSON in `preferences_blob`, with the same six
fields. Event selections remain `top_interest_clusters: [{name, includes}]`.
The Worker replaces `includes` with catalog definitions, rejects unknown or
duplicate IDs, and requires 1–12 selections. The Python catalog mirror in
`worker_preferences.py` must pass the parity test against the shared JSON.
Existing profiles retain their supported IDs; unsupported saved selections need
user review on the next edit. No D1 schema migration is needed for the selector.

## Frontend/backend boundary

Keep registration and `PATCH /api/preferences` as the save boundary. The UI
saves the selected catalog types before requesting a preview, then calls the
existing authenticated `POST /api/digest/dry-run` with no body. The backend uses
only the session's saved profile and tomorrow's collected events; the browser
cannot supply another user ID, provider instructions, model, or threshold.

Extend the current `{summary}` response additively:

```json
{
  "contract_version": "jev-preview-v1",
  "summary": {
    "correlation_id": "fixture-run",
    "dry_run": true,
    "event_count": 1,
    "rendered_count": 1,
    "sent_count": 0
  },
  "evaluations": ["each item conforms to jev-preview.schema.json"]
}
```

The above illustrates the envelope only; retain all existing summary fields and
replace the placeholder with evaluation objects from the shared examples. An
empty event set returns `evaluations: []`. An all-irrelevant event set is a valid
successful result with no recommendations, rather than a provider failure.
No preview request may call Mailgun. Scheduled runs must not return one user's
evaluations to another user; only targeted authenticated previews expose them.

The frontend displays safe event titles and links, selected type labels, the
decision, and a per-question breakdown from the backend. It never calculates
the authoritative score. A provider failure or uncertain result says that the
match could not be determined and remains eligible for the existing fallback;
neither should look like an irrelevant event. Loading, retry, empty collection,
all filtered, and expired-session states need separate messages. Disable preview
while saving, discard responses from an earlier edit/request, and render provider
data as text. A normal preview displays only the saved preferences it evaluated.

Frontend development uses mocked `fetch` responses from the shared fixtures.
Keep mock wiring in tests or an explicitly local development entry point; do
not add an automatic production fallback to fake results. The backend can test
the same fixtures without React or a TypeSafe API key.

## Small Jev questions

Send one request per event, with one `noul` question per unique selected event
type. The questions share the event state but receive independent answers.
Do not ask “Is this event relevant to this user?” and do not ask Jev to calculate
the final score. TypeSafe recommends combining narrow decisions in application
code. [Fan-out pattern](https://docs.typesafe.ai/patterns/fan-out),
[composition guidance](https://docs.typesafe.ai/concepts/how-to-build-with-system-one).

Call `POST https://api.typesafe.ai/v1/systemone` from the Worker with a server-side
Bearer key, a reviewed pinned model, `state`, and `questions`. A Noul answer is
`{"type":"noul","noul":0.94}`: a yes probability, not a Boolean and not a
separate confidence value. [Official API schema](https://api.typesafe.ai/openapi.json),
[Noul](https://docs.typesafe.ai/primitives/noul).

Freeze a reviewed atomic question for every catalog ID in
`cloudflare/shared/jev-questions.json`, with a parity-tested Worker mirror in
`worker_jev_questions.py`. For example:

| Selected type | One Boolean question |
| --- | --- |
| `live_music` | Is a live musical performance a primary advertised activity? |
| `food_drink` | Is a food or drink experience a primary advertised activity? |
| `performing_arts` | Is theatre, dance, opera, comedy, or circus a primary advertised activity? |
| `parks_and_play` | Is outdoor play or a park outing a primary advertised activity? |

Use `event_type:<catalog_id>` as the answer key, including the full category in
the instructions: TypeSafe does not send question IDs to the model. Specify
true/false criteria from the catalog; incidental refreshments should not turn
every event into `food_drink`. Event content is untrusted evidence, never new
instructions. Question coverage tests require exactly one question for each of
the 12 catalog IDs and only selected IDs in a user's request.

Send a bounded event projection: title, description, start time and timezone,
source, and venue/category only when the collector actually provides them.
Keep event keys in the local request mapping; omit identity, email, user/session
IDs, magic-link data, unrelated profile text, and credentials. Do not invent
venue, accessibility, age suitability, or price for missing fields. Known time
and geography checks belong in deterministic code. The complete illustrative
request and raw response are in the research note.

The first scoring version covers selected event types. Keep audience, location,
positive/negative signals, and seasonal anchors in the saved profile and existing
ranking path during shadow evaluation. A later scoring version may add one
atomic question for each non-deterministic constraint, such as family suitability
or crowd intensity. That change requires explicit weights, missing-data behavior,
fixtures, and false-exclusion evaluation; do not silently discard these existing
preferences when switching production ranking.

## Deterministic, additive scoring v1

This is an application policy to validate on local events, not a calibrated
probability of user interest. For each selected type `i`, use Jev's yes
probability `p_i`, derive confidence `c_i = abs(2*p_i - 1)`, and retain both.
TypeSafe documents this confidence formula for Noul.
[Noul confidence](https://docs.typesafe.ai/confidence#noul).

Selections are alternatives. Someone choosing music, food, and sport can want
a concert that has no food or sport. Apply this gate before summing:

1. If any `p_i >= 0.8`, set every contribution to zero: the event matches at
   least one selected type. Return `evaluated / eligible` with score `0`.
2. If every `p_i <= 0.2`, give each type equal weight `w_i = 1/n` and contribution
   `w_i * c_i`. Sum the contributions into `irrelevance_score`.
3. Otherwise return `uncertain / unknown`, with a null score and null
   contributions. Keep the event eligible for fallback; uncertainty is not
   evidence of irrelevance.

For an evaluated score, `decision = irrelevant` **only when**
`irrelevance_score > threshold`. Proposed starting threshold: `0.6`, on a 0–1
scale. Equality remains eligible. No selection, missing required answers, wrong
answer types, Booleans masquerading as numbers, NaN/infinity, or probabilities
outside `[0,1]` are invalid; return a fallback result, not a zero score.

With music `p=0.05` and food `p=0.10`, confidences are `0.90` and `0.80` and
contributions are `0.45 + 0.40 = 0.85`: irrelevant at threshold `0.6`. With music
`p=0.94` and food `p=0.08`, the music match opens the gate and the score is `0`.
With both `p=0.20`, the score is `0.60`: eligible at equality. These examples are
in the shared fixture file.

Calculate the comparison with decimal arithmetic from the parsed probabilities;
round only for display. Returned contributions must sum to the published score
within `1e-9`. A strong yes prevents type-only rejection regardless of how many
other types the user selected. Confidence is derived from the same probability;
do not multiply `p` by confidence as if they were independent evidence.

## Parallel agent assignments

Every agent works on its own branch/worktree. Agents are not alone in the
codebase: preserve other changes, do not revert another agent's work, and ask
the integration owner to change shared files. Python target: 3.11 on Ubuntu CI;
frontend target: the existing React/Vite app and Node 22 CI configuration.

| Owner | Exclusive paths/responsibility | Can start after | Acceptance |
| --- | --- | --- | --- |
| Contract/integration owner | `cloudflare/shared/jev-*`, `specs/jev-*`, `task.md`; fixture review and final integration | Now | Both agents agree on schema/examples, all 12 questions have catalog IDs, score direction is fixed |
| Frontend agent | `cloudflare/pages/src/`, `cloudflare/tests/`; selector refinements, save/preview flow, decision breakdown and all UI states | Contract v1 reviewed | Mocked examples drive usable UI without any provider or Worker dependency; multiple selections persist and stale responses cannot overwrite newer choices |
| Backend agent | New `cloudflare/worker/src/worker_jev.py`, `worker_relevance.py`; `tests/test_worker_jev.py`, `tests/test_worker_relevance.py` | Same contract review, in parallel with frontend | Builds per-type questions, validates real provider shape, scores deterministically and matches shared fixtures using fake fetch |
| Integration owner, after both branches | `worker_ranking.py`, `worker_orchestrator.py`, `worker_app.py`, `worker_storage.py`, `schema.sql`, `wrangler.toml`, `.env.example`, workflow/docs changes, corresponding existing Python tests | Pure backend modules and mocked UI pass independently | Dry-run response matches fixtures; authentication, D1 persistence, empty-result semantics, privacy and fallback work end to end |

The frontend and backend must not both edit the orchestrator, schema, environment,
catalog, or shared fixtures. Agree on the following backend module interface at
the contract checkpoint: `build_questions(selected_ids)`,
`build_request(event, questions, model)`,
`async evaluate_event(env, event, selected_ids)`, and the pure
`score_answers(selected_ids, answers, threshold)` returning the shared evaluation
shape after attaching canonical event metadata. The transport module knows
TypeSafe's raw response; the UI consumes only the normalized application shape.

## Transport, persistence, and rollout

Use native Worker `fetch` following the existing OpenRouter adapter. Do not assume
the Python SDK and its dependencies work unchanged in this runtime. Inject a
`JEV_FETCH` fake for offline tests. The production key belongs in the Worker secret
`TYPESAFE_API_KEY`; read it at the backend environment boundary and never return
it or a raw provider error. `JEV_MODEL` and `JEV_MODE=off|shadow|filter` are
configured in `wrangler.toml`, defaulting to `jev-1.13.0` and `off`. The adapter
requires a pinned `jev-X.Y.Z` version and rejects response model mismatches;
aliases cannot silently reuse cached answers. Recheck stable versions before
rollout. [Models](https://docs.typesafe.ai/models).

Set application limits below the provider limits: at most 12 questions/event,
8,000 description characters, two concurrent calls, a five-second attempt
timeout, at most one retry, and a 30-second total evaluation budget per preview.
Honor `Retry-After` for 429/529 only when it fits the remaining budget; otherwise
use fallback. Retry transient connection/5xx failures within the same budget;
do not retry auth or schema errors. Unprocessed events receive an explicit
budget-exhausted fallback. Validate model/answers and map every requested question
ID exactly; do not let a partial response silently raise the score.
[Error reference](https://docs.typesafe.ai/api/errors).

Cache identity-free event/type answers by event content hash, catalog/question
version, and resolved model version. Derive per-user scores locally from the
selected IDs. Changing event text or questions invalidates the cached answer;
different selections recompute the score. Later user-dependent questions need
separate private cache keys and retention. Record safe error codes and aggregate
latency/fallback counts without profiles or raw prompts.

Add a forward-only D1 migration for evaluation provenance: digest run, user,
event, selected-type snapshot, taxonomy/question/scoring versions, model,
probabilities, contributions, threshold, decision, status, and evaluated time.
Persist rejected decisions as well as recommendations for diagnosis; use the
existing 90-day digest retention policy. Keep this table private. If a later
evaluation rejects every event, clear stale recommendations for that user/run
before the current empty-ranking early return. A legitimate empty result must
not trigger fallback that reintroduces rejected events.

Merge in this order: contracts, independent frontend/backend branches, then
integration. Deploy Worker validation before the matching Pages build. Enable
`shadow` on controlled authenticated previews, compare Jev decisions with labeled
local events, and inspect false exclusions. Shadow mode leaves the existing
ranking and fallback behavior intact. `filter` may exclude only evaluated scores
above threshold; unknown/fallback events keep the existing deterministic path.
Keep `DIGEST_DELIVERY_ENABLED=false` through this work. Production filtering and
delivery cutover are separate rollout steps after validation.

Adding Jev to the local reference pipeline is separate from this Worker plan.
If requested, keep provider selection/fallback in
`src/valencia_events/personalization.py` and synchronize dependencies, lockfile,
workflow, environment docs, tests, and supported `LLM_BACKEND` values.

## Acceptance commands and release checks

Frontend agent: `pnpm --dir cloudflare test` and
`pnpm --dir cloudflare build`. Backend agent:
`uv run pytest tests/test_worker_jev.py tests/test_worker_relevance.py`.
Integration: `uv run pytest`, `uv run ruff check .`,
`uv run ruff format --check .`, and from `cloudflare/`,
`pnpm dlx wrangler deploy --dry-run --config worker/wrangler.toml`.

Tests must cover every catalog type, duplicate/unsupported selections, legacy
profile hydration, one matching type among many nonmatches, all nonmatches,
uncertainty, threshold equality, selected-type changes, model/cache invalidation,
invalid provider answers, timeout/retry limits, identity isolation, and a dry-run
that cannot deliver email. Both branches validate shared fixtures against the
same schema; do not duplicate examples independently.

Implemented boundaries are `worker_jev.py` (provider and cache),
`worker_relevance.py` (deterministic score), `worker_ranking.py` and
`worker_orchestrator.py` (filtering, private preview, and persistence), and
`pages/src/preview.js` plus `DigestPreview.jsx` (validation and rendering).
Paused-account previews, failed-summary retries, and bounded timing/source
evidence were corrected during integration review. See the
[verification record](jev-verification-2026-10-21.md) for checks and limits.

Apply `worker/migrations/0001_jev_evaluations.sql` before deploying this code even
when Jev is off. Retention references its tables in every mode. The full schema
also includes these tables for fresh databases. Deployment instructions are in
[the Cloudflare guide](../cloudflare/README.md#worker-and-d1).

After deployment, check both public health URLs, the authenticated profile
round-trip, targeted preview, D1 migration state, and current Cron configuration.
Today's public health checks alone do not prove the scheduled delivery pipeline
works. See [project-status-2026-10-21.md](project-status-2026-10-21.md).
