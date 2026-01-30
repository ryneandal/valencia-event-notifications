# València Next-Day Events Digest — AI Instructions (Revised for GitHub Copilot Best Practices)

> This document updates the original AI instructions to follow GitHub Copilot coding agent best practices so Copilot / AI agents (and humans) can produce reliable, testable, secure code.

---

## 0 — Summary of changes (what this revision adds)
- **Task scoping & acceptance criteria** for each component so Copilot can produce focused work.
- **Small, testable units**: instructions split into tiny tasks (spiders, normalizer, storage, mailer, runner, tests).
- **Repository context & examples**: include file paths, examples, and expected outputs to improve completions.
- **Safety & secrets rules**: explicit guidance to never return or include secrets.
- **Coding conventions & linting**: specify formatter, linters, and types (pydantic) to ensure consistent output.

---

## 1 — How to use this repository with Copilot (high level)
When using Copilot or a coding agent to implement features from this repo, prefer **small well-scoped issues** rather than giant "build entire app" prompts. For each issue include:
- **Goal**: one-sentence outcome (what should be implemented).
- **Success criteria / tests**: exact unit tests or example inputs/outputs that will verify the feature.
- **Files to edit / create**: exact path(s) in the repo.
- **Constraints**: allowed libraries, Python versions, security restrictions (no secrets in code).
- **Style**: formatting / linters (Black, Ruff, isort) and type usage (Pydantic/typing).

Example issue body (good):
- Title: `scrapers/valencia_events/spiders/sala_russafa_spider.py — add spider`
- Goal: "Add Scrapy spider that extracts title, start datetime, url, and description from Sala Russafa program page and writes RawEventItem to pipeline."
- Acceptance tests: provide a saved HTML fixture and `pytest` test asserting the spider yields one item with `title == '...'` and a parsed `start` datetime.
- Files: `scrapers/valencia_events/spiders/sala_russafa_spider.py`, `tests/fixtures/salarussafa.html`, `tests/test_sala_spider.py`.
- Constraints: `Scrapy` only, `DOWNLOAD_DELAY <= 1s`, respect `robots.txt`.

---

## 2 — Task decomposition (Backlog)

See [task.md](task.md) for the current backlog and project status.

When picking up a new task:
1. Select an uncompleted item from `task.md`.
2. Break it down into small, testable steps if needed.
3. Follow the prompting guidelines in Section 3.

---

## 3 — Prompting & examples (what to include in Copilot prompts)
When asking Copilot to generate code or tests, always include:
- A minimal **example input** and the **expected output** (fixture + parsed JSON).  
- The **exact file path** where the code should go.  
- Any **error-handling expectations** (timeouts, retries, logging).  
- The **test command** (e.g., `pytest tests/test_...py`) that must pass.  
- The **runtime environment** (Python 3.11, Linux/Ubuntu for GHA).

Small example snippet to include in prompts:
- "Given the `tests/fixtures/salarussafa.html` file, implement `scrapers/valencia_events/spiders/sala_russafa_spider.py` such that `pytest tests/test_sala_spider.py` passes."

---

## 4 — Repository context (important files & paths)
Provide Copilot these files or paths as context in prompts so it understands the repo layout:
- `scrapers/valencia_events/spiders/`  
- `scrapers/valencia_events/items.py`  
- `scrapers/valencia_events/pipelines.py`  
- `models.py`, `normalize.py`, `storage.py`, `mailer.py`, `runner.py`  
- `tests/fixtures/` and `tests/` (very small, focused fixtures)  
- `.github/workflows/nightly_digest.yml` (for CI expectations)  
Include these files in Copilot's context window or the workspace to improve output relevance.

---

## 5 — Explicit acceptance criteria & tests (examples)
Each task must ship with automated tests. Examples:

- **RSS spider test** (`tests/test_rss_spider.py`):
  - Fixture: `tests/fixtures/valencia_rss.xml`
  - Assertion: spider produces at least one item with non-empty title and valid ISO datetime string in `start`.

