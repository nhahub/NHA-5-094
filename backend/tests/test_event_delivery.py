from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domain.cases.orchestrator import OrchestrationResult, OrchestrationStatus
from app.events.delivery import (
    DEAD_LETTER,
    COMPLETED,
    PROCESSING,
    RETRY,
    _finish_delivery,
    claim_event_delivery,
    ensure_trusted_event_delivery,
    process_event_delivery,
    process_next_event_delivery,
    replay_trusted_event,
)
from app.events.models import EventDelivery, EventRecord
from app.events.service import EventService, ORCHESTRATION_TRUST_MARKER


@pytest.mark.asyncio
async def test_trusted_event_and_delivery_are_committed_together(
    db_session: AsyncSession, test_org, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "CASE_ORCHESTRATION_ENABLED", True)

    async def defer_dispatch(*args, **kwargs):
        return None

    monkeypatch.setattr(EventService, "dispatch_persisted_event", defer_dispatch)
    event = await EventService.emit_event(
        db=db_session,
        organization_id=test_org.id,
        event_type="CASE_CREATED",
        payload={"source": "delivery-test"},
        dispatch_orchestration=True,
    )

    delivery = await db_session.scalar(
        select(EventDelivery).where(EventDelivery.event_id == event.id)
    )
    assert event.payload[ORCHESTRATION_TRUST_MARKER] is True
    assert delivery is not None
    assert delivery.status == "PENDING"
    assert delivery.attempts == 0


@pytest.mark.asyncio
async def test_transactional_event_helper_adds_outbox_without_committing(
    db_session: AsyncSession, test_org, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "CASE_ORCHESTRATION_ENABLED", True)
    event = await EventService.add_event(
        db_session,
        organization_id=test_org.id,
        event_type="DOCUMENT_PROCESSING_COMPLETED",
        case_id=None,
        payload={"source": "transactional-helper-test"},
        dispatch_orchestration=True,
    )
    delivery = await db_session.scalar(
        select(EventDelivery).where(EventDelivery.event_id == event.id)
    )
    assert event.payload[ORCHESTRATION_TRUST_MARKER] is True
    assert delivery is not None and delivery.status == "PENDING"
    assert db_session.in_transaction()


@pytest.mark.asyncio
async def test_untrusted_events_do_not_enter_orchestration_outbox(
    db_session: AsyncSession, test_org
):
    event = await EventService.emit_event(
        db=db_session,
        organization_id=test_org.id,
        event_type="PUBLIC_NOTE_ADDED",
        payload={"text": "not a trusted orchestration event"},
    )

    delivery = await db_session.scalar(
        select(EventDelivery).where(EventDelivery.event_id == event.id)
    )
    assert delivery is None


@pytest.mark.asyncio
async def test_expired_worker_lease_can_be_reclaimed(
    db_session: AsyncSession, test_org
):
    event = EventRecord(
        organization_id=test_org.id,
        event_type="CASE_CREATED",
        actor_type="SYSTEM",
        payload={ORCHESTRATION_TRUST_MARKER: True},
    )
    db_session.add(event)
    await db_session.flush()
    await ensure_trusted_event_delivery(db_session, event)
    await db_session.commit()

    first_claim = await claim_event_delivery(db_session, event.id)
    assert first_claim is not None
    assert await claim_event_delivery(db_session, event.id) is None
    row = await db_session.scalar(
        select(EventDelivery).where(EventDelivery.event_id == event.id)
    )
    assert row.status == PROCESSING
    assert row.attempts == 1

    row.lease_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db_session.commit()
    recovered_claim = await claim_event_delivery(db_session, event.id)
    assert recovered_claim is not None
    assert recovered_claim.lease_token != first_claim.lease_token
    assert recovered_claim.attempt == 2


@pytest.mark.asyncio
async def test_stale_worker_cannot_finalize_a_reclaimed_delivery(
    db_session: AsyncSession, test_org
):
    event = EventRecord(
        organization_id=test_org.id,
        event_type="CASE_CREATED",
        actor_type="SYSTEM",
        payload={ORCHESTRATION_TRUST_MARKER: True},
    )
    db_session.add(event)
    await db_session.flush()
    await ensure_trusted_event_delivery(db_session, event)
    await db_session.commit()

    stale_claim = await claim_event_delivery(db_session, event.id)
    assert stale_claim is not None
    delivery = await db_session.scalar(
        select(EventDelivery).where(EventDelivery.event_id == event.id)
    )
    assert delivery is not None
    delivery.lease_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db_session.commit()

    current_claim = await claim_event_delivery(db_session, event.id)
    assert current_claim is not None
    assert current_claim.lease_token != stale_claim.lease_token
    assert current_claim.attempt == 2

    stale_finalize = await _finish_delivery(
        db_session, stale_claim, status=COMPLETED
    )
    assert not stale_finalize
    await db_session.refresh(delivery)
    assert delivery.status == PROCESSING
    assert delivery.lease_token == current_claim.lease_token

    current_finalize = await _finish_delivery(
        db_session, current_claim, status=COMPLETED
    )
    assert current_finalize
    await db_session.refresh(delivery)
    assert delivery.status == COMPLETED
    assert delivery.lease_token is None


