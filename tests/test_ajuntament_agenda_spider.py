"""Tests for Ajuntament agenda spider."""

from pathlib import Path

from scrapy.http import HtmlResponse

from scrapers.valencia_events.items import RawEventItem
from scrapers.valencia_events.spiders.ajuntament_agenda_spider import (
    AjuntamentAgendaSpider,
)

FIXTURE = Path("tests/fixtures/ajuntament_agenda.html")


def test_parse_ajuntament_embedded_events():
    spider = AjuntamentAgendaSpider()
    response = HtmlResponse(
        url="https://www.valencia.es/cas/agenda-de-la-ciudad",
        body=FIXTURE.read_bytes(),
        encoding="utf-8",
    )

    results = list(spider.parse(response))
    items = [r for r in results if isinstance(r, RawEventItem)]

    assert len(items) == 2

    first = items[0]
    assert first["title"] == "Teatro familiar en el centro"
    assert first["url"].startswith(
        "https://www.valencia.es/cas/agenda-de-la-ciudad/-/content/"
    )
    assert first["source"] == "ajuntament_agenda"
    assert "TEATRO" in first["description"]

    second = items[1]
    assert second["url"] == "https://www.valencia.es/cas/agenda-evento/concierto-peques"
