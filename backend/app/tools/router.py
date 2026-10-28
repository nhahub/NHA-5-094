"""HTTP entry points for case-scoped, policy-filtered tool discovery and execution."""
import uuid
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_db
from app.security.models import User
from app.security.router import get_current_user
from app.tools.schemas import ToolDefinition, ToolExecutionRequest, ToolExecutionResult
from app.tools.service import ToolGatewayService, ToolPolicyError

tools_router = APIRouter(prefix="/tools", tags=["Tools"])


@tools_router.get("", response_model=List[ToolDefinition])
async def list_available_tools(
    case_id: uuid.UUID = Query(..., description="Only list tools enabled for this case's process."),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    try:
        return await ToolGatewayService.list_tools(db, current_user, case_id)
    except ToolPolicyError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@tools_router.post("/execute", response_model=ToolExecutionResult)
async def execute_tool(
    request: ToolExecutionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    # Agent identity is supplied only by trusted in-process orchestration.
    result = await ToolGatewayService.execute_tool(db, request, current_user)
    if not result.success:
        raise HTTPException(
            status_code=result.http_status_code,
            detail={"error": result.error, "execution_id": str(result.execution_id)},
        )
    return result
