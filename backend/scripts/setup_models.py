"""
Complete Phase 2 ORM Model Definitions Script.
Writes standard SQLAlchemy 2.0 models for all 44 tables in Documentation/03-database-schema.md.
"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(BASE_DIR, "app")


def write_file(rel_path: str, content: str):
    full_path = os.path.join(APP_DIR, rel_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content.strip() + "\n")
    print(f"Generated: {rel_path}")


# 1. Organization
write_file(
    "domain/organizations/models.py",
    '''from __future__ import annotations
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import Boolean, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base

if TYPE_CHECKING:
    from app.security.models import Role, User


class Organization(Base):
    """Top-level tenant entity. Every business resource is isolated to an organization."""

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    settings: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    users: Mapped[List["User"]] = relationship("User", back_populates="organization", cascade="all, delete-orphan")
    departments: Mapped[List["Department"]] = relationship("Department", back_populates="organization", cascade="all, delete-orphan")
    roles: Mapped[List["Role"]] = relationship("Role", back_populates="organization", cascade="all, delete-orphan")


class Department(Base):
    """Department grouping within an organization (e.g. Finance, Legal, Logistics)."""

    __tablename__ = "departments"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization", back_populates="departments")
    members: Mapped[List["DepartmentMember"]] = relationship("DepartmentMember", back_populates="department", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_departments_org_name"),
    )


class DepartmentMember(Base):
    """Associates users with departments."""

    __tablename__ = "department_members"

    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    )

    department: Mapped["Department"] = relationship("Department", back_populates="members")
    user: Mapped["User"] = relationship("User", back_populates="department_memberships")
''',
)

# 2. Security & RBAC
write_file(
    "security/models.py",
    '''from __future__ import annotations
import enum
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import Boolean, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base
from app.domain.organizations.models import DepartmentMember, Organization

if TYPE_CHECKING:
    from app.domain.organizations.models import DepartmentMember, Organization


class RoleEnum(str, enum.Enum):
    CUSTOMER = "CUSTOMER"
    EMPLOYEE = "EMPLOYEE"
    MANAGER = "MANAGER"
    ADMIN = "ADMIN"


class User(Base):
    """Platform user belonging to a specific organization."""

    __tablename__ = "users"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    role: Mapped[RoleEnum] = mapped_column(
        Enum(RoleEnum, name="user_role_enum"),
        default=RoleEnum.EMPLOYEE,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization", back_populates="users")
    department_memberships: Mapped[List["DepartmentMember"]] = relationship("DepartmentMember", back_populates="user", cascade="all, delete-orphan")
    user_roles: Mapped[List["UserRole"]] = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("organization_id", "email", name="uq_users_org_email"),
    )


class Role(Base):
    """RBAC Role configured per organization."""

    __tablename__ = "roles"

    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    organization: Mapped[Optional["Organization"]] = relationship("Organization", back_populates="roles")
    role_permissions: Mapped[List["RolePermission"]] = relationship("RolePermission", back_populates="role", cascade="all, delete-orphan")
    user_roles: Mapped[List["UserRole"]] = relationship("UserRole", back_populates="role", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_roles_org_name"),
    )


class Permission(Base):
    """System-level permission code."""

    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    role_permissions: Mapped[List["RolePermission"]] = relationship("RolePermission", back_populates="permission", cascade="all, delete-orphan")


class RolePermission(Base):
    """Mapping between roles and permissions."""

    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    )

    role: Mapped["Role"] = relationship("Role", back_populates="role_permissions")
    permission: Mapped["Permission"] = relationship("Permission", back_populates="role_permissions")


class UserRole(Base):
    """Mapping between users and roles."""

    __tablename__ = "user_roles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    )

    user: Mapped["User"] = relationship("User", back_populates="user_roles")
    role: Mapped["Role"] = relationship("Role", back_populates="user_roles")
''',
)

# 3. Processes & Requirements
write_file(
    "domain/processes/models.py",
    '''from __future__ import annotations
import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base

if TYPE_CHECKING:
    from app.domain.rules.models import BusinessRule, CalculationDefinition
    from app.domain.verifications.models import VerificationDefinition
    from app.domain.workflows.models import WorkflowStage, WorkflowTransition


class ProcessStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ARCHIVED = "ARCHIVED"


class ProcessVersionStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class RequirementType(str, enum.Enum):
    DOCUMENT = "DOCUMENT"
    DATA = "DATA"
    VERIFICATION = "VERIFICATION"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    APPROVAL = "APPROVAL"


class Process(Base):
    """Business process definition (e.g. Import Order Verification, Tax Check)."""

    __tablename__ = "processes"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default=ProcessStatus.ACTIVE.value)

    versions: Mapped[List["ProcessVersion"]] = relationship("ProcessVersion", back_populates="process", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_processes_org_code"),
    )


class ProcessVersion(Base):
    """Immutable versioned snapshot of a process configuration."""

    __tablename__ = "process_versions"

    process_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("processes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default=ProcessVersionStatus.DRAFT.value)
    configuration: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    process: Mapped["Process"] = relationship("Process", back_populates="versions")
    stages: Mapped[List["WorkflowStage"]] = relationship("WorkflowStage", back_populates="process_version", cascade="all, delete-orphan")
    transitions: Mapped[List["WorkflowTransition"]] = relationship("WorkflowTransition", back_populates="process_version", cascade="all, delete-orphan")
    requirements: Mapped[List["Requirement"]] = relationship("Requirement", back_populates="process_version", cascade="all, delete-orphan")
    verifications: Mapped[List["VerificationDefinition"]] = relationship("VerificationDefinition", back_populates="process_version", cascade="all, delete-orphan")
    rules: Mapped[List["BusinessRule"]] = relationship("BusinessRule", back_populates="process_version", cascade="all, delete-orphan")
    calculations: Mapped[List["CalculationDefinition"]] = relationship("CalculationDefinition", back_populates="process_version", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("process_id", "version_number", name="uq_process_versions_proc_version"),
    )


class Requirement(Base):
    """Prerequisites that must be satisfied before stage entry/exit or process completion."""

    __tablename__ = "requirements"

    process_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("process_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_stages.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False, default=RequirementType.DOCUMENT.value)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    configuration: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    process_version: Mapped["ProcessVersion"] = relationship("ProcessVersion", back_populates="requirements")
''',
)

# 4. Workflows & Stages
write_file(
    "domain/workflows/models.py",
    '''from __future__ import annotations
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base

if TYPE_CHECKING:
    from app.domain.processes.models import ProcessVersion


class WorkflowStage(Base):
    """Discrete state/stage in a process lifecycle."""

    __tablename__ = "workflow_stages"

    process_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("process_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    stage_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_initial: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_terminal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    config: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    process_version: Mapped["ProcessVersion"] = relationship("ProcessVersion", back_populates="stages")


class WorkflowTransition(Base):
    """Deterministic, validated route between workflow stages."""

    __tablename__ = "workflow_transitions"

    process_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("process_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_stage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_stages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    to_stage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_stages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    condition_config: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    required_role: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    process_version: Mapped["ProcessVersion"] = relationship("ProcessVersion", back_populates="transitions")
''',
)

# 5. Cases & Runtime
write_file(
    "domain/cases/models.py",
    '''from __future__ import annotations
import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import DateTime, ForeignKey, Index, JSON, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base

if TYPE_CHECKING:
    from app.domain.approvals.models import Approval
    from app.domain.documents.models import Document, Evidence
    from app.domain.tasks.models import Task
    from app.domain.verifications.models import VerificationExecution


class CaseStatus(str, enum.Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    PENDING_REVIEW = "PENDING_REVIEW"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class CasePriority(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class ParticipantType(str, enum.Enum):
    CUSTOMER = "CUSTOMER"
    ASSIGNEE = "ASSIGNEE"
    REVIEWER = "REVIEWER"
    OBSERVER = "OBSERVER"


class Case(Base):
    """A running execution instance of a Process bound to an immutable ProcessVersion."""

    __tablename__ = "cases"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    process_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("processes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    process_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("process_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    case_number: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default=CaseStatus.OPEN.value, index=True)
    current_stage_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_stages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    case_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    # Relationships
    participants: Mapped[List["CaseParticipant"]] = relationship("CaseParticipant", back_populates="case", cascade="all, delete-orphan")
    case_data: Mapped[List["CaseData"]] = relationship("CaseData", back_populates="case", cascade="all, delete-orphan")
    stage_history: Mapped[List["CaseStageHistory"]] = relationship("CaseStageHistory", back_populates="case", cascade="all, delete-orphan")
    documents: Mapped[List["Document"]] = relationship("Document", back_populates="case", cascade="all, delete-orphan")
    evidence: Mapped[List["Evidence"]] = relationship("Evidence", back_populates="case", cascade="all, delete-orphan")
    verifications: Mapped[List["VerificationExecution"]] = relationship("VerificationExecution", back_populates="case", cascade="all, delete-orphan")
    tasks: Mapped[List["Task"]] = relationship("Task", back_populates="case", cascade="all, delete-orphan")
    approvals: Mapped[List["Approval"]] = relationship("Approval", back_populates="case", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_cases_org_status", "organization_id", "status"),
        Index("idx_cases_org_stage", "organization_id", "current_stage_id"),
    )


class CaseParticipant(Base):
    """People or actors involved in a specific case."""

    __tablename__ = "case_participants"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    participant_type: Mapped[str] = mapped_column(String(50), nullable=False, default=ParticipantType.CUSTOMER.value)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    external_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    case: Mapped["Case"] = relationship("Case", back_populates="participants")


class CaseData(Base):
    """Dynamic key-value or extracted structured facts accumulated for a case."""

    __tablename__ = "case_data"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    field_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    field_value: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    source_type: Mapped[str] = mapped_column(String(100), nullable=False, default="DOCUMENT")
    source_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)

    case: Mapped["Case"] = relationship("Case", back_populates="case_data")


class CaseStageHistory(Base):
    """Direct, auditable business state stage transitions history."""

    __tablename__ = "case_stage_history"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_stage_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_stages.id", ondelete="SET NULL"),
        nullable=True,
    )
    to_stage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_stages.id", ondelete="CASCADE"),
        nullable=False,
    )
    transition_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_transitions.id", ondelete="SET NULL"),
        nullable=True,
    )
    triggered_by_type: Mapped[str] = mapped_column(String(50), nullable=False, default="SYSTEM")
    triggered_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    case: Mapped["Case"] = relationship("Case", back_populates="stage_history")
''',
)

# 6. Documents & Evidence
write_file(
    "domain/documents/models.py",
    '''from __future__ import annotations
import enum
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import BigInteger, ForeignKey, Index, Integer, JSON, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base

if TYPE_CHECKING:
    from app.domain.cases.models import Case


class DocumentStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


# Backward compatibility alias
DocumentProcessingStatus = DocumentStatus


class Document(Base):
    """Top-level document record uploaded to a Case."""

    __tablename__ = "documents"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default=DocumentStatus.PENDING.value)
    uploaded_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    storage_reference: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    case: Mapped["Case"] = relationship("Case", back_populates="documents")
    versions: Mapped[List["DocumentVersion"]] = relationship("DocumentVersion", back_populates="document", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_documents_case_type", "case_id", "document_type"),
    )


class DocumentVersion(Base):
    """Immutable versioned file binary reference for a document."""

    __tablename__ = "document_versions"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    storage_reference: Mapped[str] = mapped_column(Text, nullable=False)
    file_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    uploaded_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    document: Mapped["Document"] = relationship("Document", back_populates="versions")
    extracted_fields: Mapped[List["ExtractedField"]] = relationship("ExtractedField", back_populates="document_version", cascade="all, delete-orphan")


class ExtractedField(Base):
    """Structured field extracted from a document version by Document Agent / OCR."""

    __tablename__ = "extracted_fields"

    document_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    field_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    field_value: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    bounding_box: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    extraction_method: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    document_version: Mapped["DocumentVersion"] = relationship("DocumentVersion", back_populates="extracted_fields")


class Evidence(Base):
    """A collection of supporting facts, citations and locators for decisions."""

    __tablename__ = "evidence"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evidence_type: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    case: Mapped["Case"] = relationship("Case", back_populates="evidence")
    items: Mapped[List["EvidenceItem"]] = relationship("EvidenceItem", back_populates="evidence", cascade="all, delete-orphan")


class EvidenceItem(Base):
    """Specific line item, bounding box, or system snapshot supporting an evidence bundle."""

    __tablename__ = "evidence_items"

    evidence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidence.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    field_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    value_snapshot: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    location: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    evidence: Mapped["Evidence"] = relationship("Evidence", back_populates="items")
''',
)

# 7. Rules & Calculations
write_file(
    "domain/rules/models.py",
    '''from __future__ import annotations
import enum
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base

if TYPE_CHECKING:
    from app.domain.processes.models import ProcessVersion
    from app.domain.verifications.models import VerificationRule


class RuleSeverity(str, enum.Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class BusinessRule(Base):
    """Declarative, deterministic business rule evaluated against extracted case data."""

    __tablename__ = "business_rules"

    process_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("process_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rule_type: Mapped[str] = mapped_column(String(100), nullable=False, default="EQUALITY")
    expression: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    severity: Mapped[str] = mapped_column(String(50), nullable=False, default=RuleSeverity.ERROR.value)

    process_version: Mapped["ProcessVersion"] = relationship("ProcessVersion", back_populates="rules")
    verification_rules: Mapped[List["VerificationRule"]] = relationship("VerificationRule", back_populates="rule", cascade="all, delete-orphan")


class CalculationDefinition(Base):
    """Deterministic mathematical formula definition (e.g. total = qty * unit_price)."""

    __tablename__ = "calculation_definitions"

    process_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("process_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    calculation_type: Mapped[str] = mapped_column(String(100), nullable=False, default="FORMULA")
    configuration: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    process_version: Mapped["ProcessVersion"] = relationship("ProcessVersion", back_populates="calculations")
''',
)

# 8. Verifications & Executions
write_file(
    "domain/verifications/models.py",
    '''from __future__ import annotations
import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base

if TYPE_CHECKING:
    from app.domain.cases.models import Case
    from app.domain.processes.models import ProcessVersion
    from app.domain.rules.models import BusinessRule, CalculationDefinition


class VerificationStatus(str, enum.Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    REVIEW = "REVIEW"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    INCONCLUSIVE = "INCONCLUSIVE"


class VerificationDefinition(Base):
    """Specification of a verification check required in a business process."""

    __tablename__ = "verification_definitions"

    process_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("process_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_stages.id", ondelete="SET NULL"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_policy: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    process_version: Mapped["ProcessVersion"] = relationship("ProcessVersion", back_populates="verifications")
    verification_rules: Mapped[List["VerificationRule"]] = relationship("VerificationRule", back_populates="verification", cascade="all, delete-orphan")


class VerificationRule(Base):
    """Associates business rules with a verification check."""

    __tablename__ = "verification_rules"

    verification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("verification_definitions.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    )
    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_rules.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    )
    execution_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    verification: Mapped["VerificationDefinition"] = relationship("VerificationDefinition", back_populates="verification_rules")
    rule: Mapped["BusinessRule"] = relationship("BusinessRule", back_populates="verification_rules")


class VerificationExecution(Base):
    """Runtime execution instance of a verification definition on a Case."""

    __tablename__ = "verification_executions"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    verification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("verification_definitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, default=VerificationStatus.INCONCLUSIVE.value)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_by_type: Mapped[str] = mapped_column(String(50), nullable=False, default="SYSTEM")
    executed_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    inputs: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    case: Mapped["Case"] = relationship("Case", back_populates="verifications")
    results: Mapped[List["VerificationResult"]] = relationship("VerificationResult", back_populates="verification_execution", cascade="all, delete-orphan")
    rule_executions: Mapped[List["RuleExecution"]] = relationship("RuleExecution", back_populates="verification_execution", cascade="all, delete-orphan")
    calculation_executions: Mapped[List["CalculationExecution"]] = relationship("CalculationExecution", back_populates="verification_execution", cascade="all, delete-orphan")


class VerificationResult(Base):
    """Outcome and summary of a completed verification execution."""

    __tablename__ = "verification_results"

    verification_execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("verification_executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    result: Mapped[str] = mapped_column(String(50), nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    verification_execution: Mapped["VerificationExecution"] = relationship("VerificationExecution", back_populates="results")


class RuleExecution(Base):
    """Detailed trace of an individual rule check within a verification run."""

    __tablename__ = "rule_executions"

    verification_execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("verification_executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_rules.id", ondelete="CASCADE"),
        nullable=False,
    )
    input_data: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    result: Mapped[str] = mapped_column(String(50), nullable=False)
    output_data: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    execution_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    verification_execution: Mapped["VerificationExecution"] = relationship("VerificationExecution", back_populates="rule_executions")


class CalculationExecution(Base):
    """Detailed trace of an individual calculation within a verification run."""

    __tablename__ = "calculation_executions"

    verification_execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("verification_executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    calculation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("calculation_definitions.id", ondelete="CASCADE"),
        nullable=False,
    )
    input_data: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    output_data: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    execution_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    verification_execution: Mapped["VerificationExecution"] = relationship("VerificationExecution", back_populates="calculation_executions")
''',
)

# 9. Tasks
write_file(
    "domain/tasks/models.py",
    '''from __future__ import annotations
import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base

if TYPE_CHECKING:
    from app.domain.approvals.models import Approval
    from app.domain.cases.models import Case


class TaskStatus(str, enum.Enum):
    PENDING = "PENDING"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class TaskPriority(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class Task(Base):
    """Human or system work item attached to a case."""

    __tablename__ = "tasks"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_stages.id", ondelete="SET NULL"),
        nullable=True,
    )
    task_type: Mapped[str] = mapped_column(String(100), nullable=False, default="REVIEW")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default=TaskStatus.PENDING.value)
    priority: Mapped[str] = mapped_column(String(50), nullable=False, default=TaskPriority.MEDIUM.value)
    assigned_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    assigned_role_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_department_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by_type: Mapped[str] = mapped_column(String(50), nullable=False, default="SYSTEM")
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completion_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    case: Mapped["Case"] = relationship("Case", back_populates="tasks")
    approvals: Mapped[List["Approval"]] = relationship("Approval", back_populates="task", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_tasks_assignee_status", "assigned_user_id", "status"),
    )
''',
)

# 10. Approvals
write_file(
    "domain/approvals/models.py",
    '''from __future__ import annotations
import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base

if TYPE_CHECKING:
    from app.domain.cases.models import Case
    from app.domain.tasks.models import Task


class ApprovalDecision(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class Approval(Base):
    """Explicit, auditable human decision authorizing a case to proceed."""

    __tablename__ = "approvals"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    required_role_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="SET NULL"),
        nullable=True,
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    decision: Mapped[str] = mapped_column(String(50), nullable=False, default=ApprovalDecision.PENDING.value)
    decided_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    case: Mapped["Case"] = relationship("Case", back_populates="approvals")
    task: Mapped[Optional["Task"]] = relationship("Task", back_populates="approvals")
''',
)

# 11. Tools & Integrations
write_file(
    "tools/models.py",
    '''import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base


class ToolDefinition(Base):
    """Registered capability usable by AI agents via Tool Gateway."""

    __tablename__ = "tool_definitions"

    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tool_type: Mapped[str] = mapped_column(String(100), nullable=False, default="DETERMINISTIC")
    input_schema: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    output_schema: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    permission_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ToolExecution(Base):
    """Auditable log of every tool execution invoked by agents or system."""

    __tablename__ = "tool_executions"

    case_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    tool_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tool_definitions.id", ondelete="CASCADE"),
        nullable=False,
    )
    requested_by_type: Mapped[str] = mapped_column(String(50), nullable=False, default="AGENT")
    requested_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    input_data: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    output_data: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="SUCCESS")
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Integration(Base):
    """External organizational system connection (ERP, Finance, Logistics)."""

    __tablename__ = "integrations"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    integration_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="ACTIVE")

    configs: Mapped[List["IntegrationConfig"]] = relationship("IntegrationConfig", back_populates="integration", cascade="all, delete-orphan")


class IntegrationConfig(Base):
    """Metadata and credential references for an integration adapter."""

    __tablename__ = "integration_configs"

    integration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    config_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    secret_reference: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    integration: Mapped["Integration"] = relationship("Integration", back_populates="configs")
''',
)

# 12. Knowledge & RAG with pgvector
write_file(
    "domain/knowledge/models.py",
    '''import uuid
from typing import Any, Dict, List, Optional
from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base


class KnowledgeSource(Base):
    """Source container for SOPs, compliance guidelines, and policy documents."""

    __tablename__ = "knowledge_sources"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(100), nullable=False, default="POLICY")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="ACTIVE")

    documents: Mapped[List["KnowledgeDocument"]] = relationship("KnowledgeDocument", back_populates="knowledge_source", cascade="all, delete-orphan")


class KnowledgeDocument(Base):
    """An ingested policy or guideline document."""

    __tablename__ = "knowledge_documents"

    knowledge_source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    document_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    storage_reference: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    knowledge_source: Mapped["KnowledgeSource"] = relationship("KnowledgeSource", back_populates="documents")
    chunks: Mapped[List["KnowledgeChunk"]] = relationship("KnowledgeChunk", back_populates="knowledge_document", cascade="all, delete-orphan")


class KnowledgeChunk(Base):
    """Chunked vector embeddings for semantic search using pgvector."""

    __tablename__ = "knowledge_chunks"

    knowledge_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Optional[List[float]]] = mapped_column(Vector(1536), nullable=True)
    chunk_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    knowledge_document: Mapped["KnowledgeDocument"] = relationship("KnowledgeDocument", back_populates="chunks")
''',
)

# 13. AI Agents & Models
write_file(
    "agents/models.py",
    '''import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base


class ModelConfig(Base):
    """Model provider and endpoint settings (e.g. Gemini, local Ollama)."""

    __tablename__ = "model_configs"

    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    endpoint: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    configuration: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class AgentDefinition(Base):
    """Specialized agent specification (Document, Verification, Workflow, Supervisor)."""

    __tablename__ = "agent_definitions"

    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    agent_type: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_config_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("model_configs.id", ondelete="SET NULL"),
        nullable=True,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AgentExecution(Base):
    """Runtime execution trace for an agent run."""

    __tablename__ = "agent_executions"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_definitions.id", ondelete="CASCADE"),
        nullable=False,
    )
    input_context: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    output: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="SUCCESS")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    token_usage: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
''',
)

# 14. Events
write_file(
    "events/models.py",
    '''import uuid
from typing import Any, Dict, Optional
from sqlalchemy import ForeignKey, Index, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class EventRecord(Base):
    """Authoritative event record emitted on state transitions and important business actions."""

    __tablename__ = "events"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    case_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    actor_type: Mapped[str] = mapped_column(String(50), nullable=False, default="SYSTEM")
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("idx_events_case_time", "case_id", "created_at"),
        Index("idx_events_org_time", "organization_id", "created_at"),
    )
''',
)

# 15. Audit & Notifications
write_file(
    "domain/audit/models.py",
    '''import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class AuditLog(Base):
    """Immutable audit trail of security-sensitive operations and data modifications."""

    __tablename__ = "audit_logs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_type: Mapped[str] = mapped_column(String(50), nullable=False, default="USER")
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    before_state: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    after_state: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    audit_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("idx_audit_logs_org_time", "organization_id", "created_at"),
        Index("idx_audit_logs_resource", "resource_type", "resource_id"),
    )


class Notification(Base):
    """Task alerts, approval requests, and status update notifications sent to users."""

    __tablename__ = "notifications"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    case_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    notification_type: Mapped[str] = mapped_column(String(100), nullable=False, default="TASK_ASSIGNED")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="UNREAD")
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
''',
)

if __name__ == "__main__":
    print("All ORM models generated successfully!")
