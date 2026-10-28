import uuid

import pytest

from app.security.models import RoleEnum
from app.security.schemas import UserCreate, UserRead
from app.security.service import AuthService


@pytest.mark.asyncio
async def test_create_user_maps_full_name_to_model_name_and_returns_read_schema(
    db_session, test_org
):
    user_in = UserCreate(
        organization_id=test_org.id,
        email=f"auth-{uuid.uuid4().hex}@example.com",
        full_name="Phase Evaluation Operator",
        role=RoleEnum.EMPLOYEE,
        password="temporary-test-password",
    )

    user = await AuthService.create_user(db_session, user_in)

    assert user.name == "Phase Evaluation Operator"
    assert not hasattr(user, "full_name")
    assert AuthService.verify_password("temporary-test-password", user.hashed_password)
    assert UserRead.model_validate(user).full_name == "Phase Evaluation Operator"
