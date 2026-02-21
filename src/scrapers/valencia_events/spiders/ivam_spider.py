"""Spider for IVAM agenda pages."""

from __future__ import annotations

from collections.abc import Iterable

import scrapy
from scrapy.http import Response

from scrapers.valencia_events.items import RawEventItem


class IVAMSpider(scrapy.Spider):
    """Scrape IVAM events and agenda items."""

    name = "ivam"
    allowed_domains = ["ivam.es", "www.ivam.es"]
    start_urls = ["https://ivam.es/es/agenda/"]
    custom_settings = {"DOWNLOAD_DELAY": 1}

    def parse(self, response: Response, **kwargs):
        for node in response.css("article, .agenda-item, .event-item, li"):
            title = self._clean(node.css("h3 a::text, h2 a::text, a::text").getall())
            url = node.css("h3 a::attr(href), h2 a::attr(href), a::attr(href)").get()
            start = node.css("time::attr(datetime)").get() or self._clean(
                node.css("time::text, .date::text").getall()
            )
            description = self._clean(node.css("p::text").getall())

            if title and url and start:
                yield RawEventItem(
                    title=title,
                    start=start,
                    url=response.urljoin(url),
                    description=description,
                    source=self.name,
                )

        next_href = response.css("a.next::attr(href), a[rel='next']::attr(href)").get()
        if next_href:
            yield response.follow(next_href, callback=self.parse)

    @staticmethod
    def _clean(parts: Iterable[str]) -> str:
        joined = " ".join(part.strip() for part in parts if part and part.strip())
        return " ".join(joined.split())
