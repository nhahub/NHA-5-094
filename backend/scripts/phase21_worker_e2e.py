"""Exercise the PostgreSQL outbox through the running Compose event worker(s).

Run inside the backend container after applying migrations and starting one or more
``event-worker`` services. The temporary organization owns every test event so all
test rows are removed in a ``finally`` block.
"""
from __future__ import annotations

import argparse
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

import sys
from pathlib import Path

# Ensure backend root is on sys.path when script is executed directly
backend_root = Path(__file__).resolve().parents[1]
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

# Mirror the API and Alembic startup order before importing event services.
import app.api  # noqa: F401
from app.domain.organizations.models import Organization
from app.events.delivery import (
    COMPLETED,
    _finish_delivery,
    claim_event_delivery,
    ensure_trusted_event_delivery,
)
from app.events.models import EventDelivery, EventRecord
from app.infrastructure.database.session import AsyncSessionLocal


async def verify_stale_claim_fencing() -> None:
    """Prove PostgreSQL rejects finalization by an expired worker claim."""
    organization_id = uuid.uuid4()
    try:
        async with AsyncSessionLocal() as db:
            organization = Organization(
                id=organization_id,
                name="Phase 22 Stale Claim E2E",
                slug=f"phase22-stale-{organization_id.hex[:12]}",
                status="active",
                settings={"purpose": "temporary stale-claim fencing probe"},
                is_active=True,
            )
            event = EventRecord(
                organization_id=organization_id,
                event_type="PHASE22_STALE_CLAIM_E2E",
                actor_type="SYSTEM",
                payload={"_orchestration_trusted": True},
            )
            db.add_all([organization, event])
            await db.flush()
            await ensure_trusted_event_delivery(db, event)
            await db.commit()

            stale_claim = await claim_event_delivery(db, event.id)
            assert stale_claim is not None
            delivery = await db.scalar(
                select(EventDelivery).where(EventDelivery.event_id == event.id)
            )
            assert delivery is not None
            delivery.lease_until = datetime.now(timezone.utc) - timedelta(seconds=1)
            await db.commit()

            current_claim = await claim_event_delivery(db, event.id)
            assert current_claim is not None
            assert current_claim.lease_token != stale_claim.lease_token
            assert current_claim.attempt == 2

            stale_finalized = await _finish_delivery(
                db, stale_claim, status=COMPLETED
            )
            assert not stale_finalized
            await db.refresh(delivery)
            assert delivery.status == "PROCESSING"
            assert delivery.lease_token == current_claim.lease_token

            current_finalized = await _finish_delivery(
                db, current_claim, status=COMPLETED
            )
            assert current_finalized
            await db.refresh(delivery)
            assert delivery.status == COMPLETED
            assert delivery.lease_token is None
            print(
                "PASS: PostgreSQL fenced stale claim; the reclaimed lease finalized once."
            )
    finally:
        async with AsyncSessionLocal() as db:
            organization = await db.get(Organization, organization_id)
            if organization is not None:
                await db.delete(organization)
                await db.commit()


async def run(timeout_seconds: float, simulate_expired_lease: bool) -> None:
    organization_id = uuid.uuid4()
    event_id: uuid.UUID | None = None
    result_count = 0
    try:
        async with AsyncSessionLocal() as db:
            organization = Organization(
                id=organization_id,
                name="Phase 21 Worker E2E",
                slug=f"phase21-e2e-{organization_id.hex[:12]}",
                status="active",
                settings={"purpose": "temporary event-worker E2E"},
                is_active=True,
            )
            event = EventRecord(
                organization_id=organization_id,
                event_type="PHASE21_WORKER_E2E",
                actor_type="SYSTEM",
                payload={
                    "_orchestration_trusted": True,
                    "test_run_id": str(organization_id),
                },
            )
            db.add_all([organization, event])
            await db.flush()
            event_id = event.id
            await ensure_trusted_event_delivery(db, event)
            if simulate_expired_lease:
                delivery = await db.scalar(
                    select(EventDelivery).where(EventDelivery.event_id == event.id)
                )
                assert delivery is not None
                delivery.status = "PROCESSING"
                delivery.attempts = 1
                delivery.lease_until = datetime.now(timezone.utc) - timedelta(seconds=1)
                delivery.lease_token = str(uuid.uuid4())
            await db.commit()

        deadline = asyncio.get_running_loop().time() + timeout_seconds
        while asyncio.get_running_loop().time() < deadline:
            async with AsyncSessionLocal() as db:
                delivery = await db.scalar(
                    select(EventDelivery).where(EventDelivery.event_id == event_id)
                )
                results = (
                    await db.execute(
                        select(EventRecord).where(
                            EventRecord.organization_id == organization_id,
                            EventRecord.event_type == "ORCHESTRATION_RESULT",
                            EventRecord.payload["source_event_id"].as_string() == str(event_id),
                        )
                    )
                ).scalars().all()
                result_count = len(results)
                if delivery is not None and delivery.status == "COMPLETED":
                    if result_count != 1:
                        raise AssertionError(
                            f"Expected exactly one orchestration result; found {result_count}."
                        )
                    if simulate_expired_lease and delivery.attempts != 2:
                        raise AssertionError(
                            "Expected the expired lease to be reclaimed exactly once; "
                            f"delivery attempts were {delivery.attempts}."
                        )
                    print(
                        "PASS: Compose worker completed one durable event delivery"
                        f" (expired_lease_recovery={simulate_expired_lease}); "
                        f"attempts={delivery.attempts}, duplicate_results={result_count - 1}."
                    )
                    return
            await asyncio.sleep(0.25)

        raise TimeoutError(
            f"No worker completed delivery {event_id} within {timeout_seconds:g} seconds."
        )
    finally:
        # Remove only the isolated organization created by this script. Its event,
        # outbox, and orchestration-result rows are removed by declared FK cascades.
        async with AsyncSessionLocal() as db:
            organization = await db.get(Organization, organization_id)
            if organization is not None:
                await db.delete(organization)
                await db.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument(
        "--verify-stale-claim-fencing",
        action="store_true",
        help="use PostgreSQL to verify an expired worker cannot finalize a newer claim",
    )
    parser.add_argument(
        "--simulate-expired-lease",
        action="store_true",
        help="start from a persisted expired PROCESSING lease to exercise crash recovery",
    )
    args = parser.parse_args()
    if args.verify_stale_claim_fencing:
        asyncio.run(verify_stale_claim_fencing())
        return
    asyncio.run(run(args.timeout, args.simulate_expired_lease))


if __name__ == "__main__":
    main()
