"""
processing.py
=============
Orchestration that bridges raw biometric data + manual overrides + holidays
into a month of classified DayResults (per employee). Pure-ish: it only takes
already-loaded DataFrames/dicts and calls salary_engine — no I/O — so it is
fully unit-testable.

Used by:
  * Biometric Upload page  -> writes Attendance_Processed
  * Payroll Run page        -> aggregates into Payroll_Final
  * Nashta Tracker page     -> daily nashta grid
"""
from __future__ import annotations

import pandas as pd

from . import salary_engine as eng
from . import utils


# --------------------------------------------------------------------------- #
#  Build per-employee lookup structures from sheet rows
# --------------------------------------------------------------------------- #
def biometric_by_date(bio_df: pd.DataFrame, emp_code: str) -> dict:
    """{date: merged punch info} for one employee."""
    norm = utils.normalise_emp_code(emp_code)
    out: dict = {}
    if bio_df is None or bio_df.empty:
        return out
    for _, r in bio_df.iterrows():
        if utils.normalise_emp_code(r.get("Emp_Code")) != norm:
            continue
        d = utils.parse_date(r.get("Attendance_Date"))
        if not d:
            continue
        pin = utils.time_to_minutes(r.get("In_Time"))
        pout = utils.time_to_minutes(r.get("Out_Time"))
        dur = utils.safe_int(r.get("Total_Duration_Mins"))
        se = utils.truthy(r.get("Single_Entry_Flag"))
        info = out.get(d)
        if info is None:
            out[d] = {
                "punch_in_min": pin, "punch_out_min": pout, "duration_mins": dur,
                "raw_status": str(r.get("Status_Raw", "")), "se_flag": se,
                "in_str": str(r.get("In_Time", "")), "out_str": str(r.get("Out_Time", "")),
            }
        else:
            # merge duplicate rows: earliest in, latest out, max duration
            if pin is not None and (info["punch_in_min"] is None or pin < info["punch_in_min"]):
                info["punch_in_min"], info["in_str"] = pin, str(r.get("In_Time", ""))
            if pout is not None and (info["punch_out_min"] is None or pout > info["punch_out_min"]):
                info["punch_out_min"], info["out_str"] = pout, str(r.get("Out_Time", ""))
            info["duration_mins"] = max(info["duration_mins"], dur)
            info["se_flag"] = info["se_flag"] or se
    return out


def overrides_for_employee(overrides_df: pd.DataFrame, emp_code: str) -> tuple[dict, list]:
    """
    Return (day_override_map, week_off_changes).
      day_override_map : {date -> 'SINGLE_ABSENT'|'DOUBLE_ABSENT'|'LONG_LEAVE'}
      week_off_changes : list of WEEK_OFF_CHANGE override dicts
    """
    norm = utils.normalise_emp_code(emp_code)
    day_map: dict = {}
    woc: list = []
    if overrides_df is None or overrides_df.empty:
        return day_map, woc
    for _, r in overrides_df.iterrows():
        if utils.normalise_emp_code(r.get("Emp_Code")) != norm:
            continue
        if not utils.truthy(r.get("Is_Active", "TRUE")):
            continue
        otype = str(r.get("Override_Type", "")).strip()
        start = utils.parse_date(r.get("Override_Date"))
        end = utils.parse_date(r.get("Override_Date_End")) or start
        if otype == "WEEK_OFF_CHANGE":
            woc.append(r.to_dict())
        elif otype == "LONG_LEAVE" and start:
            for d in utils.date_range(start, end):
                day_map[d] = "LONG_LEAVE"
        elif otype in ("SINGLE_ABSENT", "DOUBLE_ABSENT") and start:
            day_map[start] = otype
    return day_map, woc


# --------------------------------------------------------------------------- #
#  Process one employee for a whole month
# --------------------------------------------------------------------------- #
def process_employee_month(employee: dict, month_year: str, bio_df: pd.DataFrame,
                           overrides_df: pd.DataFrame, holidays: set) -> list[eng.DayResult]:
    base = utils.safe_float(employee.get("Base_Salary"))
    calendar_days = utils.calendar_days_in_month(month_year)
    rate = eng.daily_wage_rate(base, calendar_days)
    week_off = (employee.get("Week_Off_Default") or eng.WEEK_OFF_DEFAULT).strip().upper()
    gender = employee.get("Gender", "Male")
    shift_exc = employee.get("Shift_Exception", "None")
    emp_code = employee.get("Emp_Code")

    bio = biometric_by_date(bio_df, emp_code)
    day_map, woc = overrides_for_employee(overrides_df, emp_code)

    results = []
    for d in utils.dates_in_month(month_year):
        day_type = eng.determine_day_type(d, week_off, holidays, woc)
        mo = day_map.get(d)
        b = bio.get(d, {})
        # Trust the biometric's own week-off marking when present (WO / WOP /
        # ½P(WO)) — makes week-offs correct for every location (KN Mondays,
        # Warehouse weekends, ...) instead of assuming Monday. Manual overrides
        # still win (handled inside classify_day).
        raw_status = str(b.get("raw_status", "")).upper()
        if "WO" in raw_status and mo is None and day_type != "HOLIDAY":
            day_type = "WEEK_OFF"
        res = eng.classify_day(
            d=d, gender=gender, shift_exception=shift_exc, day_type=day_type,
            daily_rate=rate,
            punch_in_min=b.get("punch_in_min"), punch_out_min=b.get("punch_out_min"),
            duration_mins=b.get("duration_mins", 0), raw_status=b.get("raw_status", ""),
            single_entry_flag=b.get("se_flag", False), manual_override=mo,
            punch_in_str=b.get("in_str", ""), punch_out_str=b.get("out_str", ""),
        )
        results.append(res)
    return results


def process_location_month(employees_df: pd.DataFrame, month_year: str, bio_df: pd.DataFrame,
                           overrides_df: pd.DataFrame, holidays: set,
                           active_only: bool = True) -> dict:
    """Return {emp_code: (employee_dict, [DayResult, ...])} for all employees."""
    out = {}
    for _, emp in employees_df.iterrows():
        if active_only and not utils.truthy(emp.get("Is_Active", "TRUE")):
            continue
        emp_d = emp.to_dict()
        out[str(emp_d.get("Emp_Code"))] = (
            emp_d, process_employee_month(emp_d, month_year, bio_df, overrides_df, holidays))
    return out


# --------------------------------------------------------------------------- #
#  Convenience roll-ups for pages
# --------------------------------------------------------------------------- #
def attendance_rows(employee: dict, month_year: str, day_results: list) -> list[dict]:
    return [eng.attendance_row_from_day(employee, month_year, r) for r in day_results]


def single_entry_reviews(employees_df, month_year, bio_df, overrides_df, holidays) -> list[dict]:
    """All SINGLE_ENTRY_REVIEW days across employees, for the review panel."""
    flagged = []
    processed = process_location_month(employees_df, month_year, bio_df, overrides_df, holidays)
    for code, (emp, days) in processed.items():
        for r in days:
            if r.final_status == "SINGLE_ENTRY_REVIEW":
                flagged.append({
                    "Emp_Code": emp.get("Emp_Code"), "Emp_Name": emp.get("Emp_Name"),
                    "Attendance_Date": r.attendance_date, "In_Time": r.punch_in,
                    "Out_Time": r.punch_out, "Duration_Mins": r.duration_mins,
                    "Current": r.final_status,
                })
    return flagged
