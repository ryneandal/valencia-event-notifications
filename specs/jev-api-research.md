# TypeSafe Jev API research

Verified against TypeSafe's public documentation on 2026-10-21. This is research
for the integration plan; it does not enable Jev or make authenticated requests.
Examples use invented events and responses.

## Verified API contract

Send `POST https://api.typesafe.ai/v1/systemone` with
`Authorization: Bearer <API_KEY>` and `Content-Type: application/json`. The body
requires `model`, `state` (a string, object, or array), and a nonempty `questions`
object. A successful response contains `model`, `answers`, and `usage`. Answers
use the original question IDs; the returned model can resolve the requested
alias to a version. `GET /v1/models` lists the authenticated account's available
names. [Official OpenAPI schema](https://api.typesafe.ai/openapi.json).

The Boolean primitive is **Noul**, serialized as `"type": "noul"`. Its answer is
`{"type": "noul", "noul": p}`, where `p` is the probability of yes, from 0 to 1.
It is neither a JSON Boolean nor a rating. Optional `criteria.true` and
`criteria.false` describe the two outcomes. Question IDs identify results but
are not sent to the model, so the instructions must name the category explicitly.
[Noul reference](https://docs.typesafe.ai/primitives/noul).

**Noul does not return a separate `confidence`.** TypeSafe documents deriving
`confidence = abs(2 * p - 1)`: 0 at `p = 0.5`, 1 at either endpoint. Choice and
Score have their own returned confidence fields. This distinction matters when
validating the response and explaining scores in the UI.
[Confidence reference](https://docs.typesafe.ai/confidence#noul).

All questions in a call are evaluated independently against the same state;
one answer cannot read another answer. TypeSafe recommends narrow questions
combined in application code, and batching the questions needed for a decision
into one request. Independent evaluation is not a claim that event categories
are statistically independent.
[State](https://docs.typesafe.ai/concepts/state),
[fan-out](https://docs.typesafe.ai/patterns/fan-out),
[building with System One](https://docs.typesafe.ai/concepts/how-to-build-with-system-one).

## Minimal event-to-API example

For a user selecting `live_music` and `food_drink`, send the event and two atomic
category questions. No identity or full user profile is needed. The category
definitions should come from the application's versioned, bounded catalog.
This request follows the documented Noul schema; it has not been sent to Jev.
[Request reference](https://docs.typesafe.ai/primitives/noul#request-structure).

```json
{
  "model": "jev-1.13.0",
  "state": {
    "event": {
      "title": "Jazz in the garden",
      "description": "An outdoor concert by a local jazz quartet.",
      "venue": "Example Garden",
      "category": "music"
    }
  },
  "questions": {
    "event_type:live_music": {
      "type": "noul",
      "instructions": "Is live musical performance a primary activity of this event?",
      "criteria": {
        "true": "A concert, gig, recital, or other performance by musicians is a primary advertised activity.",
        "false": "Live musical performance is absent or only incidental background entertainment."
      }
    },
    "event_type:food_drink": {
      "type": "noul",
      "instructions": "Is a food or drink experience a primary activity of this event?",
      "criteria": {
        "true": "A tasting, food festival, or culinary experience is a primary advertised activity.",
        "false": "Food and drink are absent or only incidental refreshments."
      }
    }
  }
}
```

Illustrative raw success response, suitable as the starting point for an offline
fixture. Probabilities and token counts are invented, not measured results:

```json
{
  "model": "jev-1.13.0",
  "answers": {
    "event_type:live_music": {"type": "noul", "noul": 0.94},
    "event_type:food_drink": {"type": "noul", "noul": 0.08}
  },
  "usage": {"input_tokens": 240, "output_tokens": 24}
}
```

The corresponding derived confidences are `0.88` and `0.84`. Do not invent a
provider `confidence` field in this raw fixture. Preserve stable application
category IDs, including `kid-friendly_culture`; opaque question IDs need no
semantic renaming, and the server should construct them rather than accepting
arbitrary client prompts.

## Models, limits, and failures

As of the verification date, `jev-latest` points to stable `jev-1.13.0`, while
`jev-preview` points to `jev-1.14.0`. The default limits for both are 64k tokens
for state plus all questions, and 32k for state plus any single question. There
is no separate question-count limit. Organization rate limits apply to requests
and tokens per second. Long context requires a special header and trades away
speed and accuracy; this event use case should not require it.
[Models and limits](https://docs.typesafe.ai/models).

Requests must be UTF-8 JSON, at most 32 MiB, with finite numbers and no more than
64 nested levels in state/instructions/criteria. Documented failures include
400 (request rules or excessive context), 401 (authentication), 413 (body size),
415 (compression), 422 (schema), 429 (rate limit), and 529 (overload). Retry 429
and 529 with exponential backoff. The error documentation promises a descriptive
JSON body, not one uniform error envelope for every failure.
[Request rules and errors](https://docs.typesafe.ai/api/errors).

The Python SDK defaults to two retries, retries 408/429/5xx and connection or
timeout errors, and respects `Retry-After` and `retry-after-ms`. An HTTP adapter
can implement equivalent bounded behavior. The SDK's defaults are not a
recommendation for this application's total request-time budget.
[Python retry policy](https://docs.typesafe.ai/sdk/python/api/retries).

## Proposed application contract and scoring safeguards

The following are design recommendations, not TypeSafe API requirements. The
implementation plan should freeze these with shared fixtures before frontend
and backend agents work in parallel:

| Field | Recommended meaning |
| --- | --- |
| `status` | `evaluated`, `fallback`, or `pending`; provider failure must not look like a negative judgment. |
| `decision` | `eligible`, `irrelevant`, or `unknown`; use `unknown` for an unavailable evaluation. |
| `irrelevance_score` | Final application score in `[0, 1]`, or null when unavailable; larger means less relevant. |
| `threshold` | Application threshold on the same scale. Rejection uses strict `score > threshold`, so equality remains eligible. |
| `components` | Stable question/category ID, `p_yes`, derived confidence, weight, and contribution actually used in the final sum. |
| `taxonomy_version`, `scoring_version` | Versions that allow frontend fixtures and stored evaluations to remain interpretable. |
| `model`, `evaluated_at` | Backend provenance; no API key, raw user profile, or provider error body. |

Keep the score formula in deterministic code. TypeSafe explicitly supports
weighted composition of independent answers; it does not prescribe this
project's weights, threshold, or relevance policy.
[Composite scoring](https://docs.typesafe.ai/patterns/composite-scoring),
[composition example](https://docs.typesafe.ai/concepts/how-to-build-with-system-one).

For each selected type, retain the probability and derived confidence rather
than rounding immediately to a Boolean. A value near 0.5 supplies little
evidence either way; lack of information must not become a confident rejection.
Avoid treating probability and its derived confidence as independent evidence.
Explicitly define how confidence changes each additive contribution.

Selected event types are alternatives: a music lover who also selects food and
sport can still want a concert. A simple sum or average of category nonmatches
can incorrectly reject it. The final scoring rule needs an any-selected-type
match safeguard, with component contributions reflecting that rule so they
still sum to the published score. Add separate atomic questions only for
additional user constraints that cannot be checked reliably in code. Handle
known date, time, price, and exclusion rules deterministically where possible.

For rollout, pin a reviewed stable model; bound description sizes, concurrency,
timeouts, and retries; validate complete answer IDs, answer types, and finite
probabilities in `[0, 1]`; and retain the existing deterministic fallback on
errors or insufficient evidence. Test all of this offline on Python 3.11 and
the Cloudflare Worker adapter. A documented Python SDK is not evidence that
its dependencies run unchanged in Cloudflare's Python runtime.

Required scoring fixtures include one matching type among many nonmatches,
all confident nonmatches, uncertain answers, missing event details, no selected
types, strict threshold equality, malformed responses, and provider timeouts.
Evaluate false exclusions on labeled local events before enabling rejection;
the aggregate score is an application heuristic, not automatically a calibrated
probability of user interest.

## Data handling

TypeSafe states that it does not train on customer requests or responses, and
offers zero data retention for enterprise customers. Do not assume that a
standard account has zero retention or a specific retention period.
[Model data policy](https://docs.typesafe.ai/models),
[legal documentation](https://docs.typesafe.ai/legal),
[privacy policy](https://typesafe.ai/legal/privacy-policy).

The application should send only the event fields needed for the atomic
questions and minimal required preference constraints. Keep email, profile IDs,
session data, credentials, and unrelated profile text out of the request. Keep
the API key in backend environment/secrets storage, never in Pages JavaScript.
Event-type classification can be reused across users because the category
question itself does not require their identities; cache by event content,
question/catalog version, and model version. User-specific constraints need a
separate appropriately scoped cache key. These are repository privacy and
integration recommendations, not guarantees provided by Jev.
