"""Tests for RSS feed spider."""

from pathlib import Path

import pytest
from scrapy.http import TextResponse

from scrapers.valencia_events.items import RawEventItem
from scrapers.valencia_events.spiders.rss_spider import RSSSpider

AJUNTAMENT_FIXTURE = Path("tests/fixtures/ajuntament_rss.xml")
ELPERIODIC_FIXTURE = Path("tests/fixtures/elperiodic_valencia_rss.xml")
ATOM_FIXTURE = Path("tests/fixtures/atom_events.xml")


def _response_from_fixture(path: Path, url: str) -> TextResponse:
    return TextResponse(
        url=url,
        body=path.read_bytes(),
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("fixture", "url", "source"),
    [
        (
            AJUNTAMENT_FIXTURE,
            "https://www.valencia.es/agenda.xml",
            "ajuntament_rss",
        ),
        (
            ELPERIODIC_FIXTURE,
            "https://www.elperiodic.com/feed/rss_valencia.xml",
            "elperiodic_rss",
        ),
    ],
)
def test_spider_produces_items(fixture: Path, url: str, source: str):
    spider = RSSSpider(feed_url=url, source=source)
    response = _response_from_fixture(fixture, url)

    results = list(spider.parse(response))
    items = [r for r in results if isinstance(r, RawEventItem)]

    assert len(items) >= 1
    first = items[0]
    assert first["title"]
    assert first["url"].startswith("http")
    assert first["source"] == source
    assert "T" in first["start"] or "+" in first["start"]


def test_spider_settings():
    spider = RSSSpider(feed_url="https://example.com/feed.xml", source="rss_test")
    assert spider.custom_settings["DOWNLOAD_DELAY"] <= 1


def test_spider_handles_atom_entry_feed():
    spider = RSSSpider(feed_url="https://example.com/atom.xml", source="atom_source")
    response = _response_from_fixture(ATOM_FIXTURE, "https://example.com/atom.xml")

    results = list(spider.parse(response))
    items = [r for r in results if isinstance(r, RawEventItem)]

    assert len(items) == 1
    first = items[0]
    assert first["title"] == "Atom Family Workshop"
    assert first["url"] == "https://example.com/atom-workshop"
    assert first["source"] == "atom_source"
