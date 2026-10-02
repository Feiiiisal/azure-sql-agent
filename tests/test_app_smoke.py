"""UI smoke test: runs app.py with a fake agent, so no API key or database is needed."""

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
import streamlit as st  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

from src.agent import config, runtime  # noqa: E402
from src.agent.agent import Answer  # noqa: E402
from src.agent.config import Settings  # noqa: E402

APP = str(Path(__file__).resolve().parents[1] / "app.py")


class FakeRuntime:
    """Stands in for AgentRuntime: canned answers, no network."""

    def __init__(self, settings):
        self.settings = settings

    def ask(self, question):
        if "delete" in question.lower():
            return Answer(text="REFUSED: I only answer read-only questions.")
        return Answer(text="There are 847 customers.", tool_calls=2,
                      input_tokens=100, output_tokens=20,
                      sql=["SELECT TOP 1 COUNT(*) FROM SalesLT.Customer"])


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(config, "load_settings",
                        lambda: Settings("fake-key", "test-model", 1024, 6, 100, 30))
    monkeypatch.setattr(runtime, "AgentRuntime", FakeRuntime)
    st.cache_resource.clear()  # don't reuse a runtime from another test
    return AppTest.from_file(APP, default_timeout=30).run()


def test_page_loads_with_examples_and_sidebar(app):
    assert not app.exception
    assert len(app.button) == 4
    sidebar = " ".join(m.value for m in app.sidebar.markdown)
    assert "test-model" in sidebar and "100" in sidebar and "6" in sidebar
    assert "fake-key" not in sidebar


def test_clicking_example_shows_answer_sql_and_usage(app):
    app.button[0].click().run()
    assert not app.exception
    assert any("847 customers" in m.value for m in app.markdown)
    assert [e.label for e in app.expander] == ["SQL that ran"]
    assert any("100 in / 20 out" in c.value and "2 tool call" in c.value for c in app.caption)


def test_write_request_shows_refusal(app):
    app.chat_input[0].set_value("Delete all customers").run()
    assert len(app.warning) == 1 and "refused" in app.warning[0].value.lower()
    assert not app.expander  # no SQL ran
