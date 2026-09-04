# València Next-Day Events Digest — Repository Instructions

> Ground rules for coding agents and contributors working in this repository.

---

## 0 — Scope and precedence

- Follow the requested issue or user task. `task.md` records project status; do not start an unrelated backlog item unless asked to choose one.
- Before editing, inspect the working tree and preserve unrelated changes. Never revert another contributor's in-progress work.
- Keep changes small and testable, but complete the requested vertical slice: implementation, tests, configuration, dependency metadata, and user-facing documentation when each is affected.
- Treat repository code and current tests as the source of truth when prose has drifted; update stale prose in the same change.

---

## 1 — Task scoping

Prefer small, well-scoped issues. A useful task includes:

- **Goal**: one-sentence outcome (what should be implemented).
- **Success criteria / tests**: exact unit tests or example inputs/outputs that will verify the feature.
- **Files to edit / create**: exact path(s) in the repo.
- **Constraints**: allowed libraries, Python versions, security restrictions (no secrets in code).
- **Style**: formatting / linters (`uv run ruff format`, `uv run ruff check`) and type usage (Pydantic/typing).

Example issue body (good):

- Title: `src/scrapers/valencia_events/spiders/sala_russafa_spider.py — add spider`
- Goal: "Add a Scrapy spider that extracts title, start, URL, and description from the Sala Russafa program page and yields the repository's raw event shape."
- Acceptance tests: provide a saved HTML fixture and `pytest` test asserting the spider yields one item with `title == '...'` and a parsed `start` datetime.
- Files: `src/scrapers/valencia_events/spiders/sala_russafa_spider.py`, `tests/fixtures/salarussafa.html`, `tests/test_sala_spider.py`.
- Constraints: `Scrapy` only, do not reduce the repository's one-second request delay, and respect `robots.txt`.

---

## 2 — Task decomposition (Backlog)

See [task.md](task.md) for the current backlog and project status.

When a request maps to the backlog:

1. Confirm the item is still incomplete by checking the implementation and tests.
2. Break it down into small, testable steps if needed.
3. Update `task.md` only for work actually completed.

---

## 3 — Task context and examples

When writing an issue or delegating a subtask, include:

- A minimal **example input** and the **expected output** (fixture + parsed JSON).  
- The **exact file path** where the code should go.  
- Any **error-handling expectations** (timeouts, retries, logging).  
- The **test command** (e.g., `pytest tests/test_...py`) that must pass.  
- The **runtime environment** (Python 3.11, Linux/Ubuntu for GHA).

Small example snippet to include in prompts:

- "Given the `tests/fixtures/salarussafa.html` file, implement `src/scrapers/valencia_events/spiders/sala_russafa_spider.py` such that `pytest tests/test_sala_spider.py` passes."

---

## 4 — Repository context (important files & paths)

Inspect the relevant files before editing (the project uses a `src/` layout):

- `src/scrapers/valencia_events/spiders/`  
- `src/scrapers/valencia_events/items.py`  
- `src/scrapers/valencia_events/pipelines.py`  
- `src/valencia_events/` — `models.py`, `normalize.py`, `storage.py`, `mailer.py`, `runner.py`, `cli.py`, `filters.py`, `personalization.py`, `onboarding.py`, `web.py`, `services.py`  
- `cloudflare/` — Pages frontend (`pages/public/`) and Python Worker API (`worker/src/`)  
- `tests/fixtures/` and `tests/` (very small, focused fixtures)  
- `.github/workflows/nightly_digest.yml` and `.github/workflows/ci.yml` (for CI expectations)  
- `pyproject.toml`, `requirements.txt`, and `uv.lock` (dependency declarations and lock state)
- `.env.example`, `README.md`, and `specs/` (runtime configuration and public behavior)

For LLM work, keep provider selection and deterministic fallback behavior in
`src/valencia_events/personalization.py`. Supported `LLM_BACKEND` values are
`gemini`, `mistral`, and `openrouter`. Adding another backend also requires
offline tests plus synchronized environment, workflow, dependency, README,
spec, and backlog updates.

---

## 5 — Explicit acceptance criteria & tests (examples)

