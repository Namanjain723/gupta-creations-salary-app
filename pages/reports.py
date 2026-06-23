"""Page 8 — Reports."""
import pandas as pd
import streamlit as st

from modules import pdf_generator, reporting, salary_engine as eng, sheets_sync as db, ui, utils

ui.page_header("Reports", "📊", "Attendance, late-fine, advances and payroll summaries — "
               "all downloadable as Excel / PDF.")

month = st.session_state.month
loc = ui.active_location()

tabs = st.tabs(["🗓️ Day-wise Register", "📅 Attendance (month)", "⏰ Late Fines",
                "💸 Advances", "🧾 Payroll Summary"])

_, processed = reporting.get_processed(month, loc)

# --------------------------------------------------------------------------- #
#  Day-wise register — pick a day / range of days / weeks
# --------------------------------------------------------------------------- #
with tabs[0]:
    all_dates = utils.dates_in_month(month)
    first, last = all_dates[0], all_dates[-1]
    st.caption("Pick a single day, or drag to select a range of days / weeks. "
               "Codes: P=present · A=absent · WO=week-off · WOP=worked week-off · "
               "½/¼/¾=part-day · SE=single-punch.")
    picked = st.date_input("Day or date-range", value=(first, last),
                           min_value=first, max_value=last, format="DD/MM/YYYY")
    if isinstance(picked, (list, tuple)):
        start_d, end_d = picked[0], picked[-1]
    else:
        start_d = end_d = picked

    reg, date_cols, summary = reporting.daily_register(month, loc, start_d, end_d)
    if reg.empty:
        ui.empty("No employees / data for this location.")
    else:
        n_days = len(date_cols)
        st.markdown(f"**{n_days} day(s): {utils.fmt_date(start_d)} → {utils.fmt_date(end_d)}**")
        st.dataframe(reg, use_container_width=True, hide_index=True, height=460)
        ui.section("Per-day totals", "📈")
        st.dataframe(summary, use_container_width=True, hide_index=True)
        c1, c2 = st.columns(2)
        c1.download_button("⬇️ Register (Excel)", ui.df_to_excel_bytes(reg),
                           f"Register_{utils.fmt_date(start_d).replace('/', '-')}_to_"
                           f"{utils.fmt_date(end_d).replace('/', '-')}.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           use_container_width=True)
        c2.download_button("⬇️ Per-day totals (CSV)", summary.to_csv(index=False).encode(),
                           "per_day_totals.csv", "text/csv", use_container_width=True)

# --------------------------------------------------------------------------- #
#  Attendance summary (whole month)
# --------------------------------------------------------------------------- #
with tabs[1]:
    rows = []
    for code, (emp, days) in processed.items():
        present = sum(1 for r in days if r.final_status in eng.PRESENT_STATUSES)
        absent = sum(1 for r in days if r.final_status in ("ABSENT", "DOUBLE_ABSENT"))
        wo = sum(1 for r in days if r.final_status == "WEEK_OFF")
        late = sum(1 for r in days if r.late_fine > 0)
        rows.append({"Employee": emp["Emp_Name"], "Present": present, "Absent": absent,
                     "Week Off": wo, "Late Days": late})
    adf = pd.DataFrame(rows)
    if adf.empty:
        ui.empty("No data.")
    else:
        st.dataframe(adf, use_container_width=True, hide_index=True)
        ui.download_buttons(adf, f"Attendance_{utils.month_label(month).replace(' ', '')}",
                            key_prefix="att")

# --------------------------------------------------------------------------- #
#  Late fine report
# --------------------------------------------------------------------------- #
with tabs[2]:
    rows = []
    for code, (emp, days) in processed.items():
        fine = sum(r.late_fine for r in days)
        if fine:
            rows.append({"Employee": emp["Emp_Name"], "Late Days": sum(1 for r in days if r.late_fine > 0),
                         "Total Fine ₹": fine})
    ldf = pd.DataFrame(rows).sort_values("Total Fine ₹", ascending=False) if rows else pd.DataFrame()
    if ldf.empty:
        st.success("No late fines this month. 🎉")
    else:
        st.dataframe(ldf, use_container_width=True, hide_index=True)
        st.metric("Total late fine collected", ui.money(ldf["Total Fine ₹"].sum()))
        ui.download_buttons(ldf, f"LateFines_{utils.month_label(month).replace(' ', '')}",
                            key_prefix="fine")

# --------------------------------------------------------------------------- #
#  Advances report
# --------------------------------------------------------------------------- #
with tabs[3]:
    rows = []
    for code, (emp, _) in processed.items():
        adv = db.advances_for(code, month)
        if adv["total"] or adv["bf"]:
            rows.append({"Employee": emp["Emp_Name"], "Cash ₹": adv["cash"], "Bank ₹": adv["bank"],
                         "Total ₹": adv["total"], "Interest ₹": eng.calc_interest(adv["total"]),
                         "B/F ₹": adv["bf"]})
    vdf = pd.DataFrame(rows)
    if vdf.empty:
        st.info("No advances this month.")
    else:
        st.dataframe(vdf, use_container_width=True, hide_index=True)
        ui.download_buttons(vdf, f"Advances_{utils.month_label(month).replace(' ', '')}",
                            key_prefix="adv")

# --------------------------------------------------------------------------- #
#  Payroll summary
# --------------------------------------------------------------------------- #
with tabs[4]:
    pay = db.get_payroll(month)
    if pay.empty:
        pay, _ = reporting.build_payroll_rows(month, loc)
        if not pay.empty:
            st.info("Live preview (payroll not yet run for this month).")
    if pay.empty:
        ui.empty("No payroll data.")
    else:
        def s(c):
            return int(pay[c].apply(utils.safe_float).sum())
        summary = pd.DataFrame([
            {"Metric": "Employees", "Value": str(len(pay))},
            {"Metric": "Total Gross", "Value": ui.money(s("Gross_Earnings"))},
            {"Metric": "Total EPF", "Value": ui.money(s("EPF"))},
            {"Metric": "Total ESIC", "Value": ui.money(s("ESIC"))},
            {"Metric": "Total Advances", "Value": ui.money(s("Advance_Cash_Total") + s("Advance_Bank_Total"))},
            {"Metric": "Total Late Fine", "Value": ui.money(s("Late_Fine_Total"))},
            {"Metric": "Total Cash Dena", "Value": ui.money(s("Cash_Dena_Amount"))},
            {"Metric": "Total Lena", "Value": ui.money(s("Lena_Amount"))},
        ])
        st.dataframe(summary, use_container_width=True, hide_index=True)
        pdf = pdf_generator.table_pdf(
            f"Monthly Payroll Summary — {utils.month_label(month)}",
            pay[["Emp_Name", "Gross_Earnings", "Total_Deductions", "Net_Payable", "Result_Type"]],
            money_cols=["Gross_Earnings", "Total_Deductions", "Net_Payable"])
        st.download_button("⬇️ Payroll Summary PDF", pdf,
                           f"PayrollSummary_{utils.month_label(month).replace(' ', '')}.pdf",
                           "application/pdf")
