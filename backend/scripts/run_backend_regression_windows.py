"""Run pytest with workspace-inherited temp ACLs on constrained Windows hosts.

The default pytest temp directory can inherit a restrictive ACL in some managed
Windows workspaces. This runner keeps pytest's fixtures and application behavior
unchanged while creating each ``tmp_path`` with the workspace's normal inherited
permissions. On other platforms it delegates directly to pytest.
"""
from __future__ import annotations

import os
import shutil
import sys
import uuid
from pathlib import Path

import pytest


def _windows_tmp_path_compatibility() -> None:
    if os.name != "nt":
        return

    import _pytest.pathlib
    import _pytest.tmpdir

    root = Path(__file__).resolve().parents[1] / ".pytest_phase17_acl"
    root.mkdir(parents=True, exist_ok=True)

    def mktemp(_factory, basename: str, numbered: bool = True) -> Path:
        del numbered
        target = root / f"{basename[:48]}-{uuid.uuid4().hex[:10]}"
        target.mkdir()
        return target

    _pytest.tmpdir.TempPathFactory.getbasetemp = lambda _factory: root
    _pytest.tmpdir.TempPathFactory.mktemp = mktemp
    _pytest.pathlib.cleanup_dead_symlinks = lambda _path: None


def main() -> int:
    _windows_tmp_path_compatibility()
    args = sys.argv[1:] or [
        "-ra",
        "--show-capture=no",
        "-p",
        "no:cacheprovider",
        "--ignore=tests/_pytest_phase15",
    ]
    try:
        return int(pytest.main(args))
    finally:
        if os.name == "nt":
            root = Path(__file__).resolve().parents[1] / ".pytest_phase17_acl"
            if root.exists():
                for child in root.iterdir():
                    if child.is_dir():
                        shutil.rmtree(child, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
