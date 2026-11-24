"""Load and sanity-check a customer onboarding config."""
from __future__ import annotations

from pathlib import Path

import yaml

REQUIRED_KEYS = ["customer", "session", "readings", "maintenance", "asset_register",
                 "entity_resolution", "dq_thresholds"]


def load_config(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    missing = [k for k in REQUIRED_KEYS if k not in cfg]
    if missing:
        raise ValueError(f"{path}: missing config sections {missing}")
    return cfg
