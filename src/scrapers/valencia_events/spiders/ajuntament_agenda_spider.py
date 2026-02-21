"""Spider for Ajuntament de Valencia city agenda page."""

from __future__ import annotations

import json
import re
from datetime import datetime

import scrapy
from scrapy.http import Response

from scrapers.valencia_events.items import RawEventItem


class AjuntamentAgendaSpider(scrapy.Spider):
    """Parse embedded agenda event JSON from valencia.es agenda page."""

    name = "ajuntament_agenda"
    allowed_domains = ["valencia.es", "www.valencia.es"]
    start_urls = ["https://www.valencia.es/cas/agenda-de-la-ciudad"]
    custom_settings = {"DOWNLOAD_DELAY": 1}

    EVENTOS_RE = re.compile(r"var\s+eventosInicio\s*=\s*(\[[\s\S]*?\]);")

    def parse(self, response: Response, **kwargs):
        text = response.text
        match = self.EVENTOS_RE.search(text)
        if not match:
            self.logger.warning("Could not find eventosInicio JSON in agenda page")
            return

        try:
            eventos = json.loads(match.group(1))
        except json.JSONDecodeError:
            self.logger.warning("Failed to parse eventosInicio JSON payload")
            return

        for event in eventos:
            title = str(event.get("content", "")).strip()
            start = self._to_iso_date(str(event.get("startDate", "")).strip())
            url = self._resolve_event_url(response, event)
            description = str(event.get("description", "")).strip()
            category = str(event.get("categoria", "")).strip()
            if category:
                description = f"{category}. {description}".strip().strip(". ")

            if title and start and url:
                yield RawEventItem(
                    title=title,
                    start=start,
                    url=url,
                    description=description,
                    source=self.name,
                )

    @staticmethod
    def _to_iso_date(value: str) -> str:
        if not value:
            return ""
        try:
            # Source provides milliseconds since epoch as string.
            dt = datetime.fromtimestamp(int(value) / 1000)
            return dt.isoformat()
        except (TypeError, ValueError):
            return value

    @staticmethod
    def _resolve_event_url(response: Response, event: dict) -> str:
        edit_url = str(event.get("editURL", "")).strip()
        if edit_url:
            return response.urljoin(edit_url)

        event_url = str(event.get("url", "")).strip()
        if not event_url:
            return ""
        if event_url.startswith("http://") or event_url.startswith("https://"):
            return event_url

        # Liferay agenda entries commonly resolve under this content path.
        return response.urljoin(f"/cas/agenda-de-la-ciudad/-/content/{event_url}")
