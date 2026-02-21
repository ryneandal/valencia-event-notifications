"""Tests for Palau de la Musica spider."""

from pathlib import Path

from scrapy.http import HtmlResponse

from scrapers.valencia_events.items import RawEventItem
from scrapers.valencia_events.spiders.palau_musica_spider import PalauMusicaSpider

FIXTURE = Path("tests/fixtures/palau_musica_calendar.html")


def test_parse_palau_items():
    spider = PalauMusicaSpider()
    response = HtmlResponse(
        url="https://palauvalencia.com/calendar/",
        body=FIXTURE.read_bytes(),
        encoding="utf-8",
    )

    results = list(spider.parse(response))
    items = [r for r in results if isinstance(r, RawEventItem)]

    assert len(items) == 1
    first = items[0]
    assert first["title"] == "Concierto Sinfónico de Otoño"
    assert first["url"] == "https://palauvalencia.com/eventos/sinfonico-otono"
    assert first["start"] == "2025-10-20T19:30:00+02:00"
    assert first["source"] == "palau_musica"
