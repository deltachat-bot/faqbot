"""FAQ bot."""
import asyncio

from .hooks import cli


def main() -> None:
    """Run the application."""
    asyncio.run(cli.start())
