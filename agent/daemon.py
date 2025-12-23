"""Async daemon that periodically records telemetry from the Pi and Jetson hosts."""

from __future__ import annotations

import asyncio
import datetime
import logging
import os
from pathlib import Path
from typing import Any, Callable

from agent import telemetry

LOGFILE = Path(os.environ.get("BLACKROAD_AGENT_LOG", "/var/log/blackroad-agent.log"))
JETSON_HOST = os.environ.get("BLACKROAD_JETSON_HOST", "jetson.local")
JETSON_USER = os.environ.get("BLACKROAD_JETSON_USER", "jetson")


def _safe_collect(func: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return func()
    except Exception as exc:
        logging.exception("Telemetry probe failed: %s", func.__name__)
        return {"error": str(exc)}


async def loop(interval: int = 60) -> None:
    """Main telemetry loop writing Pi and Jetson stats to the logfile."""
    logging.info("Starting telemetry loop with interval=%ss", interval)
    while True:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        pi_stats = _safe_collect(telemetry.collect_local)
        jetson_stats = _safe_collect(lambda: telemetry.collect_remote(JETSON_HOST, user=JETSON_USER))

        line = f"[{now}] PI: {pi_stats} | JETSON: {jetson_stats}\n"

        try:
            LOGFILE.parent.mkdir(parents=True, exist_ok=True)
            with LOGFILE.open("a", encoding="utf-8") as handle:
                handle.write(line)
        except PermissionError:
            logging.error("Insufficient permissions to write telemetry log: %s", LOGFILE)
        except OSError:
            logging.exception("Failed to append telemetry line to %s", LOGFILE)
            # Fall back to stdout if the log cannot be written
            print(line, end="")

        await asyncio.sleep(interval)


def main() -> None:
    """Entrypoint for the console script."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(loop())


if __name__ == "__main__":
    main()
