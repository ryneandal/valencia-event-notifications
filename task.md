# Project Tasks

Last reviewed for the bounded-interest and Jev work: 2026-10-21.

- [x] **Core Infrastructure**
    - [x] Project scaffolding
    - [x] Data Normalization (`src/valencia_events/normalize.py`)
    - [x] Storage/Deduplication (`src/valencia_events/storage.py`)
    - [x] Mailer (`src/valencia_events/mailer.py`)
    - [x] CLI Runner (`src/valencia_events/cli.py`)
    - [x] Refactor to `src` package layout
    - [x] Continuous integration (`ci.yml`); the old `nightly_digest.yml` runtime
      has been removed

- [x] **Scrapers** (`src/scrapers/valencia_events/spiders/`)
    - [x] `visit_valencia_spider.py`
    - [x] `rss_spider.py` (generic RSS spider)
    - [x] `ajuntament_agenda_spider.py`
    - [x] `palau_musica_spider.py`
    - [x] `les_arts_spider.py`
    - [x] `ivam_spider.py`
    - [x] `valencia_secreta_spider.py`
    - [x] `valenciabonita_spider.py`
    - [x] [RYN-135](https://linear.app/ryneandal/issue/RYN-135/resolve-the-legacy-sala-russafa-scraper-and-validation-pipeline): retire the never-configured Sala Russafa placeholder and use `source_filters.py` as the single local raw-item validation boundary
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
    - [x] Implement 12 bounded event-type choices, preserve saved IDs, and validate
      registration/profile writes against the catalog; tested locally
    - [x] Deploy the bounded selector and Worker validation on 2026-10-21
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
    - [x] Research TypeSafe's Jev API and add a
      [parallel implementation plan](specs/jev-integration-plan.md) with shared
      schema/fixtures, per-type Noul questions, and additive irrelevance scoring
    - [x] Implement Jev transport/scoring and frontend decision interactions in
      parallel against the reviewed shared contract
    - [x] Integrate targeted previews, cached type answers, and private evaluation
      persistence; verify offline scoring, retries, identity isolation, and UI
    - [x] Complete integration review and browser verification with fake providers;
      record [results and limits](specs/jev-verification-2026-10-21.md)
    - [x] Apply the Jev D1 migration and deploy Worker before Pages; record
      [production release evidence](specs/jev-deployment-2026-10-21.md)
    - [x] Configure encrypted `TYPESAFE_API_KEY`, verify three live labeled
      fixtures, and deploy `shadow` mode with digest delivery disabled
    - [x] Fix nullable D1 bindings, validate an authenticated Worker preview,
      and enable Jev filtering with digest delivery disabled

- [ ] **Cloudflare Worker migration (Python)**
    - [x] Rewrite JS Worker as Python Worker (`cloudflare/worker/src/`)
    - [x] Pytest coverage for the Worker (`tests/test_cloudflare_worker.py`)
    - [x] Configure the deployed D1 binding in `wrangler.toml`
    - [x] Recheck public Pages/proxy/direct Worker availability on 2026-10-21;
      record the [evidence and limits](specs/project-status-2026-10-21.md)
    - [x] Recheck deployed version, Cron, D1 schema, and recent successful dry runs
      with authenticated Cloudflare access on 2026-10-21
    - [x] Complete an authenticated production provider preview
    - [ ] Complete a controlled delivery smoke
    - [x] Add the Pages Function `/api/*` proxy
    - [x] Add and deploy a `scheduled()` handler with a daily Cron Trigger
    - [x] Dispatch scheduled and authenticated preview runs through a
      SQLite-backed Python Durable Object for the scraping/parsing workload
    - [x] Add D1 event/recommendation/delivery history and idempotency
    - [x] Implement OpenRouter ranking and Mailgun digest delivery in the Worker;
      production sending remains disabled pending the controlled smoke
    - [x] Add a safe authenticated dry-run path and per-user failure isolation
    - [x] Disable and remove the legacy GitHub Actions digest schedule
    - [x] [RYN-132](https://linear.app/ryneandal/issue/RYN-132/add-inactive-subscriber-login-regression-coverage): add inactive-subscriber login coverage; login, logout, and `/api/health` are already covered
    - [x] [RYN-122](https://linear.app/ryneandal/issue/RYN-122/harden-onboarding-validation-accessibility-and-mobile-behavior): add field-level validation, keyboard/focus management, accessible progress and controls, retry-aware API errors, reduced-motion behavior, and narrow-mobile layouts
    - [x] Add `wrangler deploy --dry-run` validation to CI and rename the
      Cloudflare job for frontend + Worker scope
    - [x] [RYN-131](https://linear.app/ryneandal/issue/RYN-131/align-terraform-with-the-deployed-pages-and-worker-configuration): align Terraform compatibility settings and the Git-connected Pages build command

- [ ] **Testing**
    - [x] [RYN-133](https://linear.app/ryneandal/issue/RYN-133/expand-normalization-boundary-and-malformed-input-tests): add focused normalization boundary and malformed-input tests
    - [x] [RYN-134](https://linear.app/ryneandal/issue/RYN-134/add-an-offline-full-digest-pipeline-integration-test): add an offline full-pipeline integration test

- [ ] **Post-PoC enhancements**
    - [ ] Re-scope [RYN-130](https://linear.app/ryneandal/issue/RYN-130/generate-dynamic-related-onboarding-tags-with-an-llm): suggestions must select from the
      reviewed bounded catalog; arbitrary new event types conflict with the
      current selection contract
