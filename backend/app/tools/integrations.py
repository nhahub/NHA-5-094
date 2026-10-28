"""Application-service operations for organization external integrations."""
from __future__ import annotations

import re
import uuid
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from app.tools.models import Integration, IntegrationConfig


class IntegrationConfigurationError(ValueError):
    """Raised when an external integration is not safely configured."""


class IntegrationService:
    """Create provider configuration through the application domain boundary."""

    @staticmethod
    async def create_erpnext_connection(
        db: AsyncSession,
        *,
        organization_id: uuid.UUID,
        name: str,
        integration_type: str,
        base_url: str,
        secret_reference: str = "env:ERP_NEXT_API_CREDENTIALS",
    ) -> tuple[Integration, IntegrationConfig]:
        normalized_type = integration_type.strip().upper()
        if normalized_type not in {"ERP", "FINANCE"}:
            raise IntegrationConfigurationError("ERPNext integration type must be ERP or FINANCE.")
        if not name.strip() or len(name) > 255:
            raise IntegrationConfigurationError("Integration name must contain 1 to 255 characters.")
        parsed = urlparse(base_url)
        is_local = parsed.hostname in {"localhost", "127.0.0.1"}
        if parsed.scheme != "https" and not (parsed.scheme == "http" and is_local):
            raise IntegrationConfigurationError("ERPNext base URL must use HTTPS, except for a local test instance.")
        if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise IntegrationConfigurationError("ERPNext base URL must be an origin without embedded credentials or query data.")
        if not re.fullmatch(r"env:[A-Za-z_][A-Za-z0-9_]*", secret_reference):
            raise IntegrationConfigurationError("Credential must be stored as a secret reference like env:ERP_NEXT_API_CREDENTIALS.")

        integration = Integration(
            organization_id=organization_id,
            name=name.strip(),
            integration_type=normalized_type,
            status="ACTIVE",
        )
        db.add(integration)
        await db.flush()
        config = IntegrationConfig(
            integration_id=integration.id,
            config_metadata={"base_url": base_url.rstrip("/")},
            secret_reference=secret_reference,
        )
        db.add(config)
        await db.commit()
        await db.refresh(integration)
        await db.refresh(config)
        return integration, config
