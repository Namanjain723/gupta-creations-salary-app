"""Page 4 — Manual Overrides (week-off change / single / double absent / long leave)."""
import streamlit as st

from modules import constants as C, reporting, sheets_sync as db, ui, utils
from modules import salary_engine as eng

ui.page_header("Manual Overrides", "⚙️",
               "Adjust attendance: change a week-off day, mark single/double absent, "
               "or record long leave. Each override re-processes the month immediately.")

month = st.session_state.month
admin = st.session_state.admin
emps = db.get_employees(ui.active_location(), active_only=True)

if emps.empty:
    ui.empty("No active employees for this location.")
    st.stop()

emp_options = {f"{r['Emp_Code']} — {r['Emp_Name']}": r.to_dict() for _, r in emps.iterrows()}


def _emp_pick(label, key):
    pick = st.selectbox(label, list(emp_options), key=key)
    return emp_options[pick]


def _save(ov, msg):
    db.save_override(ov, admin)
    reporting.persist_month(month, ui.active_location(), admin)
    st.success(msg)


def _rate(emp, month):
    return eng.daily_wage_rate(utils.safe_float(emp.get("Base_Salary")),
                               utils.calendar_days_in_month(month))


# --------------------------------------------------------------------------- #
#  1 · Week-Off Change
# --------------------------------------------------------------------------- #
with st.expander("📆 Week-Off Change", expanded=True):
    with st.form("woc"):
        emp = _emp_pick("Employee", "woc_emp")
        c1, c2, c3 = st.columns(3)
        c1.text_input("Original week-off", emp.get("Week_Off_Default", "MON"), disabled=True)
        new_day = c2.selectbox("New week-off day", C.WEEK_DAYS)
        c3.empty()
        d1, d2 = st.columns(2)
        start = d1.date_input("From", utils.now_ist().date(), format="DD/MM/YYYY", key="woc_s")
        end = d2.date_input("To", utils.now_ist().date(), format="DD/MM/YYYY", key="woc_e")
        reason = st.text_input("Reason", key="woc_r")
        if st.form_submit_button("Apply Week-Off Change", type="primary"):
            _save({"Month_Year": month, "Emp_Code": emp["Emp_Code"], "Emp_Name": emp["Emp_Name"],
                   "Override_Date": utils.fmt_date(start), "Override_Date_End": utils.fmt_date(end),
                   "Override_Type": "WEEK_OFF_CHANGE", "New_Week_Off_Day": new_day, "Notes": reason},
                  f"Week-off moved to {new_day} for {emp['Emp_Name']}.")

# --------------------------------------------------------------------------- #
#  2 · Single Absent
# --------------------------------------------------------------------------- #
with st.expander("➖ Single Absent (deduct 1× daily wage)"):
    with st.form("single"):
        emp = _emp_pick("Employee", "sa_emp")
        d = st.date_input("Date", utils.now_ist().date(), format="DD/MM/YYYY", key="sa_d")
        reason = st.text_input("Reason", key="sa_r")
        rate = _rate(emp, month)
        st.caption(f"Will deduct ₹{rate:,} (1 day) for {emp['Emp_Name']}.")
        if st.form_submit_button("Apply Single Absent", type="primary"):
            _save({"Month_Year": month, "Emp_Code": emp["Emp_Code"], "Emp_Name": emp["Emp_Name"],
                   "Override_Date": utils.fmt_date(d), "Override_Type": "SINGLE_ABSENT",
                   "Notes": reason}, f"Single absent applied for {emp['Emp_Name']}.")

# --------------------------------------------------------------------------- #
#  3 · Double Absent
# --------------------------------------------------------------------------- #
with st.expander("⛔ Double Absent (deduct 2× daily wage)"):
    with st.form("double"):
        emp = _emp_pick("Employee", "da_emp")
        d = st.date_input("Date", utils.now_ist().date(), format="DD/MM/YYYY", key="da_d")
        reason = st.text_input("Reason (required)", key="da_r")
        rate = _rate(emp, month)
        st.warning(f"⚠️ This deducts ₹{rate * 2:,} (2× daily wage) for one day.")
        if st.form_submit_button("Apply Double Absent", type="primary"):
            if not reason.strip():
                st.error("Reason is required for a double absent.")
            else:
                _save({"Month_Year": month, "Emp_Code": emp["Emp_Code"], "Emp_Name": emp["Emp_Name"],
                       "Override_Date": utils.fmt_date(d), "Override_Type": "DOUBLE_ABSENT",
                       "Notes": reason}, f"Double absent applied for {emp['Emp_Name']}.")

# --------------------------------------------------------------------------- #
#  4 · Long Leave
# --------------------------------------------------------------------------- #
with st.expander("🧳 Long Leave (week-offs in range NOT exempt)"):
    with st.form("long"):
        emp = _emp_pick("Employee", "ll_emp")
        d1, d2 = st.columns(2)
        start = d1.date_input("From", utils.now_ist().date(), format="DD/MM/YYYY", key="ll_s")
        end = d2.date_input("To", utils.now_ist().date(), format="DD/MM/YYYY", key="ll_e")
        reason = st.text_input("Reason (required)", key="ll_r")
        days = utils.date_range(start, end)
        rate = _rate(emp, month)
        st.warning(f"⚠️ {len(days)} days × ₹{rate:,} = **₹{len(days) * rate:,}** deduction "
                   f"(includes any week-offs in the range).")
        if st.form_submit_button("Apply Long Leave", type="primary"):
            if not reason.strip():
                st.error("Reason is required for long leave.")
            else:
                _save({"Month_Year": month, "Emp_Code": emp["Emp_Code"], "Emp_Name": emp["Emp_Name"],
                       "Override_Date": utils.fmt_date(start), "Override_Date_End": utils.fmt_date(end),
                       "Override_Type": "LONG_LEAVE", "Notes": reason},
                      f"Long leave ({len(days)} days) applied for {emp['Emp_Name']}.")

# --------------------------------------------------------------------------- #
#  Current overrides
# --------------------------------------------------------------------------- #
st.divider()
ui.section("Active Overrides", "📋")
ov = db.get_overrides(active_only=True)
if ov.empty:
    st.info("No active overrides.")
else:
    for _, r in ov.iterrows():
        cols = st.columns([1, 2, 2, 3, 3, 1])
        cols[0].write(f"#{r['Override_ID']}")
        cols[1].write(r["Override_Type"])
        cols[2].write(r["Emp_Name"])
        cols[3].write(f"{r['Override_Date']}" + (f" → {r['Override_Date_End']}"
                      if r["Override_Date_End"] else ""))
        cols[4].write(r["Notes"] or "—")
        if cols[5].button("🗑", key=f"del_ov_{r['Override_ID']}"):
            db.delete_override(r["Override_ID"], admin)
            reporting.persist_month(month, ui.active_location(), admin)
            st.rerun()
