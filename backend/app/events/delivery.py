"""Database-backed delivery and retry handling for trusted business events."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import and_, or_, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.models import EventDelivery, EventRecord

logger = logging.getLogger(__name__)

PENDING = "PENDING"
PROCESSING = "PROCESSING"
RETRY = "RETRY"
COMPLETED = "COMPLETED"
DEAD_LETTER = "DEAD_LETTER"
MAX_DELIVERY_ATTEMPTS = 5
DELIVERY_LEASE = timedelta(minutes=15)
MAX_RETRY_DELAY = timedelta(minutes=5)


@dataclass(frozen=True)
class DeliveryClaim:
    event_id: uuid.UUID
    lease_token: str
    attempt: int


async def ensure_trusted_event_delivery(db: AsyncSession, event: EventRecord) -> None:
    """Insert an outbox row in the caller's transaction for a trusted domain event."""
    if not (event.payload or {}).get("_orchestration_trusted"):
        return

    # The event and outbox row commit together, so a process crash cannot lose delivery.
    await db.flush()
    dialect = db.bind.dialect.name if db.bind is not None else ""
    values = {
        "event_id": event.id,
        "status": PENDING,
        "attempts": 0,
    }
    if dialect == "postgresql":
        await db.execute(
            postgresql_insert(EventDelivery)
            .values(**values)
            .on_conflict_do_nothing(index_elements=["event_id"])
        )
    elif dialect == "sqlite":
        await db.execute(
            sqlite_insert(EventDelivery)
            .values(**values)
            .on_conflict_do_nothing(index_elements=["event_id"])
        )
    else:
        existing = await db.scalar(
            select(EventDelivery.id).where(EventDelivery.event_id == event.id)
        )
        if existing is None:
            db.add(EventDelivery(event_id=event.id, status=PENDING, attempts=0))


async def ensure_trusted_event_deliveries(
    db: AsyncSession, events: list[EventRecord | None]
) -> None:
    """Track each trusted event in a collection before its transaction is committed."""
    for event in events:
        if event is not None:
            await ensure_trusted_event_delivery(db, event)


async def claim_event_delivery(
    db: AsyncSession,
    event_id: uuid.UUID,
    *,
    force: bool = False,
) -> DeliveryClaim | None:
    """Claim one event atomically; expired leases are reclaimable after worker crashes."""
    row = await db.scalar(
        select(EventDelivery)
        .where(EventDelivery.event_id == event_id)
        .with_for_update(skip_locked=True)
    )
    if row is None:
        return None

    now = datetime.now(UTC)
    available_at = _as_utc(row.available_at)
    lease_until = _as_utc(row.lease_until)
    is_available = row.status in {PENDING, RETRY} and available_at is not None and available_at <= now
    is_expired = (
        row.status == PROCESSING
        and lease_until is not None
        and lease_until <= now
    )
    is_manual_retry = force and row.status in {RETRY, DEAD_LETTER}
    if not (is_available or is_expired or is_manual_retry):
        return None

    if force and row.status == DEAD_LETTER:
        row.attempts = 0
    elif row.attempts >= MAX_DELIVERY_ATTEMPTS:
        row.status = DEAD_LETTER
        row.lease_until = None
        row.lease_token = None
        row.last_error_code = row.last_error_code or "MAX_ATTEMPTS_EXCEEDED"
        await db.commit()
        return None
    row.status = PROCESSING
    row.attempts += 1
    row.available_at = now
    row.lease_until = now + DELIVERY_LEASE
    row.lease_token = str(uuid.uuid4())
    row.last_error_code = None
    claim = DeliveryClaim(event_id=event_id, lease_token=row.lease_token, attempt=row.attempts)
    await db.commit()
    return claim


