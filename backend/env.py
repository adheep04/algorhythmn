"""Environment helper utilities for API access."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional

ALIAS_KEY_MAP = {
    "spotify developer id": "SPOTIFY_CLIENT_ID",
    "spotify client id": "SPOTIFY_CLIENT_ID",
    "client id": "SPOTIFY_CLIENT_ID",
    "secret": "SPOTIFY_CLIENT_SECRET",
    "spotify secret": "SPOTIFY_CLIENT_SECRET",
    "claude": "CLAUDE_API_KEY",
    "claude api key": "CLAUDE_API_KEY",
    "anthropic": "CLAUDE_API_KEY",
    "anthropic api key": "CLAUDE_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openai api key": "OPENAI_API_KEY",
}


def load_env(path: Optional[Path] = None) -> Dict[str, str]:
    """Load environment variables from a .env file, returning a mapping.

    The file is expected to contain KEY=VALUE pairs. Existing os.environ takes
    precedence, but values from the file are also exported for downstream use.
    """

    env_path = Path(path) if path else Path(__file__).resolve().parent.parent / ".env"
    values: Dict[str, str] = {}
    if not env_path.exists():
        return values

    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, raw_value = line.split("=", 1)
            key = key.strip()
            parsed_key = _normalize_key(key)
            value = raw_value.strip().strip('"').strip("'")
            if parsed_key:
                values[parsed_key] = value
                os.environ.setdefault(parsed_key, value)
            continue

        # Support colon-separated entries and multi-pairs per line
        segments = [segment.strip() for segment in line.split(",") if segment.strip()]
        for segment in segments:
            if ":" not in segment:
                continue
            key, raw_value = segment.split(":", 1)
            parsed_key = _normalize_key(key.strip())
            value = raw_value.strip().strip('"').strip("'")
            if parsed_key:
                values[parsed_key] = value
                os.environ.setdefault(parsed_key, value)
    return values


def require(keys: Dict[str, str]) -> Dict[str, str]:
    """Ensure the provided keys exist in the environment, raising if missing."""

    missing = [name for name in keys if name not in os.environ]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")
    return {name: os.environ[name] for name in keys}


def _normalize_key(key: str) -> Optional[str]:
    lowered = key.lower().strip()
    if not lowered:
        return None
    if lowered in ALIAS_KEY_MAP:
        return ALIAS_KEY_MAP[lowered]
    return lowered.replace(" ", "_").upper()
