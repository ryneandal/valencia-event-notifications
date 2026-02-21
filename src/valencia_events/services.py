"""Service layer for external process execution."""

from __future__ import annotations

import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from .logger import get_logger
from .source_filters import should_keep_raw_event

logger = get_logger(__name__)

SCRAPER_RUNS: list[dict[str, Any]] = [
    {"name": "visit_valencia", "args": {}},
    {
        "name": "rss",
        "args": {
            "feed_url": "http://www.valencia.es/ayuntamiento/"
            "agenda_accesible.nsf/agenda.xml",
            "source": "ajuntament_rss",
        },
    },
    {
        "name": "rss",
        "args": {
            "feed_url": "https://www.elperiodic.com/rss/valencia/",
            "source": "elperiodic_rss",
        },
    },
    {"name": "palau_musica", "args": {}},
    {"name": "les_arts", "args": {}},
    {"name": "ivam", "args": {}},
    {"name": "valencia_secreta", "args": {}},
    {"name": "valenciabonita", "args": {}},
]


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    raw_items: list[dict[str, Any]] = []
    if not path.exists():
        return raw_items

    with path.open() as handle:
        for line in handle:
            if line.strip():
                try:
                    raw_items.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning(
                        "Skipping invalid JSON line",
                        extra={"path": str(path)},
                    )
    return raw_items


def _run_single_spider(
    spider_name: str,
    args: dict[str, str],
    output_file: Path,
) -> None:
    cmd = ["scrapy", "crawl", spider_name, "-O", str(output_file)]
    for key, value in args.items():
        cmd.extend(["-a", f"{key}={value}"])

    logger.info(f"Running spider: {spider_name} args={args}")
    subprocess.run(
        cmd,
        check=True,
        capture_output=True,
        text=True,
    )


def run_scrapers() -> list[dict]:
    """Run all configured scrapers and collect raw events."""
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    all_raw_items: list[dict[str, Any]] = []
    for index, run in enumerate(SCRAPER_RUNS):
        spider_name = str(run["name"])
        args = {k: str(v) for k, v in run.get("args", {}).items()}
        output_file = output_dir / f"events_{index}_{spider_name}.jsonl"

        try:
            _run_single_spider(spider_name, args, output_file)
        except subprocess.CalledProcessError as exc:
            logger.error(f"Spider failed: {spider_name}. stderr={exc.stderr}")
            continue

        spider_items = _load_jsonl(output_file)
        logger.info(f"Spider finished: {spider_name} items={len(spider_items)}")
        all_raw_items.extend(spider_items)

    filtered_items = [raw for raw in all_raw_items if should_keep_raw_event(raw)]
    source_counts = Counter(
        str(item.get("source", "unknown")) for item in filtered_items
    )
    logger.info(
        "Collected raw events: "
        f"total={len(all_raw_items)} kept={len(filtered_items)} "
        f"source_counts={dict(source_counts)}"
    )
    return filtered_items
