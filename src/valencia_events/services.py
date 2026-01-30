"""Service layer for external process execution."""

import json
import subprocess
from pathlib import Path

from .logger import get_logger

logger = get_logger(__name__)


def run_scrapers() -> list[dict]:
    """Run all configured scrapers and collect raw events.

    Returns:
        List of raw event dictionaries from all scrapers
    """
    output_file = Path("output/events.jsonl")
    output_file.parent.mkdir(exist_ok=True)

    # Run Visit Valencia spider
    logger.info("Running Visit Valencia spider...")
    try:
        subprocess.run(
            [
                "scrapy",
                "crawl",
                "visit_valencia",
                "-O",  # Overwrite
                str(output_file),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        logger.error(f"Scraper failed: {e.stderr}")

    raw_events = []
    if output_file.exists():
        with open(output_file, "r") as f:
            for line in f:
                if line.strip():
                    try:
                        raw_events.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning("Skipping invalid JSON line")

    return raw_events
