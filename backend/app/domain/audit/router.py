from typing import Any, List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.audit.schemas import AuditLogRead
from app.domain.audit.service import AuditService
from app.infrastructure.database.session import get_db
from app.security.models import User
from app.security.router import require_admin

audit_router = APIRouter(prefix="/audit", tags=["Audit"])


@audit_router.get("", response_model=List[AuditLogRead])
async def list_audit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Any:
    return await AuditService.get_audit_logs(
        db, organization_id=current_user.organization_id, skip=skip, limit=limit
    )
