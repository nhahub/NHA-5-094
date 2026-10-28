"""Loading rules for the locally agreed Phase 17 acceptance configuration."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class Phase17ThresholdConfigurationUnavailable(FileNotFoundError):
    """The historical acceptance configuration is not present in this checkout."""


def load_phase17_thresholds(path: Path) -> dict[str, Any]:
    """Load the original local gate configuration without inventing defaults."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise Phase17ThresholdConfigurationUnavailable(
            "BLOCKED: Phase 17 acceptance thresholds are unavailable. "
            "Restore the original locally agreed data/phase17_evaluation/"
            "acceptance_thresholds.json; the synthetic corpus generator does not "
            "create or infer threshold values."
        ) from exc
