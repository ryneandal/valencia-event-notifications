# Valencia Event Notifications

Receive email notifications about events happening in València, Spain every day.

## Overview

This project automatically scrapes event information from various sources in València and sends a daily digest email with events happening the next day. It uses Scrapy for web scraping, stores events in SQLite with deduplication, and sends HTML emails via SMTP.

## Features

- 🕷️ **Web Scraping**: Scrapy-based spiders for multiple event sources
- 📅 **Daily Digest**: Automated emails with tomorrow's events
- 🔄 **Deduplication**: Hash-based event deduplication in SQLite
- 🌍 **Timezone Aware**: Proper handling of Europe/Madrid timezone
- 🤖 **GitHub Actions**: Fully automated nightly workflow
- ✅ **Type Safe**: Pydantic models with full type hints

## Project Status

**Current Stage**: Active Development 🚀

The project core is implemented and running:

- ✅ Scrapy spiders for 8 sources (Visit Valencia, Ajuntament agenda, Palau de la Música, Les Arts, IVAM, València Secreta, Valencia Bonita, generic RSS)
- ✅ Date parsing and normalization
- ✅ SQLite storage with deduplication
- ✅ LLM-based event ranking per user (Gemini, Mistral, or OpenRouter via LangChain)
- ✅ Email generation (Jinja2 templates) and sending (SMTP)
- ✅ Periodic execution via GitHub Actions
- ✅ Cloudflare Pages, Python Worker, D1, and the same-origin API proxy are deployed
- ✅ The scheduled runner can load active D1 subscribers through Cloudflare's authenticated API (production configuration/run pending)
- 🚧 The tested React personalization SPA and magic-link Worker auth await production deployment/configuration (see [specs/user_management.md](specs/user_management.md))

See [task.md](task.md) for current tasks and [AGENTS.md](AGENTS.md) for AI coding agent guidelines.

## Architecture

```text
React onboarding on Cloudflare Pages [implemented; deploy pending]
  -> same-origin Pages Function
  -> Python Worker
  -> D1 subscriber/profile store

Scheduled GitHub Actions job
  -> active D1 subscribers through authenticated D1 HTTP API
  -> Scrapy -> normalization -> cached SQLite event store
  -> per-user Gemini/Mistral/OpenRouter ranking
  -> Jinja2 HTML -> SMTP
```

The Cloudflare stack owns interactive user data; the scheduled Python stack owns
scraping and digest generation. See [specs/architecture.md](specs/architecture.md)
for deployment state, trust boundaries, and failure behavior.

## Data Schema

The system deliberately separates subscriber and batch-processing state.

Cloudflare D1 is the canonical production store for subscribers:

- **`users`**: Verified email, serialized personalization profile, active/paused
  status, and creation metadata.
- **session and verification tables**: Worker-owned authentication state that is
  never exposed to the digest or an LLM.

The scheduled job uses cached SQLite (`events.db`) for event processing:

- **`events`**: Stores unique events found by scrapers.
  - `event_hash`: Unique identifier (SHA256 of title + date + url).
  - `title`, `start`, `url`, `description`, `source`.

- **`users_events`**: Join table for personalized recommendations.
  - `user_id`, `event_hash`.
  - `relevance_score`: LLM-assigned relevance.
  - `relevance_reason`: LLM explanation.
  - `is_sent`: Tracks if the event has been emailed to the user.
  - *Note: the schema exists but the digest pipeline does not yet write to this table.*

Legacy SQLite user/session tables remain during the migration but are not the
production subscriber source of truth. The scheduled runner's D1 backend reads
active recipient/profile rows directly from Cloudflare's authenticated D1 API
and fails closed rather than using a fallback recipient when D1 is unavailable
or empty.

## Quick Start

1. **Clone the repository**:

   ```bash
   git clone https://github.com/ryneandal/valencia-event-notifications.git
   cd valencia-event-notifications
   ```

