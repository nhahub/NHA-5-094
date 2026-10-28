"""Trusted, read-only ERPNext adapter for import evaluation tools."""
from __future__ import annotations

import asyncio
import json
import os
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx
from dotenv import dotenv_values
from sqlalchemy import select

from app.tools.models import Integration, IntegrationConfig


class ERPNextAdapterError(RuntimeError):
    """Safe adapter error that never includes credentials or response bodies."""


def resolve_secret_reference(reference: str | None) -> str:
    """Resolve ``env:NAME`` from process env or the repository-root .env file."""
    if not reference or not reference.startswith("env:"):
        raise ERPNextAdapterError("ERPNext credentials must use an env:NAME secret reference.")
    name = reference[4:]
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ERPNextAdapterError("ERPNext credential reference is invalid.")
    value = os.getenv(name)
    if not value:
        repository_root = Path(__file__).resolve().parents[3]
        value = dotenv_values(repository_root / ".env").get(name)
    if not value:
        raise ERPNextAdapterError("The referenced ERPNext credential is not configured.")
    if ":" not in value:
        raise ERPNextAdapterError("ERPNext credential must contain the API key and secret pair.")
    return value


class ERPNextClient:
    """Small read-only client for the Frappe/ERPNext resource API."""

    def __init__(
        self, base_url: str, api_credentials: str, *,
        transport: httpx.AsyncBaseTransport | None = None, timeout: float = 10.0,
    ) -> None:
        if not base_url.startswith(("https://", "http://127.0.0.1", "http://localhost")):
            raise ERPNextAdapterError("ERPNext base URL must use HTTPS, except for a local test instance.")
        self.base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"token {api_credentials}", "Accept": "application/json"}
        self._transport = transport
        self._timeout = timeout

    async def _get(self, resource: str, *, params: dict[str, str]) -> dict[str, Any]:
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(
                    base_url=self.base_url, headers=self._headers,
                    timeout=self._timeout, transport=self._transport,
                ) as client:
                    response = await client.get(resource, params=params)
            except (httpx.TimeoutException, httpx.RequestError) as exc:
                if attempt == 0:
                    await asyncio.sleep(0.1)
                    continue
                raise ERPNextAdapterError("ERPNext provider could not be reached.") from exc

            if response.status_code in (429,) or response.status_code >= 500:
                if attempt == 0:
                    await asyncio.sleep(0.1)
                    continue
                raise ERPNextAdapterError("ERPNext provider is temporarily unavailable.")
            if response.status_code in (401, 403):
                raise ERPNextAdapterError("ERPNext rejected the integration credentials or permissions.")
            if response.status_code >= 400:
                raise ERPNextAdapterError("ERPNext rejected the requested record lookup.")
            try:
                payload = response.json()
            except ValueError as exc:
                raise ERPNextAdapterError("ERPNext returned a malformed response.") from exc
            if not isinstance(payload, dict):
                raise ERPNextAdapterError("ERPNext returned a malformed response.")
            return payload
        raise ERPNextAdapterError("ERPNext provider is temporarily unavailable.")

    async def check_inventory(self, sku: str, quantity: float, warehouse: str) -> dict[str, Any]:
        payload = await self._get(
            "/api/resource/Bin",
            params={
                "fields": json.dumps(["item_code", "warehouse", "actual_qty", "reserved_qty"]),
                "filters": json.dumps([
                    ["item_code", "=", sku], ["warehouse", "=", warehouse],
                ]),
                "limit_page_length": "1",
            },
        )
        records = payload.get("data")
        if not isinstance(records, list):
            raise ERPNextAdapterError("ERPNext returned a malformed inventory response.")
        if not records:
            return {
                "found": False, "sku": sku, "warehouse": warehouse,
                "requested_quantity": quantity, "available_quantity": 0.0,
                "reserved_quantity": 0.0, "decision": "INSUFFICIENT",
            }
        record = records[0]
        try:
            actual = Decimal(str(record["actual_qty"]))
            reserved = Decimal(str(record.get("reserved_qty", 0)))
            requested = Decimal(str(quantity))
        except (KeyError, InvalidOperation, TypeError) as exc:
            raise ERPNextAdapterError("ERPNext returned malformed inventory quantities.") from exc
        if not all(value.is_finite() for value in (actual, reserved, requested)):
            raise ERPNextAdapterError("ERPNext returned malformed inventory quantities.")
        available = max(Decimal(0), actual - reserved)
        return {
            "found": True, "sku": sku, "warehouse": warehouse,
            "requested_quantity": float(requested), "available_quantity": float(available),
            "reserved_quantity": float(reserved),
            "decision": "AVAILABLE" if available >= requested else "INSUFFICIENT",
        }

    async def get_payment_status(self, payment_reference: str) -> dict[str, Any]:
        payload = await self._get(
            "/api/resource/Purchase Invoice",
            params={
                "fields": json.dumps([
                    "name", "bill_no", "status", "outstanding_amount", "grand_total", "currency",
                ]),
                "filters": json.dumps([["bill_no", "=", payment_reference]]),
                "limit_page_length": "1",
            },
        )
        records = payload.get("data")
        if not isinstance(records, list):
            raise ERPNextAdapterError("ERPNext returned a malformed payment response.")
        if not records:
            return {
                "found": False, "payment_reference": payment_reference,
                "status": "UNKNOWN", "outstanding_amount": None, "currency": None,
            }
        record = records[0]
        try:
            outstanding = Decimal(str(record["outstanding_amount"]))
            total = Decimal(str(record["grand_total"]))
            currency = str(record["currency"])
        except (KeyError, InvalidOperation, TypeError) as exc:
            raise ERPNextAdapterError("ERPNext returned malformed payment amounts.") from exc
        if not outstanding.is_finite() or not total.is_finite() or not currency:
            raise ERPNextAdapterError("ERPNext returned malformed payment amounts.")
        status = "PAID" if outstanding <= 0 else "PARTIALLY_PAID" if outstanding < total else "UNPAID"
        return {
            "found": True, "payment_reference": payment_reference,
            "status": status, "outstanding_amount": float(outstanding), "currency": currency,
        }

    async def get_customer(self, customer_id: str) -> dict[str, Any]:
        """Return a minimal, stable customer profile by its ERPNext document ID."""
        payload = await self._get(
            "/api/resource/Customer",
            params={
                "fields": json.dumps([
                    "name", "customer_name", "customer_group", "territory", "customer_type",
                ]),
                "filters": json.dumps([["name", "=", customer_id]]),
                "limit_page_length": "1",
            },
        )
        records = payload.get("data")
        if not isinstance(records, list):
            raise ERPNextAdapterError("ERPNext returned a malformed customer response.")
        if not records:
            return {
                "found": False, "customer_id": customer_id, "customer_name": None,
                "customer_group": None, "territory": None, "customer_type": None,
            }
        record = records[0]
        try:
            if str(record["name"]) != customer_id or not str(record["customer_name"]).strip():
                raise ValueError("invalid customer identity")
            return {
                "found": True, "customer_id": customer_id,
                "customer_name": str(record["customer_name"]),
                "customer_group": record.get("customer_group"),
                "territory": record.get("territory"),
                "customer_type": record.get("customer_type"),
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise ERPNextAdapterError("ERPNext returned malformed customer data.") from exc


async def erpnext_integration_adapter(context: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    """Resolve the organization-scoped ERPNext connection and dispatch read-only tools."""
    integration_id = context.tool_configuration.get("integration_id")
    stmt = (
        select(Integration, IntegrationConfig)
        .join(IntegrationConfig, IntegrationConfig.integration_id == Integration.id)
        .where(
            Integration.organization_id == context.actor.organization_id,
            Integration.status == "ACTIVE",
            Integration.integration_type.in_(["ERP", "FINANCE"]),
        )
    )
    if integration_id:
        stmt = stmt.where(Integration.id == integration_id)
    row = (await context.db.execute(stmt.limit(1))).first()
    if row is None:
        raise ERPNextAdapterError("No active ERPNext connection is configured for this organization.")
    _, integration_config = row
    metadata = integration_config.config_metadata or {}
    base_url = metadata.get("base_url") or os.getenv("ERP_NEXT_BASE_URL")
    if not isinstance(base_url, str) or not base_url:
        raise ERPNextAdapterError("ERPNext base URL is not configured.")
    token = resolve_secret_reference(integration_config.secret_reference)
    client = ERPNextClient(base_url, token)
    tool_name = context.tool_configuration.get("_tool_name")
    if tool_name == "get_customer":
        return await client.get_customer(arguments["customer_id"])
    if context.tool_configuration.get("integration_type", "").upper() == "FINANCE":
        return await client.get_payment_status(arguments["payment_reference"])
    return await client.check_inventory(
        arguments["sku"], arguments["quantity"], arguments["warehouse"],
    )
