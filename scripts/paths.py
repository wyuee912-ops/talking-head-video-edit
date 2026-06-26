"""Resolve project paths for talking-head-edit."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HELPERS = ROOT / "helpers"
DEFAULT_EDIT_DIR = ROOT / "edit"


def helpers_dir() -> Path:
    override = os.environ.get("TALKING_HEAD_HELPERS")
    if override:
        return Path(override).resolve()
    return HELPERS


def load_config() -> dict:
    import json

    path = ROOT / "config" / "defaults.json"
    if path.exists():
        return json.loads(path.read_text())
    return {}
