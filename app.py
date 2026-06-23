"""
Gupta Creations Pvt. Ltd. — Salary Management App
Main Streamlit entry point.  Run:  streamlit run app.py
"""
import streamlit as st

from modules import auth
from modules import constants as C
from modules import ui

st.set_page_config(
    page_title="Gupta Creations Salary App",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)

ui.inject_css()
auth.require_login()          # 🔒 only signed-in team members past this point
ui.ensure_state()

with st.sidebar:
    st.markdown("## 🏢 Gupta Creations")
    st.caption("Salary Management System")

pages = [
    st.Page("pages/dashboard.py", title="Dashboard", icon="🏠", default=True),
    st.Page("pages/employees.py", title="Employee Master", icon="👥"),
    st.Page("pages/biometric.py", title="Biometric Upload", icon="📤"),
    st.Page("pages/nashta.py", title="Nashta Tracker", icon="🍵"),
    st.Page("pages/overrides.py", title="Manual Overrides", icon="⚙️"),
    st.Page("pages/ledger.py", title="Variable Ledger", icon="💰"),
    st.Page("pages/payroll.py", title="Payroll Run", icon="🧮"),
    st.Page("pages/slips.py", title="Salary Slips", icon="📄"),
    st.Page("pages/reports.py", title="Reports", icon="📊"),
]

nav = st.navigation(pages)
ui.sidebar_controls()
auth.logout_button()
nav.run()
