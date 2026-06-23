"""
End-to-end smoke test: seed -> local DB -> process May 2026 -> payroll.
Run:  ./.venv/Scripts/python.exe tools/smoke_payroll.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules import sheets_sync as db          # noqa: E402
from modules import processing, salary_engine as eng, utils  # noqa: E402

MONTH = "05-2026"

db.reset_backend()
print("Backend mode:", db.backend_mode(), "-", db.backend_reason())

emps = db.get_employees("KAMLA NAGAR", active_only=True)
print(f"Employees loaded: {len(emps)}")

bio = db.get_biometric(MONTH, "KAMLA NAGAR")
print(f"Biometric rows: {len(bio)}")

overrides = db.get_overrides(MONTH)
holidays = db.holiday_dates()
comm_map = db.get_commissions_kn(MONTH)

processed = processing.process_location_month(emps, MONTH, bio, overrides, holidays)

print("\n{:<28} {:>7} {:>7} {:>8} {:>9} {:>10}".format(
    "Employee", "Present", "Late", "Nashta", "Net", "Result"))
print("-" * 76)

total_dena = total_lena = 0
for code, (emp, days) in processed.items():
    comm = db.commissions_for(emp, comm_map)
    adv = db.advances_for(code, MONTH)
    rec = eng.build_payroll_record(
        employee=emp, month_year=MONTH, day_results=days, commissions=comm,
        advance_cash=adv["cash"], advance_bank=adv["bank"], bf_previous=0)
    late_days = sum(1 for d in days if d.late_fine > 0)
    print("{:<28} {:>7} {:>7} {:>8} {:>9} {:>10}".format(
        emp["Emp_Name"][:28], rec["Present_Days"], late_days,
        rec["Nashta_Total"], rec["Net_Payable"], rec["Result_Type"]))
    if rec["Result_Type"] == "CASH_DENA":
        total_dena += rec["Cash_Dena_Amount"]
    else:
        total_lena += rec["Lena_Amount"]

print("-" * 76)
print(f"Total Cash Dena: Rs {total_dena:,}   |   Total Lena: Rs {total_lena:,}")
print("\nSMOKE TEST OK" if len(processed) == len(emps) else "SMOKE TEST INCOMPLETE")
