"""API Router for AI Agents — Phase 10."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.document_agent import DocumentAgentError
from app.agents.schemas import (
    AgentRunRequest,
    AgentRunResponse,
    DocumentAgentResult,
    DocumentAgentRunRequest,
)
from app.agents.service import AgentOrchestratorService
from app.agents.supervisor_agent import SupervisorAgentError
from app.infrastructure.database.session import get_db
from app.infrastructure.storage import StorageBackend, get_storage_backend
from app.security.authorization import require_internal_user
from app.security.models import User
from app.security.router import get_current_user

agents_router = APIRouter(prefix="/agents", tags=["Agents"])


@agents_router.post(
    "/document/process",
    response_model=DocumentAgentResult,
    status_code=status.HTTP_200_OK,
    summary="Run the Document Agent on a specific case document",
)
async def process_document_agent(
    request: DocumentAgentRunRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: StorageBackend = Depends(get_storage_backend),
) -> Any:
    require_internal_user(current_user)
    try:
        return await AgentOrchestratorService.process_document(
            db=db,
            actor=current_user,
            request=request,
            storage=storage,
        )
    except DocumentAgentError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


@agents_router.post(
    "/run",
    response_model=AgentRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Run an AI agent by type (supervisor, document, verification, workflow)",
)
async def run_agent(
    request: AgentRunRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: StorageBackend = Depends(get_storage_backend),
) -> Any:
    require_internal_user(current_user)
    try:
        return await AgentOrchestratorService.run_agent(
            db=db,
            actor=current_user,
            request=request,
            storage=storage,
        )
    except SupervisorAgentError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=str(exc),
        )
    except (DocumentAgentError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
