"""Contract tests for read-only Frappe/ERPNext integration calls."""
from __future__ import annotations

import json

import httpx
import pytest

from app.tools.erpnext import (
    ERPNextAdapterError,
    ERPNextClient,
    resolve_secret_reference,
)


@pytest.mark.asyncio
async def test_inventory_lookup_applies_reservations_and_builds_available_decision():
    seen: list[httpx.Request] = []

    async def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": [{
            "item_code": "VALVE-100", "warehouse": "Main Warehouse",
            "actual_qty": 15, "reserved_qty": 4,
        }]})

    client = ERPNextClient(
        "https://erp.example.test", "test-key:test-secret",
        transport=httpx.MockTransport(handle),
    )
    result = await client.check_inventory("VALVE-100", 10, "Main Warehouse")

    assert result["available_quantity"] == 11
    assert result["reserved_quantity"] == 4
    assert result["decision"] == "AVAILABLE"
    assert seen[0].headers["Authorization"] == "token test-key:test-secret"
    assert json.loads(seen[0].url.params["filters"]) == [
        ["item_code", "=", "VALVE-100"], ["warehouse", "=", "Main Warehouse"],
    ]


@pytest.mark.asyncio
async def test_inventory_missing_record_and_insufficient_stock_are_explicit():
    payloads = [
        {"data": []},
        {"data": [{"actual_qty": 8, "reserved_qty": 3}]},
    ]

    async def handle(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payloads.pop(0))

    client = ERPNextClient("https://erp.example.test", "key:secret", transport=httpx.MockTransport(handle))
    missing = await client.check_inventory("NONE", 1, "Main Warehouse")
    shortage = await client.check_inventory("VALVE-100", 6, "Main Warehouse")
    assert missing["found"] is False
    assert missing["decision"] == "INSUFFICIENT"
    assert shortage["available_quantity"] == 5
    assert shortage["decision"] == "INSUFFICIENT"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("outstanding", "total", "expected"),
    [(0, 125, "PAID"), (25, 125, "PARTIALLY_PAID"), (125, 125, "UNPAID")],
)
async def test_payment_lookup_maps_outstanding_amount(
    outstanding: float, total: float, expected: str,
):
    async def handle(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{
            "name": "PINV-0001", "bill_no": "INV-0001", "status": "Unpaid",
            "outstanding_amount": outstanding, "grand_total": total, "currency": "USD",
        }]})

    client = ERPNextClient("https://erp.example.test", "key:secret", transport=httpx.MockTransport(handle))
    result = await client.get_payment_status("INV-0001")
    assert result["status"] == expected
    assert result["outstanding_amount"] == outstanding
    assert result["currency"] == "USD"


@pytest.mark.asyncio
async def test_payment_missing_reference_returns_unknown():
    async def handle(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": []})

    client = ERPNextClient("https://erp.example.test", "key:secret", transport=httpx.MockTransport(handle))
    result = await client.get_payment_status("missing")
    assert result["status"] == "UNKNOWN"
    assert result["outstanding_amount"] is None


@pytest.mark.asyncio
async def test_customer_lookup_returns_minimal_profile_by_erpnext_id():
    seen: list[httpx.Request] = []

    async def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": [{
            "name": "CUST-0001", "customer_name": "Northstar Demo Imports Ltd",
            "customer_group": "Commercial", "territory": "All Territories",
            "customer_type": "Company", "tax_id": "must-not-be-returned",
        }]})

    client = ERPNextClient("https://erp.example.test", "key:secret", transport=httpx.MockTransport(handle))
    result = await client.get_customer("CUST-0001")

    assert result == {
        "found": True, "customer_id": "CUST-0001",
        "customer_name": "Northstar Demo Imports Ltd", "customer_group": "Commercial",
        "territory": "All Territories", "customer_type": "Company",
    }
    assert json.loads(seen[0].url.params["filters"]) == [["name", "=", "CUST-0001"]]
    assert "tax_id" not in json.loads(seen[0].url.params["fields"])


@pytest.mark.asyncio
async def test_customer_lookup_missing_and_malformed_records():
    payloads = [
        {"data": []},
        {"data": [{"name": "OTHER", "customer_name": "Wrong identity"}]},
    ]

    async def handle(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payloads.pop(0))

    client = ERPNextClient("https://erp.example.test", "key:secret", transport=httpx.MockTransport(handle))
    missing = await client.get_customer("CUST-MISSING")
    assert missing["found"] is False
    assert missing["customer_name"] is None
    with pytest.raises(ERPNextAdapterError, match="malformed customer data"):
        await client.get_customer("CUST-0001")


@pytest.mark.asyncio
async def test_transient_provider_error_retries_once():
    calls = 0

    async def handle(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"data": []})

    client = ERPNextClient("https://erp.example.test", "key:secret", transport=httpx.MockTransport(handle))
    result = await client.get_payment_status("INV-0001")
    assert result["status"] == "UNKNOWN"
    assert calls == 2


@pytest.mark.asyncio
async def test_authentication_failure_is_safe_and_does_not_leak_credentials():
    async def handle(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="test-secret should not appear")

    client = ERPNextClient("https://erp.example.test", "key:test-secret", transport=httpx.MockTransport(handle))
    with pytest.raises(ERPNextAdapterError) as error:
        await client.get_payment_status("INV-0001")
    assert "test-secret" not in str(error.value)


def test_secret_reference_resolves_env_values_without_accepting_inline_secrets(monkeypatch):
    monkeypatch.setenv("PHASE17_ERP_CREDENTIAL", "api-key:api-secret")
    assert resolve_secret_reference("env:PHASE17_ERP_CREDENTIAL") == "api-key:api-secret"
    with pytest.raises(ERPNextAdapterError):
        resolve_secret_reference("api-key:api-secret")
    with pytest.raises(ERPNextAdapterError):
        resolve_secret_reference("env:UNSET_PHASE17_ERP_CREDENTIAL")


def test_secret_reference_reads_repository_dotenv_when_not_exported(monkeypatch):
    monkeypatch.delenv("PHASE17_ERP_CREDENTIAL", raising=False)
    monkeypatch.setattr(
        "app.tools.erpnext.dotenv_values",
        lambda _path: {"PHASE17_ERP_CREDENTIAL": "api-key:api-secret"},
    )

    assert resolve_secret_reference("env:PHASE17_ERP_CREDENTIAL") == "api-key:api-secret"
