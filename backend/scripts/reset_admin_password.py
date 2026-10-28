import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.infrastructure.database.session import AsyncSessionLocal
from app.security.service import AuthService
from app.security.models import User
from sqlalchemy import select

async def reset():
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(User))
        users = res.scalars().all()
        print(f"Found {len(users)} existing user(s)")
        if not users:
            print("No users found. Creating demo account...")
            from scripts.create_demo_user import setup_demo_account
            await setup_demo_account("admin@example.com", "AdminSecurePassword2026!")
            return

        for u in users:
            u.hashed_password = AuthService.get_password_hash("AdminSecurePassword2026!")
            print(f"Updated password for user: {u.email}")
        await db.commit()
        print("Password reset successfully!")

if __name__ == "__main__":
    asyncio.run(reset())
