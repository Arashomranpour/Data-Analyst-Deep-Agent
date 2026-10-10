import pandas as pd
import streamlit as st

from analyst.config import MODEL_CHOICES, get_settings
from analyst.guardrails.classifiers import available_classifiers
from analyst.persistence import list_sessions, load_session, save_session
from analyst.ui import auth_views, views
from analyst.ui.session import AnalystSession, ChatMessage

st.set_page_config(page_title="Data Analyst Deep Agent", page_icon="🧠", layout="wide")

# ----------------------------------------------------------------------------- sign in
settings = get_settings()
user_store = auth_views.store_for(settings) if settings.auth_enabled else None
user = auth_views.gate(user_store, settings) if user_store else None  # stops here until signed in


def get_session() -> AnalystSession:
    existing = st.session_state.get("session")
    if existing is None or existing.user != (user.username if user else None):
        st.session_state.session = AnalystSession(settings.model_copy(), user.username if user else None)
    return st.session_state.session


# ----------------------------------------------------------------------------- sidebar
def render_sidebar(session: AnalystSession):
    """Draws the sidebar; returns the placeholder the live progress panel is streamed into."""
    sb = st.sidebar
    sb.title("🧠 Data Analyst Deep Agent")
    sb.caption("LangChain **deepagents** · **Guardrails AI** · Groq")

    with sb.expander("⚡ Live progress", expanded=True):
        progress_ph = st.empty()
        with progress_ph.container():
            views.render_progress(session.progress, session)

    with sb.expander("1 · Data", expanded=True):
        if st.button("📦 Load sample sales data", width="stretch"):
            session.load_sample()
            st.rerun()
        uploads = st.file_uploader("…or upload CSV files", type=["csv"], accept_multiple_files=True)
        limit = session.settings.max_upload_mb * 1024 * 1024
        for file in uploads or []:
            if file.file_id in session.loaded_files:
                continue
            if file.size > limit:
                st.error(f"{file.name} is larger than {session.settings.max_upload_mb} MB.")
                continue
            try:
                session.load_csv(file.name, pd.read_csv(file))
                session.loaded_files.add(file.file_id)
                st.rerun()
            except Exception as exc:
                st.error(f"Could not read {file.name}: {exc}")
        if session.store.tables:
            st.markdown(session.store.schema_text())

    with sb.expander("2 · Agent", expanded=False):
        if settings.llm_backend == "groq":
            choice = st.radio(
                "Model backend",
                ["Groq (your own API key)", "Offline demo model"],
                index=0 if session.settings.llm_backend == "groq" else 1,
                help="The demo model is scripted: it shows the UI and guardrails without any API key.",
            )
            session.settings.llm_backend = "groq" if choice.startswith("Groq") else "fake"
        if session.settings.llm_backend == "fake":
            st.info("Offline demo model (scripted). It always runs the same revenue-by-region analysis.")
        else:
            views.render_key_status(session)
            session.model_name = st.selectbox(
                "Model", MODEL_CHOICES, index=MODEL_CHOICES.index(session.model_name)
            )
        session.require_approval = st.toggle(
            "Human approval for every SQL query",
            value=session.require_approval,
            help="Pauses the agent before each run_sql so you can approve, edit or reject it.",
        )

    with sb.expander("3 · Guardrails", expanded=True):
        session.guards.enabled = st.toggle(
            "Guardrails AI enabled",
            value=session.guards.enabled,
            help="Turn off to see how the agent behaves unprotected (try the poisoned-data attack).",
        )
        st.caption(
            "🟢 Protected" if session.guards.enabled else "🔴 **UNPROTECTED** - for demonstration only"
        )
        detectors = ["regex", "both", *[n for n in available_classifiers() if n != "heuristic"]]
        names = {"regex": "Regex patterns (fast)", "both": "Regex + heuristic scorer (stronger)"}
        current = session.guards.injection_detector
        if current not in detectors:
            detectors.append(current)
        picked = st.selectbox(
            "Prompt-injection detector",
            detectors,
            index=detectors.index(current),
            format_func=lambda n: names.get(n, n),
            help="The heuristic scorer also catches paraphrased attacks the regexes do not know.",
        )
        if picked != current:
            session.guards.set_detector(picked)

    if session.settings.enable_session_save:
        with sb.expander("4 · Session", expanded=False):
            save_name = st.text_input("Save as", value="my_analysis", key="save_name")
            if st.button("💾 Save session", width="stretch", disabled=not session.store.tables):
                folder = save_session(session, session.sessions_root, save_name)
                st.success(f"Saved to {folder}")
            saved = list_sessions(session.sessions_root)
            if saved:
                choice = st.selectbox("Saved sessions", saved, key="restore_choice")
                if st.button("📂 Restore session", width="stretch"):
                    try:
                        load_session(session, session.sessions_root, choice)
                        st.rerun()
                    except (OSError, ValueError, KeyError) as exc:
                        st.error(f"Could not restore {choice}: {exc}")
            else:
                st.caption("No saved sessions yet.")

    sb.divider()
    sb.markdown("**Try a prompt**")
    for label, prompt in views.EXAMPLE_PROMPTS.items():
        runnable = bool(session.store.tables) and session.can_run
        if sb.button(label, key=f"ex_{label}", width="stretch", disabled=not runnable):
            st.session_state.queued_prompt = prompt
            st.rerun()
    if sb.button("🧹 New conversation", width="stretch"):
        session.reset_conversation()
        st.rerun()
    return progress_ph


