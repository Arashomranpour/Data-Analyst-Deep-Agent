---
paths:
  - "analyst/auth/**"
  - "analyst/ui/auth_views.py"
  - "streamlit_app.py"
---
# Accounts and sign-in
- Passwords: stdlib scrypt only (`hash_password` / `verify_password`), constant-time compare. Never store, log or
  echo a plaintext password; sign-in failures stay generic (same message for unknown user and wrong password).
- Usernames are validated by `normalise_username`; per-user paths (`AnalystSession.sessions_root`) rely on that, so never
  build a path from an unvalidated name.
- Keep at least one active admin (`UserStore._guard_last_admin`). Role and disabled state are re-read every run
  (`auth_views.current_user`) so changes apply immediately; sign-out clears all of `st.session_state`.
- Auth is off by default (`AUTH_ENABLED=false`) so the offline demo and the original tests are unchanged. New auth
  tests use `tmp_path` databases and the `secure_app` fixture in `tests/test_auth.py`.
