# Project Tasks

Last reconciled with the codebase: 2026-06-10.

- [x] **Core Infrastructure**
    - [x] Project scaffolding
    - [x] Data Normalization (`src/valencia_events/normalize.py`)
    - [x] Storage/Deduplication (`src/valencia_events/storage.py`)
    - [x] Mailer (`src/valencia_events/mailer.py`)
    - [x] CLI Runner (`src/valencia_events/cli.py`)
    - [x] Refactor to `src` package layout
    - [x] CI/CD (`nightly_digest.yml`, `ci.yml`)

- [ ] **Scrapers** (`src/scrapers/valencia_events/spiders/`)
    - [x] `visit_valencia_spider.py`
    - [x] `rss_spider.py` (generic RSS spider)
    - [x] `ajuntament_agenda_spider.py`
    - [x] `palau_musica_spider.py`
    - [x] `les_arts_spider.py`
    - [x] `ivam_spider.py`
    - [x] `valencia_secreta_spider.py`
    - [x] `valenciabonita_spider.py`
    - [ ] `sala_russafa_spider.py` (fixture `tests/fixtures/salarussafa.html` already exists)
    - [ ] Decide whether item validation lives in the Scrapy pipeline or `source_filters.py`; remove the unused path (`pipelines.py` is currently a stub, output flows through `scrapy -O` JSONL)

- [ ] **User Management** (See [specs/user_management.md](specs/user_management.md))
    - [x] Web app skeleton (FastAPI, `src/valencia_events/web.py`)
    - [x] User model, `users`/`user_sessions` tables, onboarding service
    - [x] Cloudflare Pages frontend + Python Worker API (`cloudflare/`)
    - [ ] **Decide hosting/DB strategy** (SQLite + GHA artifacts vs Cloudflare D1) — blocks everything below
    - [ ] Consolidate to a single web stack (FastAPI/SQLite vs Worker/D1 currently run in parallel with diverging schemas)
    - [ ] Connect the digest pipeline to the production user store (Worker-registered users in D1 are invisible to the nightly digest)
    - [ ] Real authentication — current login is email-only with no verification. Minimum: email magic-link; spec target: Google Sign-in and/or Passkeys
    - [ ] Write `users_events` rows when digests are sent (table exists but is never populated)

- [ ] **AI Personalization** (See [specs/llm_filtering.md](specs/llm_filtering.md))
    - [x] LLM integration via LangChain (`src/valencia_events/personalization.py`, Gemini + Mistral backends with fallbacks)
    - [x] Prompt engineering for event curation
    - [x] Multi-user digest generation loop (`cli.py`)
    - [ ] Persist LLM relevance scores/reasons to `users_events`

- [ ] **Cloudflare Worker migration (Python)**
    - [x] Rewrite JS Worker as Python Worker (`cloudflare/worker/src/`)
    - [x] Pytest coverage for the Worker (`tests/test_cloudflare_worker.py`)
    - [ ] Replace `database_id = "replace-with-real-id"` in `wrangler.toml`
    - [ ] Add missing Worker tests: login, logout, `/api/health`, inactive-user login
    - [ ] Add wrangler validation (e.g. `wrangler deploy --dry-run`) to CI; rename the `cloudflare-test` CI job (it now only runs frontend vitest)
    - [ ] Align config: wrangler vs Terraform `compatibility_date`; fix Terraform Pages build command (`pages/` is static, has no `package.json`)

- [ ] **Testing**
    - [ ] Add more unit tests for corner cases in normalization
    - [ ] Add integration tests for the full pipeline (scrape → normalize → store → digest)