# ------------------------------------------------------------------------------- run
def stream_events(session: AnalystSession, events, plan_ph, trace_ph, progress_ph) -> None:
    """Consume agent events, updating the live status box and the right-hand panels."""
    status = st.status("🧠 The team is working…", expanded=True)
    for event in events:
        session.record(event)
        session.progress.on_event(event)
        with progress_ph.container():
            views.render_progress(session.progress, session)
        if event.kind == "todos":
            with plan_ph.container():
                views.render_plan(session.todos)
        elif event.kind == "tool_call":
            status.markdown(views.tool_line(event))
            status.update(label=f"🧠 {event.agent} → {event.name}")
        elif event.kind == "interrupt":
            status.update(label="⏸️ Waiting for your approval", state="running")
        if event.kind in ("tool_call", "tool_result", "thought", "file"):
            with trace_ph.container():
                views.render_trace(session.trace[-12:])
    last = session.messages[-1] if session.messages else None
    if session.pending:
        status.update(label="⏸️ Waiting for your approval", state="running", expanded=True)
    elif last and last.blocked:
        status.update(label="⛔ Stopped", state="error", expanded=False)
    else:
        used = f" · {session.tokens:,} tokens" if session.tokens else ""
        status.update(label=f"✅ Done{used}", state="complete", expanded=False)


def render_history(session: AnalystSession) -> None:
    for message in session.messages:
        with st.chat_message(message.role):
            if message.blocked:
                st.error(message.content, icon="🛡️")
                continue
            st.markdown(message.content)
            for warning in message.warnings:
                st.warning(f"**Grounding check:** {warning}", icon="⚠️")


# ------------------------------------------------------------------------------- page
session = get_session()
progress_ph = render_sidebar(session)
if user:
    auth_views.render_account(user)

st.title("🧠 Data Analyst Deep Agent")
st.caption(
    "A planner delegates to specialised subagents (profiler · SQL analyst · visualizer · critic). "
    "Guardrails AI screens every input, query, tool result and answer."
)

left, right = st.columns([5, 4], gap="large")
with right:
    tab_names = ["🗺️ Plan & trace", "📊 Data & charts", "📄 Report", "🛡️ Guardrails"]
    if user and user.is_admin:
        tab_names.append("👑 Admin")
    tabs = st.tabs(tab_names)
    tab_plan, tab_data, tab_report, tab_guard = tabs[:4]
    with tab_plan:
        plan_box, trace_box = st.container(), st.container()
        plan_ph, trace_ph = plan_box.empty(), trace_box.empty()

with left:
    history_box = st.container()
    approval_box = st.container()
    ready = bool(session.store.tables) and session.can_run
    typed = st.chat_input("Ask about your data…", disabled=not ready or session.pending is not None)

if not session.can_run:
    with left:
        views.render_key_gate(session)
elif not ready:
    with left:
        st.info("👈 Load the sample dataset or upload a CSV to begin.")

decision = None
if session.pending:
    with approval_box:
        decision = views.render_interrupt(session.pending)

prompt = typed or st.session_state.pop("queued_prompt", None)
acted = False
if (prompt or decision) and ready:
    acted = True
    with history_box:
        render_history(session)
        try:
            runner = session.ensure_runner()
            if prompt:
                session.messages.append(ChatMessage("user", prompt))
                session.trace.clear()
                with st.chat_message("user"):
                    st.markdown(prompt)
                session.progress.begin()
                events = runner.ask(prompt, session.thread_id)
            else:
                session.pending = None
                session.progress.resume()
                events = runner.resume(decision, session.thread_id)
            with st.chat_message("assistant"):
                stream_events(session, events, plan_ph, trace_ph, progress_ph)
        except RuntimeError as exc:
            session.messages.append(ChatMessage("assistant", f"⚠️ {exc}", blocked=True))
    st.rerun()

with history_box:
    render_history(session)
with plan_ph.container():
    views.render_plan(session.todos)
with trace_ph.container():
    views.render_trace(session.trace)

with tab_data:
    views.render_charts(session)
    views.render_data(session)
with tab_report:
    views.render_report(session)
with tab_guard:
    attack = views.render_guardrails(session)
    if attack and ready:
        st.session_state.queued_prompt = attack
        st.rerun()
if user and user.is_admin:
    with tabs[4]:
        auth_views.render_admin(user_store, user)
