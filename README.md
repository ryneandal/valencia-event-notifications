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

**Current Stage**: Scaffolding Complete ✅

The project structure is set up with stubs for all major components. Implementation is pending for:
- Spider implementations (RSS, Sala Russafa, etc.)
- Date parsing and normalization logic
- Database operations
- Email template and sending
- Main orchestrator workflow

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to contribute and [AGENTS.md](AGENTS.md) for AI coding agent guidelines.

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

## Quick Start

1. **Clone the repository**:
   ```bash
   git clone https://github.com/ryneandal/valencia-event-notifications.git
   cd valencia-event-notifications
   ```

2. **Set up Python environment** (requires Python 3.11+):
   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Run tests**:
   ```bash
   pytest
   ```

5. **Run linters**:
   ```bash
   black .
   isort .
   ruff check .
   ```

6. **Run the Digest**:
   The workflow is managed via a CLI:
   ```bash
   python runner.py main
   ```
   View available commands:
   ```bash
   python runner.py --help
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
│   └── valencia_events/
│       ├── spiders/          # Spider implementations
│       ├── items.py          # Scrapy item definitions
│       ├── pipelines.py      # Scrapy pipelines
│       └── settings.py       # Scrapy settings
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
