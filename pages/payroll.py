"""Page 6 — Payroll Run."""
import streamlit as st

from modules import reporting, sheets_sync as db, ui, utils

ui.page_header("Payroll Run", "🧮",
               "Verify the checklist, preview every employee's salary, then run payroll "
               "for the month. Handles positive & negative nashta and Lena carry-forward.")

month = st.session_state.month
loc = ui.active_location()
admin = st.session_state.admin

# --------------------------------------------------------------------------- #
#  Pre-run checklist
# --------------------------------------------------------------------------- #
emps = db.get_employees(loc, active_only=True)
bio = db.get_biometric(month, loc)
overrides = db.get_overrides(month)
sales = db.get_sales_kn(month)

with st.spinner("Computing preview…"):
    pay_df, processed = reporting.build_payroll_rows(month, loc)

se_pending = sum(1 for _, (_, days) in processed.items()
                 for r in days if r.final_status == "SINGLE_ENTRY_REVIEW")

ui.section("Pre-Run Checklist", "✅")
checks = [
    (not emps.empty, f"{len(emps)} active employees loaded"),
    (not bio.empty, f"Biometric data present ({len(bio)} rows)"),
    (se_pending == 0, f"Single-entry reviews complete ({se_pending} pending)"),
    (not sales.empty, f"Commissions present ({len(sales)} rows in SALE_REPORT_KN)"),
]
for ok, label in checks:
    st.write(("✅ " if ok else "⚠️ ") + label)

st.divider()

# --------------------------------------------------------------------------- #
#  Preview
# --------------------------------------------------------------------------- #
ui.section("Payroll Preview", "👁️")
if pay_df.empty:
    ui.empty("Nothing to preview — add employees & biometric data first.")
    st.stop()

prev = pay_df[["Emp_Name", "Present_Days", "Gross_Earnings", "Total_Deductions",
               "Net_Payable", "Result_Type"]].copy()
for c in ["Gross_Earnings", "Total_Deductions", "Net_Payable"]:
    prev[c] = prev[c].apply(ui.money)
prev.columns = ["Employee", "Present", "Gross", "Deductions", "Net", "Result"]
st.dataframe(prev, use_container_width=True, hide_index=True)

tot_dena = int(pay_df[pay_df["Result_Type"] == "CASH_DENA"]["Cash_Dena_Amount"]
               .apply(utils.safe_float).sum())
tot_lena = int(pay_df[pay_df["Result_Type"] == "LENA"]["Lena_Amount"]
               .apply(utils.safe_float).sum())
ui.kpi_row([("Employees", len(pay_df)), ("Total Cash Dena", ui.money(tot_dena)),
            ("Total Lena", ui.money(tot_lena))])

st.divider()

# --------------------------------------------------------------------------- #
#  Run
# --------------------------------------------------------------------------- #
ui.section("Run Payroll", "🚀")
st.warning(f"This will generate final salary for **{utils.month_label(month)}** for "
           f"**{len(pay_df)} employees** and overwrite any previous run for this month.")
confirm = st.checkbox("I have verified the preview above.")
if st.button("🧮 Run Payroll", type="primary", disabled=not confirm):
    reporting.persist_month(month, loc, admin)
    db.save_payroll(pay_df.to_dict("records"), month, admin)
    st.success(f"✅ Payroll run complete for {utils.month_label(month)} — "
               f"{len(pay_df)} employees. Cash Dena {ui.money(tot_dena)}, Lena {ui.money(tot_lena)}.")
    st.balloons()

# --------------------------------------------------------------------------- #
#  Last saved run
# --------------------------------------------------------------------------- #
saved = db.get_payroll(month)
if not saved.empty:
    st.divider()
    ui.section("Last Saved Payroll_Final", "💾")
    st.caption(f"{len(saved)} rows saved for {utils.month_label(month)}. "
               "Go to **Salary Slips** to print, or **Reports** to export.")
    ui.download_buttons(saved, f"Payroll_{utils.month_label(month).replace(' ', '')}",
                        key_prefix="payroll")
    with st.expander("View full Payroll_Final table"):
        st.dataframe(saved, use_container_width=True, hide_index=True)
