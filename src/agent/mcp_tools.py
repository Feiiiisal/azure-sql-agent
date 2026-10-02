"""Thin MCP client: starts the read-only SQL server and exposes its tools to Claude.

The agent never opens a database connection itself; every query goes through
the MCP server launched from scripts/run_mssql_mcp.py.
"""

from __future__ import annotations

import asyncio
import os
import sys
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .config import PROJECT_ROOT, Settings, scrub

SERVER_SCRIPT = PROJECT_ROOT / "scripts" / "run_mssql_mcp.py"

# Layer 2: only read / schema-inspection tools are ever shown to the model, and
# only these arguments. The model cannot pick another profile/catalog or ask for
# a snapshot file.
ALLOWED_ARGS = {
    "run_query": ("sql", "parameters"),
    "get_object": ("kind", "name", "schema", "includes"),
}

WAKE_RETRIES = 4
WAKE_WAIT_SECONDS = 15
# Markers of a paused serverless database that is still resuming.
WAKING_MARKERS = ("not currently available", "40613", "40197", "resuming", "is paused")


class ToolError(Exception):
    """The MCP tool reported an error (message is already scrubbed)."""


class DatabaseWaking(ToolError):
    """The serverless database is paused/resuming and did not wake in time."""


class McpTools:
    """Async context manager: `async with McpTools(settings) as tools:`."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._stack = AsyncExitStack()
        self._session: ClientSession | None = None
        self.specs: list[dict[str, Any]] = []  # tool definitions in Anthropic format

    async def __aenter__(self) -> "McpTools":
        params = StdioServerParameters(
            command=sys.executable, args=[str(SERVER_SCRIPT)], cwd=PROJECT_ROOT
        )
        # The server logs startup chatter to stderr; keep the CLI output clean.
        errlog = self._stack.enter_context(open(os.devnull, "w"))
        read, write = await self._stack.enter_async_context(stdio_client(params, errlog))
        self._session = await self._stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()
        self.specs = [self._to_spec(t) for t in (await self._session.list_tools()).tools
                      if t.name in ALLOWED_ARGS]
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._stack.aclose()

    @staticmethod
    def _to_spec(tool: Any) -> dict[str, Any]:
        """Convert an MCP tool to Anthropic's format, keeping only allowed inputs."""
        schema = dict(tool.input_schema)
        allowed = ALLOWED_ARGS[tool.name]
        props = {k: v for k, v in schema.get("properties", {}).items() if k in allowed}
        required = [k for k in schema.get("required", []) if k in allowed]
        schema = {**schema, "properties": props, "required": required}
        return {"name": tool.name, "description": tool.description or "", "input_schema": schema}

    async def call(self, name: str, args: dict[str, Any]) -> str:
        """Call a tool; retry while a paused serverless database wakes up."""
        if name not in ALLOWED_ARGS:
            raise ToolError(f"Tool not allowed: {name}")
        # Drop any argument the model was not offered.
        args = {k: v for k, v in args.items() if k in ALLOWED_ARGS[name]}
        for attempt in range(1, WAKE_RETRIES + 1):
            try:
                return await self._call_once(name, args)
            except DatabaseWaking:
                if attempt == WAKE_RETRIES:
                    raise
                print(f"  (database is waking up, retrying in {WAKE_WAIT_SECONDS}s "
                      f"[{attempt}/{WAKE_RETRIES}]...)")
                await asyncio.sleep(WAKE_WAIT_SECONDS)
        raise AssertionError("unreachable")

    async def _call_once(self, name: str, args: dict[str, Any]) -> str:
        assert self._session is not None
        # Query timeout is enforced by the server; this is a safety net on top
        # (extra headroom covers the connection timeout while a database resumes).
        limit = self._settings.timeout_seconds + 70
        try:
            result = await asyncio.wait_for(self._session.call_tool(name, args), limit)
        except asyncio.TimeoutError:
            raise ToolError("The database query timed out.") from None
        except Exception as exc:  # the server reports SQL errors as exceptions too
            raise self._classify(str(exc)) from None
        text = "\n".join(getattr(c, "text", "") for c in result.content)
        if result.is_error:
            raise self._classify(text)
        return text

    @staticmethod
    def _classify(message: str) -> ToolError:
        message = scrub(message)
        if any(m in message.lower() for m in WAKING_MARKERS):
            return DatabaseWaking("The database is still waking up from pause.")
        return ToolError(message)
