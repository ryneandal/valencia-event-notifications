"""Event scrapers for various sources."""

import logging
from abc import ABC, abstractmethod
from datetime import datetime

import feedparser

from .models import Event

logger = logging.getLogger(__name__)


class EventScraper(ABC):
    """Base class for event scrapers."""

    @abstractmethod
    def scrape(self) -> list[Event]:
        """Scrape events from the source.

        Returns:
            List of scraped events
        """
        pass


class RSSFeedScraper(EventScraper):
    """Scraper for RSS feeds."""

    def __init__(self, feed_url: str, source_name: str, neighborhood: str = None):
        """Initialize RSS feed scraper.

        Args:
            feed_url: URL of the RSS feed
            source_name: Name of the source
            neighborhood: Neighborhood name (e.g., La Roqueta, Russafa)
        """
        self.feed_url = feed_url
        self.source_name = source_name
        self.neighborhood = neighborhood

    def scrape(self) -> list[Event]:
        """Scrape events from RSS feed."""
        events = []
        try:
            feed = feedparser.parse(self.feed_url)

            for entry in feed.entries:
                try:
                    # Extract event data from RSS entry
                    title = entry.get("title", "")
                    description = entry.get("description", "") or entry.get("summary", "")
                    link = entry.get("link", "")

                    # Try to parse published date as event date
                    start_time = None
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        start_time = datetime(*entry.published_parsed[:6])
                    elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                        start_time = datetime(*entry.updated_parsed[:6])

                    if start_time:
                        event = Event(
                            title=title,
                            description=description,
                            location=None,
                            start_time=start_time,
                            end_time=None,
                            url=link,
                            source=self.source_name,
                            neighborhood=self.neighborhood,
                        )
                        events.append(event)
                except Exception as e:
                    logger.warning(f"Error parsing RSS entry: {e}")
                    continue

            logger.info(f"Scraped {len(events)} events from {self.source_name}")
        except Exception as e:
            logger.error(f"Error scraping RSS feed {self.feed_url}: {e}")

        return events


class ValenciaCulturalAgendaScraper(EventScraper):
    """Scraper for Valencia cultural agenda (example placeholder)."""

    def __init__(self):
        """Initialize Valencia cultural agenda scraper."""
        self.source_name = "Valencia Cultural Agenda"

    def scrape(self) -> list[Event]:
        """Scrape events from Valencia cultural agenda.

        Note: This is a placeholder. In a real implementation, this would:
        1. First try to find an RSS feed or API
        2. Fall back to HTML scraping with Scrapy if needed
        3. Filter for La Roqueta and Russafa neighborhoods
        """
        events = []
        logger.info(f"Scraping from {self.source_name} (placeholder)")
        # Placeholder - in reality, implement actual scraping logic here
        return events


class TimeOutValenciaScraper(EventScraper):
    """Scraper for TimeOut Valencia events (example placeholder)."""

    def __init__(self):
        """Initialize TimeOut Valencia scraper."""
        self.source_name = "TimeOut Valencia"

    def scrape(self) -> list[Event]:
        """Scrape events from TimeOut Valencia.

        Note: This is a placeholder. In a real implementation, this would:
        1. Check for RSS feed or API endpoints
        2. Use Scrapy spider for HTML scraping as fallback
        3. Filter for downtown Valencia events
        """
        events = []
        logger.info(f"Scraping from {self.source_name} (placeholder)")
        # Placeholder - in reality, implement actual scraping logic here
        return events


def get_all_scrapers() -> list[EventScraper]:
    """Get all configured event scrapers.

    Returns:
        List of event scraper instances
    """
    scrapers = []

    # Add Valencia cultural agenda scraper
    scrapers.append(ValenciaCulturalAgendaScraper())

    # Add TimeOut Valencia scraper
    scrapers.append(TimeOutValenciaScraper())

    # Add more scrapers as needed
    # Example: scrapers.append(RSSFeedScraper("https://example.com/rss", "Example Source"))

    return scrapers
