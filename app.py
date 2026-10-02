"""Streamlit chat UI on top of the existing agent.  Run: streamlit run app.py

All query logic lives in src/agent/. This file only draws the page; every
question goes through agent.ask(), which applies the SELECT-only guard.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import streamlit as st

from src.agent.agent import explain_error
from src.agent.config import ConfigError, Settings, load_settings
from src.agent.mcp_tools import DatabaseWaking
from src.agent.runtime import AgentRuntime

EVAL_FILE = Path(__file__).parent / "tests" / "eval_set.json"

st.set_page_config(page_title="Azure SQL Agent")


@st.cache_resource  # one agent + MCP session shared across reruns
def get_runtime() -> AgentRuntime:
    return AgentRuntime(load_settings())


def example_questions(n: int = 4) -> list[str]:
    """First n data questions from the eval set (skips the refusal case)."""
    cases = json.loads(EVAL_FILE.read_text(encoding="utf-8"))
    return [c["question"] for c in cases if not c.get("expect_refusal")][:n]


def sidebar(settings: Settings) -> None:
    """Show only safe settings: never the API key, server or database name."""
    st.sidebar.header("Read-only demo")
    st.sidebar.write("Only single SELECT queries with a row limit are run. "
                     "Requests to change data are refused.")
    st.sidebar.markdown(f"**Model:** `{settings.model}`  \n"
                        f"**MAX_ROWS:** {settings.max_rows}  \n"
                        f"**MAX_TOOL_CALLS:** {settings.max_tool_calls}")


def show_result(entry: dict[str, Any]) -> None:
    """Draw the assistant half of one chat turn."""
    with st.chat_message("assistant"):
        error, ans = entry["error"], entry["answer"]
        if error is not None:
            # A paused serverless database is expected: info, not an error.
            (st.info if isinstance(error, DatabaseWaking) else st.error)(explain_error(error))
            return
        if ans.refused:
            st.warning("Request refused (this demo is read-only): "
                       + ans.text.removeprefix("REFUSED:").strip())
        else:
            st.markdown(ans.text)
        if ans.sql:
            with st.expander("SQL that ran"):
                for sql in ans.sql:
                    st.code(sql, language="sql")
        st.caption(f"{ans.input_tokens} in / {ans.output_tokens} out tokens · "
                   f"{ans.tool_calls} tool call(s)")


def main() -> None:
    st.title("Ask your Azure SQL data")
    try:
        runtime = get_runtime()
    except ConfigError as exc:  # names the missing variable, never its value
        st.error(str(exc))
        st.stop()
    sidebar(runtime.settings)

    history = st.session_state.setdefault("history", [])
    clicked = None
    for col, q in zip(st.columns(4), example_questions()):
        if col.button(q, use_container_width=True):
            clicked = q

    for entry in history:  # replay earlier turns (each question stands alone)
        with st.chat_message("user"):
            st.write(entry["question"])
        show_result(entry)

    question = st.chat_input("Ask a question about the data") or clicked
    if question:
        with st.chat_message("user"):
            st.write(question)
        entry: dict[str, Any] = {"question": question, "answer": None, "error": None}
        with st.spinner("Thinking... (a paused database can take a minute to wake)"):
            try:
                entry["answer"] = runtime.ask(question)
            except Exception as exc:  # shown via explain_error, which scrubs secrets
                entry["error"] = exc
        history.append(entry)
        show_result(entry)


main()
