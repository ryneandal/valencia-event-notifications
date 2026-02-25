"""Spider for Palau de la Musica event listings."""

from __future__ import annotations

import html
from collections.abc import Iterable
from urllib.parse import parse_qs, urlparse

import scrapy
from scrapy.http import Response
from w3lib.html import remove_tags

from scrapers.valencia_events.items import RawEventItem


class PalauMusicaSpider(scrapy.Spider):
    """Scrape Palau de la Musica calendar pages."""

    name = "palau_musica"
    allowed_domains = ["palauvalencia.com", "www.palauvalencia.com"]
    start_urls = ["https://palauvalencia.com/programacio-i-vendes/"]
    custom_settings = {"DOWNLOAD_DELAY": 1}

    def parse(self, response: Response, **kwargs):
        selectors = response.css("div[id^='event-'].card_container")
        if selectors:
            for node in selectors:
                title_raw = self._clean(node.css(".event-title::text").getall())
                title = self._clean([remove_tags(html.unescape(title_raw))])
                event_url = node.css("a[href*='/event?id=']::attr(href)").get()
                ticket_url = node.css("a[href*='webfecha=']::attr(href)").get()

                start = self._extract_start(ticket_url)
                description = self._clean(node.css(".card-text::text").getall())

                if title and event_url and start:
                    yield RawEventItem(
                        title=title,
                        start=start,
                        url=response.urljoin(event_url),
                        description=description,
                        source=self.name,
                    )
            return

        # Backward-compatible parsing path used by unit-test fixtures.
        for node in response.css("article.tribe-events-calendar-list__event-row"):
            title = self._clean(
                node.css(".tribe-events-calendar-list__event-title a::text").getall()
            )
            event_url = node.css(
                ".tribe-events-calendar-list__event-title a::attr(href)"
            ).get()
            start = (node.css("time::attr(datetime)").get() or "").strip()
            description = self._clean(
                node.css(
                    ".tribe-events-calendar-list__event-description::text"
                ).getall()
            )

            if title and event_url and start:
                yield RawEventItem(
                    title=title,
                    start=start,
                    url=response.urljoin(event_url),
                    description=description,
                    source=self.name,
                )

    @staticmethod
    def _clean(parts: Iterable[str]) -> str:
        joined = " ".join(part.strip() for part in parts if part and part.strip())
        return " ".join(joined.split())

    def _extract_start(self, ticket_url: str | None) -> str:
        if not ticket_url:
            return ""

        parsed = urlparse(ticket_url)
        params = parse_qs(parsed.query)
        date = params.get("webfecha", [""])[0]
        hour = params.get("webhora", [""])[0]
        if not date:
            return ""
        if hour:
            return f"{date} {hour}"
        return date
