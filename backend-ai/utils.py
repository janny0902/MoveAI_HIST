"""Shared helpers for backend-ai."""

from __future__ import annotations

import os
from pathlib import Path


TRUCK_CAPACITY_M3 = float(os.getenv("TRUCK_CAPACITY_M3", "50"))


def credentials_present() -> bool:
    path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    if not path:
        return False
    return Path(path).is_file()


def csv_exists(base: str = "/data/volumetric") -> bool:
    root = Path(base)
    if not root.is_dir():
        return False
    for name in ("origin 체적.csv", "origin.csv", "volumetric.csv"):
        if (root / name).is_file():
            return True
    return any(root.glob("*.csv"))
