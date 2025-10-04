"""Utility helpers for backend pipeline."""
from __future__ import annotations

import hashlib
import json
from typing import Dict, Iterable, List


def normalize_name(name: str) -> str:
    return name.strip().casefold()


def hash_preferences(preferences: Dict[str, Iterable[str]]) -> str:
    """Create a stable hash representing user preferences."""

    sorted_prefs: Dict[str, List[str]] = {}
    for key, values in preferences.items():
        sorted_prefs[key] = sorted([str(item).strip() for item in values])
    blob = json.dumps(sorted_prefs, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))
