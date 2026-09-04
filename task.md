# Project Tasks

Last reconciled with the codebase and PoC architecture: 2026-09-04.

- [x] **Core Infrastructure**
    - [x] Project scaffolding
    - [x] Data Normalization (`src/valencia_events/normalize.py`)
    - [x] Storage/Deduplication (`src/valencia_events/storage.py`)
    - [x] Mailer (`src/valencia_events/mailer.py`)
    - [x] CLI Runner (`src/valencia_events/cli.py`)
    - [x] Refactor to `src` package layout
    - [x] Continuous integration (`ci.yml`); the old `nightly_digest.yml` runtime
      has been removed

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
    - [x] Port the retained sources to Worker-compatible asynchronous collectors
      for the Cloudflare production runtime

- [ ] **User Management** (See [specs/user_management.md](specs/user_management.md))
    - [x] Select Cloudflare Pages + Python Worker + D1 as the production web stack
    - [x] Deploy static Pages dashboard, same-origin API proxy, Worker, and D1
    - [x] Implement and validate the React/Vite personalization onboarding SPA
    - [x] Deploy the React/Vite personalization onboarding SPA to production Pages
    - [x] Verify the production D1 profile contains all six personalization fields
    - [x] Implement and test verified, single-use email magic links
    - [x] Configure Mailgun delivery, migrate D1, and deploy magic-link auth
    - [x] Add pause/resume subscription controls
    - [x] Remove the legacy FastAPI onboarding path and D1 HTTP subscriber bridge;
      retained SQLite tools are local-only

- [ ] **AI Personalization** (See [specs/llm_filtering.md](specs/llm_filtering.md))
    - [x] LLM integration via LangChain (`src/valencia_events/personalization.py`,
      OpenRouter defaulting to `nvidia/nemotron-3-ultra-550b-a55b:free`, with
      Gemini and Mistral as explicit alternatives)
    - [x] Prompt engineering for event curation
    - [x] Multi-user digest generation loop (`cli.py`)
    - [x] Persist selected order, relevance reasons, model ID, and fallback state
      to D1 `recommendations`

- [ ] **Cloudflare Worker migration (Python)**
    - [x] Rewrite JS Worker as Python Worker (`cloudflare/worker/src/`)
    - [x] Pytest coverage for the Worker (`tests/test_cloudflare_worker.py`)
    - [x] Configure the deployed D1 binding in `wrangler.toml`
    - [x] Add the Pages Function `/api/*` proxy
    - [x] Add and deploy a `scheduled()` handler with a daily Cron Trigger
    - [x] Add D1 event/recommendation/delivery history and idempotency
    - [x] Implement OpenRouter ranking and Mailgun digest delivery in the Worker;
      production sending remains disabled pending the controlled smoke
    - [x] Add a safe authenticated dry-run path and per-user failure isolation
    - [x] Disable and remove the legacy GitHub Actions digest schedule
    - [ ] Add missing Worker tests: login, logout, `/api/health`, inactive-user login
    - [x] Add `wrangler deploy --dry-run` validation to CI and rename the
      Cloudflare job for frontend + Worker scope
    - [ ] Align config: wrangler vs Terraform `compatibility_date`; fix Terraform Pages build command (`pages/` is static, has no `package.json`)

- [ ] **Testing**
    - [ ] Add more unit tests for corner cases in normalization
    - [ ] Add integration tests for the full pipeline (scrape → normalize → store → digest)

- [ ] **Post-PoC enhancements**
    - [ ] [RYN-130](https://linear.app/ryneandal/issue/RYN-130/generate-dynamic-related-onboarding-tags-with-an-llm): generate privacy-bounded,
      schema-validated related interest/signal tags through the configured LLM
      and display them as optional accessible chips during registration/editing;
      retain deterministic tags and the exact six-field profile contract as the
      fallback
