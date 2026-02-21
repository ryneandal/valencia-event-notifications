# Project Tasks

- [ ] **Scrapers**
    - [ ] `scrapers/valencia_events/spiders/rss_spider.py` (Generic RSS spider)
    - [ ] `scrapers/valencia_events/spiders/sala_russafa_spider.py` (Target: Sala Russafa)
    - [ ] Add more spiders for other targets defined in `targets/` (if any)

- [ ] **Testing**
    - [ ] Add more unit tests for corner cases in normalization
    - [ ] Add integration tests for the full pipeline

- [x] **Core Infrastructure**
    - [x] Project scaffolding
    - [x] `visit_valencia_spider.py`
    - [x] Data Normalization (`src/valencia_events/normalize.py`)
    - [x] Storage/Deduplication (`src/valencia_events/storage.py`)
    - [x] Mailer (`src/valencia_events/mailer.py`)
    - [x] CLI Runner (`src/valencia_events/cli.py`)
    - [x] Refactor to `src` package layout
    - [x] CI/CD (`nightly_digest.yml`)

- [ ] **User Management** (See [specs/user_management.md](specs/user_management.md))
    - [x] Implement User Model & Database migration (`users` and `users_events` tables added)
    - [ ] Select hosting/DB strategy (Persistent storage vs GHA artifacts)
    - [x] Web App skeleton (FastAPI)
    - [x] Google Sign-in implementation
    - [x] Passkey implementation
    - [x] User Profile UI (Preferences input)

- [ ] **AI Personalization** (See [specs/llm_filtering.md](specs/llm_filtering.md))
    - [x] `google-generativeai` integration
    - [x] Prompt engineering for event curation
    - [x] Multi-user digest generation loop
