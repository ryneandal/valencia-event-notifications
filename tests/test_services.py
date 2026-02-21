"""Tests for scraper orchestration services."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from valencia_events import services


def test_run_scrapers_aggregates_and_filters(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    def fake_run(spider_name: str, args: dict[str, str], output_file: Path):
        if spider_name == "ivam":
            raise subprocess.CalledProcessError(1, [spider_name], stderr="boom")

        records = [
            {
                "title": f"Event from {spider_name}",
                "start": "2025-10-20T19:00:00+02:00",
                "url": f"https://example.com/{spider_name}",
                "description": "ok",
                "source": args.get("source", spider_name),
            }
        ]
        if spider_name == "valencia_secreta":
            records.append(
                {
                    "title": "Editorial sponsored content",
                    "start": "sin fecha concreta",
                    "url": "https://example.com/editorial",
                    "description": "noise",
                    "source": "valencia_secreta",
                }
            )

        output_file.parent.mkdir(parents=True, exist_ok=True)
        with output_file.open("w") as handle:
            for record in records:
                handle.write(json.dumps(record) + "\n")

    monkeypatch.setattr(services, "_run_single_spider", fake_run)

    raw_items = services.run_scrapers()
    sources = {item["source"] for item in raw_items}

    assert "ivam" not in sources
    assert "valencia_secreta" in sources
    assert "ajuntament_agenda" in sources
    assert "elperiodic_rss" in sources
    assert all(item["title"] != "Editorial sponsored content" for item in raw_items)
