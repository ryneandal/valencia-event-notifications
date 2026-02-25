"""Spider for ValenciaBonita event pages."""

from __future__ import annotations

import re
from collections.abc import Iterable

import scrapy
from scrapy.http import Response

from scrapers.valencia_events.items import RawEventItem


class ValenciaBonitaSpider(scrapy.Spider):
    """Scrape ValenciaBonita event-like posts."""

    name = "valenciabonita"
    allowed_domains = ["valenciabonita.es", "www.valenciabonita.es"]
    start_urls = [
        "https://www.valenciabonita.es/category/planes-y-eventos/",
        "https://www.valenciabonita.es/category/planes-con-ninos/",
    ]
    custom_settings = {"DOWNLOAD_DELAY": 1}
    max_pages_per_category = 2

    def parse(self, response: Response, **kwargs):
        seen_urls: set[str] = set()
        for article in response.css("article.jeg_post, article.post"):
            url = (
                article.css(
                    "h3.jeg_post_title a::attr(href), .jeg_thumb a::attr(href), "
                    "h2 a::attr(href)"
                ).get()
                or ""
            ).strip()
            if not url:
                continue
            abs_url = response.urljoin(url)
            if (
                abs_url in seen_urls
                or "valenciabonita.es/" not in abs_url
                or "#respond" in abs_url
            ):
                continue

            start = article.css(
                "time::attr(datetime)"
            ).get() or self._extract_date_from_url(abs_url)
            if not start:
                continue

            title = self._clean(
                article.css(
                    "h3.jeg_post_title a::text, .jeg_thumb a::attr(aria-label), "
                    "h2 a::text"
                ).getall()
            )
            if not title or title.isdigit():
                continue

            description = self._clean(article.css(".jeg_post_excerpt p::text").getall())
            seen_urls.add(abs_url)

            yield RawEventItem(
                title=title,
                start=start,
                url=abs_url,
                description=description,
                source=self.name,
            )

        page = 1
        try:
            page = int(response.meta.get("page", 1))
        except AttributeError:
            page = 1
        next_href = response.css(
            "a.page_nav.next::attr(href), a[rel='next']::attr(href)"
        ).get()
        if next_href and page < self.max_pages_per_category:
            yield response.follow(
                next_href, callback=self.parse, meta={"page": page + 1}
            )

    @staticmethod
    def _clean(parts: Iterable[str]) -> str:
        joined = " ".join(part.strip() for part in parts if part and part.strip())
        return " ".join(joined.split())

    @staticmethod
    def _extract_date_from_url(url: str) -> str:
        match = re.search(r"/(20\d{2})/(\d{2})/(\d{2})/", url)
        if not match:
            return ""
        year, month, day = match.groups()
        return f"{day}/{month}/{year}"
