"""Command-line entry point: type a question, get an answer, the SQL, and token usage.

Run from the project root:  python -m src.agent.cli
"""

from __future__ import annotations

import asyncio
import sys

import anthropic

from .agent import Answer, ask, explain_error
from .config import ConfigError, Settings, load_settings
from .mcp_tools import McpTools


def show(ans: Answer) -> None:
    """Print the answer, the exact SQL that ran, and what it cost in tokens."""
    print(f"\n{ans.text}\n")
    for sql in ans.sql:
        print(f"SQL used:\n  {sql}\n")
    print(f"[tokens: {ans.input_tokens} in / {ans.output_tokens} out, "
          f"{ans.tool_calls} tool call(s)]\n")


async def run(settings: Settings, first_question: str | None) -> None:
    client = anthropic.AsyncAnthropic(api_key=settings.api_key)
    async with McpTools(settings) as tools:
        question = first_question
        while True:
            if question is None:
                question = (await asyncio.to_thread(input, "Question (blank to quit)> ")).strip()
            if not question:
                return
            try:
                show(await ask(question, tools, client, settings))
            except Exception as exc:  # show a friendly message, keep the session alive
                print(f"\n{explain_error(exc)}\n")
            if first_question is not None:
                return
            question = None


def main() -> None:
    try:
        settings = load_settings()
    except ConfigError as exc:
        sys.exit(str(exc))
    first = " ".join(sys.argv[1:]).strip() or None  # optional one-shot question
    try:
        asyncio.run(run(settings, first))
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # e.g. the MCP server failed to start
        sys.exit(explain_error(exc))


if __name__ == "__main__":
    main()
