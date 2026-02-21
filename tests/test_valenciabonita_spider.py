"""Tests for ValenciaBonita spider."""

from pathlib import Path

from scrapy.http import HtmlResponse

from scrapers.valencia_events.items import RawEventItem
from scrapers.valencia_events.spiders.valenciabonita_spider import (
    ValenciaBonitaSpider,
)

FIXTURE = Path("tests/fixtures/valenciabonita_agenda.html")


def test_parse_valenciabonita_items():
    spider = ValenciaBonitaSpider()
    response = HtmlResponse(
        url="https://www.valenciabonita.es/",
        body=FIXTURE.read_bytes(),
        encoding="utf-8",
    )

    results = list(spider.parse(response))
    items = [r for r in results if isinstance(r, RawEventItem)]

    assert len(items) == 2
    first = items[0]
    assert first["title"] == "Ruta gastronómica por barrios"
    assert first["url"] == (
        "https://www.valenciabonita.es/2025/10/18/ruta-gastronomica-valencia/"
    )
    assert first["start"] == "2025-10-18T13:00:00+02:00"
    assert first["source"] == "valenciabonita"
