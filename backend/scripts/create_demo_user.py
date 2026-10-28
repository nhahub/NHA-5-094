"""Create a demo organization, admin user, and load demo process definition."""
from __future__ import annotations

import asyncio
import getpass
import sys
import uuid
from pathlib import Path

# Ensure backend root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

import app.main  # noqa: F401
from app.core.config import settings
from app.domain.organizations.models import Organization
from app.domain.processes.configuration_loader import load_process_definition
from app.infrastructure.database.session import AsyncSessionLocal
from app.security.models import RoleEnum
from app.security.schemas import UserCreate
from app.security.service import AuthService


async def setup_demo_account(
    email: str,
    password: str,
    full_name: str = "Local Administrator",
) -> None:
    if settings.APP_ENV.lower() != "development":
        raise RuntimeError("Demo-account bootstrap is available only when APP_ENV=development.")
    if len(password) < 15 or len(password.encode("utf-8")) > 72:
        raise ValueError("Use a password with at least 15 characters and no more than 72 UTF-8 bytes.")

    email = email.strip().lower()
    if not email:
        raise ValueError("A demo administrator email is required.")

    async with AsyncSessionLocal() as db:
        # 1. Check or create demo organization
        result = await db.execute(select(Organization).limit(1))
        org = result.scalars().first()
        if not org:
            org = Organization(
                id=uuid.uuid4(),
                name="Verifia Demo Organization",
                slug="verifia-demo",
                status="active",
                settings={},
                is_active=True,
            )
            db.add(org)
            await db.commit()
            await db.refresh(org)
            print(f"Created organization: {org.name} ({org.id})")
        else:
            print(f"Using existing organization: {org.name} ({org.id})")

        # 2. Check or create demo user
        user = await AuthService.get_user_by_email(db, email)
        if user:
            raise ValueError("This email already has an account. Choose another email; existing passwords are never reset by this script.")

        user_in = UserCreate(
            organization_id=org.id,
            email=email,
            full_name=full_name,
            password=password,
            role=RoleEnum.ADMIN,
            is_active=True,
        )
        user = await AuthService.create_user(db, user_in)
        print("Created local demo administrator:")

        print("=" * 45)
        print(f"Email:    {email}")
        print("Password: the value entered at the prompt (not stored or displayed)")
        print("=" * 45)

        # 3. Load workflow if not loaded
        config_path = Path(__file__).resolve().parents[2] / "workflows" / "import_export" / "process.json"
        if config_path.exists():
            try:
                process, version = await load_process_definition(
                    db, organization_id=org.id, path=config_path, process_id=None
                )
                print(f"Loaded process workflow: {process.code} v{version.version_number}")
            except SQLAlchemyError:
                await db.rollback()
                print("Note: Demo workflow was not loaded; a matching process may already exist.")


def main() -> None:
    if settings.APP_ENV.lower() != "development":
        raise SystemExit("Refusing to create demo data unless APP_ENV=development.")

    import argparse
    parser = argparse.ArgumentParser(description="Create local demo administrator account.")
    parser.add_argument("--email", "-e", help="Administrator email address")
    args = parser.parse_args()

    email = args.email

    if not email:
        email = input("Local demo administrator email [admin@example.com]: ").strip()
        if not email:
            email = "admin@example.com"

    password = getpass.getpass("Set a local demo password (15+ characters): ")
    confirmation = getpass.getpass("Confirm the password: ")
    if password != confirmation:
        raise SystemExit("The passwords did not match.")

    asyncio.run(setup_demo_account(email=email, password=password))


if __name__ == "__main__":
    main()


