"""Events package managing immutable business event logging.

Keep package initialization free of router imports. A standalone worker is started
as ``python -m app.events.worker``, which imports this package before the worker
module. Eagerly importing the router here pulls the complete API/domain graph into
that startup path and creates a circular import through authorization and agents.
"""
from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "EventRecord",
    "events_router",
    "EventRecordCreate",
    "EventRecordRead",
    "EventService",
]


def __getattr__(name: str) -> Any:
    """Load legacy package exports only when a caller requests them."""
    modules = {
        "EventRecord": ("app.events.models", "EventRecord"),
        "events_router": ("app.events.router", "events_router"),
        "EventRecordCreate": ("app.events.schemas", "EventRecordCreate"),
        "EventRecordRead": ("app.events.schemas", "EventRecordRead"),
        "EventService": ("app.events.service", "EventService"),
    }
    try:
        module_name, attribute = modules[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    return getattr(import_module(module_name), attribute)
