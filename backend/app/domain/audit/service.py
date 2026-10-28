import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.audit.models import AuditLog


class AuditService:
    """Service recording and retrieving security and compliance audit logs."""

    @classmethod
    def _sanitize_json(cls, data: Any) -> Any:
        """Recursively convert UUIDs, datetimes, and non-primitive objects to JSON primitives."""
        if data is None:
            return None
        if isinstance(data, uuid.UUID):
            return str(data)
        if isinstance(data, Decimal):
            return str(data)
        if hasattr(data, "isoformat") and callable(data.isoformat):
            return data.isoformat()
        if isinstance(data, dict):
            return {str(k): cls._sanitize_json(v) for k, v in data.items()}
        if isinstance(data, (list, tuple, set)):
            return [cls._sanitize_json(item) for item in data]
        return data

    @classmethod
    async def log_action(
        cls,
        db: AsyncSession,
        organization_id: uuid.UUID,
        action: str,
        resource_type: str,
        actor_type: str = "USER",
        actor_id: Optional[uuid.UUID] = None,
        resource_id: Optional[uuid.UUID] = None,
        before_state: Optional[Dict[str, Any]] = None,
        after_state: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        audit_metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> AuditLog:
        # Support user_id/details backward compatibility
        if actor_id is None and "user_id" in kwargs:
            actor_id = kwargs["user_id"]
        if audit_metadata is None and "details" in kwargs:
            audit_metadata = kwargs["details"]

        log_entry = AuditLog(
            organization_id=organization_id,
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            before_state=cls._sanitize_json(before_state),
            after_state=cls._sanitize_json(after_state),
            ip_address=ip_address,
            audit_metadata=cls._sanitize_json(audit_metadata or {}),
        )
        db.add(log_entry)
        await db.commit()
        await db.refresh(log_entry)
        return log_entry

    @staticmethod
    async def get_audit_logs(
        db: AsyncSession, organization_id: uuid.UUID, skip: int = 0, limit: int = 100
    ) -> List[AuditLog]:
        stmt = (
            select(AuditLog)
            .where(AuditLog.organization_id == organization_id)
            .order_by(AuditLog.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())
