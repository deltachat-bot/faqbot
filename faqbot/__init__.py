import asyncio

from .hooks import cli


def main() -> None:
    asyncio.run(cli.start())
