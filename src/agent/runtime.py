"""Keep ONE MCP session alive in a background thread, for UIs that rerun a lot.

Streamlit re-executes the whole script on every click, but the MCP session is
async and must be opened and closed by the same task. So a single long-lived
task owns the session, and the UI hands it questions through a queue.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import threading

import anthropic

from .agent import Answer, ask
from .config import Settings
from .mcp_tools import McpTools


class AgentRuntime:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = anthropic.AsyncAnthropic(api_key=settings.api_key)
        self._queue: asyncio.Queue = asyncio.Queue()
        self._failed: Exception | None = None  # set if the MCP server dies
        loop = asyncio.new_event_loop()
        threading.Thread(target=loop.run_until_complete, args=(self._serve(),),
                         daemon=True).start()
        self._loop = loop

    async def _serve(self) -> None:
        """Own the MCP session; answer queued questions one at a time."""
        try:
            async with McpTools(self.settings) as tools:
                while True:
                    question, fut = await self._queue.get()
                    try:  # same agent loop and guard as the CLI
                        fut.set_result(await ask(question, tools, self._client, self.settings))
                    except Exception as exc:
                        fut.set_exception(exc)
        except Exception as exc:  # MCP server failed to start or crashed
            self._failed = exc
            while not self._queue.empty():
                self._queue.get_nowait()[1].set_exception(exc)

    def ask(self, question: str, timeout: float = 300) -> Answer:
        """Blocking call for the UI thread."""
        if self._failed:
            raise self._failed
        fut: concurrent.futures.Future = concurrent.futures.Future()
        self._loop.call_soon_threadsafe(self._queue.put_nowait, (question, fut))
        return fut.result(timeout)