2. **Install `uv`** (if not already installed):

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

   See [uv documentation](https://docs.astral.sh/uv/) for more details.

3. **Install dependencies**:

   ```bash
   uv sync --extra dev
   ```

4. **Run tests**:

   ```bash
   uv run pytest
   ```

5. **Run linters**:

   ```bash
   uv run ruff format --check .
   uv run ruff check .
   ```

6. **Run the Digest**:

   The workflow is exposed as a single CLI entry point:

   ```bash
   uv run valencia-events --help
   ```

   Common usage:

   ```bash
   # Run the full workflow (scrape -> normalize -> store -> email)
   uv run valencia-events

   # Target a single registered user
   uv run valencia-events --user-email your@email.com

   # Show command help
   uv run valencia-events --help
   ```

## Configuration

The email workflow requires:

- `SMTP_USER`: Email account for sending (e.g., Gmail)
- `SMTP_APP_PASSWORD`: App-specific password for SMTP
- `RECIPIENT_EMAIL`: Fallback recipient only when the explicitly selected
  subscriber backend is `sqlite`
- `SUBSCRIBER_BACKEND`: Required explicit choice of `d1` (production) or
  `sqlite` (local/test)
- `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_D1_DATABASE_ID`: Required for the D1
  subscriber backend
- `CLOUDFLARE_API_TOKEN`: Least-privilege D1 query credential; required for the
  D1 subscriber backend

Personalized ranking is optional and falls back to deterministic ranking if it is
unconfigured or a provider call fails. Configure one provider:

- `LLM_BACKEND`: `gemini`, `mistral`, or `openrouter`
- `GEMINI_API_KEY` (or `GOOGLE_API_KEY`), `MISTRAL_API_KEY`, or
  `OPENROUTER_API_KEY`: Credential for the selected backend
- `GEMINI_MODEL` / `GEMINI_FALLBACK_MODEL`, `MISTRAL_MODEL` /
  `MISTRAL_FALLBACK_MODEL`, or `OPENROUTER_MODEL` /
  `OPENROUTER_FALLBACK_MODEL`: Optional primary and fallback model overrides
- `FAMILY_PROFILE_JSON`: Optional JSON profile for ranking personalization
- `OPENROUTER_APP_URL` and `OPENROUTER_APP_TITLE`: Optional OpenRouter app
  attribution metadata

OpenRouter model IDs use `provider/model` slugs. Its default is
`openrouter/auto`; set `OPENROUTER_MODEL` when you need a fixed model, cost, or
data-policy choice. OpenRouter settings use process environment variables first
and fall back to `.env` in the current working directory. See `.env.example` for
complete examples.

For GitHub Actions, store credentials as repository secrets and backend/model
selection as repository variables. Never commit real keys to `.env` or source files.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for:

- How to write good issues
- Development setup
- Testing guidelines
- Code style requirements

## Cloudflare Frontend + Worker

The deployed interactive stack lives under [`cloudflare/`](cloudflare/):

- `cloudflare/pages/public/`: currently deployed static dashboard and React/Vite
  build destination.
- `cloudflare/pages/src/`: tested React personalization onboarding SPA, pending
  production deployment.
- `functions/`: same-origin `/api/*` Worker proxy discovered from the Pages
  project's repository root.
- `cloudflare/worker/src/`: deployed Python Worker API with canonical D1-backed
  subscriber/profile/session storage.
- `cloudflare/design-poc/`: approved Mediterranean/València visual reference.
- `cloudflare/tests/` and `tests/test_cloudflare_worker.py`: frontend, proxy, and
  Worker behavior tests.

Email-only authentication remains the deployed development integration path.
Verified magic-link code is implemented and tested, and its D1 migration is
applied, but it still needs provider configuration and Worker deployment. The D1 subscriber loader is
also implemented and tested but needs production credentials and a successful
scheduled run.

Run Cloudflare tests:

```bash
cd cloudflare
pnpm install
pnpm test
```

## Project Structure

```plaintext
valencia-event-notifications/
├── src/
│   ├── valencia_events/      # Main application package
│   │   ├── cli.py            # CLI entry point
│   │   ├── services.py       # Core services
│   │   ├── filters.py        # Event filtering logic
│   │   ├── models.py         # Pydantic data models
│   │   ├── normalize.py      # Data normalization
│   │   ├── storage.py        # SQLite storage layer
│   │   ├── mailer.py         # Email functionality
│   │   ├── logger.py         # Logging config
│   │   └── templates/        # Email templates
│   └── scrapers/             # Scrapy project package
│       └── valencia_events/
│           ├── spiders/
│           ├── items.py
│           ├── pipelines.py
│           └── settings.py
├── scrapy.cfg                # Scrapy configuration
├── cloudflare/               # Pages SPA, API proxy, Python Worker, D1 schema
├── specs/                    # Product and architecture contracts
├── targets/                  # Local artifacts (HTML/JSON dumps)
├── tests/                    # Test suite
├── .github/workflows/        # GitHub Actions
├── pyproject.toml            # Project configuration
└── events.db                 # SQLite database
```

## License

MIT License - see LICENSE file for details

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on how to submit well-scoped, testable issues and pull requests.
