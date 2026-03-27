from __future__ import annotations

import asyncio
import logging

from dotenv import load_dotenv

from raidbot.config import Settings
from raidbot.runtime import build_runtime


async def run() -> None:
    load_dotenv()
    settings = Settings.from_env()
    logging.basicConfig(level=settings.log_level)
    runtime = build_runtime(settings)
    await runtime.listener.run_forever()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
