"""Streamlit pieces for sign-in, the account box and the admin panel. Account rules live in
`analyst.auth.users`; this module only draws forms and keeps the signed-in user in session state."""

import pandas as pd
import streamlit as st

from analyst.auth.users import ROLES, AuthError, User, UserStore
from analyst.config import Settings

USER_KEY = "auth_username"


@st.cache_resource
def get_user_store(path: str, admin_username: str | None, admin_password: str | None) -> UserStore:
    """One store per database file. Creates the bootstrap admin from the environment if the DB is empty."""
    store = UserStore(path)
    if admin_username and admin_password and store.count() == 0:
        store.create_user(admin_username, admin_password, role="admin")
    return store


def store_for(settings: Settings) -> UserStore:
    return get_user_store(settings.users_db, settings.admin_username, settings.admin_password)


def current_user(store: UserStore) -> User | None:
    """The signed-in user, re-read from the database every run so a disabled account or a changed
    role takes effect immediately."""
    name = st.session_state.get(USER_KEY)
    user = store.get_user(name) if name else None
    if user is None or user.disabled:
        st.session_state.pop(USER_KEY, None)
        return None
    return user


def logout() -> None:
    st.session_state.clear()  # drops the whole AnalystSession too: nothing leaks to the next sign-in


def gate(store: UserStore, settings: Settings) -> User:
    """Show the sign-in page and stop the script until someone is signed in."""
    user = current_user(store)
    if user:
        return user

    _, middle, _ = st.columns([1, 2, 1])
    with middle:
        st.title("🧠 Data Analyst Deep Agent")
        first_run = store.count() == 0
        if first_run:
            st.info("No accounts yet. The first account you create becomes the administrator.")
        tabs = st.tabs(["Sign in", "Create account"] if settings.allow_signup or first_run else ["Sign in"])
        with tabs[0]:
            with st.form("login"):
                name = st.text_input("Username")
                password = st.text_input("Password", type="password")
                if st.form_submit_button("Sign in", type="primary", width="stretch"):
                    try:
                        st.session_state[USER_KEY] = store.authenticate(name, password).username
                        st.rerun()
                    except AuthError as exc:
                        st.error(str(exc))
        if len(tabs) > 1:
            with tabs[1]:
                with st.form("signup"):
                    name = st.text_input("Choose a username")
                    password = st.text_input("Choose a password (8+ characters)", type="password")
                    confirm = st.text_input("Repeat the password", type="password")
                    if st.form_submit_button("Create account", width="stretch"):
                        if password != confirm:
                            st.error("The passwords do not match.")
                        else:
                            try:
                                st.session_state[USER_KEY] = store.create_user(name, password).username
                                st.rerun()
                            except AuthError as exc:
                                st.error(str(exc))
    st.stop()


def render_account(user: User) -> None:
    badge = "👑 admin" if user.is_admin else "analyst"
    box = st.sidebar.container(border=True)
    box.markdown(f"👤 **{user.username}** · {badge}")
    if box.button("Sign out", width="stretch"):
        logout()
        st.rerun()


def render_admin(store: UserStore, me: User) -> None:
    """User management for administrators."""
    st.subheader("Users")
    users = store.list_users()
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "username": u.username,
                    "role": u.role,
                    "status": "disabled" if u.disabled else "active",
                    "created": u.created_at,
                }
                for u in users
            ]
        ),
        width="stretch",
        hide_index=True,
    )

    with st.expander("➕ Create a user"):
        with st.form("admin_create"):
            name = st.text_input("Username")
            password = st.text_input("Temporary password", type="password")
            role = st.selectbox("Role", ROLES, index=1)
            if st.form_submit_button("Create"):
                try:
                    store.create_user(name, password, role=role)
                    st.success(f"Created {name.strip().lower()} ({role}).")
                    st.rerun()
                except AuthError as exc:
                    st.error(str(exc))

    with st.expander("✏️ Manage a user"):
        target = st.selectbox("User", [u.username for u in users], key="admin_target")
        chosen = next(u for u in users if u.username == target)
        role = st.selectbox("Role", ROLES, index=ROLES.index(chosen.role), key="admin_role")
        new_password = st.text_input("New password (leave empty to keep)", type="password", key="admin_pw")
        left, middle, right = st.columns(3)
        try:
            if left.button("Save changes", width="stretch"):
                if role != chosen.role:
                    store.set_role(target, role)
                if new_password:
                    store.reset_password(target, new_password)
                st.rerun()
            if middle.button("Enable" if chosen.disabled else "Disable", width="stretch"):
                store.set_disabled(target, not chosen.disabled)
                st.rerun()
            if right.button("Delete", width="stretch", disabled=target == me.username):
                store.delete_user(target)
                st.rerun()
        except AuthError as exc:
            st.error(str(exc))
