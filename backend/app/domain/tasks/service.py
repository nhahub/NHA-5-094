import uuid
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.audit.service import AuditService
from app.domain.cases.models import Case
from app.domain.documents.models import Evidence
from app.domain.organizations.models import Department, DepartmentMember
from app.domain.tasks.models import Task, TaskPriority, TaskReviewComment, TaskStatus
from app.domain.tasks.schemas import (
    TaskAssignmentRequest,
    TaskCreate,
    TaskResolutionRequest,
    TaskReviewCommentCreate,
    TaskUpdate,
)
from app.events.service import EventService
from app.security.models import Role, RoleEnum, User, UserRole


class TaskService:
    """Service managing human and system work items."""

    @staticmethod
    async def create_task(
        db: AsyncSession,
        task_in: TaskCreate,
        created_by_id: uuid.UUID | None = None,
        created_by_type: str = "USER",
        organization_id: uuid.UUID | None = None,
    ) -> Task:
        # Verify case exists
        case_stmt = select(Case).where(Case.id == task_in.case_id)
        if organization_id is not None:
            case_stmt = case_stmt.where(Case.organization_id == organization_id)
        case_res = await db.execute(case_stmt)
        case = case_res.scalars().first()
        if not case:
            raise ValueError(f"Case {task_in.case_id} not found.")
        if task_in.assigned_user_id:
            assignee = (await db.execute(
                select(User.id).where(
                    User.id == task_in.assigned_user_id,
                    User.organization_id == case.organization_id,
                    User.is_active.is_(True),
                )
            )).first()
            if assignee is None:
                raise ValueError("Assignee must be an active user in the case organization.")
        if task_in.assigned_role_id:
            role = (await db.execute(
                select(Role.id).where(
                    Role.id == task_in.assigned_role_id,
                    Role.organization_id == case.organization_id,
                )
            )).first()
            if role is None:
                raise ValueError("Assigned role must belong to the case organization.")
        if task_in.assigned_department_id:
            department = (await db.execute(
                select(Department.id).where(
                    Department.id == task_in.assigned_department_id,
                    Department.organization_id == case.organization_id,
                )
            )).first()
            if department is None:
                raise ValueError("Assigned department must belong to the case organization.")

        task = Task(
            case_id=task_in.case_id,
            stage_id=task_in.stage_id,
            task_type=task_in.task_type,
            title=task_in.title,
            description=task_in.description,
            priority=task_in.priority.value if isinstance(task_in.priority, TaskPriority) else str(task_in.priority),
            status=(
                TaskStatus.ASSIGNED.value
                if task_in.assigned_user_id or task_in.assigned_role_id or task_in.assigned_department_id
                else TaskStatus.PENDING.value
            ),
            assigned_user_id=task_in.assigned_user_id,
            assigned_role_id=task_in.assigned_role_id,
            assigned_department_id=task_in.assigned_department_id,
            created_by_type=created_by_type,
            created_by_id=created_by_id,
            due_at=task_in.due_at,
        )
        db.add(task)
        await db.flush()

        await EventService.emit_event(
            db=db,
            event_type="TASK_CREATED",
            entity_type="TASK",
            entity_id=task.id,
            organization_id=case.organization_id,
            case_id=case.id,
            actor_id=created_by_id,
            actor_type=created_by_type,
            payload={"task_type": task.task_type, "title": task.title, "priority": task.priority,
                     "status": task.status},
            dispatch_orchestration=True,
        )

        await db.commit()
        await db.refresh(task)
        return task

    @staticmethod
    async def get_task_by_id(db: AsyncSession, task_id: uuid.UUID) -> Task | None:
        stmt = select(Task).where(Task.id == task_id)
        result = await db.execute(stmt)
        return result.scalars().first()

    @staticmethod
    async def get_task_for_organization(
        db: AsyncSession, task_id: uuid.UUID, organization_id: uuid.UUID
    ) -> Task | None:
        result = await db.execute(
            select(Task).join(Case, Task.case_id == Case.id).where(
                Task.id == task_id, Case.organization_id == organization_id
            )
        )
        return result.scalars().first()

    @staticmethod
    async def _is_assigned_to_user(db: AsyncSession, task: Task, user: User) -> bool:
        if task.assigned_user_id is not None:
            return task.assigned_user_id == user.id
        if task.assigned_role_id is not None:
            membership = await db.execute(
                select(UserRole.user_id)
                .join(Role, Role.id == UserRole.role_id)
                .where(
                    UserRole.user_id == user.id,
                    UserRole.role_id == task.assigned_role_id,
                    Role.organization_id == user.organization_id,
                )
            )
            return membership.first() is not None
        if task.assigned_department_id is not None:
            membership = await db.execute(
                select(DepartmentMember.user_id).where(
                    DepartmentMember.user_id == user.id,
                    DepartmentMember.department_id == task.assigned_department_id,
                )
            )
            return membership.first() is not None
        return True

    @staticmethod
    async def assign_task(
        db: AsyncSession,
        task_id: uuid.UUID,
        assignment: TaskAssignmentRequest,
        *,
        organization_id: uuid.UUID,
        actor: User,
    ) -> Task | None:
        if actor.role.value not in {RoleEnum.MANAGER.value, RoleEnum.ADMIN.value}:
            raise PermissionError("Only managers or administrators can assign review tasks.")
        task = await TaskService.get_task_for_organization(db, task_id, organization_id)
        if task is None:
            return None
        if task.status in {TaskStatus.COMPLETED.value, TaskStatus.REJECTED.value, TaskStatus.CANCELLED.value}:
            raise ValueError("A resolved task cannot be reassigned.")
        assignee = (await db.execute(
            select(User).where(
                User.id == assignment.assigned_user_id,
                User.organization_id == organization_id,
                User.is_active.is_(True),
            )
        )).scalars().first()
        if assignee is None:
            raise ValueError("Assignee must be an active user in this organization.")
        before = {"assigned_user_id": str(task.assigned_user_id) if task.assigned_user_id else None}
        case_id = task.case_id
        task.assigned_user_id = assignee.id
        task.status = TaskStatus.ASSIGNED.value
        await EventService.emit_event(
            db=db, event_type="TASK_ASSIGNED", organization_id=organization_id,
            case_id=case_id, actor_id=actor.id, actor_type="USER",
            payload={"task_id": str(task.id), "assigned_user_id": str(assignee.id)},
        )
        await db.refresh(task)
        await AuditService.log_action(
            db=db, organization_id=organization_id, action="TASK_ASSIGNED",
            resource_type="TASK", resource_id=task.id, actor_id=actor.id,
            before_state=before, after_state={"assigned_user_id": str(assignee.id)},
        )
        return task

    @staticmethod
    async def start_task(
        db: AsyncSession,
        task_id: uuid.UUID,
        *,
        organization_id: uuid.UUID,
        actor: User,
    ) -> Task | None:
        if actor.role.value == RoleEnum.CUSTOMER.value:
            raise PermissionError("Customers cannot work internal review tasks.")
        task = await TaskService.get_task_for_organization(db, task_id, organization_id)
        if task is None:
            return None
        if task.status not in {TaskStatus.PENDING.value, TaskStatus.ASSIGNED.value}:
            raise ValueError("Only pending or assigned tasks can be started.")
        role = actor.role.value
        if not await TaskService._is_assigned_to_user(db, task, actor) and role not in {
            RoleEnum.MANAGER.value, RoleEnum.ADMIN.value,
        }:
            raise PermissionError("Only the assignee or a manager can start this task.")
        case_id = task.case_id
        task.status = TaskStatus.IN_PROGRESS.value
        if task.assigned_user_id is None:
            task.assigned_user_id = actor.id
        await EventService.emit_event(
            db=db, event_type="TASK_STARTED", organization_id=organization_id,
            case_id=case_id, actor_id=actor.id, actor_type="USER",
            payload={"task_id": str(task.id), "assigned_user_id": str(task.assigned_user_id)},
        )
        await db.refresh(task)
        await AuditService.log_action(
            db=db, organization_id=organization_id, action="TASK_STARTED",
            resource_type="TASK", resource_id=task.id, actor_id=actor.id,
            after_state={"status": task.status, "assigned_user_id": str(task.assigned_user_id)},
        )
        return task

    @staticmethod
    async def add_review_comment(
        db: AsyncSession,
        task_id: uuid.UUID,
        comment_in: TaskReviewCommentCreate,
        *,
        organization_id: uuid.UUID,
        actor: User,
    ) -> TaskReviewComment | None:
        task = await TaskService.get_task_for_organization(db, task_id, organization_id)
        if task is None:
            return None
        if actor.role.value == RoleEnum.CUSTOMER.value:
            raise PermissionError("Customers cannot add internal review comments.")
        if task.status in {TaskStatus.COMPLETED.value, TaskStatus.REJECTED.value, TaskStatus.CANCELLED.value}:
            raise ValueError("Comments cannot be added to a resolved task.")
        evidence_ids = list(dict.fromkeys(comment_in.evidence_ids))
        if evidence_ids:
            evidence_rows = await db.execute(
                select(Evidence.id).where(
                    Evidence.case_id == task.case_id, Evidence.id.in_(evidence_ids)
                )
            )
            found = set(evidence_rows.scalars().all())
            if found != set(evidence_ids):
                raise ValueError("Every evidence link must belong to the task's case.")
        record = TaskReviewComment(
            task_id=task.id, author_id=actor.id, comment=comment_in.comment.strip(),
            evidence_ids=[str(item) for item in evidence_ids],
        )
        case_id = task.case_id
        db.add(record)
        await db.flush()
        await EventService.emit_event(
            db=db, event_type="TASK_REVIEW_COMMENT_ADDED", organization_id=organization_id,
            case_id=case_id, actor_id=actor.id, actor_type="USER",
            payload={"task_id": str(task.id), "comment_id": str(record.id),
                     "evidence_ids": record.evidence_ids},
        )
        await db.refresh(record)
        await AuditService.log_action(
            db=db, organization_id=organization_id, action="TASK_REVIEW_COMMENT_ADDED",
            resource_type="TASK", resource_id=task.id, actor_id=actor.id,
            after_state={"comment_id": str(record.id), "evidence_ids": record.evidence_ids},
        )
        return record

    @staticmethod
    async def get_review_comments(
        db: AsyncSession, task_id: uuid.UUID, organization_id: uuid.UUID
    ) -> list[TaskReviewComment] | None:
        task = await TaskService.get_task_for_organization(db, task_id, organization_id)
        if task is None:
            return None
        result = await db.execute(
            select(TaskReviewComment).where(TaskReviewComment.task_id == task_id)
            .order_by(TaskReviewComment.created_at.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def resolve_task(
        db: AsyncSession,
        task_id: uuid.UUID,
        resolution: TaskResolutionRequest,
        *,
        organization_id: uuid.UUID,
        actor: User,
    ) -> Task | None:
        task = await TaskService.get_task_for_organization(db, task_id, organization_id)
        if task is None:
            return None
        role = actor.role.value
        if role == RoleEnum.CUSTOMER.value:
            raise PermissionError("Customers cannot resolve internal review tasks.")
        if not await TaskService._is_assigned_to_user(db, task, actor) and role not in {
            RoleEnum.MANAGER.value, RoleEnum.ADMIN.value,
        }:
            raise PermissionError("Only the assignee or a manager can resolve this task.")
        if task.status not in {TaskStatus.PENDING.value, TaskStatus.ASSIGNED.value, TaskStatus.IN_PROGRESS.value}:
            raise ValueError("Only an open review task can be resolved.")
        evidence_ids = list(dict.fromkeys(resolution.evidence_ids))
        if evidence_ids:
            evidence_rows = await db.execute(
                select(Evidence.id).where(
                    Evidence.case_id == task.case_id, Evidence.id.in_(evidence_ids)
                )
            )
            if set(evidence_rows.scalars().all()) != set(evidence_ids):
                raise ValueError("Every evidence link must belong to the task's case.")
        task.status = resolution.outcome
        task.completed_at = datetime.now(timezone.utc)
        task_id = task.id
        case_id = task.case_id
        task.completion_metadata = {
            **(task.completion_metadata or {}),
            "human_resolution": {
                "outcome": resolution.outcome,
                "comment": resolution.comment.strip(),
                "evidence_ids": [str(item) for item in evidence_ids],
                "resolved_by": str(actor.id),
                "resolved_at": task.completed_at.isoformat(),
            },
        }
        comment = TaskReviewComment(
            task_id=task.id, author_id=actor.id, comment=resolution.comment.strip(),
            evidence_ids=[str(item) for item in evidence_ids],
        )
        db.add(comment)
        await db.flush()
        if resolution.outcome == TaskStatus.REJECTED.value:
            case = await db.get(Case, case_id)
            if case is not None:
                case.status = "PENDING_REVIEW"
        resolution_event_type = (
            "TASK_COMPLETED"
            if resolution.outcome == TaskStatus.COMPLETED.value
            else "TASK_REJECTED"
        )
        await EventService.emit_event(
            db=db, event_type=resolution_event_type, organization_id=organization_id,
            case_id=case_id, actor_id=actor.id, actor_type="USER",
            payload={"task_id": str(task_id), "updated_fields": ["status", "completion_metadata"],
                     "status": resolution.outcome, "resolution": resolution.outcome},
            dispatch_orchestration=True,
        )
        await AuditService.log_action(
            db=db, organization_id=organization_id, action="TASK_RESOLVED",
            resource_type="TASK", resource_id=task_id, actor_id=actor.id,
            after_state={"status": resolution.outcome, "comment_id": str(comment.id),
                         "evidence_ids": [str(item) for item in evidence_ids]},
        )
        return await TaskService.get_task_for_organization(db, task_id, organization_id)

    @staticmethod
    async def get_tasks(
        db: AsyncSession,
        organization_id: uuid.UUID | None = None,
        case_id: uuid.UUID | None = None,
        assigned_user_id: uuid.UUID | None = None,
        status: str | None = None,
        priority: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Task]:
        stmt = select(Task).join(Case, Task.case_id == Case.id)
        if organization_id:
            stmt = stmt.where(Case.organization_id == organization_id)
        if case_id:
            stmt = stmt.where(Task.case_id == case_id)
        if assigned_user_id:
            stmt = stmt.where(Task.assigned_user_id == assigned_user_id)
        if status:
            stmt = stmt.where(Task.status == status)
        if priority:
            stmt = stmt.where(Task.priority == priority)

        stmt = stmt.order_by(Task.created_at.desc()).offset(skip).limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_tasks_for_user(
        db: AsyncSession,
        user_id: uuid.UUID,
        organization_id: uuid.UUID | None = None,
    ) -> list[Task]:
        role_ids = select(UserRole.role_id).where(UserRole.user_id == user_id)
        department_ids = select(DepartmentMember.department_id).where(
            DepartmentMember.user_id == user_id
        )
        stmt = select(Task).join(Case, Task.case_id == Case.id).where(
            or_(
                Task.assigned_user_id == user_id,
                Task.assigned_role_id.in_(role_ids),
                Task.assigned_department_id.in_(department_ids),
            )
        )
        if organization_id:
            stmt = stmt.where(Case.organization_id == organization_id)
        stmt = stmt.order_by(Task.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_tasks_by_case(
        db: AsyncSession, case_id: uuid.UUID, organization_id: uuid.UUID | None = None
    ) -> list[Task]:
        stmt = select(Task).join(Case, Case.id == Task.case_id).where(Task.case_id == case_id)
        if organization_id is not None:
            stmt = stmt.where(Case.organization_id == organization_id)
        stmt = stmt.order_by(Task.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def update_task(
        db: AsyncSession,
        task_id: uuid.UUID,
        task_update: TaskUpdate,
        actor_id: uuid.UUID | None = None,
        actor_type: str = "USER",
        organization_id: uuid.UUID | None = None,
    ) -> Task | None:
        stmt = select(Task).join(Case, Case.id == Task.case_id).where(Task.id == task_id)
        if organization_id is not None:
            stmt = stmt.where(Case.organization_id == organization_id)
        result = await db.execute(stmt)
        task = result.scalars().first()
        if not task:
            return None

        update_data = task_update.model_dump(exclude_unset=True)
        old_status = task.status

        for field, value in update_data.items():
            if field == "status" and isinstance(value, TaskStatus) or field == "priority" and isinstance(value, TaskPriority):
                value = value.value
            setattr(task, field, value)

        # Handle completion timestamp
        if (
            task.status == TaskStatus.COMPLETED.value
            and old_status != TaskStatus.COMPLETED.value
            and not task.completed_at
        ):
            task.completed_at = datetime.now(timezone.utc)

        # Look up case for org id
        case_stmt = select(Case).where(Case.id == task.case_id)
        case_res = await db.execute(case_stmt)
        case = case_res.scalars().first()
        org_id = case.organization_id if case else None

        await EventService.emit_event(
            db=db,
            event_type="TASK_UPDATED",
            entity_type="TASK",
            entity_id=task.id,
            organization_id=org_id,
            case_id=task.case_id,
            actor_id=actor_id,
            actor_type=actor_type,
            payload={"updated_fields": list(update_data.keys()), "status": task.status},
            dispatch_orchestration=(
                task.status == TaskStatus.COMPLETED.value
                and old_status != TaskStatus.COMPLETED.value
            ),
        )

        await db.commit()
        await db.refresh(task)
        return task
