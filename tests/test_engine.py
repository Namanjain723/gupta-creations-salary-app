"""
Engine correctness tests — these encode the master-spec examples verbatim.
If any of these fail, the payroll will NOT match the paper chits.
"""
import pandas as pd

from modules import salary_engine as eng
from modules import processing
from modules import utils


# --------------------------------------------------------------------------- #
#  Daily rate / fines / interest
# --------------------------------------------------------------------------- #
def test_daily_rate_matches_paper_chit():
    assert eng.daily_wage_rate(22000, 31) == 710      # spec: 22000/31 -> 710
    assert eng.daily_wage_rate(18000, 31) == 581
    assert eng.daily_wage_rate(22000, 30) == 733


def test_late_fine_slabs():
    assert eng.calc_late_fine(0) == 0
    assert eng.calc_late_fine(1) == 16 and eng.calc_late_fine(14) == 16
    assert eng.calc_late_fine(15) == 32 and eng.calc_late_fine(29) == 32
    assert eng.calc_late_fine(30) == 48 and eng.calc_late_fine(59) == 48
    assert eng.calc_late_fine(60) == 64 and eng.calc_late_fine(89) == 64
    assert eng.calc_late_fine(90) == 80 and eng.calc_late_fine(119) == 80
    assert eng.calc_late_fine(120) == 0   # 120+ : salary cut instead of fine
    assert eng.calc_late_fine(200) == 0


def test_commission_scaling():
    """Default = full rupees (live sheet & slips); ×100 only for the raw KN report."""
    from modules import sheets_sync as db
    # default scale 1 — commissions are entered in rupees (PK 1547, RJ 2653)
    assert db.commission_to_rupees("1547") == 1547
    assert db.commission_to_rupees("2653") == 2653
    assert db.commission_to_rupees(0) == 0 and db.commission_to_rupees("") == 0
    # opt-in ×100 mode for importing the raw decimal KN export
    assert db.commission_to_rupees("28.30", scale=100) == 2830
    assert db.commission_to_rupees("8.56", scale=100) == 856


def test_interest_engine():
    assert eng.calc_interest(10000) == 0
    assert eng.calc_interest(9999) == 0
    assert eng.calc_interest(12000) == 120
    assert eng.calc_interest(25000) == 250


def test_nashta_daily():
    assert eng.calc_nashta("PRESENT", 0) == 20      # on time
    assert eng.calc_nashta("PRESENT", 16) == 4      # small positive
    assert eng.calc_nashta("PRESENT", 32) == -12    # goes negative
    assert eng.calc_nashta("PRESENT", 48) == -28
    assert eng.calc_nashta("PRESENT", 80) == -60
    assert eng.calc_nashta("ABSENT", 0) == 0        # neutral
    assert eng.calc_nashta("WEEK_OFF", 0) == 0      # neutral


def test_monthly_nashta_example_408():
    """Spec example: 22 on-time + 2x16-fine + 1x32-fine + 1x48-fine = +408."""
    days = []
    days += [eng.DayResult(final_status="PRESENT", late_fine=0, nashta_daily=eng.calc_nashta("PRESENT", 0)) for _ in range(22)]
    days += [eng.DayResult(final_status="PRESENT", late_fine=16, nashta_daily=eng.calc_nashta("PRESENT", 16)) for _ in range(2)]
    days += [eng.DayResult(final_status="PRESENT", late_fine=32, nashta_daily=eng.calc_nashta("PRESENT", 32)) for _ in range(1)]
    days += [eng.DayResult(final_status="PRESENT", late_fine=48, nashta_daily=eng.calc_nashta("PRESENT", 48)) for _ in range(1)]
    total = sum(d.nashta_daily for d in days)
    assert total == 408


# --------------------------------------------------------------------------- #
#  Shift resolution
# --------------------------------------------------------------------------- #
def test_shift_resolution():
    # Male, normal day -> 10:30 start
    assert eng.resolve_shift("Male", "None", False)[0] == utils.time_to_minutes("10:30")
    # Male, Monday -> 11:30 start
    assert eng.resolve_shift("Male", "None", True)[0] == utils.time_to_minutes("11:30")
    # Female, normal -> end 21:00
    assert eng.resolve_shift("Female", "None", False)[1] == utils.time_to_minutes("21:00")
    # Neha_Munjal exception -> end 20:00
    assert eng.resolve_shift("Female", "Neha_Munjal", False)[1] == utils.time_to_minutes("20:00")


# --------------------------------------------------------------------------- #
#  classify_day behaviours
# --------------------------------------------------------------------------- #
def _present(d, pin, dur=600, **kw):
    return eng.classify_day(d=d, gender="Male", shift_exception="None",
                            day_type="WORKING", daily_rate=710,
                            punch_in_min=utils.time_to_minutes(pin), duration_mins=dur,
                            punch_in_str=pin, **kw)


