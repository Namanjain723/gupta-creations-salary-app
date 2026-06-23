"""
auth.py
=======
Lightweight login gate so the shared app link is only usable by your team.

Users come from Streamlit secrets when deployed:
    [auth]
    [auth.users]
    naman = "a-strong-password"
    manager = "another-password"

If no users are configured (e.g. local run), a default admin login is used —
CHANGE IT before sharing the link. Roles: anyone listed in [auth.viewers] is
read-only (Save/Run buttons hidden); everyone else is an admin.
"""
from __future__ import annotations

import streamlit as st

DEFAULT_USERS = {"admin": "gupta123"}   # local fallback — override in secrets!


def _config() -> tuple[dict, set]:
    users, viewers = {}, set()
    try:
        auth = st.secrets.get("auth", {}) if hasattr(st, "secrets") else {}
        users = dict(auth.get("users", {}))
        viewers = {str(v).strip() for v in auth.get("viewers", [])}
    except Exception:
        pass
    return (users or DEFAULT_USERS), viewers


def require_login():
    """Block the app until a valid user signs in. Returns the username."""
    if st.session_state.get("_auth_user"):
        return st.session_state["_auth_user"]

    users, _ = _config()
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown("### 🔒 Gupta Creations — Salary App")
        st.caption("Please sign in to continue.")
        with st.form("login_form"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            ok = st.form_submit_button("Sign in", type="primary", use_container_width=True)
        if ok:
            if u in users and str(p) == str(users[u]):
                st.session_state["_auth_user"] = u
                st.rerun()
            else:
                st.error("Invalid username or password.")
        if users == DEFAULT_USERS:
            st.info("First time? Default login is **admin / gupta123** — "
                    "change it in Settings/secrets before sharing the link.")
    st.stop()


def current_user() -> str:
    return st.session_state.get("_auth_user", "")


def is_viewer() -> bool:
    """Read-only role check (used to hide Save/Run actions)."""
    _, viewers = _config()
    return current_user() in viewers


def can_edit() -> bool:
    return not is_viewer()


def logout_button():
    user = current_user()
    if not user:
        return
    with st.sidebar:
        st.divider()
        st.caption(f"👤 Signed in as **{user}**" + ("  ·  read-only" if is_viewer() else ""))
        if st.button("Sign out", use_container_width=True):
            st.session_state.pop("_auth_user", None)
            st.rerun()
