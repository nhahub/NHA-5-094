"""Publish a JSON process definition for an organization using domain services."""
from __future__ import annotations

import argparse
import asyncio
import uuid
from pathlib import Path

# Import the application so all ORM tables are registered on shared metadata
# before process services issue cross-domain queries.
import app.main  # noqa: F401
from app.domain.processes.configuration_loader import load_process_definition
from app.infrastructure.database.session import AsyncSessionLocal


async def _load(organization_id: uuid.UUID, path: Path, process_id: uuid.UUID | None) -> None:
    async with AsyncSessionLocal() as db:
        process, version = await load_process_definition(
            db, organization_id=organization_id, path=path, process_id=process_id,
        )
        print(f"Published {process.code} version {version.version_number} ({version.id})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organization-id", required=True, type=uuid.UUID)
    parser.add_argument(
        "--process-id", type=uuid.UUID,
        help="Publish a new immutable version of an existing matching process.",
    )
    parser.add_argument(
        "--config", type=Path,
        default=Path(__file__).resolve().parents[2] / "workflows" / "import_export" / "process.json",
    )
    args = parser.parse_args()
    asyncio.run(_load(args.organization_id, args.config, args.process_id))


if __name__ == "__main__":
    main()
