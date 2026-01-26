"""Spider for Visit Valencia event listings."""

from collections.abc import Iterable

import scrapy
from scrapy.http import Response

from scrapers.valencia_events.items import RawEventItem


class VisitValenciaSpider(scrapy.Spider):
    """Scrape paginated Visit Valencia event cards."""

    name = "visit_valencia"
    allowed_domains = ["visitvalencia.com", "www.visitvalencia.com"]
    start_urls = ["https://www.visitvalencia.com/en/events-valencia"]
    custom_settings = {"DOWNLOAD_DELAY": 1}

    def parse(self, response: Response, **kwargs):
        """Parse a listing page and yield raw event items."""
        for card in response.css("div.card--horizontal"):
            item = self._parse_card(response, card)
            if item["title"] and item["url"]:
                yield item

        next_href = response.css("li.pager__item--next a::attr(href)").get()
        if next_href:
            yield response.follow(next_href, callback=self.parse)

    def _parse_card(self, response: Response, card: scrapy.Selector) -> RawEventItem:
        """Extract a RawEventItem from a single card."""
        title = self._clean_text(
            card.xpath(".//h3[contains(@class,'card__heading')]//text()").getall()
        )
        url = card.css("a.card__link::attr(href), a.button::attr(href)").get()
        date_text = self._clean_text(
            card.xpath(".//div[contains(@class,'card__date')]//text()").getall()
        )
        if date_text.lower().startswith("date:"):
            date_text = date_text[len("date:") :].strip()

        description = self._clean_text(
            card.xpath(".//div[contains(@class,'card__description')]//text()").getall()
        )
        if not description:
            alt_text = card.xpath(".//img/@alt").get()
            description = alt_text.strip() if alt_text else ""

        return RawEventItem(
            title=title,
            start=date_text,
            url=response.urljoin(url) if url else None,
            description=description,
            source=self.name,
        )

    @staticmethod
    def _clean_text(text_parts: Iterable[str]) -> str:
        """Normalize whitespace in extracted text parts."""
        joined = " ".join(part.strip() for part in text_parts if part and part.strip())
        return " ".join(joined.split())
