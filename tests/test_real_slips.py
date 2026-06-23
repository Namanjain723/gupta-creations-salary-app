"""
GOLDEN regression — the 7 real handwritten/printed salary slips (May-2026,
paid 07-06-26). These lock the verified formula to the rupee. If any of these
fail, the digital slip no longer matches the paper chit. ALKA is excluded
(handwritten, does not reconcile cleanly).

Verified by 3 independent agents: Dena = EARNINGS - SALARY_DEDUCTIONS (excl
B/F, Advance_Cash, Jama); Cash Dena = Dena - HDFC; Lena = B/F + Advance_Cash
- Jama (permanent); non-permanent nets cash advance in-month.
"""
from datetime import date, timedelta

from modules import salary_engine as eng
from modules import utils


def _rec(*, base, epf=0, esic=0, permanent=True, s=0, b=0, l=0, tg=0,
         extra_present=0, extra_present_days=0, absent=0, late_fine=0,
         interest=0, adv_cash=0, adv_bank=0, jama=0, bf=0, hdfc=0):
    emp = {"Emp_Code": "X", "Emp_Name": "T", "Base_Salary": base, "EPF": epf,
           "ESIC": esic, "Is_Permanent": "TRUE" if permanent else "FALSE",
           "TG_Ladies_Bonus": 0}
    attendance = {"absent_deduction": absent, "late_fine_total": late_fine,
                  "monthly_nashta": 0, "extra_present_pay": extra_present,
                  "present_days": 26, "extra_present_days": extra_present_days,
                  "cut_lines": [], "extra_present_lines": []}
    return eng.build_payroll_record(
        employee=emp, month_year="05-2026", attendance=attendance,
        commissions={"s_com": s, "b_com": b, "l_com": l},
        tg_bonus_override=(tg or None), advance_cash=adv_cash, advance_bank=adv_bank,
        jama=jama, hdfc=hdfc, interest=interest, bf_previous=bf, nashta_enabled=False)


def test_slip_pradeep_pk():
    r = _rec(base=20500, epf=1800, esic=144, s=1547, b=111,
             extra_present=1322, extra_present_days=2, absent=2975, hdfc=17233)
    assert r["Dena_Amount"] == 18561
    assert r["Cash_Dena_Amount"] == 1328
    assert r["Lena_Amount"] == 0


def test_slip_vinod_vn():
    r = _rec(base=20600, epf=1800, esic=155, s=1809, extra_present=665,
             extra_present_days=1, hdfc=18645)
    assert r["Dena_Amount"] == 21119
    assert r["Cash_Dena_Amount"] == 2474


def test_slip_sandeep():
    r = _rec(base=18500, epf=1800, esic=139, extra_present=1791, extra_present_days=3,
             absent=1194, interest=193, adv_cash=10000, adv_bank=5000, jama=5000,
             bf=20000, hdfc=11561)
    assert r["Dena_Amount"] == 11965
    assert r["Cash_Dena_Amount"] == 404
    assert r["Lena_Amount"] == 25000


def test_slip_rakesh_rj():
    r = _rec(base=23300, epf=1800, esic=0, s=2653, b=165, l=856, absent=752,
             interest=120, late_fine=293, adv_bank=8000, jama=8000, bf=22000, hdfc=12748)
    assert r["Dena_Amount"] == 16009
    assert r["Cash_Dena_Amount"] == 3261
    assert r["Lena_Amount"] == 14000


def test_slip_avdhesh_av():
    r = _rec(base=28000, epf=1593, esic=0, s=2312, tg=1915, extra_present=903,
             extra_present_days=1, absent=9258, interest=560, adv_cash=20000,
             adv_bank=11000, jama=11000, bf=46000, hdfc=6374)
    assert r["Dena_Amount"] == 10719
    assert r["Cash_Dena_Amount"] == 4345
    assert r["Lena_Amount"] == 55000


def test_slip_amit_at_non_permanent():
    r = _rec(base=18000, permanent=False, s=1086, b=376, extra_present=581,
             extra_present_days=1, absent=2177, interest=23, adv_cash=20000)
    assert r["Result_Type"] == "LENA"
    assert r["Cash_Dena_Amount"] == 0
    assert r["Lena_Amount"] == 2157
    assert r["EPF"] == 0 and r["ESIC"] == 0   # non-permanent: no statutory


def test_slip_ankit_am():
    r = _rec(base=20700, epf=1504, esic=106, s=1223, extra_present=668,
             extra_present_days=1, absent=7012, interest=595, adv_bank=10000,
             jama=10000, bf=69500, hdfc=2412)
    assert r["Dena_Amount"] == 3374
    assert r["Cash_Dena_Amount"] == 962
    assert r["Lena_Amount"] == 59500


# --------------------------------------------------------------------------- #
#  Rounding + per-block cut grouping (the precision the verifiers flagged)
# --------------------------------------------------------------------------- #
def test_round_half_up():
    assert utils.round_half_up(330.5) == 331        # PK half-day (banker's gives 330)
    assert utils.round_half_up(28000 / 31 * 8) == 7226   # AVDHESH 8-day block
    assert utils.round_half_up(20700 / 31 * 9) == 6010   # ANKIT 9-day block
    assert utils.round_half_up(20500 / 31) == 661


def _absent_days(base, n, start=date(2026, 5, 9)):
    days = []
    for i in range(n):
        d = start + timedelta(days=i)
        days.append(eng.DayResult(attendance_date=utils.fmt_date(d), day_type="WORKING",
                                  final_status="ABSENT", attendance_value=0.0))
    return days


def test_group_cut_lines_block_rounding():
    raw = 28000 / 31
    lines = eng.group_cut_lines(_absent_days(28000, 8), raw)
    assert len(lines) == 1 and lines[0]["days"] == 8 and lines[0]["amount"] == 7226
    raw2 = 20700 / 31
    lines2 = eng.group_cut_lines(_absent_days(20700, 9), raw2)
    assert lines2[0]["amount"] == 6010      # NOT 9*668=6012


def test_group_cut_lines_splits_on_gap():
    """Two absent days separated by a present day -> two separate runs."""
    raw = 28000 / 31
    days = _absent_days(28000, 1, date(2026, 5, 18))
    days.append(eng.DayResult(attendance_date="20/05/2026", day_type="WORKING",
                              final_status="PRESENT", attendance_value=1.0))
    days += _absent_days(28000, 1, date(2026, 5, 27))
    lines = eng.group_cut_lines(days, raw)
    assert len(lines) == 2
    assert sum(l["amount"] for l in lines) == 1806   # 903 + 903 (AVDHESH 18 & 27)
