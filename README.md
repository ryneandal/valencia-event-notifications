# valencia-event-notifications

Receive email notifications about nearby events in downtown València every day.

This project automatically scrapes events from various sources for La Roqueta and Russafa neighborhoods, filters for tomorrow's events, and sends a daily HTML digest via email.

## Features

- 🔍 **Event Scraping**: Scrapes events from multiple sources (RSS/API preferred, HTML fallback with Scrapy)
- 📅 **Tomorrow Filtering**: Filters events for tomorrow in Europe/Madrid timezone
- 🗂️ **SQLite Storage**: Stores events with automatic deduplication
- 📧 **Email Digest**: Sends beautiful HTML email digest via Gmail SMTP
- 🤖 **GitHub Actions**: Runs nightly with scheduled and manual triggers
- 💾 **Artifact Management**: Database uploaded/downloaded between runs
- ✅ **Tested**: Comprehensive test suite with pytest

## Setup

### Prerequisites

- Python 3.9 or higher
- Gmail account with App Password for sending emails

### Installation

1. Clone the repository:
```bash
git clone https://github.com/ryneandal/valencia-event-notifications.git
cd valencia-event-notifications
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

### Configuration

The application requires the following environment variables:

- `GMAIL_USER`: Your Gmail address (e.g., `your-email@gmail.com`)
- `GMAIL_PASSWORD`: Your Gmail App Password ([How to create](https://support.google.com/accounts/answer/185833))
- `RECIPIENT_EMAIL`: Email address to send notifications to

For local testing, you can create a `.env` file:
```bash
export GMAIL_USER=your-email@gmail.com
export GMAIL_PASSWORD=your-app-password
export RECIPIENT_EMAIL=recipient@example.com
```

For GitHub Actions, set these as repository secrets.

## Usage

### Running Locally

```bash
# Run with default settings
python run.py

# Run with custom database path
python run.py --db-path /path/to/events.db

# Run with custom recipient email
python run.py --recipient-email someone@example.com

# Scrape events only (don't send email)
python run.py --scrape-only

# Skip email sending (for testing)
python run.py --skip-email
```

### GitHub Actions

The workflow runs automatically:
- **Scheduled**: Daily at 7 PM UTC (8 PM Madrid time in winter)
- **Manual**: Via workflow_dispatch with optional email skip

To configure:
1. Go to Settings → Secrets and variables → Actions
2. Add the required secrets:
   - `GMAIL_USER`
   - `GMAIL_PASSWORD`
   - `RECIPIENT_EMAIL`

## Project Structure

```
valencia-event-notifications/
├── .github/
│   └── workflows/
│       └── event-notifications.yml  # GitHub Actions workflow
├── valencia_events/
│   ├── __init__.py
│   ├── models.py          # Pydantic Event model
│   ├── database.py        # SQLite database layer
│   ├── scrapers.py        # Event scrapers (RSS/API/HTML)
│   ├── filters.py         # Event filtering logic
│   └── email_digest.py    # HTML email generation and sending
├── tests/
│   ├── __init__.py
│   ├── test_models.py
│   ├── test_database.py
│   ├── test_filters.py
│   └── test_email_digest.py
├── run.py                 # Main runner script
├── requirements.txt       # Production dependencies
├── requirements-dev.txt   # Development dependencies
├── pyproject.toml        # Project configuration
└── README.md
```

## Development

### Running Tests

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Run all tests
pytest

# Run with coverage
pytest --cov=valencia_events

# Run specific test file
pytest tests/test_models.py
```

### Code Quality

```bash
# Format code with black
black valencia_events/ tests/

# Lint with ruff
ruff check valencia_events/ tests/
```

## Event Model

Events are normalized to a Pydantic model:

```python
class Event(BaseModel):
    title: str                    # Event title
    description: Optional[str]    # Event description
    location: Optional[str]       # Event location
    start_time: datetime          # Event start time
    end_time: Optional[datetime]  # Event end time
    url: Optional[str]            # Event URL
    source: str                   # Source website
    neighborhood: Optional[str]   # La Roqueta, Russafa, etc.
```

## Adding New Event Sources

To add a new event scraper:

1. Create a new scraper class inheriting from `EventScraper`
2. Implement the `scrape()` method
3. Return a list of `Event` objects
4. Add to `get_all_scrapers()` in `scrapers.py`

Example:
```python
class NewSourceScraper(EventScraper):
    def scrape(self) -> List[Event]:
        # Your scraping logic here
        return events
```

## How It Works

1. **Scraping**: The runner script calls all configured scrapers
2. **Deduplication**: Events are deduplicated based on title, time, and location
3. **Storage**: New events are stored in SQLite database
4. **Filtering**: Events are filtered for tomorrow (Europe/Madrid timezone)
5. **Email**: HTML digest is generated and sent via Gmail SMTP
6. **Artifact**: Database is uploaded to GitHub Actions artifacts

## License

MIT

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
