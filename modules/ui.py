"""
ui.py
=====
Shared Streamlit UI helpers: theme CSS, KPI cards, money formatting (with the
real ₹ glyph, since the browser renders UTF-8), sidebar selectors, Excel/CSV
download buttons, and nashta cell colouring.
"""
from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from . import constants as C
from . import sheets_sync as db
from . import utils

THEME = C.THEME


# --------------------------------------------------------------------------- #
#  Theme / CSS
# --------------------------------------------------------------------------- #
def inject_css():
    st.markdown(f"""
    <style>
      .stApp {{ background: {THEME['background']}; }}
      section[data-testid="stSidebar"] {{ background: {THEME['sidebar_bg']}; }}
      .block-container {{ padding-top: 2.2rem; }}
      div[data-testid="stMetric"] {{
          background: {THEME['card_bg']}; border: 1px solid {THEME['border']};
          border-radius: 12px; padding: 14px 16px; box-shadow: {THEME['shadow']};
      }}
      div[data-testid="stMetricLabel"] p {{ color: {THEME['text_secondary']};
          font-size: 0.78rem; font-weight: 600; }}
      .gc-pill {{ display:inline-block; padding:3px 10px; border-radius:999px;
          font-size:0.72rem; font-weight:700; }}
      .gc-green {{ background:{THEME['tab_a_bg']}; color:{THEME['success']}; }}
      .gc-red   {{ background:{THEME['tab_b_bg']}; color:{THEME['danger']}; }}
      .gc-amber {{ background:#FFF8E1; color:#B7791F; }}
      .gc-title {{ font-size:1.05rem; font-weight:700; color:{THEME['text_primary']};
          margin: 6px 0 2px; }}
      h1 {{ color:{THEME['text_primary']}; }}
      .stTabs [data-baseweb="tab-list"] {{ gap: 4px; }}
    </style>""", unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
#  Session state
# --------------------------------------------------------------------------- #
def ensure_state():
    ss = st.session_state
    if "month" not in ss:
        opts = utils.month_options(back=8, fwd=2)
        ss.month = "05-2026" if "05-2026" in opts else opts[len(opts) // 2]
    ss.setdefault("location", C.DEFAULT_LOCATION)
    ss.setdefault("admin", "Admin")


def sidebar_controls():
    """Render the shared month / location selectors + status in the sidebar."""
    ss = st.session_state
    with st.sidebar:
        st.markdown("### 📅 Payroll Period")
        opts = utils.month_options(back=10, fwd=3)
        if ss.month not in opts:
            opts = sorted(set(opts + [ss.month]))
        ss.month = st.selectbox("Month", opts, index=opts.index(ss.month),
                                format_func=utils.month_label, key="_month_sel")
        loc_opts = ["ALL"] + C.LOCATIONS
        ss.location = st.selectbox("Location", loc_opts,
                                   index=loc_opts.index(ss.location)
                                   if ss.location in loc_opts else 1, key="_loc_sel")
        if ss.location in C.LOCATIONS and ss.location not in C.ACTIVE_LOCATIONS:
            st.caption("⚠️ This location isn't configured yet (Phase 1 = Kamla Nagar).")

        st.divider()
        backend_badge()
        st.caption(f"🕒 Last synced: {db.last_sync_str()}")
        if st.button("🔄 Reload data", use_container_width=True):
            db.clear_cache()
            st.rerun()
        st.caption(f"{C.APP_VERSION}")


def backend_badge():
    mode = db.backend_mode()
    if mode == "GOOGLE_SHEETS":
        st.success("🟢 Connected to Google Sheets", icon="✅")
    else:
        st.info("💾 Local mode (offline). Add Google credentials to sync to Sheets.",
                icon="💾")


def active_location() -> str | None:
    loc = st.session_state.get("location", C.DEFAULT_LOCATION)
    return None if loc == "ALL" else loc


# --------------------------------------------------------------------------- #
#  Formatting / widgets
# --------------------------------------------------------------------------- #
def money(v, dash=False) -> str:
    if dash and utils.safe_float(v) == 0:
        return "—"
    return utils.fmt_inr(v)


def pill(text: str, kind: str = "green") -> str:
    return f'<span class="gc-pill gc-{kind}">{text}</span>'


def kpi_row(items: list[tuple]):
    """items: list of (label, value, help_or_None)."""
    cols = st.columns(len(items))
    for col, item in zip(cols, items):
        label, value = item[0], item[1]
        helptxt = item[2] if len(item) > 2 else None
        col.metric(label, value, help=helptxt)


def section(title: str, emoji: str = ""):
    st.markdown(f"#### {emoji} {title}".strip())


def empty(msg: str):
    st.info(msg)


def page_header(title: str, emoji: str, subtitle: str = ""):
    st.markdown(f"# {emoji} {title}")
    if subtitle:
        st.caption(subtitle)


# --------------------------------------------------------------------------- #
#  Downloads
# --------------------------------------------------------------------------- #
def df_to_excel_bytes(data, sheet_name="Sheet1") -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xl:
        if isinstance(data, dict):
            for name, df in data.items():
                df.to_excel(xl, sheet_name=name[:31], index=False)
        else:
            data.to_excel(xl, sheet_name=sheet_name[:31], index=False)
    return buf.getvalue()


def download_buttons(df: pd.DataFrame, filename_base: str, *, excel=True, csv=True,
                     key_prefix="dl"):
    cols = st.columns(2 if (excel and csv) else 1)
    i = 0
    if excel:
        cols[i].download_button("⬇️ Excel", df_to_excel_bytes(df),
                                file_name=f"{filename_base}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                use_container_width=True, key=f"{key_prefix}_xlsx")
        i += 1
    if csv:
        cols[i].download_button("⬇️ CSV", df.to_csv(index=False).encode("utf-8"),
                                file_name=f"{filename_base}.csv", mime="text/csv",
                                use_container_width=True, key=f"{key_prefix}_csv")


# --------------------------------------------------------------------------- #
#  Nashta colours
# --------------------------------------------------------------------------- #
def nashta_bg(value) -> str:
    v = utils.safe_float(value)
    if v >= 20:
        return "background-color:#C8F7C5;"          # green
    if v > 0:
        return "background-color:#FFF6C8;"          # light yellow
    if v == 0:
        return "background-color:#ECEFF1;color:#90A4AE;"  # grey
    if v >= -12:
        return "background-color:#FFE0B2;"          # orange
    return "background-color:#FFCDD2;"              # red


def style_nashta_grid(df: pd.DataFrame, value_cols: list):
    sty = df.style
    sty = sty.map(lambda v: nashta_bg(_extract_num(v)), subset=value_cols)
    return sty


def _extract_num(cell):
    import re
    m = re.search(r"-?\d+", str(cell).replace(",", ""))
    return int(m.group()) if m else 0
