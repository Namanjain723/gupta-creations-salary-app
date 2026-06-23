"""Page 5 — Variable Ledger (advances / interest / B-F / TG bonus + commissions)."""
import pandas as pd
import streamlit as st

from modules import constants as C, salary_engine as eng, sheets_sync as db, ui, utils

ui.page_header("Variable Ledger", "💰",
               "Record advances, balance-forward, interest and TG bonus. "
               "Commissions are pulled from the SALE_REPORT_KN tab.")

month = st.session_state.month
admin = st.session_state.admin
emps = db.get_employees(ui.active_location(), active_only=True)

if emps.empty:
    ui.empty("No active employees for this location.")
    st.stop()

emp_options = {f"{r['Emp_Code']} — {r['Emp_Name']}": r.to_dict() for _, r in emps.iterrows()}

tab_entry, tab_comm, tab_out = st.tabs(["➕ Entries", "🧾 Commissions", "📊 Outstanding"])

# --------------------------------------------------------------------------- #
#  Entries
# --------------------------------------------------------------------------- #
with tab_entry:
    with st.form("ledger_add", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        pick = c1.selectbox("Employee", list(emp_options))
        etype = c2.selectbox("Type", C.LEDGER_ENTRY_TYPES)
        amount = c3.number_input("Amount ₹", min_value=0, step=100)
        c1, c2 = st.columns([1, 2])
        edate = c1.date_input("Date", utils.now_ist().date(), format="DD/MM/YYYY")
        notes = c2.text_input("Notes")
        if st.form_submit_button("Add entry", type="primary"):
            emp = emp_options[pick]
            db.save_ledger_entry({
                "Month_Year": month, "Emp_Code": emp["Emp_Code"], "Emp_Name": emp["Emp_Name"],
                "Entry_Date": utils.fmt_date(edate), "Entry_Type": etype,
                "Amount": amount, "Notes": notes}, admin)
            st.success(f"Added {etype} {ui.money(amount)} for {emp['Emp_Name']}.")
            st.rerun()

    st.divider()
    fcol1, fcol2 = st.columns(2)
    filt_emp = fcol1.selectbox("Filter employee", ["All"] + list(emp_options), key="led_filt")
    led = db.get_ledger(month)
    if filt_emp != "All":
        code = emp_options[filt_emp]["Emp_Code"]
        led = led[led["Emp_Code"].apply(utils.normalise_emp_code) ==
                  utils.normalise_emp_code(code)]
    if led.empty:
        st.info("No ledger entries for this month yet.")
    else:
        for _, r in led.iterrows():
            cols = st.columns([1, 2, 2, 2, 3, 1])
            cols[0].write(f"#{r['Ledger_ID']}")
            cols[1].write(r["Entry_Type"])
            cols[2].write(r["Emp_Name"])
            cols[3].write(ui.money(r["Amount"]))
            cols[4].write(f"{r['Entry_Date']} · {r['Notes'] or '—'}")
            if cols[5].button("🗑", key=f"del_led_{r['Ledger_ID']}"):
                db.delete_ledger_entry(r["Ledger_ID"], admin)
                st.rerun()

# --------------------------------------------------------------------------- #
#  Commissions (SALE_REPORT_KN)
# --------------------------------------------------------------------------- #
with tab_comm:
    st.caption("Pulled from the SALE_REPORT_KN tab in the **KN scaled format** "
               "(2 decimals). The app multiplies by 100 for payroll — "
               "e.g. **19.80 → ₹1,980**, **8.56 → ₹856**. Enter values exactly as the "
               "KN team provides them (with the decimal).")
    sales = db.get_sales_kn(month)
    if sales.empty:
        st.info(f"No SALE_REPORT_KN rows for {utils.month_label(month)}. "
                "Paste monthly commission data into that tab (or add rows below).")
        sales = pd.DataFrame(columns=C.COLUMNS[C.TAB_SALES_KN])
    for col in ["S_Com", "B_Com", "L_Com", "Total_Commission"]:
        sales[col] = pd.to_numeric(sales[col], errors="coerce").fillna(0.0).round(2)
    edited = st.data_editor(
        sales, use_container_width=True, num_rows="dynamic", key="comm_editor",
        column_config={
            "S_Com": st.column_config.NumberColumn("S.Com (×100=₹)", format="%.2f"),
            "B_Com": st.column_config.NumberColumn("B.Com (×100=₹)", format="%.2f"),
            "L_Com": st.column_config.NumberColumn("L.Com (×100=₹)", format="%.2f"),
            "Total_Commission": st.column_config.NumberColumn("Total", format="%.2f"),
        })
    # live ₹ preview so the admin can sanity-check the conversion
    if not edited.empty:
        prev = edited[["Emp_Name", "S_Com", "B_Com", "L_Com"]].copy()
        for c in ["S_Com", "B_Com", "L_Com"]:
            prev[c] = prev[c].apply(lambda v: ui.money(db.commission_to_rupees(v), dash=True))
        prev.columns = ["Employee", "S.Com ₹", "B.Com ₹", "L.Com ₹"]
        with st.expander("👁️ Preview in rupees (what payroll will use)"):
            st.dataframe(prev, use_container_width=True, hide_index=True)
    if st.button("💾 Save commission corrections", type="primary"):
        edited["Month_Year"] = edited["Month_Year"].replace("", month).fillna(month)
        edited.loc[edited["Month_Year"] == "", "Month_Year"] = month
        db.save_sales_kn(edited, admin)
        st.success("Commissions saved. ✓")
        st.rerun()

# --------------------------------------------------------------------------- #
#  Outstanding advances
# --------------------------------------------------------------------------- #
with tab_out:
    rows = []
    for _, emp in emps.iterrows():
        adv = db.advances_for(emp["Emp_Code"], month)
        if adv["total"] == 0 and adv["bf"] == 0:
            continue
        interest = eng.calc_interest(adv["total"])
        rows.append({"Employee": emp["Emp_Name"], "Cash": adv["cash"], "Bank": adv["bank"],
                     "Total Advance": adv["total"], "Interest Due (1%)": interest,
                     "B/F": adv["bf"]})
    if not rows:
        st.info("No outstanding advances this month.")
    else:
        odf = pd.DataFrame(rows)
        st.dataframe(odf.style.map(
            lambda v: "background-color:#FFCDD2;font-weight:700;"
            if isinstance(v, (int, float)) and v > 10000 else "",
            subset=["Total Advance"]), use_container_width=True, hide_index=True)
        flagged = odf[odf["Total Advance"] > 10000]["Employee"].tolist()
        if flagged:
            st.error(f"🔴 Advance > ₹10,000 (interest applies): {', '.join(flagged)}")
