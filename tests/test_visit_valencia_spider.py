"""Tests for Visit Valencia spider parsing event cards and pagination."""

from pathlib import Path

import pytest
from scrapy.http import HtmlResponse, Request

from scrapers.valencia_events.items import RawEventItem
from scrapers.valencia_events.spiders.visit_valencia_spider import (
    VisitValenciaSpider,
)

FIXTURE_PATH = Path("tests/fixtures/visit_valencia_events.html")


@pytest.fixture
def spider() -> VisitValenciaSpider:
    """Instantiate the spider for tests."""
    return VisitValenciaSpider()


@pytest.fixture
def response() -> HtmlResponse:
    """Build a fake HtmlResponse from the cached fixture."""
    body = FIXTURE_PATH.read_bytes()
    return HtmlResponse(
        url="https://www.visitvalencia.com/en/agenda-convention-bureau?page=0",
        body=body,
        encoding="utf-8",
    )


def test_parse_cards_extracts_items(
    spider: VisitValenciaSpider,
    response: HtmlResponse,
):
    """Ensure event cards are parsed into RawEventItems."""
    results = list(spider.parse(response))
    items = [r for r in results if isinstance(r, RawEventItem)]

    assert len(items) == 93

    first = items[0]
    assert (
        first["title"]
        == "What to do in Valencia this Christmas: ice rink, train and carousel"
    )
    assert first["start"] == "From 28/11/2025 to 06/01/2026"
    assert (
        first["url"]
        == "https://www.visitvalencia.com/en/events-valencia/skating-rink-plaza-del-ayuntamiento"
    )
    assert first["description"] == "Pista patinaje Valencia.jpg"
    assert first["source"] == "visit_valencia"


def test_parse_follows_next_page(spider: VisitValenciaSpider, response: HtmlResponse):
    """Ensure the spider enqueues the next pagination link."""
    results = list(spider.parse(response))
    next_requests = [r for r in results if isinstance(r, Request)]

    assert not next_requests, "Fixture has no pagination links"
