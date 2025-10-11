"""Scrapy items for Valencia Events.

Defines the data structures for scraped event information.
"""

import scrapy


class RawEventItem(scrapy.Item):
    """Raw event item scraped from various sources.
    
    Fields:
        title (str): Event title/name
        start (str): Event start date/time (raw string to be normalized)
        url (str): URL to event details page
        description (str): Event description text
        source (str): Source identifier (e.g., 'sala_russafa', 'rss_feed')
    """
    title = scrapy.Field()
    start = scrapy.Field()
    url = scrapy.Field()
    description = scrapy.Field()
    source = scrapy.Field()
