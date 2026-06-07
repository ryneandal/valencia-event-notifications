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

- ✅ Scrapy spiders for gathering events (Visit Valencia)
- ✅ Date parsing and normalization
- ✅ SQLite storage with deduplication
- ✅ Email generation (Jinja2 templates) and sending (SMTP)
- ✅ Periodic execution via GitHub Actions

See [task.md](task.md) for current tasks and [AGENTS.md](AGENTS.md) for AI coding agent guidelines.

## Architecture

```
┌─────────────┐
│   Scrapers  │  Scrapy spiders collect raw events
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Normalizer  │  Parse dates, validate data → Event models
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Storage   │  SQLite with deduplication
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Mailer    │  Build HTML, send via SMTP
└─────────────┘
```

## Data Schema

The project uses SQLite (`events.db`) with the following schema:

- **`events`**: Stores unique events found by scrapers.
  - `event_hash`: Unique identifier (SHA256 of title + date + url).
  - `title`, `start`, `url`, `description`, `source`.

- **`users`**: User profiles for personalization.
  - `email`: User's email address.
  - `preferences`: Natural language description of interests (e.g., "hiking, art").
  - `is_active`: Subscription status.

- **`users_events`**: Join table for personalized recommendations.
  - `user_id`, `event_hash`.
  - `relevance_score`: LLM-assigned relevance.
  - `relevance_reason`: LLM explanation.
  - `is_sent`: Tracks if the event has been emailed to the user.

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

The following environment variables are required for the full workflow:

- `SMTP_USER`: Email account for sending (e.g., Gmail)
- `SMTP_APP_PASSWORD`: App-specific password for SMTP
- `RECIPIENT_EMAIL`: Email address to receive digests
- `GEMINI_API_KEY` or `GOOGLE_API_KEY`: Enable Gemini-based event ranking
- `MISTRAL_API_KEY`: Enable Mistral-based event ranking
- `LLM_BACKEND`: Optional override (`gemini` or `mistral`)
- `FAMILY_PROFILE_JSON`: Optional JSON profile for ranking personalization
- `GEMINI_MODEL`, `GEMINI_FALLBACK_MODEL`, `MISTRAL_MODEL`, `MISTRAL_FALLBACK_MODEL`: Optional model overrides

For GitHub Actions, these should be set as repository secrets.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for:

- How to write good issues
- Development setup
- Testing guidelines
- Code style requirements

## Cloudflare Frontend + Worker

A Cloudflare-compatible user dashboard implementation is available under [`cloudflare/`](cloudflare/):

- `cloudflare/pages/public/`: Static Pages frontend (register/login/preferences UI).
- `cloudflare/worker/src/`: Python Worker API (`/api/register`, `/api/login`, `/api/me`, `/api/preferences`, `/api/logout`) with D1-compatible schema.
- `cloudflare/tests/`: Frontend interaction tests for the static dashboard.
- `tests/test_cloudflare_worker.py`: Pytest coverage for the Worker API behavior.

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
