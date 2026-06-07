"""Logging configuration for Valencia Events."""

import logging


def configure_logging(level: int = logging.INFO) -> None:
    """Configure logging for the application.

    Args:
        level: Root logging level to apply.
    """
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the specified name.

    Args:
        name: Logger name, typically ``__name__``.

    Returns:
        Logger configured through the standard logging hierarchy.
    """
    return logging.getLogger(name)
