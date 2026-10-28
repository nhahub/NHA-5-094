import uuid
from datetime import UTC, datetime, timedelta

import bcrypt as _bcrypt
from jose import JWTError, jwt
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.security.models import RoleEnum, User
from app.security.schemas import ProvisionedUserCreate, UserCreate

# Use bcrypt directly instead of passlib to be compatible with both bcrypt
# 4.x (pinned in requirements.txt for CI) and bcrypt 5.x (which may be
# present on the local host). Passlib 1.7.4's bcrypt backend detection breaks
# with bcrypt 5.x because it removed the __about__ sub-module and tightened
# the 72-byte limit enforcement in a way that disrupts passlib's internal
# wrap-bug detection probe. Direct bcrypt calls work identically on both
# versions and produce the same standard $2b$ hash format.


class AuthService:
    """Service handling password hashing, JWT generation, and user auth."""

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        try:
            return _bcrypt.checkpw(
                plain_password.encode("utf-8"),
                hashed_password.encode("utf-8"),
            )
        except Exception:
            return False

    @staticmethod
    def get_password_hash(password: str) -> str:
        return _bcrypt.hashpw(
            password.encode("utf-8"),
            _bcrypt.gensalt(),
        ).decode("utf-8")

    @staticmethod
    def create_access_token(
        user_id: uuid.UUID,
        organization_id: uuid.UUID,
        role: RoleEnum,
        token_version: int = 0,
        expires_delta: timedelta | None = None,
    ) -> str:
        if expires_delta:
            expire = datetime.now(UTC) + expires_delta
        else:
            expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode = {
            "sub": str(user_id),
            "org_id": str(organization_id),
            "role": role.value,
            "ver": token_version,
            "exp": int(expire.timestamp()),
        }
        return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    @staticmethod
    def decode_token(token: str) -> dict | None:
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            return payload
        except JWTError:
            return None

    @classmethod
    async def get_user_by_email(cls, db: AsyncSession, email: str) -> User | None:
        users = await cls.get_users_by_email(db, email)
        return users[0] if len(users) == 1 else None

    @classmethod
    async def get_users_by_email(cls, db: AsyncSession, email: str) -> list[User]:
        normalized = cls.normalize_email(email)
        result = await db.execute(select(User).where(func.lower(User.email) == normalized))
        return list(result.scalars().all())

    @staticmethod
    def normalize_email(email: str) -> str:
        return email.strip().lower()

    @classmethod
    async def get_user_by_id(cls, db: AsyncSession, user_id: uuid.UUID) -> User | None:
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalars().first()

    @classmethod
    async def list_organization_users(
        cls,
        db: AsyncSession,
        organization_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[User]:
        result = await db.execute(
            select(User)
            .where(User.organization_id == organization_id)
            .order_by(func.lower(User.email))
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    @classmethod
    async def create_user(cls, db: AsyncSession, user_in: UserCreate) -> User:
        hashed_password = cls.get_password_hash(user_in.password)
        db_user = User(
            organization_id=user_in.organization_id,
            email=cls.normalize_email(user_in.email),
            name=user_in.full_name,
            hashed_password=hashed_password,
            role=user_in.role,
            is_active=user_in.is_active,
        )
        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)
        return db_user

    @classmethod
    async def provision_user(
        cls,
        db: AsyncSession,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID,
        user_in: ProvisionedUserCreate,
    ) -> User:
        # Import locally to avoid the audit package's router importing this auth module.
        from app.domain.audit.models import AuditLog

        email = cls.normalize_email(str(user_in.email))
        if await cls.get_users_by_email(db, email):
            raise ValueError("Unable to provision this account with the supplied details.")

        role = RoleEnum(user_in.role)
        user = User(
            organization_id=organization_id,
            email=email,
            name=user_in.full_name,
            hashed_password=cls.get_password_hash(user_in.password),
            role=role,
            is_active=True,
        )
        db.add(user)
        try:
            await db.flush()
            db.add(
                AuditLog(
                    organization_id=organization_id,
                    actor_type="USER",
                    actor_id=actor_id,
                    action="USER_PROVISIONED",
                    resource_type="USER",
                    resource_id=user.id,
                    after_state={
                        "email": email,
                        "role": role.value,
                        "is_active": True,
                    },
                    audit_metadata={"provisioning_method": "organization_admin"},
                )
            )
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise ValueError("Unable to provision this account with the supplied details.") from exc
        await db.refresh(user)
        return user

    @classmethod
    async def _set_password(
        cls, db: AsyncSession, *, user: User, new_password: str, actor_id: uuid.UUID, action: str
    ) -> None:
        from app.domain.audit.models import AuditLog

        user.hashed_password = cls.get_password_hash(new_password)
        user.token_version += 1
        db.add(
            AuditLog(
                organization_id=user.organization_id,
                actor_type="USER",
                actor_id=actor_id,
                action=action,
                resource_type="USER",
                resource_id=user.id,
                after_state={"email": user.email, "token_version": user.token_version},
                audit_metadata={"credential_material_recorded": False},
            )
        )
        await db.commit()

    @staticmethod
    async def revoke_access_tokens(
        db: AsyncSession, *, user: User, actor_id: uuid.UUID
    ) -> None:
        from app.domain.audit.models import AuditLog

        user.token_version += 1
        db.add(
            AuditLog(
                organization_id=user.organization_id,
                actor_type="USER",
                actor_id=actor_id,
                action="USER_SESSIONS_REVOKED",
                resource_type="USER",
                resource_id=user.id,
                after_state={"token_version": user.token_version},
                audit_metadata={"reason": "logout"},
            )
        )
        await db.commit()

    @classmethod
    async def change_password(
        cls, db: AsyncSession, *, user: User, current_password: str, new_password: str
    ) -> bool:
        if (
            not cls.verify_password(current_password, user.hashed_password)
            or cls.verify_password(new_password, user.hashed_password)
        ):
            return False
        await cls._set_password(
            db,
            user=user,
            new_password=new_password,
            actor_id=user.id,
            action="USER_PASSWORD_CHANGED",
        )
        return True

    @classmethod
    async def admin_reset_password(
        cls,
        db: AsyncSession,
        *,
        organization_id: uuid.UUID,
        target_user_id: uuid.UUID,
        actor_id: uuid.UUID,
        new_password: str,
    ) -> User | None:
        user = (await db.execute(
            select(User).where(
                User.id == target_user_id,
                User.organization_id == organization_id,
            )
        )).scalars().first()
        if user is None:
            return None
        await cls._set_password(
            db,
            user=user,
            new_password=new_password,
            actor_id=actor_id,
            action="USER_PASSWORD_RESET",
        )
        return user

    @classmethod
    async def authenticate_user(
        cls, db: AsyncSession, email: str, password: str
    ) -> User | None:
        users = await cls.get_users_by_email(db, email)
        if len(users) != 1:
            return None
        user = users[0]
        if not user.is_active:
            return None
        from app.domain.organizations.models import Organization

        organization = await db.get(Organization, user.organization_id)
        if not organization or not organization.is_active or organization.status.lower() != "active":
            return None
        if not cls.verify_password(password, user.hashed_password):
            return None
        return user
