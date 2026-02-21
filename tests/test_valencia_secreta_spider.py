"""Tests for Valencia Secreta spider."""

from pathlib import Path

from scrapy.http import HtmlResponse

from scrapers.valencia_events.items import RawEventItem
from scrapers.valencia_events.spiders.valencia_secreta_spider import (
    ValenciaSecretaSpider,
)

FIXTURE = Path("tests/fixtures/valencia_secreta_agenda.html")


def test_parse_valencia_secreta_items():
    spider = ValenciaSecretaSpider()
    response = HtmlResponse(
        url="https://valenciasecreta.com/",
        body=FIXTURE.read_bytes(),
        encoding="utf-8",
    )

    results = list(spider.parse(response))
    items = [r for r in results if isinstance(r, RawEventItem)]

    assert len(items) == 2
    first = items[0]
    assert first["title"] == "Mercado nocturno en Ruzafa"
    assert first["url"] == "https://valenciasecreta.com/mercado-nocturno-valencia/"
    assert first["start"] == "2025-10-26T18:00:00+01:00"
    assert first["source"] == "valencia_secreta"
