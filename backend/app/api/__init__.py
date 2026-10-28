"""API package aggregating all domain and infrastructure routers for API v1."""
from fastapi import APIRouter

from app.security import auth_router
from app.domain.cases import cases_router
from app.domain.processes import processes_router
from app.domain.workflows import workflows_router
from app.domain.documents import documents_router
from app.domain.verifications import verification_router
from app.domain.rules import rules_router
from app.domain.tasks import tasks_router
from app.domain.approvals import approvals_router
from app.domain.knowledge import knowledge_router
from app.tools import tools_router
from app.agents.router import agents_router
from app.events import events_router
from app.domain.audit import audit_router

api_router = APIRouter()

# Register all domain sub-routers
api_router.include_router(auth_router)
api_router.include_router(cases_router)
api_router.include_router(processes_router)
api_router.include_router(workflows_router)
api_router.include_router(documents_router)
api_router.include_router(verification_router)
api_router.include_router(rules_router)
api_router.include_router(tasks_router)
api_router.include_router(approvals_router)
api_router.include_router(knowledge_router)
api_router.include_router(tools_router)
api_router.include_router(agents_router)
api_router.include_router(events_router)
api_router.include_router(audit_router)

__all__ = ["api_router"]
