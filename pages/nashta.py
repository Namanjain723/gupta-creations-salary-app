"""Page 3B — Nashta Tracker (100% biometric-driven, no manual entry)."""
import streamlit as st

from modules import pdf_generator, reporting, ui, utils

ui.page_header("Nashta Tracker", "🍵",
               "Daily ₹20 breakfast balance, net of late fines. 100% biometric-driven — "
               "no manual entry. Green = on time (+₹20), red = chronically late (negative).")

month = st.session_state.month
loc = ui.active_location()
loc_label = st.session_state.location

view = st.radio("View", ["Daily Detail", "Monthly Summary"], horizontal=True)

if view == "Daily Detail":
    df, date_cols, _ = reporting.nashta_daily_grid(month, loc)
    if df.empty:
        ui.empty("No attendance data for this month/location yet.")
        st.stop()

    emp_filter = st.selectbox("Employee", ["All"] + df["Employee"].tolist())
    show = df if emp_filter == "All" else df[df["Employee"] == emp_filter]

    st.caption("🟢 +₹20 on time · 🟡 small positive · 🟠 −₹12 · 🔴 ≤ −₹28 · ⚪ WO/Absent")
    value_cols = date_cols + ["TOTAL"]
    styler = ui.style_nashta_grid(show, value_cols)
    st.dataframe(styler, use_container_width=True, hide_index=True, height=460)

    company_total = int(df["TOTAL"].sum())
    st.metric("Company-wide net nashta (this month)", ui.money(company_total))

    c1, c2 = st.columns(2)
    c1.download_button("⬇️ Download Excel", ui.df_to_excel_bytes(df),
                       f"Nashta_{loc_label.replace(' ', '')}_{utils.month_label(month).replace(' ', '')}.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       use_container_width=True)
else:
    df = reporting.nashta_summary_df(month, loc)
    if df.empty:
        ui.empty("No attendance data for this month/location yet.")
        st.stop()

    disp = df[["Emp_Name", "OnTime_Days", "Late_Days_16", "Late_Days_32", "Late_Days_48",
               "Late_Days_64", "Late_Days_80", "Net_Monthly_Nashta", "Monthly_Result"]].copy()
    disp.columns = ["Employee", "On-Time", "₹16", "₹32", "₹48", "₹64", "₹80",
                    "Net Nashta", "Result"]
    st.dataframe(disp, use_container_width=True, hide_index=True)

    c1, c2 = st.columns(2)
    c1.download_button("⬇️ Excel", ui.df_to_excel_bytes(df),
                       f"Nashta_Summary_{utils.month_label(month).replace(' ', '')}.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       use_container_width=True)
    pdf = pdf_generator.table_pdf(
        f"Nashta Monthly Summary — {utils.month_label(month)} ({loc_label})",
        disp, money_cols=["Net Nashta"])
    c2.download_button("⬇️ PDF", pdf,
                       f"Nashta_{utils.month_label(month).replace(' ', '')}.pdf",
                       "application/pdf", use_container_width=True)
