"""Scrapy settings for Valencia Events project.

For more information about settings see:
https://docs.scrapy.org/en/latest/topics/settings.html
"""

BOT_NAME = "valencia_events"

SPIDER_MODULES = ["scrapers.valencia_events.spiders"]
NEWSPIDER_MODULE = "scrapers.valencia_events.spiders"

# Crawl responsibly by identifying yourself
USER_AGENT = (
    "valencia_events (+https://github.com/ryneandal/valencia-event-notifications)"
)

# Obey robots.txt rules
ROBOTSTXT_OBEY = True

# Configure maximum concurrent requests
CONCURRENT_REQUESTS = 16

# Configure a delay for requests for the same website (default: 0)
DOWNLOAD_DELAY = 1

# Disable cookies (enabled by default)
COOKIES_ENABLED = False

# Disable Telnet Console (enabled by default)
TELNETCONSOLE_ENABLED = False

# Set settings whose default value is deprecated to a future-proof value
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
FEED_EXPORT_ENCODING = "utf-8"
