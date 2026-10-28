from typing import Any

from pydantic import BaseModel


class CaseReviewBundle(BaseModel):
    """Organization-scoped aggregate used by human review clients."""

    case: dict[str, Any]
    review_tasks: list[dict[str, Any]]
    approvals: list[dict[str, Any]]
    documents: list[dict[str, Any]]
    verifications: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    discrepancies: list[dict[str, Any]]
    recommendations: list[dict[str, Any]]
