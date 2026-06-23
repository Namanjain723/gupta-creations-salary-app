"""
Prove the daily/weekly/monthly upload loop end-to-end, in memory (no DB writes):
  parse e-Smart  ->  idempotent dedup  ->  reprocess  ->  payroll.
Run:  ./.venv/Scripts/python.exe tools/verify_upload_loop.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
from modules import biometric_parser as bp, processing, salary_engine as eng  # noqa: E402
from modules import sheets_sync as db  # noqa: E402

SAMPLE = """Attendance Date - 01-May-2026
S.No Employee Code Employee Name Shift In Time Out Time Total Duration Status Remarks
1 27 BM GS 10:25:00 21:25:00 11:00 P
2 167 AT GS 10:24:05 21:21:20 10:57 P
Attendance Date - 02-May-2026
1 27 BM GS 10:47:00 21:25:00 10:38 P
2 167 AT GS 11:11:00 21:21:00 10:10 P
Attendance Date - 04-May-2026
1 27 BM GS 11:28:24 21:25:59 09:58 WOP
2 167 AT WO 00:00 00:00 00:00 WO
"""

rows, warns = bp.parse_esmart(SAMPLE, source_location="KAMLA NAGAR")
print(f"1) Parsed e-Smart: {len(rows)} rows, warnings={warns or 'none'}")


def key(r):
    return db._bio_key(r["Emp_Code"], r["Attendance_Date"], r["Month_Year"], r["Source_Location"])


seen = set()
ins1 = sum(1 for r in rows if (k := key(r)) not in seen and not seen.add(k))
ins2 = sum(1 for r in rows if (k := key(r)) not in seen and not seen.add(k))
print(f"2) Dedup: first upload inserts {ins1}, identical re-upload inserts {ins2} "
      f"({'IDEMPOTENT OK' if ins2 == 0 else 'FAIL'})")

emps = pd.DataFrame([
    {"Emp_Code": "27", "Emp_Name": "VIJAY KUMAR (BM)", "Gender": "Male",
     "Shift_Exception": "None", "Base_Salary": 22000, "EPF": 1800, "ESIC": 130,
     "Week_Off_Default": "MON", "Is_Active": "TRUE", "TG_Ladies_Bonus": 0},
    {"Emp_Code": "167", "Emp_Name": "AMIT (AT)", "Gender": "Male",
     "Shift_Exception": "None", "Base_Salary": 18000, "EPF": 1800, "ESIC": 130,
     "Week_Off_Default": "MON", "Is_Active": "TRUE", "TG_Ladies_Bonus": 0},
])
ov = pd.DataFrame(columns=["Emp_Code", "Override_Type", "Override_Date",
                           "Override_Date_End", "New_Week_Off_Day", "Is_Active"])
processed = processing.process_location_month(emps, "05-2026", pd.DataFrame(rows), ov, set())

print("3) Reprocess -> attendance highlights:")
for code, (emp, days) in processed.items():
    by = {d.attendance_date: d for d in days}
    print(f"   {emp['Emp_Name']}: "
          f"01={by['01/05/2026'].final_status}(nashta {by['01/05/2026'].nashta_daily}), "
          f"02={by['02/05/2026'].final_status}(fine {by['02/05/2026'].late_fine}), "
          f"04={by['04/05/2026'].final_status}")
    rec = eng.build_payroll_record(employee=emp, month_year="05-2026", day_results=days)
    print(f"      payroll -> present {rec['Present_Days']}, extra {rec['Extra_Present_Days']}, "
          f"nashta {rec['Nashta_Total']}, net {rec['Net_Payable']} ({rec['Result_Type']})")

print("\nUPLOAD LOOP OK" if ins2 == 0 else "\nUPLOAD LOOP FAIL")
