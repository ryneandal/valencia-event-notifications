"""Tests for RSS feed spider.

Test acceptance criteria:
- Spider produces at least one item with non-empty title
- Spider produces valid ISO datetime string in 'start' field
- Spider respects robots.txt
- DOWNLOAD_DELAY <= 1 second
"""

import pytest


class TestRSSSpider:
    """Test suite for RSS feed spider."""

    @pytest.fixture
    def spider(self):
        """Create spider instance for testing."""
        # TODO: Import and instantiate RSS spider
        # from scrapers.valencia_events.spiders.rss_spider import RSSSpider
        # return RSSSpider()
        pytest.skip("RSS spider not yet implemented")

    @pytest.fixture
    def rss_fixture(self):
        """Load RSS XML fixture."""
        # TODO: Load tests/fixtures/valencia_rss.xml
        pytest.skip("RSS fixture not yet created")

    def test_spider_produces_items(self, spider, rss_fixture):
        """Test that spider produces items from RSS feed."""
        # TODO: Implement test
        # - Create fake response from fixture
        # - Call spider.parse()
        # - Assert at least one item yielded
        # - Assert item has non-empty title
        # - Assert item has valid datetime in start field
        pytest.skip("Test not yet implemented")

    def test_spider_settings(self, spider):
        """Test spider has correct settings."""
        # TODO: Verify DOWNLOAD_DELAY <= 1
        pytest.skip("Test not yet implemented")
