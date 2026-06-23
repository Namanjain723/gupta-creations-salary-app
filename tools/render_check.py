"""Render the RJ slip end-to-end and assert it matches the paper chit to the rupee."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules import pdf_generator as pdf, salary_engine as eng  # noqa: E402

emp = {"Emp_Code": "181", "Emp_Name": "RAKESH KUMAR KUSHWAHA (RJ)", "Base_Salary": 23300,
       "EPF": 1800, "ESIC": 0, "Is_Permanent": "TRUE", "Bank_Account_Number": "50100747202541"}
att = {"absent_deduction": 752, "late_fine_total": 293, "monthly_nashta": 0,
       "extra_present_pay": 0, "present_days": 25, "extra_present_days": 0,
       "cut_lines": [{"start": "19/05/2026", "end": "19/05/2026", "days": 1, "frac": 1.0,
                      "label": "A", "amount": 752}], "extra_present_lines": []}
rec = eng.build_payroll_record(
    employee=emp, month_year="05-2026", attendance=att,
    commissions={"s_com": 2653, "b_com": 165, "l_com": 856},
    advance_bank=8000, jama=8000, interest=120, bf_previous=22000, hdfc=12748)
rec["_advance_bank_lines"] = [{"date": "01/06/2026", "amount": 8000}]
rec["_jama_lines"] = [{"date": "02/06/2026", "amount": 8000}]

pdf_bytes = pdf.slips_pdf([rec], "05-2026")
print(f"PDF bytes={len(pdf_bytes)}  Dena={rec['Dena_Amount']}  "
      f"Cash={rec['Cash_Dena_Amount']}  Lena={rec['Lena_Amount']}")
assert len(pdf_bytes) > 1500
assert rec["Dena_Amount"] == 16009
assert rec["Cash_Dena_Amount"] == 3261
assert rec["Lena_Amount"] == 14000
print("SLIP RENDER OK — RJ reconciles to the rupee and the PDF builds")
