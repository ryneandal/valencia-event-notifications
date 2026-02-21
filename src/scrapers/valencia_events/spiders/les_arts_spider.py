"""Spider for Les Arts agenda pages."""

from __future__ import annotations

from collections.abc import Iterable

import scrapy
from scrapy.http import Response

from scrapers.valencia_events.items import RawEventItem


class LesArtsSpider(scrapy.Spider):
    """Scrape Les Arts agenda listings."""

    name = "les_arts"
    allowed_domains = ["lesarts.com", "www.lesarts.com"]
    start_urls = ["https://www.lesarts.com/es/programacion.html"]
    custom_settings = {"DOWNLOAD_DELAY": 1}

    def parse(self, response: Response, **kwargs):
        selectors = response.css(".contenidor-product")
        if selectors:
            for node in selectors:
                title = self._clean(node.css("a.titol::text").getall())
                url = node.css(
                    "a.titol::attr(href), a.imatge::attr(href), "
                    "::attr(data-open-espectacle)"
                ).get()
                date_text = self._clean(
                    node.css(".data .data-inici::text, .data .data-fi::text").getall()
                )
                hour_text = self._clean(node.css(".data .hora::text").getall())
                start = f"{date_text} {hour_text}".strip()
                description = self._clean(
                    node.css(".subtitol::text, .espai::text, .resum::text").getall()
                )

                if title and url and start:
                    yield RawEventItem(
                        title=title,
                        start=start,
                        url=response.urljoin(url),
                        description=description,
                        source=self.name,
                    )
            return

        # Backward-compatible parsing path used by unit-test fixtures.
        for node in response.css("article.evento"):
            title = self._clean(node.css("h2 a::text").getall())
            url = node.css("h2 a::attr(href)").get()
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
