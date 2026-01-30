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
   uv sync
   ```

4. **Run tests**:
   ```bash
   uv run pytest
   ```

5. **Run linters**:
   ```bash
   uv run black .
   uv run isort .
   uv run ruff check .
   ```

6. **Run the Digest**:
   The workflow is managed via a CLI app (using `typer`):
   ```bash
   uv run runner.py --help
   ```

   Common commands:
   ```bash
   # Run the full workflow (scrape -> normalize -> send)
   uv run runner.py
   
   # Only scrape events
   uv run runner.py scrape
   
   # Send test email
   uv run runner.py send-test-email --to your@email.com
   ```

## Configuration

The following environment variables are required for the full workflow:

- `SMTP_USER`: Email account for sending (e.g., Gmail)
- `SMTP_APP_PASSWORD`: App-specific password for SMTP
- `RECIPIENT_EMAIL`: Email address to receive digests
- `EVENTBRITE_TOKEN`: (Optional) API token for Eventbrite events

For GitHub Actions, these should be set as repository secrets.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for:
- How to write good issues
- Development setup
- Testing guidelines
- Code style requirements

## Project Structure

```
valencia-event-notifications/
├── scrapers/                  # Scrapy project
│   ├── valencia_events/
│   │   ├── spiders/          # Spider implementations
│   │   │   └── visit_valencia_spider.py
│   │   ├── items.py          # Scrapy item definitions
│   │   ├── pipelines.py      # Scrapy pipelines
│   │   └── settings.py       # Scrapy settings
│   └── scrapy.cfg            # Scrapy configuration
├── targets/                  # Local artifacts (HTML/JSON dumps) from runs
├── models.py                 # Pydantic data models
├── normalize.py              # Data normalization logic
├── storage.py                # SQLite storage layer
├── mailer.py                 # Email functionality
├── runner.py                 # Main orchestrator (CLI)
├── logger.py                 # Logging configuration
├── tests/                    # Test suite
│   ├── fixtures/            # Test fixtures
│   └── test_*.py            # Test modules
├── .github/workflows/        # GitHub Actions
├── pyproject.toml           # Project configuration
└── requirements.txt         # Dependencies
```

## License

MIT License - see LICENSE file for details

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on how to submit well-scoped, testable issues and pull requests.
