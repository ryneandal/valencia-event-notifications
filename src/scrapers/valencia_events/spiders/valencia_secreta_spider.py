"""Spider for Valencia Secreta event pages."""

from __future__ import annotations

from collections.abc import Iterable

import scrapy
from scrapy.http import Response

from scrapers.valencia_events.items import RawEventItem


class ValenciaSecretaSpider(scrapy.Spider):
    """Scrape Valencia Secreta event-like posts."""

    name = "valencia_secreta"
    allowed_domains = ["valenciasecreta.com", "www.valenciasecreta.com"]
    start_urls = ["https://valenciasecreta.com/"]
    custom_settings = {"DOWNLOAD_DELAY": 1}

    def parse(self, response: Response, **kwargs):
        for node in response.css("article, .post"):
            title = self._clean(node.css("h2 a::text, h3 a::text, a::text").getall())
            url = node.css("h2 a::attr(href), h3 a::attr(href), a::attr(href)").get()
            start = node.css("time::attr(datetime)").get() or self._clean(
                node.css(
                    "time::text, .post-date::text, .entry-date::text, .date::text"
                ).getall()
            )
            description = self._clean(
                node.css("p::text, .entry-excerpt::text, .excerpt::text").getall()
            )

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
