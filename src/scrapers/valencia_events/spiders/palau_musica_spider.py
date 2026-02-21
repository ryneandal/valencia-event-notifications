"""Spider for Palau de la Musica event listings."""

from __future__ import annotations

from collections.abc import Iterable

import scrapy
from scrapy.http import Response

from scrapers.valencia_events.items import RawEventItem


class PalauMusicaSpider(scrapy.Spider):
    """Scrape Palau de la Musica calendar pages."""

    name = "palau_musica"
    allowed_domains = ["palauvalencia.com", "www.palauvalencia.com"]
    start_urls = ["https://palauvalencia.com/calendar/"]
    custom_settings = {"DOWNLOAD_DELAY": 1}

    def parse(self, response: Response, **kwargs):
        selectors = response.css("article, .tribe-events-calendar-list__event-row")
        for node in selectors:
            title = self._clean(
                node.css(
                    "h3 a::text, h2 a::text, "
                    ".tribe-events-calendar-list__event-title a::text"
                ).getall()
            )
            url = node.css(
                "h3 a::attr(href), h2 a::attr(href), "
                ".tribe-events-calendar-list__event-title a::attr(href)"
            ).get()
            start = node.css("time::attr(datetime)").get() or self._clean(
                node.css("time::text, .date::text").getall()
            )
            description = self._clean(
                node.css(
                    "p::text, .tribe-events-calendar-list__event-description::text"
                ).getall()
            )

            if title and url and start:
                yield RawEventItem(
                    title=title,
                    start=start,
                    url=response.urljoin(url),
                    description=description,
                    source=self.name,
                )

        next_href = response.css(
            "a.next::attr(href), .tribe-events-c-nav__next a::attr(href)"
        ).get()
        if next_href:
            yield response.follow(next_href, callback=self.parse)

    @staticmethod
    def _clean(parts: Iterable[str]) -> str:
        joined = " ".join(part.strip() for part in parts if part and part.strip())
        return " ".join(joined.split())
