# FastAPI evaluates these dependency defaults as route metadata.
# ruff: noqa: B008
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domain.organizations.models import Organization
from app.infrastructure.database.session import get_db
from app.security.models import RoleEnum, User
from app.security.schemas import (
    LoginRequest,
    PasswordChangeRequest,
    PasswordResetRequest,
    ProvisionedUserCreate,
    Token,
    UserRead,
)
from app.security.service import AuthService

auth_router = APIRouter(prefix="/auth", tags=["Authentication"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/token")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = AuthService.decode_token(token)
    if not payload or not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        user_id = uuid.UUID(payload["sub"])
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    user = await AuthService.get_user_by_id(db, user_id=user_id)
    role_value = user.role.value if user and isinstance(user.role, RoleEnum) else (user.role if user else None)
    if (
        not user
        or not user.is_active
        or payload.get("org_id") != str(user.organization_id)
        or payload.get("role") != role_value
        or type(payload.get("ver", 0)) is not int
        or payload.get("ver", 0) != user.token_version
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    organization = await db.get(Organization, user.organization_id)
    if not organization or not organization.is_active or organization.status.lower() != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require an active organization administrator for identity administration."""
    if current_user.role != RoleEnum.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization administrator access is required.",
        )
    return current_user


@auth_router.get("/users", response_model=list[UserRead])
async def list_organization_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Any:
    return await AuthService.list_organization_users(
        db, organization_id=current_user.organization_id, skip=skip, limit=limit
    )


@auth_router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def provision_organization_user(
    user_in: ProvisionedUserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Any:
    try:
        return await AuthService.provision_user(
            db,
            organization_id=current_user.organization_id,
            actor_id=current_user.id,
            user_in=user_in,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@auth_router.post("/users/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_organization_user_password(
    user_id: uuid.UUID,
    reset: PasswordResetRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Response:
    user = await AuthService.admin_reset_password(
        db,
        organization_id=current_user.organization_id,
        target_user_id=user_id,
        actor_id=current_user.id,
        new_password=reset.new_password,
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@auth_router.post("/login", response_model=Token)
async def login(credentials: LoginRequest, db: AsyncSession = Depends(get_db)) -> Any:
    user = await AuthService.authenticate_user(db, credentials.email, credentials.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    token = AuthService.create_access_token(
        user.id, user.organization_id, user.role, token_version=user.token_version
    )
    return Token(
        access_token=token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@auth_router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> Any:
    user = await AuthService.authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    token = AuthService.create_access_token(
        user.id, user.organization_id, user.role, token_version=user.token_version
    )
    return Token(
        access_token=token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@auth_router.get("/me", response_model=UserRead)
async def read_current_user(current_user: User = Depends(get_current_user)) -> Any:
    return current_user


@auth_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout_user(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    await AuthService.revoke_access_tokens(
        db, user=current_user, actor_id=current_user.id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@auth_router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_current_password(
    request: PasswordChangeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    changed = await AuthService.change_password(
        db,
        user=current_user,
        current_password=request.current_password,
        new_password=request.new_password,
    )
    if not changed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect or the new password is unchanged.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
