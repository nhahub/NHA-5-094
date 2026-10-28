"""Configure the least-privilege Tool Gateway grants for the Phase 17 demo."""
from __future__ import annotations

import argparse
import asyncio
import uuid

from sqlalchemy import select

import app.main  # noqa: F401 - register all ORM models before issuing queries
from app.infrastructure.database.session import AsyncSessionLocal
from app.security.models import Permission, Role, RolePermission

PHASE17_TOOL_PERMISSIONS = (
    "tool.check_required_documents",
    "tool.compare_documents",
    "tool.calculate_order_total",
    "tool.run_verification",
    "tool.check_inventory",
    "tool.get_customer",
    "tool.get_payment_status",
    "tool.create_task",
    "tool.request_approval",
    "tool.transition_workflow",
)
PHASE17_ROLES = ("EMPLOYEE", "MANAGER")


async def configure(organization_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as db:
        for code in PHASE17_TOOL_PERMISSIONS:
            permission = (await db.execute(
                select(Permission).where(Permission.code == code)
            )).scalars().first()
            if permission is None:
                permission = Permission(code=code, description="Phase 17 demo Tool Gateway capability")
                db.add(permission)
                await db.flush()

            for role_name in PHASE17_ROLES:
                role = (await db.execute(
                    select(Role).where(
                        Role.organization_id == organization_id,
                        Role.name == role_name,
                    )
                )).scalars().first()
                if role is None:
                    role = Role(
                        organization_id=organization_id,
                        name=role_name,
                        description="Phase 17 synthetic evaluation role",
                    )
                    db.add(role)
                    await db.flush()
                existing = (await db.execute(
                    select(RolePermission).where(
                        RolePermission.role_id == role.id,
                        RolePermission.permission_id == permission.id,
                    )
                )).scalars().first()
                if existing is None:
                    db.add(RolePermission(role_id=role.id, permission_id=permission.id))
        await db.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organization-id", required=True, type=uuid.UUID)
    args = parser.parse_args()
    asyncio.run(configure(args.organization_id))
    print("Configured Phase 17 Tool Gateway permissions for EMPLOYEE and MANAGER roles.")


if __name__ == "__main__":
    main()
