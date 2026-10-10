"""Accounts (UserStore) and the multi-user Streamlit flow."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from analyst.auth.users import AuthError, UserStore, hash_password, verify_password
from analyst.config import Settings, get_settings
from analyst.persistence import list_sessions, save_session
from analyst.ui.session import AnalystSession


class Clock:
    def __init__(self):
        self.now = 1_000.0

    def __call__(self):
        return self.now


@pytest.fixture
def store(tmp_path):
    return UserStore(tmp_path / "users.db")


# ------------------------------------------------------------------------------- hashing
def test_password_hashes_are_salted_and_verifiable():
    a, b = hash_password("correct horse"), hash_password("correct horse")
    assert a != b and "correct horse" not in a
    assert verify_password("correct horse", a) and not verify_password("wrong", a)
    assert not verify_password("x", "garbage") and not verify_password("x", "md5$aa$bb")


# ------------------------------------------------------------------------------- accounts
def test_first_account_is_admin_the_rest_are_analysts(store):
    assert store.create_user("Alice", "password1").role == "admin"
    bob = store.create_user("bob", "password2")
    assert bob.role == "analyst" and bob.username == "bob"
    assert [u.username for u in store.list_users()] == ["alice", "bob"]


@pytest.mark.parametrize("name", ["", "ab", "has space", "../etc", "a" * 33, "bad/name"])
def test_bad_usernames_are_rejected(store, name):
    with pytest.raises(AuthError, match="Usernames"):
        store.create_user(name, "password1")


def test_short_passwords_and_duplicates_are_rejected(store):
    with pytest.raises(AuthError, match="at least"):
        store.create_user("alice", "short")
    store.create_user("alice", "password1")
    with pytest.raises(AuthError, match="taken"):
        store.create_user("ALICE", "password1")


def test_sign_in_is_case_insensitive_and_errors_are_generic(store):
    store.create_user("alice", "password1")
    assert store.authenticate("  Alice ", "password1").username == "alice"
    with pytest.raises(AuthError, match="Invalid username or password"):
        store.authenticate("nobody", "x")
    with pytest.raises(AuthError, match="Invalid username or password"):
        store.authenticate("alice", "x")


def test_lockout_after_repeated_failures_then_recovers(tmp_path):
    clock = Clock()
    store = UserStore(tmp_path / "u.db", max_attempts=3, lockout_s=60, clock=clock)
    store.create_user("alice", "password1")
    for _ in range(3):
        with pytest.raises(AuthError, match="Invalid"):
            store.authenticate("alice", "wrong")
    with pytest.raises(AuthError, match="Too many failed attempts"):
        store.authenticate("alice", "password1")  # even the right password is refused while locked
    clock.now += 61
    assert store.authenticate("alice", "password1").username == "alice"


def test_successful_sign_in_resets_the_failure_counter(tmp_path):
    store = UserStore(tmp_path / "u.db", max_attempts=3)
    store.create_user("alice", "password1")
    for _ in range(2):
        with pytest.raises(AuthError):
            store.authenticate("alice", "wrong")
    store.authenticate("alice", "password1")
    for _ in range(2):  # two more failures must not trip the lock (counter was reset)
        with pytest.raises(AuthError, match="Invalid"):
            store.authenticate("alice", "wrong")


def test_disabled_accounts_cannot_sign_in(store):
    store.create_user("alice", "password1")
    store.create_user("bob", "password2")
    store.set_disabled("bob", True)
    with pytest.raises(AuthError, match="disabled"):
        store.authenticate("bob", "password2")
    store.set_disabled("bob", False)
    assert store.authenticate("bob", "password2")


def test_admin_operations_and_the_last_admin_is_protected(store):
    store.create_user("alice", "password1")  # admin
    store.create_user("bob", "password2")
    store.set_role("bob", "admin")
    store.set_role("alice", "analyst")  # fine: bob is still an admin
    with pytest.raises(AuthError, match="at least one active administrator"):
        store.set_role("bob", "analyst")
    with pytest.raises(AuthError, match="at least one active administrator"):
        store.set_disabled("bob", True)
    with pytest.raises(AuthError, match="at least one active administrator"):
        store.delete_user("bob")
    store.reset_password("alice", "brand-new-pw")
    assert store.authenticate("alice", "brand-new-pw")
    store.delete_user("alice")
    assert store.get_user("alice") is None
    with pytest.raises(AuthError, match="No such user"):
        store.reset_password("ghost", "password1")


def test_accounts_survive_reopening_the_database(tmp_path):
    UserStore(tmp_path / "u.db").create_user("alice", "password1")
    assert UserStore(tmp_path / "u.db").authenticate("alice", "password1")


# ------------------------------------------------------------- per-user saved sessions
def test_each_user_has_a_private_sessions_folder(tmp_path):
    settings = Settings(llm_backend="fake", sessions_dir=str(tmp_path))
    alice, bob = AnalystSession(settings, "alice"), AnalystSession(settings, "bob")
    alice.load_sample()
    save_session(alice, alice.sessions_root, "mine")
    assert list_sessions(alice.sessions_root) == ["mine"]
    assert list_sessions(bob.sessions_root) == []
    assert alice.sessions_root == Path(tmp_path) / "alice"
    assert AnalystSession(settings).sessions_root == Path(tmp_path)  # auth off: shared folder as before


# --------------------------------------------------------------------------- streamlit
APP = str(Path(__file__).resolve().parent.parent / "streamlit_app.py")


@pytest.fixture
def secure_app(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_BACKEND", "fake")
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("USERS_DB", str(tmp_path / "users.db"))
    monkeypatch.setenv("SESSIONS_DIR", str(tmp_path / "sessions"))
    get_settings.cache_clear()
    yield AppTest.from_file(APP, default_timeout=60).run()
    get_settings.cache_clear()


def _submit(at, form_label):
    return next(b for b in at.button if b.label == form_label)


def test_signed_out_visitors_only_see_the_sign_in_page(secure_app):
    assert not secure_app.exception
    assert not secure_app.chat_input  # the app itself is not rendered
    assert any("first account" in i.value for i in secure_app.info)


def test_sign_up_then_use_the_app_as_admin(secure_app):
    at = secure_app
    at.text_input[2].set_value("alice")  # Create-account tab: username, password, repeat
    at.text_input[3].set_value("password1")
    at.text_input[4].set_value("password1")
    _submit(at, "Create account").click().run()
    assert not at.exception
    assert at.chat_input and any("alice" in m.value and "admin" in m.value for m in at.sidebar.markdown)
    assert any("Admin" in t.label for t in at.tabs)


def test_wrong_password_is_refused_and_signup_mismatch_is_caught(secure_app):
    at = secure_app
    at.text_input[0].set_value("nobody")
    at.text_input[1].set_value("password1")
    _submit(at, "Sign in").click().run()
    assert any("Invalid username or password" in e.value for e in at.error)
    assert not at.chat_input

    at.text_input[2].set_value("alice")
    at.text_input[3].set_value("password1")
    at.text_input[4].set_value("different")
    _submit(at, "Create account").click().run()
    assert any("do not match" in e.value for e in at.error) and not at.chat_input


def test_sign_out_returns_to_the_sign_in_page(secure_app):
    at = secure_app
    at.text_input[2].set_value("alice")
    at.text_input[3].set_value("password1")
    at.text_input[4].set_value("password1")
    _submit(at, "Create account").click().run()
    next(b for b in at.sidebar.button if b.label == "Sign out").click().run()
    assert not at.chat_input and not at.exception
