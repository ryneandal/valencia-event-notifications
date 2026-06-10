"""Scrapy pipelines for Valencia Events.

Processes scraped items before they are persisted.
"""

from scrapy.exceptions import DropItem

REQUIRED_FIELDS = ("title", "start", "url", "source")


class ValenciaEventsPipeline:
    """Pipeline for processing scraped event items.

    This pipeline will:
    - Validate item fields
    - Clean/normalize data
    - Write items to output (e.g., JSONL file)
    """

    def open_spider(self, spider):
        """Handle spider startup.

        Args:
            spider: The spider instance.
        """
        pass

    def close_spider(self, spider):
        """Handle spider shutdown.

        Args:
            spider: The spider instance.
        """
        pass

    def process_item(self, item, spider):
        """Validate and normalize a scraped item.

        Args:
            item: The scraped item.
            spider: The spider instance.

        Returns:
            The validated and normalized item.

        Raises:
            DropItem: If a required field is missing or blank.
        """
        for field in REQUIRED_FIELDS:
            value = item.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                raise DropItem(f"Missing required field {field!r}")

        for field in item.fields:
            value = item.get(field)
            if isinstance(value, str):
                item[field] = " ".join(value.split())

        return item
