"""
reporting.py
============
Page-facing aggregation. Wires sheets_sync (data) + processing (attendance) +
salary_engine (payroll/nashta) so the Streamlit pages stay thin. No Streamlit
imports here — keeps it testable and reusable.
"""
from __future__ import annotations

import pandas as pd

from . import salary_engine as eng
from . import processing
from . import sheets_sync as db
from . import utils


def get_processed(month: str, location: str | None):
    """Return (employees_df, {code: (emp, [DayResult])}) for a month/location."""
    emps = db.get_employees(location, active_only=True)
    bio = db.get_biometric(month, location)
    overrides = db.get_overrides(month)
    holidays = db.holiday_dates()
    processed = processing.process_location_month(emps, month, bio, overrides, holidays)
    return emps, processed


def build_payroll_rows(month: str, location: str | None = None, run_date: str = "") -> tuple:
    """Compute Payroll_Final rows for every active employee. Returns (df, processed)."""
    emps, processed = get_processed(month, location)
    comm_map = db.get_commissions_kn(month)
    rows = []
    for i, (code, (emp, days)) in enumerate(processed.items(), start=1):
        comm = db.commissions_for(emp, comm_map)
        adv = db.advances_for(code, month)
        prev_lena = db.get_previous_lena(code, month)
        rec = eng.build_payroll_record(
            employee=emp, month_year=month, day_results=days, commissions=comm,
            advance_cash=adv["cash"], advance_bank=adv["bank"],
            jama=adv.get("jama", 0), hdfc=adv.get("hdfc", 0),
            interest=adv["interest"], bf_previous=prev_lena + adv["bf"],
            tg_bonus_override=(adv["tg"] if adv["tg"] > 0 else None),
            payroll_id=i, run_date=run_date)
        rec["_advance_cash_lines"] = adv.get("cash_lines", [])
        rec["_advance_bank_lines"] = adv.get("bank_lines", [])
        rec["_jama_lines"] = adv.get("jama_lines", [])
        rows.append(rec)
    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    return df, processed


def persist_month(month: str, location: str | None = None, admin: str = "Admin") -> dict:
    """Process the month and write Attendance_Processed + Nashta summary. Returns counts."""
    _, processed = get_processed(month, location)
    att_rows, nashta_rows = [], []
    overrides_applied = se_flagged = 0
    for code, (emp, days) in processed.items():
        att_rows += processing.attendance_rows(emp, month, days)
        nashta_rows.append(eng.nashta_summary_row(emp, month, days))
        for r in days:
            if r.manual_override and r.manual_override != "None":
                overrides_applied += 1
            if r.final_status == "SINGLE_ENTRY_REVIEW":
                se_flagged += 1
    if att_rows:
        db.upsert_attendance(att_rows, month, admin)
    if nashta_rows:
        db.save_nashta_summary(nashta_rows, month, admin)
    return {"rows": len(att_rows), "overrides": overrides_applied,
            "single_entries": se_flagged, "employees": len(processed)}


def nashta_summary_df(month: str, location: str | None = None) -> pd.DataFrame:
    _, processed = get_processed(month, location)
    rows = [eng.nashta_summary_row(emp, month, days)
            for code, (emp, days) in processed.items()]
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def nashta_daily_grid(month: str, location: str | None = None):
    """
    Build the daily nashta grid: one row per employee, one column per date.
    Returns (display_df, value_cols, totals_dict).
    """
    _, processed = get_processed(month, location)
    dates = utils.dates_in_month(month)
    date_cols = [utils.fmt_date(d)[:5] for d in dates]   # 'dd/mm'

    rows = []
    for code, (emp, days) in processed.items():
        by_date = {d.attendance_date: d for d in days}
        row = {"Employee": emp.get("Emp_Name", "")}
        total = 0
        for d, col in zip(dates, date_cols):
            r = by_date.get(utils.fmt_date(d))
            if r is None or r.day_type in ("WEEK_OFF", "HOLIDAY") and r.final_status != "EXTRA_PRESENT":
                row[col] = "WO" if (r and r.day_type == "WEEK_OFF") else "—"
                if r:
                    total += r.nashta_daily
                continue
            if r.final_status == "ABSENT":
                row[col] = "A"
            else:
                v = r.nashta_daily
                total += v
                row[col] = (f"+{v}" if v > 0 else str(v))
        row["TOTAL"] = total
        rows.append(row)

    df = pd.DataFrame(rows)
    return df, date_cols, {}


