"""Run the eval set against the real agent (uses the API and the database).

    python -m tests.run_evals

An answer passes if every expected string appears in it (case-insensitive,
thousands separators ignored). A refusal case passes if the agent refuses and
runs no SQL. This is deterministic and cheap: no second model acts as judge.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import anthropic

from src.agent.agent import Answer, ask, explain_error
from src.agent.config import ConfigError, Settings, load_settings
from src.agent.mcp_tools import McpTools

EVAL_FILE = Path(__file__).with_name("eval_set.json")


def passed(case: dict, ans: Answer) -> bool:
    if case.get("expect_refusal"):
        return ans.refused and not ans.sql
    text = ans.text.lower().replace(",", "")
    return all(e.lower().replace(",", "") in text for e in case["expected"])


async def run_case(case: dict, tools: McpTools, client: anthropic.AsyncAnthropic,
                   settings: Settings) -> tuple[bool, Answer | None]:
    try:
        ans = await ask(case["question"], tools, client, settings)
    except Exception as exc:
        print(f"      error: {explain_error(exc)}")
        return False, None
    return passed(case, ans), ans


async def main() -> int:
    try:
        settings = load_settings()
    except ConfigError as exc:
        sys.exit(str(exc))
    cases = json.loads(EVAL_FILE.read_text(encoding="utf-8"))
    client = anthropic.AsyncAnthropic(api_key=settings.api_key)
    wins = tokens_in = tokens_out = 0
    async with McpTools(settings) as tools:
        for case in cases:
            ok, ans = await run_case(case, tools, client, settings)
            wins += ok
            if ans:
                tokens_in += ans.input_tokens
                tokens_out += ans.output_tokens
            print(f"{'PASS' if ok else 'FAIL'}  {case['question']}")
            if not ok and ans:
                print(f"      got: {ans.text[:200]}")
    print(f"\n{wins}/{len(cases)} passed  [tokens: {tokens_in} in / {tokens_out} out]")
    return 0 if wins == len(cases) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