Each behavior change must ship with automated tests. Documentation-only changes
do not need artificial tests. Examples:

- **RSS spider test** (`tests/test_rss_spider.py`):
  - Fixture: `tests/fixtures/valencia_rss.xml`
  - Assertion: spider produces at least one item with non-empty title and valid ISO datetime string in `start`.

- **Normalizer tests** (`tests/test_normalize.py`):
  - Inputs: variety of date strings (`"12/10/2025 20:00"`, `"12 de octubre de 2025 20:00"`, ISO strings).
  - Assertion: `normalize_raw()` returns `Event.start` as timezone-aware datetimes in `Europe/Madrid`.

- **Storage dedupe test** (`tests/test_storage.py`):
  - Start with empty DB fixture, insert event A, insert duplicate A, assert only one row present and function returns only first inserted event.

- **LLM provider tests** (`tests/test_personalization.py`):
  - Assert environment-based backend/model selection and fallback behavior.
  - Mock provider calls; tests must never require API credentials or network access.

Small regression tests are the preferred validation signal.

---

## 6 — Security, secrets, and privacy instructions

- **Never** include secrets (SMTP passwords, API tokens, or private keys) in code, tests, logs, prompts, or documentation. Use environment variables and GitHub Secrets.
- Use `.gitignore` to prevent local credentials from being committed.  
- Read external-service credentials from `os.environ`; use obvious fake values in tests and examples.
- User preference data is private. Send only fields required for event ranking to an LLM, and never add email addresses, session data, or credentials to model prompts.

---

## 7 — Style & linting (enforceable rules)

- Python 3.11, use type hints and `pydantic` for models.  
- Formatting & linting: **ruff** (`uv run ruff format .` and `uv run ruff check .`).
- Logging: use the existing stdlib helper, `valencia_events.logger.get_logger`; do not log secrets or complete user profiles.
- Tests: **pytest**, small fixtures, no network calls (use cached HTML and mock network where appropriate).
- Dependencies: update both `pyproject.toml` and `requirements.txt`, then regenerate and commit `uv.lock`.

---

## 8 — Useful task templates

Use short templates for common tasks; include them in `.github/copilot-prompts/` if desired:

### Spider task template

~~~plaintext
Task: Implement Scrapy spider at {file_path}
Goal: extract fields 'title','start','url','description' from {site}
Fixtures: tests/fixtures/{fixture}.html
Tests: pytest tests/test_{name}_spider.py should pass
Constraints: obey robots.txt and do not reduce DOWNLOAD_DELAY below 1
~~~

### Normalizer task template

~~~plaintext
Task: Implement normalize_raw in normalize.py
Goal: convert raw items into pydantic Event models with timezone-aware start
Fixtures: tests/test_normalize.py includes examples
~~~

### LLM backend task template

~~~plaintext
Task: Add {provider} backend in src/valencia_events/personalization.py
Goal: select it with LLM_BACKEND and retain deterministic fallback behavior
Configuration: document API key, primary model, and optional fallback model
Tests: pytest tests/test_personalization.py; mock all provider calls
Constraints: no secrets or live network calls; synchronize dependency and workflow files
~~~

These templates keep delegated work focused and verifiable.

---

## 9 — CI / GitHub Actions expectations

- **Unit tests run on PRs**: GitHub Actions (`ci.yml`) runs `pytest`, `ruff check`, and `ruff format --check`. Fail PRs on lint/test failures.  
- **SQLite persistence**: the nightly workflow currently uses `actions/cache` for `events.db`; changing the production store is an explicit architecture decision tracked in `task.md`.
- **Secrets**: SMTP credentials, recipient addresses, and provider API keys belong in repository secrets. Backend/model choices belong in repository variables.
- **Manual runs**: provide `workflow_dispatch` for debugging runs.

---

## 10 — Example "good" and "bad" prompts (for contributors)

**Good prompt**:

- Includes files to change, fixture examples, tests to pass, constraints, and allowed libs.

**Bad prompt**:

- "Build the whole project" with no tests or examples. These produce noisy, brittle completions.

Always prefer the Good style.