_STATUS_SHORT = {
    "PRESENT": "P", "ABSENT": "A", "WEEK_OFF": "WO", "EXTRA_PRESENT": "WOP",
    "HALF_DAY": "½", "QUARTER_DAY": "¼", "SEMI_DAY": "¾", "THIRD_DAY": "⅓",
    "DOUBLE_ABSENT": "AA", "SINGLE_ENTRY_REVIEW": "SE", "HOLIDAY": "H",
}


def daily_register(month: str, location: str | None, start_date, end_date):
    """
    Day-wise attendance register for a chosen day / date-range.
    Returns (register_df [Employee + one column per date + P-days],
             date_cols, per_day_summary_df).
    """
    _, processed = get_processed(month, location)
    dates = [d for d in utils.dates_in_month(month) if start_date <= d <= end_date]
    cols = [utils.fmt_date(d)[:5] for d in dates]            # 'dd/mm'

    reg_rows, summary = [], []
    for code, (emp, days) in processed.items():
        by = {r.attendance_date: r for r in days}
        row = {"Employee": emp.get("Emp_Name", "")}
        pdays = 0
        for d, col in zip(dates, cols):
            r = by.get(utils.fmt_date(d))
            status = r.final_status if r else "ABSENT"
            row[col] = _STATUS_SHORT.get(status, status[:2])
            if r and r.final_status in eng.PRESENT_STATUSES:
                pdays += 1
        row["P-days"] = pdays
        reg_rows.append(row)

    for d, col in zip(dates, cols):
        present = absent = wo = 0
        for code, (emp, days) in processed.items():
            r = next((x for x in days if x.attendance_date == utils.fmt_date(d)), None)
            if r and r.final_status in eng.PRESENT_STATUSES:
                present += 1
            elif r and r.final_status == "WEEK_OFF":
                wo += 1
            else:
                absent += 1
        summary.append({"Date": utils.fmt_date(d), "Present": present,
                        "Absent": absent, "Week Off": wo})

    return pd.DataFrame(reg_rows), cols, pd.DataFrame(summary)


def dashboard_metrics(month: str, location: str | None = None) -> dict:
    """KPIs for the dashboard."""
    emps, processed = get_processed(month, location)
    pay_df, _ = build_payroll_rows(month, location)

    # Reference day: real "today" if viewing the current month, else the
    # month's last calendar day (so historical months still show live counts).
    today = utils.now_ist().date()
    y, mo = utils.parse_month_year(month)
    last_day = utils.dates_in_month(month)[-1]
    ref_day = today if (y == today.year and mo == today.month) else last_day
    present_today = absent_today = weekoff_today = 0
    pending_se = 0
    late_counts = {}
    for code, (emp, days) in processed.items():
        for r in days:
            if r.final_status == "SINGLE_ENTRY_REVIEW":
                pending_se += 1
            if r.late_fine > 0:
                late_counts[code] = late_counts.get(code, 0) + 1
        td = next((r for r in days if r.attendance_date == utils.fmt_date(ref_day)), None)
        if td:
            if td.final_status in eng.PRESENT_STATUSES:
                present_today += 1
            elif td.final_status == "WEEK_OFF":
                weekoff_today += 1
            elif td.final_status in ("ABSENT", "DOUBLE_ABSENT"):
                absent_today += 1

    def col_sum(c):
        return int(pay_df[c].apply(utils.safe_float).sum()) if (not pay_df.empty and c in pay_df) else 0

    cash_dena = col_sum("Cash_Dena_Amount")
    lena = col_sum("Lena_Amount")
    return {
        "active": len(emps),
        "ref_day": utils.fmt_date(ref_day),
        "present_today": present_today,
        "absent_today": absent_today,
        "weekoff_today": weekoff_today,
        "total_payroll": cash_dena,
        "total_lena": lena,
        "late_fine": col_sum("Late_Fine_Total"),
        "nashta_expense": col_sum("Nashta_Total"),
        "epf": col_sum("EPF"),
        "esic": col_sum("ESIC"),
        "advances": col_sum("Advance_Cash_Total") + col_sum("Advance_Bank_Total"),
        "pending_se": pending_se,
        "late_counts": late_counts,
        "payroll_df": pay_df,
        "processed": processed,
    }