- **Normalizer tests** (`tests/test_normalize.py`):
  - Inputs: variety of date strings (`"12/10/2025 20:00"`, `"12 de octubre de 2025 20:00"`, ISO strings).
  - Assertion: `normalize_raw()` returns `Event.start` as timezone-aware datetimes in `Europe/Madrid`.

- **Storage dedupe test** (`tests/test_storage.py`):
  - Start with empty DB fixture, insert event A, insert duplicate A, assert only one row present and function returns only first inserted event.

Small, passing tests are the single best signal Copilot needs to validate success.

---

## 6 — Security, secrets, and privacy instructions
- **Never** include secrets (SMTP passwords, API tokens, or private keys) in code or prompts. Use environment variables and GitHub Secrets. Reinforce this in every PR description and in Copilot prompts.  
- Use `.gitignore` to prevent local credentials from being committed.  
- For external APIs (Eventbrite/Meetup), instruct Copilot to read tokens from `os.environ` and not to hardcode them.

---

## 7 — Style & linting (enforceable rules)
- Python 3.11, use type hints and `pydantic` for models.  
- Formatting: **Black**, imports sorted with **isort**, lint with **ruff**. Add pre-commit hooks to enforce.  
- Logging: use `structlog` or stdlib `logging` with JSON-friendly messages for easier debugging in GHA.  
- Tests: **pytest**, small fixtures, no network calls (use cached HTML and mock network where appropriate).

---

## 8 — Useful prompt templates for Copilot tasks
Use short templates for common tasks; include them in `.github/copilot-prompts/` if desired:

**Spider task template**
~~~
Task: Implement Scrapy spider at {file_path}
Goal: extract fields 'title','start','url','description' from {site}
Fixtures: tests/fixtures/{fixture}.html
Tests: pytest tests/test_{name}_spider.py should pass
Constraints: obey robots.txt, DOWNLOAD_DELAY <= 1
~~~

**Normalizer task template**
~~~
Task: Implement normalize_raw in normalize.py
Goal: convert raw items into pydantic Event models with timezone-aware start
Fixtures: tests/test_normalize.py includes examples
~~~

Providing these templates speeds up agent output and reduces back-and-forth.

---

## 9 — CI / GitHub Actions expectations
- **Unit tests run on PRs**: Add a GitHub Actions job to run `pytest`, `ruff`, and `black --check`. Fail PRs on lint/test failures.  
- **Artifact persistence**: If using SQLite, include `actions/download-artifact` and `upload-artifact` to persist small DB state between runs (document retention policy).  
- **Secrets**: `SMTP_USER`, `SMTP_APP_PASSWORD`, `EVENTBRITE_TOKEN` must be set as repo secrets.  
- **Manual runs**: provide `workflow_dispatch` for debugging runs.

---

## 10 — Example "good" and "bad" prompts (for contributors)
**Good prompt**:
- Includes files to change, fixture examples, tests to pass, constraints, and allowed libs.

**Bad prompt**:
- "Build the whole project" with no tests or examples. These produce noisy, brittle completions.

Always prefer the Good style.

---

## 11 — Operational notes for maintainers
- Keep fixtures small and representative; store a cached copy of target pages in `tests/fixtures/`.  
- Use short lived tokens for testing; revoke if leaked.  
- Rotate secrets and monitor GHA logs for unexpected network calls.  
- Add a CONTRIBUTING.md that explains how to write Copilot-friendly issues (template with Goal + Tests + Files + Constraints).

---

## 12 — Appendix: links & references
- GitHub Copilot — Best practices (see GitHub docs for "Get the best results" and coding agent guidance).

---

*This file is a revision of the original AI instructions to ensure compatibility with Copilot coding agent workflows and best practices. If you'd like, I can apply these edits directly to the repository files (generate updated README, CONTRIBUTING, and a set of example issues + prompt templates).*