@pytest.mark.asyncio
async def test_background_worker_completes_one_event_once(
    db_session: AsyncSession,
    test_org,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.domain.cases.orchestrator import CaseOrchestrator

    event = EventRecord(
        organization_id=test_org.id,
        event_type="CASE_CREATED",
        actor_type="SYSTEM",
        payload={ORCHESTRATION_TRUST_MARKER: True},
    )
    db_session.add(event)
    await db_session.flush()
    await ensure_trusted_event_delivery(db_session, event)
    await db_session.commit()

    calls = 0

    async def succeed(**kwargs):
        nonlocal calls
        calls += 1
        return OrchestrationResult(
            event_type="CASE_CREATED",
            event_id=event.id,
            status=OrchestrationStatus.SUCCESS,
        )

    monkeypatch.setattr(CaseOrchestrator, "dispatch_event", succeed)
    result = await process_next_event_delivery(db_session)
    assert result.status == OrchestrationStatus.SUCCESS
    assert await process_next_event_delivery(db_session) is None
    delivery = await db_session.scalar(
        select(EventDelivery).where(EventDelivery.event_id == event.id)
    )
    assert delivery.status == COMPLETED
    assert calls == 1


@pytest.mark.asyncio
async def test_dead_letter_can_be_manually_replayed(
    db_session: AsyncSession,
    test_org,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.domain.cases.orchestrator import CaseOrchestrator

    event = EventRecord(
        organization_id=test_org.id,
        event_type="CASE_CREATED",
        actor_type="SYSTEM",
        payload={ORCHESTRATION_TRUST_MARKER: True},
    )
    db_session.add(event)
    await db_session.flush()
    await ensure_trusted_event_delivery(db_session, event)
    delivery = await db_session.scalar(
        select(EventDelivery).where(EventDelivery.event_id == event.id)
    )
    delivery.status = DEAD_LETTER
    delivery.attempts = 5
    await db_session.commit()

    async def succeed(**kwargs):
        return OrchestrationResult(
            event_type="CASE_CREATED",
            event_id=event.id,
            status=OrchestrationStatus.SUCCESS,
        )

    monkeypatch.setattr(CaseOrchestrator, "dispatch_event", succeed)
    result = await replay_trusted_event(db_session, event)
    await db_session.refresh(delivery)
    assert result.status == OrchestrationStatus.SUCCESS
    assert delivery.status == COMPLETED
    assert delivery.attempts == 1


@pytest.mark.asyncio
async def test_manual_replay_respects_orchestration_kill_switch(
    db_session: AsyncSession,
    test_org,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.domain.cases.orchestrator import CaseOrchestrator

    monkeypatch.setattr(settings, "CASE_ORCHESTRATION_ENABLED", False)
    event = EventRecord(
        organization_id=test_org.id,
        event_type="CASE_CREATED",
        actor_type="SYSTEM",
        payload={ORCHESTRATION_TRUST_MARKER: True},
    )
    db_session.add(event)
    await db_session.commit()

    result = await CaseOrchestrator.resume_event(db_session, event.id)
    delivery = await db_session.scalar(
        select(EventDelivery).where(EventDelivery.event_id == event.id)
    )
    assert result.status == OrchestrationStatus.SKIPPED
    assert delivery is None


@pytest.mark.asyncio
async def test_failed_delivery_retries_then_moves_to_dead_letter(
    db_session: AsyncSession,
    test_org,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.domain.cases.orchestrator import CaseOrchestrator
    import app.events.delivery as delivery_module

    event = EventRecord(
        organization_id=test_org.id,
        event_type="CASE_CREATED",
        actor_type="SYSTEM",
        payload={ORCHESTRATION_TRUST_MARKER: True},
    )
    db_session.add(event)
    await db_session.flush()
    await ensure_trusted_event_delivery(db_session, event)
    await db_session.commit()

    async def fail_dispatch(**kwargs):
        return OrchestrationResult(
            event_type="CASE_CREATED",
            event_id=event.id,
            status=OrchestrationStatus.ERROR,
            error="safe test error",
        )

    monkeypatch.setattr(CaseOrchestrator, "dispatch_event", fail_dispatch)
    monkeypatch.setattr(delivery_module, "MAX_DELIVERY_ATTEMPTS", 2)

    first_result = await process_event_delivery(db_session, event)
    row = await db_session.scalar(
        select(EventDelivery).where(EventDelivery.event_id == event.id)
    )
    assert first_result.status == OrchestrationStatus.ERROR
    assert row.status == RETRY
    assert row.last_error_code == "ORCHESTRATION_ERROR"

    await process_event_delivery(db_session, event, force=True)
    await db_session.refresh(row)
    assert row.status == DEAD_LETTER
    assert row.attempts == 2

