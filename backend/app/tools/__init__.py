"""Tools package managing controlled Tool Gateway invocation for deterministic execution.

Exports are loaded lazily so importing a focused module such as
``app.tools.integrations`` does not eagerly import the router and create an
agent/service import cycle.
"""

from importlib import import_module
from typing import Any

_EXPORT_MODULES = {
    "tools_router": "app.tools.router",
    "ToolDefinition": "app.tools.schemas",
    "ToolExecutionRequest": "app.tools.schemas",
    "ToolExecutionResult": "app.tools.schemas",
    "ToolGatewayService": "app.tools.service",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value

__all__ = [
    "ToolDefinition",
    "ToolExecutionRequest",
    "ToolExecutionResult",
    "ToolGatewayService",
    "tools_router",
]
