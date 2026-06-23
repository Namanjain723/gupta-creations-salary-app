"""
salary_engine.py
================
Core business-logic engine for Gupta Creations payroll. 100% pure functions —
no Streamlit, no gspread — so every rule is unit-testable in isolation.

Implements, exactly per the master spec:
  * Shift timings (gender + Monday + special exceptions)
  * Late-fine slabs (relative to shift start)
  * Punch-in salary cuts (½ day / ⅓ day) + punch-out early-leave cut
  * Duration-based attendance classification
  * Nashta engine (₹20 − late_fine; can go negative; absent/WO neutral)
  * Daily wage rate = base / CALENDAR days
  * Interest (1% if advance > ₹10,000)
  * Manual overrides (week-off change / single / double absent / long leave)
  * Final payroll assembly (Cash Dena vs Lena, balance-forward carry)

All amounts are rounded to whole rupees, matching the handwritten paper chits.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

from . import utils

# --------------------------------------------------------------------------- #
#  CONFIG  (hard-coded constants — override via set_config() if ever needed)
# --------------------------------------------------------------------------- #
SHIFT_RULES = {
    "default_male":   {"start": "10:30", "end": "21:30"},
    "default_female": {"start": "10:30", "end": "21:00"},
    "monday_male":    {"start": "11:30", "end": "21:30"},
    "monday_female":  {"start": "11:30", "end": "21:00"},
    # Special exceptions (Employee_Master.Shift_Exception)
    "Warehouse":   {"start": "10:30", "end": "21:00", "monday_start": "11:30"},
    "Neha_Munjal": {"start": "10:30", "end": "20:00", "monday_start": "11:30"},
    "Naman_Jain":  {"start": "10:30", "end": "21:00", "monday_start": "11:30"},
    "MDO":         {"start": "10:30", "end": "21:00", "monday_start": "11:30"},
}

WEEK_OFF_DEFAULT = "MON"
NASHTA_BASE = 20

# Late-fine slabs: (inclusive upper bound of late-minutes, fine ₹)
LATE_FINE_SLABS = [(0, 0), (14, 16), (29, 32), (59, 48), (89, 64), (119, 80)]
LATE_FINE_VALUES = [0, 16, 32, 48, 64, 80]

# Duration thresholds (minutes) -> earned fraction of the day
FULL_DAY_MINS = 480     # 8h  -> 1.0
SEMI_DAY_MINS = 360     # 6h  -> 0.75
HALF_DAY_MINS = 240     # 4h  -> 0.5
QUARTER_DAY_MINS = 120  # 2h  -> 0.25  (< 120 -> absent)

# Punch-in salary-cut windows (minutes since midnight)
PIN_1430, PIN_1500 = 870, 900     # 14:30 .. 15:00  -> Half-Day cut (earn 0.5)
PIN_1600, PIN_1900 = 960, 1140    # 16:00 .. 19:00  -> 1/3-Day cut (earn 0.667)

# Early-leave quarter-cut grace: real punch-outs cluster a few minutes before
# close, so only treat it as "left early" if they leave more than this many
# minutes before shift end (and after 19:00). Tunable.
EARLY_LEAVE_GRACE_MIN = 30

INTEREST_THRESHOLD = 10_000
INTEREST_RATE = 0.01

# Earned-fraction -> Final_Status label
_STATUS_BY_EARN = [
    (1.0, "PRESENT"), (0.75, "SEMI_DAY"), (0.667, "THIRD_DAY"),
    (0.5, "HALF_DAY"), (0.25, "QUARTER_DAY"), (0.0, "ABSENT"),
]

PRESENT_STATUSES = {
    "PRESENT", "SEMI_DAY", "THIRD_DAY", "HALF_DAY", "QUARTER_DAY", "EXTRA_PRESENT",
}


# --------------------------------------------------------------------------- #
#  Small rule helpers
# --------------------------------------------------------------------------- #
def resolve_shift(gender: str, shift_exception: str, is_monday: bool) -> tuple[int, int]:
    """Return (shift_start_min, shift_end_min) for this employee on this day."""
    exc = (shift_exception or "None").strip()
    if exc and exc != "None" and exc in SHIFT_RULES:
        rule = SHIFT_RULES[exc]
        start = rule.get("monday_start") if is_monday else rule["start"]
        return utils.time_to_minutes(start), utils.time_to_minutes(rule["end"])

    female = str(gender).strip().lower().startswith("f")
    if is_monday:
        key = "monday_female" if female else "monday_male"
    else:
        key = "default_female" if female else "default_male"
    rule = SHIFT_RULES[key]
    return utils.time_to_minutes(rule["start"]), utils.time_to_minutes(rule["end"])


def calc_late_fine(late_minutes: int) -> int:
    """Late-fine ₹ from minutes late vs shift start. ≥120 late -> ₹0 (cut applies)."""
    if late_minutes is None or late_minutes <= 0:
        return 0
    if late_minutes <= 14:
        return 16
    if late_minutes <= 29:
        return 32
    if late_minutes <= 59:
        return 48
    if late_minutes <= 89:
        return 64
    if late_minutes <= 119:
        return 80
    return 0  # 120+ : salary cut applies instead of a fine


def late_fine_slab_label(fine: int) -> str:
    return f"₹{int(fine)}"


def calc_nashta(final_status: str, late_fine: int) -> int:
    """Daily nashta = ₹20 − late_fine for present days; 0 (neutral) for A / WO."""
    if final_status in ("ABSENT", "WEEK_OFF", "DOUBLE_ABSENT", "HOLIDAY",
                        "SINGLE_ENTRY_REVIEW"):
        return 0
    return NASHTA_BASE - int(late_fine)


def nashta_sign(value: int) -> str:
    return "POSITIVE" if value > 0 else ("NEGATIVE" if value < 0 else "ZERO")


def daily_wage_rate(base_salary: float, calendar_days: int) -> int:
    """Daily rate = round_half_up(base / CALENDAR days)  e.g. 22000/31 -> 710, 20500/31 -> 661."""
    if calendar_days <= 0:
        return 0
    return utils.round_half_up(utils.safe_float(base_salary) / calendar_days)


def raw_daily_rate(base_salary: float, calendar_days: int) -> float:
    """Unrounded daily rate — multiply by day-count BEFORE rounding (per-block precision)."""
    if calendar_days <= 0:
        return 0.0
    return utils.safe_float(base_salary) / calendar_days


def calc_interest(total_advance_outstanding: float) -> int:
    adv = utils.safe_float(total_advance_outstanding)
    if adv <= INTEREST_THRESHOLD:
        return 0
    return utils.round_half_up(adv * INTEREST_RATE)


def _status_for_earn(earn: float) -> str:
    for val, name in _STATUS_BY_EARN:
        if abs(earn - val) < 1e-6 or earn >= val:
            return name
    return "ABSENT"


# --------------------------------------------------------------------------- #
#  Day-type determination (week-off / holiday / working) given overrides
# --------------------------------------------------------------------------- #
def effective_week_off(d, default_off: str, week_off_changes: list[dict]) -> str:
    """
    Return the week-off weekday code in force for date `d`.
    A WEEK_OFF_CHANGE override re-points the off day within its date range.
    """
    for ov in week_off_changes or []:
        start = utils.parse_date(ov.get("Override_Date"))
        end = utils.parse_date(ov.get("Override_Date_End")) or start
        if start and end and start <= d <= end:
            new_day = (ov.get("New_Week_Off_Day") or "").strip().upper()
            if new_day in utils.WEEKDAY_CODES:
                return new_day
    return (default_off or WEEK_OFF_DEFAULT).strip().upper()


def determine_day_type(d, default_off: str, holidays: set,
                       week_off_changes: list[dict]) -> str:
    """Return 'HOLIDAY' / 'WEEK_OFF' / 'WORKING' for a date."""
    if d in (holidays or set()):
        return "HOLIDAY"
    if utils.day_code(d) == effective_week_off(d, default_off, week_off_changes):
        return "WEEK_OFF"
    return "WORKING"


# --------------------------------------------------------------------------- #
#  The core: classify one calendar day for one employee
# --------------------------------------------------------------------------- #
@dataclass
class DayResult:
    attendance_date: str = ""
    day_of_week: str = ""
    day_type: str = "WORKING"
    raw_status: str = ""
    manual_override: str = "None"
    final_status: str = "ABSENT"
    attendance_value: float = 0.0   # earned fraction of the day
    punch_in: str = ""
    punch_out: str = ""
    duration_mins: int = 0
    late_fine: int = 0
    nashta_daily: int = 0
    nashta_sign: str = "ZERO"
    daily_wage_rate: int = 0
    day_deduction: int = 0          # ₹ deducted for this day (attendance-based)
    extra_present_pay: int = 0      # ₹ bonus for working a week-off (WOP)
    single_entry_flag: bool = False
    notes: str = ""


def classify_day(
    *,
    d,
    gender: str,
    shift_exception: str,
    day_type: str,
    daily_rate: int,
    punch_in_min: int | None = None,
    punch_out_min: int | None = None,
    duration_mins: int = 0,
    raw_status: str = "",
    single_entry_flag: bool = False,
    manual_override: str | None = None,   # SINGLE_ABSENT / DOUBLE_ABSENT / LONG_LEAVE
    punch_in_str: str = "",
    punch_out_str: str = "",
) -> DayResult:
    """
    Apply the full daily rule-stack and return a DayResult.

    Priority of rules (highest first):
       manual override  >  punch-in salary cut  >  duration classification
    """
    is_monday = utils.day_code(d) == "MON"
    res = DayResult(
        attendance_date=utils.fmt_date(d),
        day_of_week=utils.day_code(d),
        day_type=day_type,
        raw_status=str(raw_status or ""),
        manual_override=manual_override or "None",
        daily_wage_rate=daily_rate,
        punch_in=punch_in_str,
        punch_out=punch_out_str,
        duration_mins=int(duration_mins or 0),
        single_entry_flag=bool(single_entry_flag),
    )

    # ---- 1. Manual overrides win outright --------------------------------- #
    if manual_override == "DOUBLE_ABSENT":
        res.final_status = "DOUBLE_ABSENT"
        res.attendance_value = -1.0
        res.day_deduction = int(round(daily_rate * 2))
        res.notes = "Manual DOUBLE absent — 2× daily wage deducted"
        return _finish(res)
    if manual_override in ("SINGLE_ABSENT", "LONG_LEAVE"):
        res.final_status = "ABSENT"
        res.attendance_value = 0.0
        res.day_deduction = daily_rate
        res.notes = ("Long-leave day (week-offs not exempt)"
                     if manual_override == "LONG_LEAVE" else "Manual single absent")
        return _finish(res)

    # ---- 2. Holidays (paid, neutral) -------------------------------------- #
    if day_type == "HOLIDAY":
        res.final_status = "HOLIDAY"
        res.attendance_value = 1.0   # paid
        res.notes = "Holiday — paid"
        return _finish(res)

    present = punch_in_min is not None and duration_mins >= 1

    # ---- 3. Week-off handling --------------------------------------------- #
    if day_type == "WEEK_OFF":
        if present and duration_mins >= QUARTER_DAY_MINS:
            # Week-Off-Present (WOP): paid week-off + extra day pay + nashta
            shift_start, shift_end = resolve_shift(gender, shift_exception, is_monday)
            late = (punch_in_min - shift_start) if punch_in_min > shift_start else 0
            fine = calc_late_fine(late)
            if punch_in_min >= PIN_1430:
                fine = 0
            res.final_status = "EXTRA_PRESENT"
            res.attendance_value = 1.0
            res.extra_present_pay = daily_rate
            res.late_fine = fine
            res.notes = f"WOP — worked week-off (+₹{daily_rate} extra day pay)"
            return _finish(res)
        res.final_status = "WEEK_OFF"
        res.attendance_value = 1.0   # paid as part of base
        res.notes = "Week off"
        return _finish(res)

    # ---- 4. Single-entry review (SE flag, ~1 min) ------------------------- #
    if single_entry_flag and duration_mins < QUARTER_DAY_MINS:
        res.final_status = "SINGLE_ENTRY_REVIEW"
        res.attendance_value = 0.0
        res.day_deduction = daily_rate   # default-absent until admin reviews
        res.notes = "Single punch (SE) — defaults to ABSENT, awaiting admin review"
        return _finish(res)

    # ---- 5. Plain absent -------------------------------------------------- #
    if not present or duration_mins < QUARTER_DAY_MINS:
        res.final_status = "ABSENT"
        res.attendance_value = 0.0
        res.day_deduction = daily_rate
        res.notes = "Absent (no/short punch)"
        return _finish(res)

    # ---- 6. Present working day — fines, cuts, classification ------------- #
    shift_start, shift_end = resolve_shift(gender, shift_exception, is_monday)
    late_minutes = (punch_in_min - shift_start) if punch_in_min > shift_start else 0
    fine = calc_late_fine(late_minutes)

    # punch-in salary cut (overrides duration classification)
    pin_earn = None
    if PIN_1430 <= punch_in_min <= PIN_1500:
        pin_earn = 0.5
    elif PIN_1600 <= punch_in_min <= PIN_1900:
        pin_earn = 0.667
    if punch_in_min >= PIN_1430:
        fine = 0  # salary cut takes precedence over fine

    # duration classification
    if duration_mins >= FULL_DAY_MINS:
        dur_earn = 1.0
    elif duration_mins >= SEMI_DAY_MINS:
        dur_earn = 0.75
    elif duration_mins >= HALF_DAY_MINS:
        dur_earn = 0.5
    else:
        dur_earn = 0.25

    earn = pin_earn if pin_earn is not None else dur_earn

    # punch-out early-leave cut: left meaningfully before shift end (beyond the
    # grace window) but after 19:00 -> earn capped at 0.75 (¼-day cut)
    early_note = ""
    if (punch_out_min is not None
            and PIN_1900 < punch_out_min < shift_end - EARLY_LEAVE_GRACE_MIN):
        if earn > 0.75:
            earn = 0.75
            early_note = " | left early (after 19:00) — ¼ day cut"

    earn = round(earn, 3)
    res.final_status = _status_for_earn(earn)
    res.attendance_value = earn
    res.late_fine = fine
    res.day_deduction = int(round(daily_rate * (1 - earn)))

    bits = []
    if late_minutes > 0 and fine > 0:
        bits.append(f"{late_minutes} min late → ₹{fine} fine")
    elif punch_in_min >= PIN_1430:
        bits.append("very late → salary cut (no fine)")
    else:
        bits.append("on time +₹20")
    if earn < 1.0:
        bits.append(f"earned {earn:g} day")
    res.notes = "; ".join(bits) + early_note
    return _finish(res)


def _finish(res: DayResult) -> DayResult:
    """Compute nashta + sign once the status/fine are settled."""
    res.nashta_daily = calc_nashta(res.final_status, res.late_fine)
    res.nashta_sign = nashta_sign(res.nashta_daily)
    return res


# --------------------------------------------------------------------------- #
#  Cut-line grouping + monthly attendance roll-up
# --------------------------------------------------------------------------- #
def _cut_fraction(r: DayResult) -> float:
    """Deduction fraction for a day: 0=full pay, 0.25/0.5/0.75 partial, 1=absent, 2=double."""
    if r.final_status == "DOUBLE_ABSENT":
        return 2.0
    if r.final_status == "EXTRA_PRESENT":
        return 0.0
    if r.day_type in ("WEEK_OFF", "HOLIDAY"):
        return 0.0
    if r.final_status in ("ABSENT", "SINGLE_ENTRY_REVIEW"):
        return 1.0
    return round(max(0.0, 1.0 - r.attendance_value), 3)


_CUT_LABELS = {2.0: "AA", 1.0: "A", 0.75: "3/4", 0.667: "1/3", 0.5: "1/2", 0.333: "1/3", 0.25: "1/4"}


def _cut_label(frac: float) -> str:
    return _CUT_LABELS.get(round(frac, 3), f"{frac:g}")


def group_cut_lines(day_results: list[DayResult], raw_daily: float) -> list[dict]:
    """
    Collapse runs of consecutive days with the SAME deduction-fraction into one
    block, billed as round_half_up(raw_daily * fraction * days) — ONE rounding
    per block. Reproduces the clerk's exact maths (8-day=7226, 9-day=6010).
    """
    lines: list[dict] = []
    run = None
    for r in day_results:
        frac = _cut_fraction(r)
        if frac <= 0:
            if run:
                lines.append(run)
                run = None
            continue
        if run and abs(run["frac"] - frac) < 1e-6:
            run["days"] += 1
            run["end"] = r.attendance_date
        else:
            if run:
                lines.append(run)
            run = {"frac": frac, "days": 1, "start": r.attendance_date,
                   "end": r.attendance_date, "status": r.final_status}
    if run:
        lines.append(run)
    for ln in lines:
        ln["amount"] = utils.round_half_up(raw_daily * ln["frac"] * ln["days"])
        ln["label"] = _cut_label(ln["frac"])
    return lines


def rollup_attendance(day_results: list[DayResult], raw_daily: float) -> dict:
    """Aggregate a month of DayResults into the totals + dated lines a slip needs."""
    cut_lines = group_cut_lines(day_results, raw_daily)
    daily = utils.round_half_up(raw_daily)
    extra_present_lines = [{"date": r.attendance_date, "amount": daily}
                           for r in day_results if r.final_status == "EXTRA_PRESENT"]
    return {
        "absent_deduction": sum(l["amount"] for l in cut_lines),
        "late_fine_total": sum(r.late_fine for r in day_results),
        "monthly_nashta": sum(r.nashta_daily for r in day_results),
        "extra_present_pay": sum(l["amount"] for l in extra_present_lines),
        "present_days": sum(1 for r in day_results if r.final_status in PRESENT_STATUSES),
        "extra_present_days": len(extra_present_lines),
        "cut_lines": cut_lines,
        "extra_present_lines": extra_present_lines,
    }


# --------------------------------------------------------------------------- #
#  Monthly aggregation -> a Payroll_Final record (verified real-slip formula)
# --------------------------------------------------------------------------- #
def build_payroll_record(
    *,
    employee: dict,
    month_year: str,
    day_results: list[DayResult] | None = None,
    attendance: dict | None = None,         # pre-computed roll-up (else from day_results)
    commissions: dict | None = None,
    advance_cash: float = 0,
    advance_bank: float = 0,
    jama: float = 0,
    hdfc: float = 0,                         # bank-transferred portion of this month's pay
    interest: float = 0,
    bf_previous: float = 0,
    tg_bonus_override: float | None = None,
    nashta_enabled: bool = False,
    payroll_id: int = 0,
    run_date: str = "",
    cfg: dict | None = None,
) -> dict:
    """
    Assemble one Payroll_Final row using the verified real-slip formula.

      EARNINGS         = base + S/B/L_Com + TG + extra-present (+nashta if enabled)
                         (EXCLUDES B/F, Advance_Cash, Jama)
      SALARY_DEDUCTIONS= EPF + ESIC + Interest + cuts + L-Fine + Advance_Bank
      Dena (Net)       = EARNINGS - SALARY_DEDUCTIONS
      Permanent  : Cash_Dena = Dena - HDFC ; Lena = B/F + Advance_Cash - Jama (carry)
      Non-permanent: Dena also subtracts Advance_Cash; no EPF/ESIC/B-F;
                     Dena<0 -> Lena = -Dena, Cash_Dena = 0
    """
    commissions = commissions or {}
    base = utils.safe_float(employee.get("Base_Salary"))
    calendar_days = utils.calendar_days_in_month(month_year)
    raw_daily = raw_daily_rate(base, calendar_days)
    rate = utils.round_half_up(raw_daily)
    is_permanent = utils.truthy(employee.get("Is_Permanent", "TRUE"))

    if attendance is None:
        attendance = rollup_attendance(day_results or [], raw_daily)
    absent_deduction = utils.round_half_up(attendance.get("absent_deduction", 0))
    late_fine_total = utils.round_half_up(attendance.get("late_fine_total", 0))
    monthly_nashta = int(attendance.get("monthly_nashta", 0))
    extra_present_pay = utils.round_half_up(attendance.get("extra_present_pay", 0))
    present_days = int(attendance.get("present_days", 0))
    extra_present_days = int(attendance.get("extra_present_days", 0))

    s_com = utils.safe_float(commissions.get("s_com"))
    b_com = utils.safe_float(commissions.get("b_com"))
    l_com = utils.safe_float(commissions.get("l_com"))
    tg_bonus = (utils.safe_float(tg_bonus_override) if tg_bonus_override is not None
                else utils.safe_float(employee.get("TG_Ladies_Bonus")))

    # The slip shows ONE "L Fine" line. With nashta ON it is the net-negative
    # nashta and any positive nashta becomes earnings; with nashta OFF (default,
    # matching the real chits) it is simply the summed late fines.
    if nashta_enabled:
        nashta_earning = monthly_nashta if monthly_nashta > 0 else 0
        fine_line = abs(monthly_nashta) if monthly_nashta < 0 else 0
        nashta_result = "EARNING" if monthly_nashta > 0 else ("DEDUCTION" if monthly_nashta < 0 else "ZERO")
    else:
        nashta_earning, fine_line, nashta_result = 0, late_fine_total, "ZERO"

    advance_cash = utils.round_half_up(advance_cash)
    advance_bank = utils.round_half_up(advance_bank)
    jama = utils.round_half_up(jama)
    hdfc = utils.round_half_up(hdfc)
    bf_previous = utils.round_half_up(bf_previous)
    interest = utils.round_half_up(interest)
    epf = utils.round_half_up(employee.get("EPF")) if is_permanent else 0
    esic = utils.round_half_up(employee.get("ESIC")) if is_permanent else 0

    earnings = (utils.round_half_up(base) + utils.round_half_up(s_com) + utils.round_half_up(b_com)
                + utils.round_half_up(l_com) + utils.round_half_up(tg_bonus)
                + extra_present_pay + nashta_earning)
    salary_ded = epf + esic + interest + absent_deduction + fine_line + advance_bank
    dena = earnings - salary_ded

    if not is_permanent:
        dena -= advance_cash       # casual staff net cash advances in-month
        lena_balance = 0
    else:
        lena_balance = bf_previous + advance_cash - jama   # running loan carry

    if dena >= 0:
        result_type = "CASH_DENA"
        net_payable = dena
        cash_dena = dena - hdfc
        hdfc_amt = hdfc
        lena_amount = max(0, lena_balance)
    else:
        result_type = "LENA"
        net_payable = dena
        cash_dena = 0
        hdfc_amt = 0
        lena_amount = max(0, lena_balance) + abs(dena)

    total_deductions = salary_ded + (advance_cash if not is_permanent else 0)
    earned_salary = utils.round_half_up(base) - absent_deduction
    attendance_fraction = round(earned_salary / base, 4) if base else 0.0

    rec = {
        "Payroll_ID": payroll_id,
        "Month_Year": month_year,
        "Run_Date": run_date or utils.now_ist_iso(),
        "Emp_Code": employee.get("Emp_Code", ""),
        "Emp_Name": employee.get("Emp_Name", ""),
        "Is_Permanent": "TRUE" if is_permanent else "FALSE",
        "Base_Salary": utils.round_half_up(base),
        "Calendar_Days": calendar_days,
        "Daily_Rate": rate,
        "Present_Days": present_days,
        "Extra_Present_Days": extra_present_days,
        "Attendance_Fraction": attendance_fraction,
        "Earned_Salary": earned_salary,
        "S_Com": utils.round_half_up(s_com),
        "B_Com": utils.round_half_up(b_com),
        "L_Com": utils.round_half_up(l_com),
        "TG_Bonus": utils.round_half_up(tg_bonus),
        "Extra_Present_Pay": extra_present_pay,
        "Nashta_Total": monthly_nashta,
        "Nashta_Result": nashta_result,
        "BF_From_Previous": bf_previous,
        "Gross_Earnings": earnings,
        "EPF": epf,
        "ESIC": esic,
        "Late_Fine_Total": fine_line,
        "Nashta_Deduction": fine_line if nashta_enabled else 0,
        "Advance_Cash_Total": advance_cash,
        "Advance_Bank_Total": advance_bank,
        "Jama_Total": jama,
        "Interest": interest,
        "Absent_Deduction": absent_deduction,
        "Total_Deductions": total_deductions,
        "Dena_Amount": net_payable,
        "Net_Payable": net_payable,
        "HDFC_Amount": hdfc_amt,
        "Result_Type": result_type,
        "Cash_Dena_Amount": cash_dena,
        "Lena_Amount": lena_amount,
        "Bank_Account": employee.get("Bank_Account_Number") or employee.get("Account_Number", ""),
        "Slip_Generated": "FALSE",
        "Notes": "",
    }
    # non-column extras the slip renderer uses (dropped on sheet write)
    rec["_cut_lines"] = attendance.get("cut_lines", [])
    rec["_extra_present_lines"] = attendance.get("extra_present_lines", [])
    return rec


def attendance_row_from_day(emp: dict, month_year: str, r: DayResult) -> dict:
    """Map a DayResult to an Attendance_Processed sheet row (dict)."""
    return {
        "Month_Year": month_year,
        "Emp_Code": emp.get("Emp_Code", ""),
        "Emp_Name": emp.get("Emp_Name", ""),
        "Attendance_Date": r.attendance_date,
        "Day_Type": r.day_type,
        "Raw_Status": r.raw_status,
        "Manual_Override": r.manual_override,
        "Override_Applied_By": "",
        "Final_Status": r.final_status,
        "Attendance_Value": r.attendance_value,
        "Punch_In": r.punch_in,
        "Punch_Out": r.punch_out,
        "Duration_Mins": r.duration_mins,
        "Late_Fine_Amount": r.late_fine,
        "Nashta_Daily": r.nashta_daily,
        "Nashta_Sign": r.nashta_sign,
        "Daily_Wage_Rate": r.daily_wage_rate,
        "Day_Deduction": r.day_deduction,
        "Notes": r.notes,
    }


def nashta_summary_row(emp: dict, month_year: str, day_results: list[DayResult]) -> dict:
    """Build one Nashta_Monthly_Summary row from a month of DayResults."""
    counts = {0: 0, 16: 0, 32: 0, 48: 0, 64: 0, 80: 0}
    present = ontime = 0
    pos = neg = 0
    for r in day_results:
        if r.final_status in PRESENT_STATUSES:
            present += 1
            counts[r.late_fine] = counts.get(r.late_fine, 0) + 1
            if r.late_fine == 0:
                ontime += 1
        if r.nashta_daily > 0:
            pos += r.nashta_daily
        elif r.nashta_daily < 0:
            neg += r.nashta_daily
    net = pos + neg
    return {
        "Month_Year": month_year,
        "Emp_Code": emp.get("Emp_Code", ""),
        "Emp_Name": emp.get("Emp_Name", ""),
        "Location": emp.get("Location", ""),
        "Total_Present_Days": present,
        "OnTime_Days": ontime,
        "Late_Days_16": counts.get(16, 0),
        "Late_Days_32": counts.get(32, 0),
        "Late_Days_48": counts.get(48, 0),
        "Late_Days_64": counts.get(64, 0),
        "Late_Days_80": counts.get(80, 0),
        "Nashta_Earned_Positive": pos,
        "Nashta_Deducted_Negative": neg,
        "Net_Monthly_Nashta": net,
        "Monthly_Result": "EARNING" if net > 0 else ("DEDUCTION" if net < 0 else "ZERO"),
    }


# --------------------------------------------------------------------------- #
#  Self-check (run `python -m modules.salary_engine`)
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    assert daily_wage_rate(22000, 31) == 710, daily_wage_rate(22000, 31)
    assert calc_late_fine(0) == 0 and calc_late_fine(10) == 16 and calc_late_fine(20) == 32
    assert calc_late_fine(45) == 48 and calc_late_fine(75) == 64 and calc_late_fine(100) == 80
    assert calc_late_fine(125) == 0
    assert calc_nashta("PRESENT", 32) == -12
    assert calc_nashta("ABSENT", 0) == 0
    assert calc_interest(9000) == 0 and calc_interest(12000) == 120
    print("salary_engine self-check passed: 710 rate, fine slabs, nashta, interest OK")
