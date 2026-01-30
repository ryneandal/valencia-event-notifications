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
    - [x] Data Normalization (`normalize.py`)
    - [x] Storage/Deduplication (`storage.py`)
    - [x] Mailer (`mailer.py`)
    - [x] CLI Runner (`runner.py`)
    - [x] CI/CD (`nightly_digest.yml`)

- [ ] **User Management** (See [specs/user_management.md](specs/user_management.md))
    - [ ] Select hosting/DB strategy (Persistent storage vs GHA artifacts)
    - [ ] Web App skeleton (FastAPI)
    - [ ] Google Sign-in implementation
    - [ ] Passkey implementation
    - [ ] User Profile UI (Preferences input)

- [ ] **AI Personalization** (See [specs/llm_filtering.md](specs/llm_filtering.md))
    - [ ] `google-generativeai` integration
    - [ ] Prompt engineering for event curation
    - [ ] Multi-user digest generation loop
