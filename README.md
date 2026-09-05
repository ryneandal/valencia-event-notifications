# Valencia Event Notifications

Receive email notifications about events happening in València, Spain every day.

## Overview

This project collects event information from sources around València and sends a
personalized next-day digest. The deployed registration platform uses Cloudflare
Pages, Workers, D1, and Mailgun. The Cloudflare Worker now contains the scheduled
collection, ranking, rendering, and idempotency path; delivery remains disabled
by default while the final controlled production smoke is completed. The
existing Scrapy/SQLite/SMTP command is local reference tooling only.

## Features

- 🕷️ **Web Scraping**: Scrapy-based spiders for multiple event sources
- 📅 **Daily Digest**: Automated emails with tomorrow's events
- 🔄 **Deduplication**: Hash-based event deduplication in SQLite
- 🌍 **Timezone Aware**: Proper handling of Europe/Madrid timezone
- ☁️ **Cloudflare-native production**: Pages, Workers, D1, Cron Triggers, and Mailgun
- ✅ **Type Safe**: Pydantic models with full type hints

## Project Status

**Current Stage**: Active Development 🚀

The project core is implemented and running:

- ✅ Scrapy spiders for 8 sources (Visit Valencia, Ajuntament agenda, Palau de la Música, Les Arts, IVAM, València Secreta, Valencia Bonita, generic RSS)
- ✅ Date parsing and normalization
- ✅ SQLite storage with deduplication
- ✅ LLM-based event ranking per user (Gemini, Mistral, or OpenRouter via LangChain)
- ✅ Email generation (Jinja2 templates) and sending (SMTP)
- ✅ Cloudflare Pages, Python Worker, D1, and the same-origin API proxy are deployed
- ✅ React personalization, verified magic links, and branded Mailgun delivery are live
- ✅ A verified production profile with the complete personalization shape is stored in D1
- ✅ Worker-native event collection, OpenRouter ranking with deterministic
  fallback, branded digest rendering, D1 history, and safe authenticated preview
- 🚧 Worker runtime/CPU confirmation, custom Mailgun domain, authenticated
  provider preview, and one controlled live digest remain before delivery cutover

See [task.md](task.md) for current tasks and [AGENTS.md](AGENTS.md) for AI coding agent guidelines.

## Architecture

```text
React onboarding on Cloudflare Pages [deployed]
  -> same-origin Pages Function
  -> Python Worker
  -> D1 subscriber/profile store

Cloudflare Cron Trigger [deployed; delivery disabled by default]
  -> scheduled Worker -> event-source fetch/normalization
  -> D1 events, active subscribers, and delivery history
  -> OpenRouter ranking (Nemotron default)
  -> Mailgun HTML digest
```

Cloudflare owns the complete target production platform. The local Python
pipeline remains migration/reference code, not the final scheduler. See
[specs/architecture.md](specs/architecture.md) for deployment state, trust
boundaries, and failure behavior.

The local Scrapy spiders deliberately stop at extraction. Raw-item validation is
owned by `valencia_events.source_filters.should_keep_raw_event` when
`run_scrapers()` combines their feeds; normalization then creates the validated
Pydantic event. The old Scrapy item pipeline was removed to avoid enforcing the
same required fields twice. Sala Russafa was never a configured source and its
synthetic placeholder fixture has been retired; adding it later requires a new
captured fixture and source review.

## Data Schema

The system deliberately separates subscriber and batch-processing state.

Cloudflare D1 is the canonical production store for subscribers:

- **`users`**: Verified email, serialized personalization profile, verification
  state, and creation metadata.
- **`subscriptions`**: Reversible digest delivery state, separate from verified
  account/session state.
- **session and verification tables**: Worker-owned authentication state that is
  never exposed to the digest or an LLM.

The local reference command uses SQLite (`events.db`) for event processing:

- **`events`**: Stores unique events found by scrapers.
  - `event_hash`: Unique identifier (SHA256 of title + date + url).
  - `title`, `start`, `url`, `description`, `source`.

The scheduled Cloudflare Worker stores event, recommendation, run, and delivery
history in D1. Retained SQLite users exist only to exercise the local CLI; local
sessions and the unused local recommendation join table have been removed.

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

6. **Run the local reference digest**:

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

The local reference email workflow can use:

- `SMTP_USER`: Email account for sending (e.g., Gmail)
- `SMTP_APP_PASSWORD`: App-specific password for SMTP
- `RECIPIENT_EMAIL`: Optional local fallback recipient

Personalized ranking is optional and falls back to deterministic ranking if it is
unconfigured or a provider call fails. Configure one provider:

- `LLM_BACKEND`: `openrouter` (default), `gemini`, or `mistral`
- `GEMINI_API_KEY` (or `GOOGLE_API_KEY`), `MISTRAL_API_KEY`, or
  `OPENROUTER_API_KEY`: Credential for the selected backend
- `GEMINI_MODEL` / `GEMINI_FALLBACK_MODEL`, `MISTRAL_MODEL` /
  `MISTRAL_FALLBACK_MODEL`, or `OPENROUTER_MODEL` /
  `OPENROUTER_FALLBACK_MODEL`: Optional primary and fallback model overrides
- `FAMILY_PROFILE_JSON`: Optional JSON profile for ranking personalization
- `OPENROUTER_APP_URL` and `OPENROUTER_APP_TITLE`: Optional OpenRouter app
  attribution metadata

OpenRouter model IDs use `provider/model` slugs. Its default is
`nvidia/nemotron-3-ultra-550b-a55b:free`; set `OPENROUTER_MODEL` to override the
model, cost, or data-policy choice. OpenRouter settings use process environment
variables first and fall back to `.env` in the current working directory. See
`.env.example` for complete examples.

The production scheduled Worker reads OpenRouter and Mailgun credentials only
from Cloudflare Worker secrets. `DIGEST_DELIVERY_ENABLED` remains `false` until
the controlled smoke succeeds; scheduled runs collect, rank (or fall back),
persist, and render without sending. The old GitHub Actions digest workflow has
been removed. Never commit real keys to `.env` or source files.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for:

- How to write good issues
- Development setup
- Testing guidelines
- Code style requirements

## Cloudflare Frontend + Worker

The deployed interactive stack lives under [`cloudflare/`](cloudflare/):

- `cloudflare/pages/public/`: deployed React/Vite build destination.
- `cloudflare/pages/src/`: production React personalization onboarding SPA.
- `functions/`: same-origin `/api/*` Worker proxy discovered from the Pages
  project's repository root.
- `cloudflare/worker/src/`: deployed Python Worker API with canonical D1-backed
  subscriber/profile/session storage.
- `cloudflare/design-poc/`: approved Mediterranean/València visual reference.
- `cloudflare/tests/` and `tests/test_cloudflare_worker.py`: frontend, proxy, and
  Worker behavior tests.

Verified magic-link authentication and the Cloudflare-native scheduled digest
pipeline are implemented. The account screen can run an authenticated preview
for only the current subscriber, and the scheduled trigger is fail-closed in
dry-run mode until production delivery is explicitly enabled.

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
├── .github/workflows/        # Continuous integration
├── pyproject.toml            # Project configuration
└── events.db                 # SQLite database
```

## License

MIT License - see LICENSE file for details

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on how to submit well-scoped, testable issues and pull requests.