def test_on_time_full_day():
    r = _present("02/05/2026", "10:25")   # before 10:30 -> on time
    assert r.final_status == "PRESENT"
    assert r.attendance_value == 1.0
    assert r.late_fine == 0
    assert r.nashta_daily == 20
    assert r.day_deduction == 0


def test_late_17min_fine_32_nashta_neg12():
    r = _present("02/05/2026", "10:47")   # 17 min late -> ₹32
    assert r.late_fine == 32
    assert r.nashta_daily == -12
    assert r.final_status == "PRESENT"


def test_monday_late_uses_1130_start():
    # 4 May 2026 is Monday: start 11:30; arriving 11:40 = 10 min late -> ₹16
    r = _present("04/05/2026", "11:40")
    assert r.late_fine == 16
    assert r.nashta_daily == 4


def test_absent_short_duration():
    r = eng.classify_day(d="02/05/2026", gender="Male", shift_exception="None",
                         day_type="WORKING", daily_rate=710,
                         punch_in_min=utils.time_to_minutes("10:30"), duration_mins=30)
    assert r.final_status == "ABSENT"
    assert r.day_deduction == 710
    assert r.nashta_daily == 0


def test_half_day_punch_in_cut():
    # punch-in 14:45 -> Half-Day cut (earn 0.5), late fine overridden to 0
    r = _present("02/05/2026", "14:45", dur=300)
    assert r.attendance_value == 0.5
    assert r.final_status == "HALF_DAY"
    assert r.late_fine == 0
    assert r.day_deduction == 355   # 710 * 0.5


def test_third_day_punch_in_cut():
    # punch-in 16:30 -> 1/3-Day cut (earn 0.667)
    r = _present("02/05/2026", "16:30", dur=200)
    assert r.attendance_value == 0.667
    assert r.final_status == "THIRD_DAY"
    assert r.late_fine == 0


def test_single_entry_review_defaults_absent():
    r = eng.classify_day(d="02/05/2026", gender="Male", shift_exception="None",
                         day_type="WORKING", daily_rate=710,
                         punch_in_min=utils.time_to_minutes("10:30"), duration_mins=1,
                         single_entry_flag=True)
    assert r.final_status == "SINGLE_ENTRY_REVIEW"
    assert r.day_deduction == 710


def test_week_off_paid_neutral():
    r = eng.classify_day(d="04/05/2026", gender="Male", shift_exception="None",
                         day_type="WEEK_OFF", daily_rate=710)
    assert r.final_status == "WEEK_OFF"
    assert r.day_deduction == 0
    assert r.nashta_daily == 0
    assert r.attendance_value == 1.0   # paid


def test_week_off_present_wop():
    r = eng.classify_day(d="04/05/2026", gender="Male", shift_exception="None",
                         day_type="WEEK_OFF", daily_rate=710,
                         punch_in_min=utils.time_to_minutes("11:25"), duration_mins=600)
    assert r.final_status == "EXTRA_PRESENT"
    assert r.extra_present_pay == 710
    assert r.day_deduction == 0


def test_double_absent_override():
    r = eng.classify_day(d="02/05/2026", gender="Male", shift_exception="None",
                         day_type="WORKING", daily_rate=710, manual_override="DOUBLE_ABSENT")
    assert r.final_status == "DOUBLE_ABSENT"
    assert r.day_deduction == 1420   # 2 x 710


def test_long_leave_includes_week_off():
    # LONG_LEAVE override on a week-off day still deducts (no exemption)
    r = eng.classify_day(d="04/05/2026", gender="Male", shift_exception="None",
                         day_type="WEEK_OFF", daily_rate=710, manual_override="LONG_LEAVE")
    assert r.final_status == "ABSENT"
    assert r.day_deduction == 710


# --------------------------------------------------------------------------- #
#  Day-type / week-off change
# --------------------------------------------------------------------------- #
def test_determine_day_type_default_monday_off():
    d = utils.parse_date("04/05/2026")   # Monday
    assert eng.determine_day_type(d, "MON", set(), []) == "WEEK_OFF"
    d2 = utils.parse_date("05/05/2026")  # Tuesday
    assert eng.determine_day_type(d2, "MON", set(), []) == "WORKING"


def test_week_off_change_override():
    woc = [{"Override_Date": "01/05/2026", "Override_Date_End": "31/05/2026",
            "New_Week_Off_Day": "WED"}]
    mon = utils.parse_date("04/05/2026")   # was off -> now WORKING
    wed = utils.parse_date("06/05/2026")   # Wednesday -> now WEEK_OFF
    assert eng.determine_day_type(mon, "MON", set(), woc) == "WORKING"
    assert eng.determine_day_type(wed, "MON", set(), woc) == "WEEK_OFF"


