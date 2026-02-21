"""Main entry point for valencia_events package."""

import typer

from .cli import main

if __name__ == "__main__":
    typer.run(main)
