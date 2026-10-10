"""Local user accounts: SQLite file, scrypt password hashes, roles, and brute-force lockout.

No external service and no extra dependency (hashing is stdlib `hashlib.scrypt`). Passwords are never
stored or logged; only salted hashes. Sign-in failures are deliberately generic so the form does not
reveal which usernames exist.
"""

import base64
import hashlib
import hmac
import re
import secrets
import sqlite3
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ROLES = ("admin", "analyst")
MIN_PASSWORD = 8
_USERNAME = re.compile(r"^[a-z0-9_.-]{3,32}$")
_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "maxmem": 64 * 1024 * 1024, "dklen": 32}
_GENERIC = "Invalid username or password."


class AuthError(Exception):
    """A sign-in or account-management request was refused. The message is safe to show the user."""


@dataclass(frozen=True)
class User:
    username: str
    role: str
    disabled: bool
    created_at: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest_b64)
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt_b64), **_SCRYPT)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


_DUMMY_HASH = hash_password("not-a-real-password")  # burns the same time for unknown usernames


def normalise_username(username: str) -> str:
    name = (username or "").strip().lower()
    if not _USERNAME.match(name):
        raise AuthError("Usernames are 3-32 characters: letters, digits, '.', '_' or '-'.")
    return name


def check_password_strength(password: str) -> None:
    if len(password or "") < MIN_PASSWORD:
        raise AuthError(f"Passwords need at least {MIN_PASSWORD} characters.")


class UserStore:
    def __init__(
        self,
        path: str | Path,
        max_attempts: int = 5,
        lockout_s: float = 60.0,
        clock: Callable[[], float] = time.time,
    ):
        self.path = Path(path)
        self.max_attempts, self.lockout_s, self._clock = max_attempts, lockout_s, clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('admin','analyst')),
                    disabled INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    failed_attempts INTEGER NOT NULL DEFAULT 0,
                    locked_until REAL NOT NULL DEFAULT 0)"""
            )

    @contextmanager
    def _db(self):
        """One short-lived connection per operation (safe across Streamlit threads and processes).
        Commits when the block succeeds, rolls back when it raises."""
        conn = sqlite3.connect(self.path, timeout=10)
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ---- queries -------------------------------------------------------
    def count(self) -> int:
        with self._db() as db:
            return db.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def get_user(self, username: str) -> User | None:
        with self._db() as db:
            row = db.execute(
                "SELECT username, role, disabled, created_at FROM users WHERE username = ?",
                ((username or "").strip().lower(),),
            ).fetchone()
        return _user(row) if row else None

    def list_users(self) -> list[User]:
        with self._db() as db:
            rows = db.execute(
                "SELECT username, role, disabled, created_at FROM users ORDER BY username"
            ).fetchall()
        return [_user(r) for r in rows]

    # ---- sign in -------------------------------------------------------
    def create_user(self, username: str, password: str, role: str | None = None) -> User:
        """Add an account. With role=None the very first account becomes the admin, the rest analysts."""
        name = normalise_username(username)
        check_password_strength(password)
        if role is not None and role not in ROLES:
            raise AuthError(f"Unknown role '{role}'.")
        with self._db() as db:
            first = db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
            role = role or ("admin" if first else "analyst")
            try:
                db.execute(
                    "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                    (name, hash_password(password), role, datetime.now(UTC).isoformat(timespec="seconds")),
                )
            except sqlite3.IntegrityError as exc:
                raise AuthError("That username is taken.") from exc
        return self.get_user(name)  # type: ignore[return-value]

    def authenticate(self, username: str, password: str) -> User:
        name = (username or "").strip().lower()
        error = ""  # raised after the transaction closes, so failed-attempt counters are kept
        with self._db() as db:
            row = db.execute(
                "SELECT password_hash, disabled, failed_attempts, locked_until FROM users WHERE username = ?",
                (name,),
            ).fetchone()
            if row is None:
                verify_password(password or "", _DUMMY_HASH)
                error = _GENERIC
            else:
                stored, disabled, failed, locked_until = row
                now = self._clock()
                if locked_until > now:
                    error = f"Too many failed attempts. Try again in {int(locked_until - now) + 1}s."
                elif not verify_password(password or "", stored):
                    failed += 1
                    lock = now + self.lockout_s if failed >= self.max_attempts else 0
                    db.execute(
                        "UPDATE users SET failed_attempts = ?, locked_until = ? WHERE username = ?",
                        (0 if lock else failed, lock, name),
                    )
                    error = _GENERIC
                elif disabled:
                    error = "This account is disabled. Ask an administrator."
                else:
                    db.execute(
                        "UPDATE users SET failed_attempts = 0, locked_until = 0 WHERE username = ?", (name,)
                    )
        if error:
            raise AuthError(error)
        return self.get_user(name)  # type: ignore[return-value]

    # ---- administration ------------------------------------------------
    def set_role(self, username: str, role: str) -> None:
        if role not in ROLES:
            raise AuthError(f"Unknown role '{role}'.")
        self._guard_last_admin(username, losing_admin=role != "admin")
        self._update(username, "role = ?", (role,))

    def set_disabled(self, username: str, disabled: bool) -> None:
        self._guard_last_admin(username, losing_admin=disabled)
        self._update(username, "disabled = ?", (int(disabled),))

    def reset_password(self, username: str, new_password: str) -> None:
        check_password_strength(new_password)
        self._update(
            username,
            "password_hash = ?, failed_attempts = 0, locked_until = 0",
            (hash_password(new_password),),
        )

    def delete_user(self, username: str) -> None:
        self._guard_last_admin(username, losing_admin=True)
        with self._db() as db:
            db.execute("DELETE FROM users WHERE username = ?", ((username or "").strip().lower(),))

    # ---- internals -----------------------------------------------------
    def _update(self, username: str, assignment: str, params: tuple) -> None:
        name = (username or "").strip().lower()
        with self._db() as db:
            cur = db.execute(f"UPDATE users SET {assignment} WHERE username = ?", (*params, name))
            if cur.rowcount == 0:
                raise AuthError(f"No such user '{name}'.")

    def _guard_last_admin(self, username: str, losing_admin: bool) -> None:
        user = self.get_user(username)
        if user is None or not losing_admin or not user.is_admin or user.disabled:
            return
        others = [
            u for u in self.list_users() if u.is_admin and not u.disabled and u.username != user.username
        ]
        if not others:
            raise AuthError("There must always be at least one active administrator.")


def _user(row) -> User:
    return User(row[0], row[1], bool(row[2]), row[3])