async def claim_next_event_delivery(db: AsyncSession) -> DeliveryClaim | None:
    """Claim the oldest available event, using SKIP LOCKED for competing workers."""
    now = datetime.now(UTC)
    eligible = or_(
        and_(
            EventDelivery.status.in_([PENDING, RETRY]),
            EventDelivery.available_at <= now,
        ),
        and_(
            EventDelivery.status == PROCESSING,
            EventDelivery.lease_until.is_not(None),
            EventDelivery.lease_until <= now,
        ),
    )
    exhausted = cast(CursorResult[Any], await db.execute(
        update(EventDelivery)
        .where(eligible, EventDelivery.attempts >= MAX_DELIVERY_ATTEMPTS)
        .values(
            status=DEAD_LETTER,
            lease_until=None,
            lease_token=None,
            last_error_code="MAX_ATTEMPTS_EXCEEDED",
        )
    ))
    if exhausted.rowcount:
        await db.flush()

    eligible = and_(eligible, EventDelivery.attempts < MAX_DELIVERY_ATTEMPTS)
    row = await db.scalar(
        select(EventDelivery)
        .where(eligible)
        .order_by(EventDelivery.available_at, EventDelivery.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if row is None:
        if exhausted.rowcount:
            await db.commit()
        return None

    row.status = PROCESSING
    row.attempts += 1
    row.lease_until = now + DELIVERY_LEASE
    row.lease_token = str(uuid.uuid4())
    row.last_error_code = None
    claim = DeliveryClaim(event_id=row.event_id, lease_token=row.lease_token, attempt=row.attempts)
    await db.commit()
    return claim


async def _finish_delivery(
    db: AsyncSession,
    claim: DeliveryClaim,
    *,
    status: str,
    error_code: str | None = None,
    retry_after: timedelta | None = None,
) -> bool:
    """Finish only the lease owner; a stale worker cannot overwrite a newer claim."""
    now = datetime.now(UTC)
    values: dict[str, Any] = {
        "status": status,
        "lease_until": None,
        "lease_token": None,
        "last_error_code": error_code,
    }
    if status == COMPLETED:
        values["completed_at"] = now
    elif status in {RETRY, DEAD_LETTER}:
        values["available_at"] = now + (retry_after or timedelta(0))
    result = cast(CursorResult[Any], await db.execute(
        update(EventDelivery)
        .where(
            EventDelivery.event_id == claim.event_id,
            EventDelivery.status == PROCESSING,
            EventDelivery.lease_token == claim.lease_token,
        )
        .values(**values)
    ))
    await db.commit()
    return result.rowcount == 1


async def _dispatch_claimed_event(
    db: AsyncSession,
    claim: DeliveryClaim,
    *,
    storage: Any = None,
    model_adapter: Any = None,
):
    from app.domain.cases.orchestrator import (
        CaseOrchestrator,
        OrchestrationStatus,
    )

    event = await db.get(EventRecord, claim.event_id)
    if event is None:
        await _finish_delivery(db, claim, status=DEAD_LETTER, error_code="MISSING_EVENT")
        return None

    if not (event.payload or {}).get("_orchestration_trusted"):
        await _finish_delivery(db, claim, status=DEAD_LETTER, error_code="UNTRUSTED_EVENT")
        return None

    try:
        result = await CaseOrchestrator.dispatch_event(
            db=db,
            event=event,
            storage=storage,
            model_adapter=model_adapter,
        )
    except Exception as exc:  # delivery boundary must survive unexpected handler failures
        logger.exception("Unexpected delivery failure for event %s.", claim.event_id)
        status = DEAD_LETTER if claim.attempt >= MAX_DELIVERY_ATTEMPTS else RETRY
        delay = _retry_delay(claim.attempt) if status == RETRY else timedelta(0)
        await _finish_delivery(
            db,
            claim,
            status=status,
            error_code=type(exc).__name__[:100],
            retry_after=delay,
        )
        return None

    if result.status == OrchestrationStatus.ERROR:
        status = DEAD_LETTER if claim.attempt >= MAX_DELIVERY_ATTEMPTS else RETRY
        delay = _retry_delay(claim.attempt) if status == RETRY else timedelta(0)
        await _finish_delivery(
            db,
            claim,
            status=status,
            error_code="ORCHESTRATION_ERROR",
            retry_after=delay,
        )
    else:
        await _finish_delivery(db, claim, status=COMPLETED)
    return result


def _retry_delay(attempt: int) -> timedelta:
    seconds = min(2 ** max(attempt, 1), int(MAX_RETRY_DELAY.total_seconds()))
    return timedelta(seconds=seconds)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


async def process_event_delivery(
    db: AsyncSession,
    event: EventRecord,
    *,
    storage: Any = None,
    model_adapter: Any = None,
    force: bool = False,
):
    """Claim and deliver one trusted event, returning its orchestration result if claimed."""
    await ensure_trusted_event_delivery(db, event)
    await db.commit()
    claim = await claim_event_delivery(db, event.id, force=force)
    if claim is None:
        return None
    return await _dispatch_claimed_event(
        db,
        claim,
        storage=storage,
        model_adapter=model_adapter,
    )


async def process_next_event_delivery(
    db: AsyncSession,
    *,
    storage: Any = None,
    model_adapter: Any = None,
):
    """Claim and process one item for a background worker."""
    claim = await claim_next_event_delivery(db)
    if claim is None:
        return None
    return await _dispatch_claimed_event(
        db,
        claim,
        storage=storage,
        model_adapter=model_adapter,
    )


async def replay_trusted_event(
    db: AsyncSession,
    event: EventRecord,
    *,
    storage: Any = None,
    model_adapter: Any = None,
):
    """Immediately redrive a trusted failed or dead-lettered event for operator recovery."""
    if not (event.payload or {}).get("_orchestration_trusted"):
        raise PermissionError("Only trusted domain events can be resumed.")
    await ensure_trusted_event_delivery(db, event)
    await db.commit()
    return await process_event_delivery(
        db,
        event,
        storage=storage,
        model_adapter=model_adapter,
        force=True,
    )
