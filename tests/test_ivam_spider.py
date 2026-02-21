"""Tests for IVAM spider."""

from pathlib import Path

from scrapy.http import HtmlResponse

from scrapers.valencia_events.items import RawEventItem
from scrapers.valencia_events.spiders.ivam_spider import IVAMSpider

FIXTURE = Path("tests/fixtures/ivam_agenda.html")


def test_parse_ivam_items():
    spider = IVAMSpider()
    response = HtmlResponse(
        url="https://ivam.es/es/agenda/",
        body=FIXTURE.read_bytes(),
        encoding="utf-8",
    )

    results = list(spider.parse(response))
    items = [r for r in results if isinstance(r, RawEventItem)]

    assert len(items) == 1
    first = items[0]
    assert first["title"] == "Visita comentada"
    assert first["url"] == "https://ivam.es/es/eventos/visita-comentada"
    assert first["start"] == "2025-10-28T12:00:00+01:00"
    assert first["source"] == "ivam"
