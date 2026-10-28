from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.tools.integrations import IntegrationConfigurationError, IntegrationService
from app.tools.models import Integration, IntegrationConfig
from scripts.configure_phase17_permissions import PHASE17_TOOL_PERMISSIONS


def test_phase17_tool_permissions_include_each_initial_integration_tool():
    assert {"tool.check_inventory", "tool.get_customer", "tool.get_payment_status"} <= set(
        PHASE17_TOOL_PERMISSIONS
    )


@pytest.mark.asyncio
async def test_erpnext_configuration_persists_endpoint_and_secret_reference_only(
    db_session: AsyncSession, test_org,
):
    integration, config = await IntegrationService.create_erpnext_connection(
        db_session,
        organization_id=test_org.id,
        name="Northstar ERP test",
        integration_type="ERP",
        base_url="https://erp.example.test",
    )
    assert integration.organization_id == test_org.id
    assert integration.status == "ACTIVE"
    assert config.config_metadata == {"base_url": "https://erp.example.test"}
    assert config.secret_reference == "env:ERP_NEXT_API_CREDENTIALS"
    assert "api-secret" not in str(config.config_metadata)


@pytest.mark.asyncio
async def test_erpnext_configuration_rejects_inline_secrets_and_insecure_remote_urls(
    db_session: AsyncSession, test_org,
):
    with pytest.raises(IntegrationConfigurationError, match="HTTPS"):
        await IntegrationService.create_erpnext_connection(
            db_session, organization_id=test_org.id, name="unsafe",
            integration_type="ERP", base_url="http://erp.example.test",
        )
    with pytest.raises(IntegrationConfigurationError, match="secret reference"):
        await IntegrationService.create_erpnext_connection(
            db_session, organization_id=test_org.id, name="unsafe",
            integration_type="ERP", base_url="https://erp.example.test",
            secret_reference="key:api-secret",
        )
    integrations = list((await db_session.execute(select(Integration))).scalars())
    configs = list((await db_session.execute(select(IntegrationConfig))).scalars())
    assert integrations == []
    assert configs == []
