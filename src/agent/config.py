"""Load settings from .env and scrub secrets out of any text we show.

Nothing here is hardcoded: every value comes from environment variables.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Variables whose values must never appear in output, logs or error messages.
SECRET_VARS = (
    "ANTHROPIC_API_KEY",
    "AZURE_SQL_SERVER",
    "AZURE_SQL_DATABASE",
    "AZURE_SQL_USERNAME",
    "AZURE_SQL_PASSWORD",
)


@dataclass(frozen=True)
class Settings:
    api_key: str
    model: str
    max_tokens: int
    max_tool_calls: int
    max_rows: int
    timeout_seconds: int


class ConfigError(Exception):
    """A setting is missing or invalid. The message names the variable only."""


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be a whole number") from None
    if value < 1:
        raise ConfigError(f"{name} must be at least 1")
    return value


def load_settings() -> Settings:
    """Read .env, fail early (naming the variable, never its value) if broken."""
    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise ConfigError("Missing required variable ANTHROPIC_API_KEY (set it in .env)")
    return Settings(
        api_key=api_key,
        model=os.environ.get("ANTHROPIC_MODEL", "").strip() or "claude-sonnet-5-5",
        max_tokens=_int("MAX_TOKENS", 1024),
        max_tool_calls=_int("MAX_TOOL_CALLS", 6),
        max_rows=_int("MAX_ROWS", 100),
        timeout_seconds=_int("QUERY_TIMEOUT_SECONDS", 30),
    )


def scrub(text: str) -> str:
    """Remove secret values and Azure SQL host names from text before showing it."""
    for name in SECRET_VARS:
        value = os.environ.get(name, "").strip()
        if len(value) >= 3:
            text = text.replace(value, "<redacted>")
    return re.sub(r"[\w.-]+\.database\.windows\.net", "<redacted-server>", text)


def fail(message: str) -> None:
    """Exit with a clear message (used by entry points)."""
    sys.exit(message)
