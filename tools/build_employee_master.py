"""
Build seed_data/Employee_Master.csv from the real employee_directory.csv.

Keeps the 10 KN pilot salaries; everyone else gets Base_Salary 0 (the admin
fills these in on the Employees page). Rows without an Emp_Code are saved as
inactive reference entries (can't be matched to biometric until a code exists).

Run:  ./.venv/Scripts/python.exe tools/build_employee_master.py
"""
import csv
from pathlib import Path

SEED = Path(__file__).resolve().parent.parent / "seed_data"

MASTER_COLS = ["Emp_Code", "Emp_Name", "Short_Code", "Gender", "Location", "Department",
               "Shift_Type", "Shift_Exception", "Base_Salary", "EPF", "ESIC", "Bank_Name",
               "Account_Number", "IFSC", "TG_Ladies_Bonus", "Week_Off_Default", "Is_Active",
               "Is_Permanent", "Joined_Date", "Notes"]

# Verified pilot salaries (code -> base, EPF, ESIC). Everyone else starts at 0.
PILOT = {
    "27": (22000, 1800, 130), "37": (20500, 1800, 130), "19": (20700, 1800, 130),
    "181": (23300, 1800, 0), "101": (28000, 1800, 0), "45": (21300, 1800, 0),
    "167": (18000, 1800, 130), "26": (20600, 1800, 130), "35": (22400, 1800, 0),
    "197": (17500, 1800, 130),
}


def clean(v):
    return (v or "").strip()


def main():
    rows_out = []
    seen_codes = set()
    with open(SEED / "employee_directory.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            code = clean(r.get("Emp_Code"))
            name = clean(r.get("Emp_Name"))
            short = clean(r.get("Short_Code"))
            # display name
            if name and short:
                disp = f"{name} ({short})"
            elif name:
                disp = name
            elif short:
                disp = short
            else:
                disp = f"EMP {code}" if code else "UNKNOWN"

            base, epf, esic = PILOT.get(code, (0, 0, 0))
            active = "TRUE" if code and code not in seen_codes else "FALSE"
            if code:
                if code in seen_codes:
                    continue  # skip duplicate code
                seen_codes.add(code)

            rows_out.append({
                "Emp_Code": code,
                "Emp_Name": disp,
                "Short_Code": short,
                "Gender": clean(r.get("Gender")) or "Male",
                "Location": clean(r.get("Location")),
                "Department": clean(r.get("Department")),
                "Shift_Type": "GS",
                "Shift_Exception": clean(r.get("Shift_Exception")) or "None",
                "Base_Salary": base,
                "EPF": epf,
                "ESIC": esic,
                "Bank_Name": "", "Account_Number": "", "IFSC": "",
                "TG_Ladies_Bonus": 0,
                "Week_Off_Default": "MON",
                "Is_Active": active,
                "Is_Permanent": "TRUE" if epf > 0 else "FALSE",  # permanent = on EPF
                "Joined_Date": "",
                "Notes": clean(r.get("Notes")),
            })

    with open(SEED / "Employee_Master.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MASTER_COLS)
        w.writeheader()
        w.writerows(rows_out)

    active = sum(1 for r in rows_out if r["Is_Active"] == "TRUE")
    by_loc = {}
    for r in rows_out:
        by_loc[r["Location"]] = by_loc.get(r["Location"], 0) + 1
    print(f"Wrote Employee_Master.csv: {len(rows_out)} rows ({active} active with codes)")
    for loc, n in sorted(by_loc.items()):
        print(f"  {loc}: {n}")
    print(f"Pilot salaries set for {len(PILOT)} KN employees; rest Base_Salary=0 (fill in app).")


if __name__ == "__main__":
    main()
