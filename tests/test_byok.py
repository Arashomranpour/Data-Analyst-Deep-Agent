"""Bring-your-own-key: the host's GROQ_API_KEY is never used for visitors, and keys never leak."""

import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from analyst.agent.runner import describe_error
from analyst.config import Settings, get_settings
from analyst.persistence import save_session
from analyst.ui.session import AnalystSession

APP = str(Path(__file__).resolve().parent.parent / "streamlit_app.py")
HOST_KEY = "gsk_HOSTSECRET1234567890"


def test_host_key_is_ignored_unless_explicitly_allowed():
    ignored = AnalystSession(Settings(llm_backend="groq", groq_api_key=HOST_KEY))
    assert ignored.settings.groq_api_key is None and not ignored.can_run

    allowed = AnalystSession(Settings(llm_backend="groq", groq_api_key=HOST_KEY, allow_server_key=True))
    assert allowed.settings.groq_api_key == HOST_KEY and allowed.can_run


def test_offline_demo_needs_no_key():
    assert AnalystSession(Settings(llm_backend="fake")).can_run


def test_changing_the_key_or_backend_rebuilds_the_agent():
    session = AnalystSession(Settings(llm_backend="fake"))
    first = session.ensure_runner()
    assert session.ensure_runner() is first
    session.settings.llm_backend = "groq"
    session.settings.groq_api_key = "gsk_userkey12345678"
    assert session.ensure_runner() is not first


def test_keys_are_scrubbed_from_error_messages():
    message = describe_error(RuntimeError(f"upstream exploded while using {HOST_KEY} for request"))
    assert "HOSTSECRET" not in message and "gsk_***" in message


def test_a_saved_session_never_contains_the_key(tmp_path):
    session = AnalystSession(Settings(llm_backend="groq", groq_api_key="gsk_unused"))
    session.settings.groq_api_key = "gsk_USERSECRET1234567"
    session.load_sample()
    folder = save_session(session, tmp_path, "s")
    blob = "".join(p.read_text(encoding="utf-8") for p in folder.rglob("*.json"))
    assert "USERSECRET" not in blob and json.loads((folder / "session.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------------------------- the UI
@pytest.fixture
def groq_app(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "groq")
    monkeypatch.setenv("GROQ_API_KEY", HOST_KEY)
    get_settings.cache_clear()
    yield AppTest.from_file(APP, default_timeout=60).run()
    get_settings.cache_clear()


def test_visitors_see_the_key_prompt_not_the_hosts_key(groq_app):
    at = groq_app
    assert not at.exception
    assert any("Bring your own Groq API key" in s.value for s in at.subheader)
    assert at.chat_input[0].disabled
    page = " ".join(str(el.value) for el in at.main if hasattr(el, "value"))
    assert "HOSTSECRET" not in page


def test_entering_a_key_unlocks_the_app_and_only_the_last_four_are_shown(groq_app):
    at = groq_app
    at.text_input(key="groq_key_input").set_value("gsk_visitorkey000ABCD")
    next(b for b in at.button if b.label == "Use this key").click().run()
    assert not at.exception
    next(b for b in at.sidebar.button if "Load sample" in b.label).click().run()
    assert not at.chat_input[0].disabled
    sidebar_text = " ".join(c.value for c in at.sidebar.caption)
    assert "ABCD" in sidebar_text and "visitorkey" not in sidebar_text


def test_demo_button_lets_visitors_try_without_a_key(groq_app):
    at = groq_app
    next(b for b in at.button if "offline demo" in b.label).click().run()
    next(b for b in at.sidebar.button if "Load sample" in b.label).click().run()
    at.chat_input[0].set_value("Which region has the highest revenue?").run()
    assert not at.exception and any(
        "highest revenue" in m.markdown[0].value for m in at.chat_message if m.markdown
    )


def test_detector_can_be_switched_from_the_sidebar(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "fake")
    get_settings.cache_clear()
    at = AppTest.from_file(APP, default_timeout=60).run()
    box = next(s for s in at.sidebar.selectbox if "injection detector" in s.label)
    assert box.value == "both"  # the stronger detector is the default
    box.select("regex").run()
    assert at.session_state.session.guards.injection_detector == "regex"
    get_settings.cache_clear()


def test_session_saving_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "fake")
    monkeypatch.setenv("ENABLE_SESSION_SAVE", "false")
    get_settings.cache_clear()
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not any("Save session" in b.label for b in at.sidebar.button)
    get_settings.cache_clear()
