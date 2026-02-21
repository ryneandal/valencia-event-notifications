"""Tests for Les Arts spider."""

from pathlib import Path

from scrapy.http import HtmlResponse

from scrapers.valencia_events.items import RawEventItem
from scrapers.valencia_events.spiders.les_arts_spider import LesArtsSpider

FIXTURE = Path("tests/fixtures/les_arts_agenda.html")


def test_parse_les_arts_items():
    spider = LesArtsSpider()
    response = HtmlResponse(
        url="https://www.lesarts.com/es/agenda/",
        body=FIXTURE.read_bytes(),
        encoding="utf-8",
    )

    results = list(spider.parse(response))
    items = [r for r in results if isinstance(r, RawEventItem)]

    assert len(items) == 1
    first = items[0]
    assert first["title"] == "La Traviata"
    assert first["url"] == "https://www.lesarts.com/es/agenda/la-traviata"
    assert first["start"] == "2025-11-03T20:00:00+01:00"
    assert first["source"] == "les_arts"
