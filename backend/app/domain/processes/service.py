import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.processes.models import (
    Process,
    ProcessStatus,
    ProcessVersion,
    ProcessVersionStatus,
    Requirement,
)
from app.domain.processes.schemas import (
    BusinessRuleCreate,
    ProcessCreate,
    ProcessVersionCreate,
    RequirementCreate,
    VerificationDefinitionCreate,
    WorkflowStageCreate,
    WorkflowTransitionCreate,
)
from app.domain.rules.models import BusinessRule
from app.domain.verifications.models import VerificationDefinition
from app.domain.workflows.models import WorkflowStage, WorkflowTransition


class ProcessService:
    """Service managing Process definitions, immutable ProcessVersions, and child components."""

    @staticmethod
    def _assert_version_is_draft(version: ProcessVersion) -> None:
        """Enforces that published or archived process versions cannot be modified in place."""
        if version.status != ProcessVersionStatus.DRAFT.value and version.status != ProcessVersionStatus.DRAFT:
            raise ValueError(
                f"ProcessVersion {version.version_number} is in '{version.status}' status and cannot be modified. "
                "Create a new draft version to make changes."
            )

    @classmethod
    async def create_process(
        cls, db: AsyncSession, organization_id: uuid.UUID, process_in: ProcessCreate, created_by: Optional[uuid.UUID] = None
    ) -> Process:
        process = Process(
            organization_id=organization_id,
            name=process_in.name,
            code=process_in.code,
            description=process_in.description,
            status=process_in.status.value if hasattr(process_in.status, "value") else process_in.status,
        )
        db.add(process)
        await db.commit()
        await db.refresh(process)

        # Create initial draft version (v1)
        initial_version = ProcessVersion(
            process_id=process.id,
            version_number=1,
            status=ProcessVersionStatus.DRAFT.value,
            configuration={},
            created_by=created_by,
        )
        db.add(initial_version)
        await db.commit()
        await db.refresh(process)
        return process

    @staticmethod
    async def get_processes(
        db: AsyncSession, organization_id: uuid.UUID, skip: int = 0, limit: int = 50
    ) -> List[Process]:
        stmt = (
            select(Process)
            .where(Process.organization_id == organization_id)
            .order_by(Process.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_customer_options(
        db: AsyncSession, organization_id: uuid.UUID, skip: int = 0, limit: int = 100
    ) -> list[tuple[Process, ProcessVersion]]:
        stmt = (
            select(Process, ProcessVersion)
            .join(ProcessVersion, ProcessVersion.process_id == Process.id)
            .where(
                Process.organization_id == organization_id,
                Process.status == ProcessStatus.ACTIVE.value,
                ProcessVersion.status == ProcessVersionStatus.PUBLISHED.value,
            )
            .order_by(Process.name, ProcessVersion.version_number.desc())
            .offset(skip)
            .limit(limit)
        )
        return list((await db.execute(stmt)).all())

    @staticmethod
    async def get_process_by_id(db: AsyncSession, process_id: uuid.UUID) -> Optional[Process]:
        stmt = select(Process).where(Process.id == process_id)
        result = await db.execute(stmt)
        return result.scalars().first()

    @staticmethod
    async def get_versions_by_process_id(
        db: AsyncSession, process_id: uuid.UUID
    ) -> List[ProcessVersion]:
        stmt = (
            select(ProcessVersion)
            .where(ProcessVersion.process_id == process_id)
            .order_by(ProcessVersion.version_number.desc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_version_by_id(
        db: AsyncSession, version_id: uuid.UUID
    ) -> Optional[ProcessVersion]:
        stmt = select(ProcessVersion).where(ProcessVersion.id == version_id)
        result = await db.execute(stmt)
        return result.scalars().first()

    @staticmethod
    async def get_version_detail(
        db: AsyncSession, version_id: uuid.UUID
    ) -> Optional[ProcessVersion]:
        stmt = (
            select(ProcessVersion)
            .where(ProcessVersion.id == version_id)
            .options(
                selectinload(ProcessVersion.stages),
                selectinload(ProcessVersion.transitions),
                selectinload(ProcessVersion.requirements),
                selectinload(ProcessVersion.verifications),
                selectinload(ProcessVersion.rules),
            )
        )
        result = await db.execute(stmt)
        return result.scalars().first()

    @classmethod
    async def create_new_version(
        cls,
        db: AsyncSession,
        process_id: uuid.UUID,
        version_in: ProcessVersionCreate,
        created_by: Optional[uuid.UUID] = None,
    ) -> ProcessVersion:
        # Determine next version number
        stmt = (
            select(ProcessVersion.version_number)
            .where(ProcessVersion.process_id == process_id)
            .order_by(ProcessVersion.version_number.desc())
        )
        result = await db.execute(stmt)
        latest_num = result.scalars().first() or 0

        new_version = ProcessVersion(
            process_id=process_id,
            version_number=latest_num + 1,
            status=ProcessVersionStatus.DRAFT.value,
            configuration=version_in.configuration or {},
            created_by=created_by,
        )
        db.add(new_version)
        await db.commit()
        await db.refresh(new_version)
        return new_version

    @classmethod
    async def add_stage_to_version(
        cls, db: AsyncSession, version_id: uuid.UUID, stage_in: WorkflowStageCreate
    ) -> WorkflowStage:
        version = await cls.get_version_by_id(db, version_id)
        if not version:
            raise ValueError("ProcessVersion not found")
        cls._assert_version_is_draft(version)

        stage = WorkflowStage(
            process_version_id=version_id,
            name=stage_in.name,
            code=stage_in.code,
            description=stage_in.description,
            stage_order=stage_in.stage_order,
            is_initial=stage_in.is_initial,
            is_terminal=stage_in.is_terminal,
            config=stage_in.config or {},
        )
        db.add(stage)
        await db.commit()
        await db.refresh(stage)
        return stage

    @classmethod
    async def add_transition_to_version(
        cls, db: AsyncSession, version_id: uuid.UUID, transition_in: WorkflowTransitionCreate
    ) -> WorkflowTransition:
        version = await cls.get_version_by_id(db, version_id)
        if not version:
            raise ValueError("ProcessVersion not found")
        cls._assert_version_is_draft(version)

        transition = WorkflowTransition(
            process_version_id=version_id,
            from_stage_id=transition_in.from_stage_id,
            to_stage_id=transition_in.to_stage_id,
            name=transition_in.name,
            code=transition_in.code,
            condition_config=transition_in.condition_config or {},
            requires_approval=transition_in.requires_approval,
            required_role=transition_in.required_role,
        )
        db.add(transition)
        await db.commit()
        await db.refresh(transition)
        return transition

    @classmethod
    async def add_requirement_to_version(
        cls, db: AsyncSession, version_id: uuid.UUID, req_in: RequirementCreate
    ) -> Requirement:
        version = await cls.get_version_by_id(db, version_id)
        if not version:
            raise ValueError("ProcessVersion not found")
        cls._assert_version_is_draft(version)

        req_type = req_in.type.value if hasattr(req_in.type, "value") else str(req_in.type)
        req = Requirement(
            process_version_id=version_id,
            stage_id=req_in.stage_id,
            name=req_in.name,
            code=req_in.code,
            type=req_type,
            description=req_in.description,
            required=req_in.required,
            configuration=req_in.configuration or {},
        )
        db.add(req)
        await db.commit()
        await db.refresh(req)
        return req

    @classmethod
    async def add_verification_to_version(
        cls, db: AsyncSession, version_id: uuid.UUID, verif_in: VerificationDefinitionCreate
    ) -> VerificationDefinition:
        version = await cls.get_version_by_id(db, version_id)
        if not version:
            raise ValueError("ProcessVersion not found")
        cls._assert_version_is_draft(version)

        verif = VerificationDefinition(
            process_version_id=version_id,
            stage_id=verif_in.stage_id,
            name=verif_in.name,
            code=verif_in.code,
            description=verif_in.description,
            result_policy=verif_in.result_policy or {},
        )
        db.add(verif)
        await db.commit()
        await db.refresh(verif)
        return verif

    @classmethod
    async def add_rule_to_version(
        cls, db: AsyncSession, version_id: uuid.UUID, rule_in: BusinessRuleCreate
    ) -> BusinessRule:
        version = await cls.get_version_by_id(db, version_id)
        if not version:
            raise ValueError("ProcessVersion not found")
        cls._assert_version_is_draft(version)

        severity = rule_in.severity.value if hasattr(rule_in.severity, "value") else str(rule_in.severity)
        rule = BusinessRule(
            process_version_id=version_id,
            name=rule_in.name,
            code=rule_in.code,
            description=rule_in.description,
            rule_type=rule_in.rule_type,
            expression=rule_in.expression or {},
            severity=severity,
        )
        db.add(rule)
        await db.commit()
        await db.refresh(rule)
        return rule

    @classmethod
    async def publish_version(
        cls, db: AsyncSession, version_id: uuid.UUID
    ) -> ProcessVersion:
        version = await cls.get_version_by_id(db, version_id)
        if not version:
            raise ValueError("ProcessVersion not found")
        
        # Validate that version has at least 1 stage
        stmt = select(WorkflowStage).where(WorkflowStage.process_version_id == version_id)
        result = await db.execute(stmt)
        stages = list(result.scalars().all())
        if not stages:
            raise ValueError("Cannot publish ProcessVersion without at least one WorkflowStage.")

        version.status = ProcessVersionStatus.PUBLISHED.value
        version.published_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(version)
        return version

    @classmethod
    async def archive_version(
        cls, db: AsyncSession, version_id: uuid.UUID
    ) -> ProcessVersion:
        version = await cls.get_version_by_id(db, version_id)
        if not version:
            raise ValueError("ProcessVersion not found")
        version.status = ProcessVersionStatus.ARCHIVED.value
        await db.commit()
        await db.refresh(version)
        return version
