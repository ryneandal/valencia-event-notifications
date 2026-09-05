# Contributing to Valencia Event Notifications

Thank you for your interest in contributing! This project follows GitHub Copilot best practices for AI-assisted development.

## How to Write Good Issues

When creating issues for this project, please follow this template to ensure Copilot can produce focused, testable work:

### Issue Template

**Title**: `<file_path> — <brief description>`

Example: `src/scrapers/valencia_events/spiders/new_venue_spider.py — add spider`

**Goal** (one sentence):
What should be implemented?

**Success Criteria / Tests**:
- Exact unit tests or example inputs/outputs that will verify the feature
- Include expected test file paths

**Files to Create/Edit**:
- List exact paths in the repo
- Example: `src/scrapers/valencia_events/spiders/new_venue_spider.py`
- Example: `tests/test_new_venue_spider.py`
- Example: `tests/fixtures/new_venue.html`

**Constraints**:
- Allowed libraries (e.g., `Scrapy` only)
- Performance constraints (e.g., `DOWNLOAD_DELAY <= 1s`)
- Security restrictions (no secrets in code, use `os.environ`)
- Specific patterns to follow (e.g., respect `robots.txt`)

**Style**:
- Python 3.11
- Type hints required
- Pydantic for models
- Format and lint with Ruff

## Example Good Issue

**Title**: `normalize.py — implement date parsing`

**Goal**: Implement `normalize_raw()` and `parse_datetime()` functions to convert raw scraped items into validated Event models with timezone-aware datetimes.

**Success Criteria**:
- `pytest tests/test_normalize.py` passes
- Handles ISO 8601 strings
- Handles `"DD/MM/YYYY HH:MM"` format
- Handles Spanish month names: `"DD de mes de YYYY HH:MM"`
- Handles RFC 822 (RSS feeds)
- All datetimes converted to `Europe/Madrid` timezone
- Invalid dates raise `ValueError`

**Files**:
- Edit: `normalize.py`
- Edit: `tests/test_normalize.py` (add actual test implementations)

**Constraints**:
- Use `pytz` for timezone handling
- Use `pydantic` for validation
- Read secrets from `os.environ` only

**Style**:
- Python 3.11 with type hints
- Format with Black (line length 88)
- Lint with Ruff

## Example Bad Issue

❌ "Build the entire scraping system"
- Too broad, no specific tests
- No file paths specified
- No constraints or examples

## Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/ryneandal/valencia-event-notifications.git
   cd valencia-event-notifications
   ```

2. Create virtual environment:
   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Run tests:
   ```bash
   pytest
   ```

5. Run linters:
   ```bash
   black .
   isort .
   ruff check .
   ```

## Testing Guidelines

- Keep test fixtures small and representative
- Store cached HTML/XML in `tests/fixtures/`
- No network calls in tests (use fixtures and mocks)
- Each test should verify one specific behavior
- Use descriptive test names

## Security

- **Never** commit secrets (passwords, tokens, keys)
- Use environment variables for all credentials
- GitHub Secrets for CI/CD workflows:
  - `SMTP_USER`
  - `SMTP_APP_PASSWORD`
  - `RECIPIENT_EMAIL`
  - `EVENTBRITE_TOKEN`

## Code Style

This project uses:
- **Black** for formatting (line length 88)
- **isort** for import sorting
- **Ruff** for linting
- **pytest** for testing
- **Type hints** throughout (Python 3.11+)
- **Pydantic** for data models

Run before committing:
```bash
black .
isort .
ruff check .
pytest
```

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
├── runner.py                 # Main orchestrator
├── tests/                    # Test suite
│   ├── fixtures/            # Test fixtures (HTML, XML, etc.)
│   ├── test_rss_spider.py
│   ├── test_normalize.py
│   ├── test_storage.py
│   └── test_mailer.py
├── .github/workflows/        # GitHub Actions
│   ├── ci.yml               # Tests and linting
│   └── nightly_digest.yml   # Daily digest workflow
├── pyproject.toml           # Project configuration
├── requirements.txt         # Python dependencies
└── scrapy.cfg              # Scrapy configuration
```

## Questions?

Open an issue following the template above, or reach out to the maintainers.
