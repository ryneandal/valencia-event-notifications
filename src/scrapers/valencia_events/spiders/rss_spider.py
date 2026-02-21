"""Generic RSS spider for event feeds."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

import scrapy
from scrapy.http import Response

from scrapers.valencia_events.items import RawEventItem


class RSSSpider(scrapy.Spider):
    """Parse RSS feeds into RawEventItem records."""

    name = "rss"
    custom_settings = {"DOWNLOAD_DELAY": 1}

    def __init__(self, feed_url: str = "", source: str = "rss", **kwargs):
        super().__init__(**kwargs)
        self.feed_url = feed_url
        self.source = source
        self.start_urls = [feed_url] if feed_url else []

    def parse(self, response: Response, **kwargs):
        try:
            root = ET.fromstring(response.text)
        except ET.ParseError:
            return

        for node in self._iter_items(root):
            title = self._clean(self._child_text(node, "title"))
            link = self._clean(
                self._child_text(node, "link") or self._child_attr(node, "link", "href")
            )
            description = self._clean(
                self._child_text(node, "description")
                or self._child_text(node, "summary")
                or self._child_text(node, "content")
                or self._child_text(node, "encoded")
            )
            raw_date = self._clean(
                self._child_text(node, "pubDate")
                or self._child_text(node, "published")
                or self._child_text(node, "updated")
                or self._child_text(node, "date")
            )

            start = self._to_iso_date(raw_date)
            if not title or not link or not start:
                continue

            yield RawEventItem(
                title=title,
                start=start,
                url=link,
                description=description,
                source=self.source,
            )

    @staticmethod
    def _iter_items(root: ET.Element):
        for node in root.iter():
            if node.tag.split("}")[-1] in {"item", "entry"}:
                yield node

    @staticmethod
    def _child_text(node: ET.Element, child_name: str) -> str:
        for child in node:
            if child.tag.split("}")[-1] == child_name:
                return child.text or ""
        return ""

    @staticmethod
    def _child_attr(node: ET.Element, child_name: str, attr_name: str) -> str:
        for child in node:
            if child.tag.split("}")[-1] == child_name:
                value = child.attrib.get(attr_name, "")
                if value:
                    return value
        return ""

    @staticmethod
    def _clean(value: str | None) -> str:
        if not value:
            return ""
        return " ".join(value.split())

    def _to_iso_date(self, value: str) -> str:
        if not value:
            return ""

        try:
            dt = parsedate_to_datetime(value)
            return dt.isoformat()
        except (TypeError, ValueError):
            pass

        try:
            normalized = value.replace("Z", "+00:00")
            dt = datetime.fromisoformat(normalized)
            return dt.isoformat()
        except ValueError:
            return value
