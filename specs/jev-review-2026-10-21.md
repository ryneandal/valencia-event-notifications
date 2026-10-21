# Jev release review — 2026-10-21

Two independent agents reviewed the release from
`bea8f1f65f67f4a1d8c6e11e3bcffaa0210349bd` through
`f74e4d157859aff90237d135dfe2934021c1ec1c`. The scope covers bounded interests,
Jev transport/scoring and previews, signup recovery, production activation, and
the nullable D1 fix. A third agent prepared the separate
[product opportunities proposal](product-opportunities-2026-10-21.md).

## Standards review

**S1 — P3, stale deployment documentation.** `AGENTS.md` requires prose to match
the implementation. The Cloudflare guide incorrectly described the checked-in
Jev mode as `off`, and the user-management status still listed deployed
capabilities as pending. Both passages are corrected: Wrangler selects `filter`,
missing or invalid runtime modes fall back to `off`, and authenticated production
checks are complete. The outstanding email-delivery smoke remains documented.

No substantive code-smell findings were reported. The standards reviewer
accepted the follow-up changes, including the validator fixes below.

## Specification review

**C1 — P2, canonical profiles could exceed the size limit.** Adding trusted
event-type definitions could expand an accepted 16,384-byte input beyond the
documented bound. That saved profile could not be submitted unchanged later.
The validator now checks the normalized UTF-8 size before returning a value to
either registration or profile update.

**C2 — P2, nonstandard numbers broke browser restoration.** Python accepted
`NaN`, `Infinity`, and `-Infinity`, then persisted JSON that browser parsing
rejects. Strict parsing now rejects those constants. Serialization also rejects
nonfinite values produced by numeric overflow, such as `1e400`.

Both routes return HTTP 422 for these inputs before changing a profile or
sending a magic link. Trusted event definitions and ordinary profiles retain
their existing behavior. The specification reviewer accepted both fixes and
their regression coverage; no other demonstrated correctness defects were
reported.

## Verification

| Check | Result |
| --- | --- |
| Regression reproduction | Ten registration/PATCH cases failed before the fix: two size-expansion cases and eight nonfinite-number cases |
| Boundary behavior | A canonical profile containing Unicode text at exactly 16,384 UTF-8 bytes remains valid and round-trips unchanged |
| Preference tests | 49 passed, including assertions that rejection leaves saved data and outgoing email unchanged |
| Complete Python suite | 262 passed locally on Python 3.12.9; CI targets Python 3.11 |
| Frontend suite | 103 passed |
| Ruff | Lint passed; all 73 Python files passed formatting checks |
| Worker bundle | Wrangler dry-run succeeded |
| Independent follow-up | Both reviewers accepted the fixes |

The runtime changes are limited to profile validation. Jev scoring, authentication,
the active `filter` configuration, and disabled digest delivery are unchanged.
The product proposal contains future experiments, not shipped features or
pricing commitments.
