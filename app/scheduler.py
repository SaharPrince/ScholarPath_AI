"""Run official-source discovery and extraction on a daily cadence.

The database must live on persistent storage in production. The loop is hosted
inside the single web service so it shares the same SQLite file as the API.
"""
import asyncio
import logging

from app.discovery import discover_from_active_sources
from app.extraction import extract_candidate_details

logger = logging.getLogger(__name__)
DISCOVERY_INTERVAL_SECONDS = 24 * 60 * 60


async def run_discovery_cycle() -> None:
    """Discover official-source links, then extract facts from new candidates."""
    discovery_results = await discover_from_active_sources()
    extraction_results = await extract_candidate_details()
    logger.info(
        "Scholarship discovery cycle completed: sources=%s extraction=%s",
        [result.__dict__ for result in discovery_results],
        extraction_results,
    )


async def daily_discovery_loop() -> None:
    """Run once at startup and repeat every 24 hours without overlapping cycles."""
    while True:
        try:
            await run_discovery_cycle()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Daily scholarship discovery cycle failed")
        await asyncio.sleep(DISCOVERY_INTERVAL_SECONDS)
