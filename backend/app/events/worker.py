"""Standalone worker for durable case-orchestration event delivery."""
from __future__ import annotations

import asyncio
import logging

# Import the application router graph before event services. The events package
# exposes its router in __init__, and warming the graph avoids a domain import cycle
# when this worker is launched as a standalone module.
import app.api  # noqa: F401
from app.core.config import settings
from app.core.logging import setup_logging
from app.events.delivery import process_next_event_delivery
from app.infrastructure.database.session import AsyncSessionLocal, async_engine
from app.infrastructure.storage import get_storage_backend

logger = logging.getLogger(__name__)


async def run_worker(poll_interval_seconds: float = 1.0) -> None:
    """Poll the PostgreSQL outbox until the process is stopped."""
    setup_logging()
    # SQL echo is useful for local API debugging but floods a long-lived polling
    # worker with a query every second. Keep worker logs focused on delivery state.
    async_engine.echo = False
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine.Engine").setLevel(logging.WARNING)
    logger.info("Starting durable event worker.")
    try:
        storage = get_storage_backend()
    except Exception as exc:
        # Events not requiring object storage can still progress. Document events will
        # retry and eventually dead-letter until their configured adapter is available.
        logger.warning("Storage adapter is unavailable to the event worker (%s).", type(exc).__name__)
        storage = None

    while True:
        if not settings.CASE_ORCHESTRATION_ENABLED:
            await asyncio.sleep(poll_interval_seconds)
            continue

        try:
            async with AsyncSessionLocal() as db:
                result = await process_next_event_delivery(db, storage=storage)
            if result is not None:
                logger.info(
                    "Event delivery finished with status %s.",
                    getattr(result.status, "value", result.status),
                )
                continue
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Event worker poll failed; it will retry.")
        await asyncio.sleep(poll_interval_seconds)


if __name__ == "__main__":
    asyncio.run(run_worker())