# --------------------------------------------------------------------------- #
#  Payroll record — verified real-slip model (see tests/test_real_slips.py for
#  the to-the-rupee golden cases; these check the structural rules)
# --------------------------------------------------------------------------- #
def test_payroll_permanent_advance_goes_to_lena_not_dena():
    """Permanent: a cash advance is a loan (Lena), NOT a deduction from salary."""
    emp = {"Emp_Code": "27", "Emp_Name": "BM", "Base_Salary": 22000, "EPF": 1800,
           "ESIC": 130, "Is_Permanent": "TRUE", "TG_Ladies_Bonus": 0}
    att = {"absent_deduction": 0, "late_fine_total": 0, "monthly_nashta": 0,
           "extra_present_pay": 0, "present_days": 27, "extra_present_days": 0}
    rec = eng.build_payroll_record(
        employee=emp, month_year="05-2026", attendance=att,
        commissions={"s_com": 1980, "b_com": 301}, advance_cash=5000, bf_previous=0)
    # Dena = 22000+1980+301 - (1800+130) = 22351 ; cash advance does NOT reduce it
    assert rec["Dena_Amount"] == 22351
    assert rec["Cash_Dena_Amount"] == 22351      # no HDFC set
    assert rec["Lena_Amount"] == 5000            # the advance becomes the loan carry


def test_payroll_hdfc_splits_dena_into_bank_and_cash():
    emp = {"Emp_Code": "27", "Base_Salary": 22000, "EPF": 1800, "ESIC": 130,
           "Is_Permanent": "TRUE"}
    att = {"absent_deduction": 0, "monthly_nashta": 0, "extra_present_pay": 0,
           "present_days": 27, "extra_present_days": 0, "late_fine_total": 0}
    rec = eng.build_payroll_record(employee=emp, month_year="05-2026", attendance=att, hdfc=15000)
    assert rec["Dena_Amount"] == 20070           # 22000-1800-130
    assert rec["HDFC_Amount"] == 15000
    assert rec["Cash_Dena_Amount"] == 5070       # Dena - HDFC


def test_payroll_nonpermanent_no_statutory_and_nets_advance():
    """Non-permanent: no EPF/ESIC; cash advance nets in-month; negative -> Lena."""
    emp = {"Emp_Code": "9", "Base_Salary": 18000, "EPF": 1800, "ESIC": 130,
           "Is_Permanent": "FALSE", "TG_Ladies_Bonus": 0}
    att = {"absent_deduction": 16000, "monthly_nashta": 0, "extra_present_pay": 0,
           "present_days": 5, "extra_present_days": 0, "late_fine_total": 0}
    rec = eng.build_payroll_record(employee=emp, month_year="05-2026", attendance=att,
                                   advance_cash=5000)
    assert rec["EPF"] == 0 and rec["ESIC"] == 0
    # 18000 - 16000 - 5000 = -3000 -> Lena
    assert rec["Result_Type"] == "LENA"
    assert rec["Lena_Amount"] == 3000
    assert rec["Cash_Dena_Amount"] == 0


# --------------------------------------------------------------------------- #
#  End-to-end: process a month from biometric rows
# --------------------------------------------------------------------------- #
def test_process_employee_month_end_to_end():
    emp = {"Emp_Code": "27", "Emp_Name": "VIJAY KUMAR", "Gender": "Male",
           "Shift_Exception": "None", "Base_Salary": 22000, "Week_Off_Default": "MON"}
    # two working days punched: one on time, one 17-min late
    bio = pd.DataFrame([
        {"Emp_Code": "27", "Attendance_Date": "02/05/2026", "In_Time": "10:25:00",
         "Out_Time": "21:30:00", "Total_Duration_Mins": "660", "Status_Raw": "P",
         "Single_Entry_Flag": "FALSE"},
        {"Emp_Code": "27", "Attendance_Date": "05/05/2026", "In_Time": "10:47:00",
         "Out_Time": "21:30:00", "Total_Duration_Mins": "640", "Status_Raw": "P",
         "Single_Entry_Flag": "FALSE"},
    ])
    overrides = pd.DataFrame(columns=["Emp_Code", "Override_Type", "Override_Date",
                                      "Override_Date_End", "New_Week_Off_Day", "Is_Active"])
    days = processing.process_employee_month(emp, "05-2026", bio, overrides, set())
    assert len(days) == 31  # full month classified

    by_date = {d.attendance_date: d for d in days}
    assert by_date["02/05/2026"].final_status == "PRESENT"
    assert by_date["02/05/2026"].nashta_daily == 20
    assert by_date["05/05/2026"].late_fine == 32
    assert by_date["05/05/2026"].nashta_daily == -12
    # Mondays (4,11,18,25) are week offs
    assert by_date["04/05/2026"].final_status == "WEEK_OFF"
    # un-punched working days are absent
    assert by_date["06/05/2026"].final_status == "ABSENT"
