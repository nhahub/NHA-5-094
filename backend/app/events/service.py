import logging
import uuid
from contextvars import ContextVar, Token
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.events.models import EventRecord

logger = logging.getLogger(__name__)
_orchestration_active: ContextVar[bool] = ContextVar("orchestration_active", default=False)
ORCHESTRATION_TRUST_MARKER = "_orchestration_trusted"


class EventService:
    """Service managing immutable business events."""

    @staticmethod
    def orchestration_active() -> bool:
        """Return whether the current async flow is already handling an event."""
        return _orchestration_active.get()

    @staticmethod
    def begin_orchestration() -> Token[bool]:
        """Prevent nested event emissions from recursively starting new sagas."""
        return _orchestration_active.set(True)

    @staticmethod
    def end_orchestration(token: Token[bool]) -> None:
        _orchestration_active.reset(token)

    @staticmethod
    async def add_event(
        db: AsyncSession,
        *,
        event_type: str,
        organization_id: uuid.UUID | None = None,
        actor_type: str = "SYSTEM",
        actor_id: uuid.UUID | None = None,
        case_id: uuid.UUID | None = None,
        payload: dict[str, Any] | None = None,
        dispatch_orchestration: bool = False,
        **extra: Any,
    ) -> EventRecord:
        """Add an event to the caller's transaction and enqueue trusted work atomically.

        Unlike ``emit_event``, this method does not commit. It supports domain flows
        that must commit the event together with their own state changes.
        """
        event_payload = dict(payload or {})
        event_payload.pop(ORCHESTRATION_TRUST_MARKER, None)
        if dispatch_orchestration:
            event_payload[ORCHESTRATION_TRUST_MARKER] = True
        for key, value in extra.items():
            if key != ORCHESTRATION_TRUST_MARKER and key not in event_payload:
                event_payload[key] = str(value) if isinstance(value, uuid.UUID) else value

        event = EventRecord(
            organization_id=organization_id,
            case_id=case_id,
            event_type=event_type,
            actor_type=actor_type,
            actor_id=actor_id,
            payload=event_payload,
        )
        db.add(event)
        await db.flush()
        if (
            dispatch_orchestration
            and settings.CASE_ORCHESTRATION_ENABLED
            and not _orchestration_active.get()
        ):
            from app.events.delivery import ensure_trusted_event_delivery

            await ensure_trusted_event_delivery(db, event)
        return event

    @staticmethod
    async def dispatch_persisted_event(
        db: AsyncSession,
        event: EventRecord,
        *,
        storage: Any = None,
        model_adapter: Any = None,
    ) -> Any:
        """Claim and dispatch a trusted event after its event/outbox transaction commits."""
        if (
            _orchestration_active.get()
            or not settings.CASE_ORCHESTRATION_ENABLED
            or not (event.payload or {}).get(ORCHESTRATION_TRUST_MARKER)
        ):
            return None
        try:
            from app.events.delivery import process_event_delivery

            return await process_event_delivery(
                db=db,
                event=event,
                storage=storage,
                model_adapter=model_adapter,
            )
        except Exception:
            logger.exception(
                "Could not dispatch persisted event %s (%s).",
                event.id,
                event.event_type,
            )

    @staticmethod
    async def emit_event(
        db: AsyncSession,
        event_type: str,
        organization_id: uuid.UUID | None = None,
        actor_type: str = "SYSTEM",
        actor_id: uuid.UUID | None = None,
        case_id: uuid.UUID | None = None,
        payload: dict[str, Any] | None = None,
        dispatch_orchestration: bool = False,
        storage: Any = None,
        model_adapter: Any = None,
        **kwargs: Any,
    ) -> EventRecord:
        event = await EventService.add_event(
            db,
            event_type=event_type,
            organization_id=organization_id,
            actor_type=actor_type,
            actor_id=actor_id,
            case_id=case_id,
            payload=payload,
            dispatch_orchestration=dispatch_orchestration,
            **kwargs,
        )
        await db.commit()
        await db.refresh(event)
        if (
            dispatch_orchestration
            and settings.CASE_ORCHESTRATION_ENABLED
            and not _orchestration_active.get()
        ):
            await EventService.dispatch_persisted_event(
                db=db,
                event=event,
                storage=storage,
                model_adapter=model_adapter,
            )
        return event

    @staticmethod
    async def get_events_for_case(
        db: AsyncSession, case_id: uuid.UUID, skip: int = 0, limit: int = 100
    ) -> list[EventRecord]:
        stmt = (
            select(EventRecord)
            .where(EventRecord.case_id == case_id)
            .order_by(EventRecord.created_at.asc())
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_events_for_organization(
        db: AsyncSession, organization_id: uuid.UUID, skip: int = 0, limit: int = 100
    ) -> list[EventRecord]:
        stmt = (
            select(EventRecord)
            .where(EventRecord.organization_id == organization_id)
            .order_by(EventRecord.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())
