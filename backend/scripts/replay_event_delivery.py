"""Manually redrive a trusted failed or interrupted event delivery.

Run this operator command only from a backend environment that has authorized
database access. It does not expose event payloads or provider error details.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Load the API/domain registration graph before importing case orchestration.
import app.api  # noqa: F401
from sqlalchemy import select

from app.domain.cases.orchestrator import CaseOrchestrator
from app.events.models import EventDelivery
from app.infrastructure.database.session import AsyncSessionLocal
from app.infrastructure.storage import get_storage_backend


async def replay(event_id: uuid.UUID) -> int:
    try:
        storage = get_storage_backend()
    except Exception:
        storage = None

    async with AsyncSessionLocal() as db:
        result = await CaseOrchestrator.resume_event(db, event_id, storage=storage)

    async with AsyncSessionLocal() as db:
        delivery = await db.scalar(
            select(EventDelivery).where(EventDelivery.event_id == event_id)
        )

    status = getattr(result.status, "value", result.status)
    if delivery is None:
        print(f"Event {event_id}: orchestration status={status}; no delivery record.")
        return 1

    print(
        f"Event {event_id}: delivery={delivery.status}, attempts={delivery.attempts}, "
        f"orchestration={status}, error_code={delivery.last_error_code or 'none'}."
    )
    if delivery.status == "COMPLETED":
        return 0
    return 2 if status == "SKIPPED" else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("event_id", type=uuid.UUID, help="trusted persisted event UUID")
    args = parser.parse_args()
    try:
        code = asyncio.run(replay(args.event_id))
    except (LookupError, PermissionError) as exc:
        print(f"Replay rejected: {exc}", file=sys.stderr)
        code = 1
    raise SystemExit(code)


if __name__ == "__main__":
    main()
