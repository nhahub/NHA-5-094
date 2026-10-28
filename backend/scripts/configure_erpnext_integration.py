"""Configure organization-scoped ERPNext integration references without secrets."""
from __future__ import annotations

import argparse
import asyncio
import uuid

# Import the application so all ORM tables are registered on shared metadata
# before the integration models resolve their organization foreign keys.
import app.main  # noqa: F401
from app.infrastructure.database.session import AsyncSessionLocal
from app.tools.integrations import IntegrationService


async def _configure(
    organization_id: uuid.UUID, base_url: str,
    credential_reference: str, integration_types: list[str],
) -> None:
    async with AsyncSessionLocal() as db:
        for integration_type in integration_types:
            integration, _ = await IntegrationService.create_erpnext_connection(
                db,
                organization_id=organization_id,
                name=f"Northstar ERPNext {integration_type.title()} Test Connection",
                integration_type=integration_type,
                base_url=base_url,
                secret_reference=credential_reference,
            )
            print(f"Configured {integration.integration_type} integration {integration.id}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organization-id", required=True, type=uuid.UUID)
    parser.add_argument("--base-url", required=True, help="ERPNext origin, e.g. https://erp.example.test")
    parser.add_argument("--credential-reference", default="env:ERP_NEXT_API_CREDENTIALS")
    parser.add_argument("--types", nargs="+", choices=["ERP", "FINANCE"], default=["ERP", "FINANCE"])
    args = parser.parse_args()
    asyncio.run(_configure(
        args.organization_id, args.base_url, args.credential_reference, args.types,
    ))


if __name__ == "__main__":
    main()
