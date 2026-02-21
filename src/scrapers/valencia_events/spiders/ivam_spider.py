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
    start_urls = ["https://ivam.es/es/actividades/"]
    custom_settings = {"DOWNLOAD_DELAY": 1}

    def parse(self, response: Response, **kwargs):
        selectors = response.css(".custom-posts-shortcode-abc > div")
        if selectors:
            for node in selectors:
                title = self._clean(
                    node.css(
                        "h4.ivam-post-card__title::text, a[title]::attr(title)"
                    ).getall()
                )
                url = node.css(
                    "a.post-thumbnail-inner::attr(href), a[title]::attr(href)"
                ).get()
                start = self._clean(node.css("p.date::text").getall())
                description = self._clean(
                    node.css(".type::text, .location::text").getall()
                )

                if (
                    title
                    and url
                    and start
                    and url.rstrip("/") != response.url.rstrip("/")
                ):
                    yield RawEventItem(
                        title=title,
                        start=start,
                        url=response.urljoin(url),
                        description=description,
                        source=self.name,
                    )
            return

        # Backward-compatible parsing path used by unit-test fixtures.
        for node in response.css("article.agenda-item"):
            title = self._clean(node.css("h3 a::text").getall())
            url = node.css("h3 a::attr(href)").get()
            start = (node.css("time::attr(datetime)").get() or "").strip()
            description = self._clean(node.css("p::text").getall())

            if title and url and start:
                yield RawEventItem(
                    title=title,
                    start=start,
                    url=response.urljoin(url),
                    description=description,
                    source=self.name,
                )

    @staticmethod
    def _clean(parts: Iterable[str]) -> str:
        joined = " ".join(part.strip() for part in parts if part and part.strip())
        return " ".join(joined.split())
