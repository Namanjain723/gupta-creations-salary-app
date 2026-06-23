"""
Generate realistic seed biometric data for the 10 KN pilot employees.

Produces:
  seed_data/Biometric_Raw.csv              -> full May-2026 month (seeds local DB)
  seed_data/sample_upload_KN_June2026.csv  -> template-format file to test upload

Deterministic (fixed random seed) so re-running gives identical data.
Run:  ./.venv/Scripts/python.exe tools/generate_seed_biometric.py
"""
import calendar
import csv
import random
from datetime import date
from pathlib import Path

random.seed(42)
SEED_DIR = Path(__file__).resolve().parent.parent / "seed_data"

# (code, name, lateness profile)  profiles tune how often / how late they punch
EMPLOYEES = [
    ("27", "VIJAY KUMAR (BM)", "punctual"),
    ("37", "PRADEEP KUMAR (PK)", "normal"),
    ("19", "ANKIT MANDAL (AM)", "normal"),
    ("181", "RAKESH KUMAR KUSHWAHA (RJ)", "normal"),
    ("101", "AVDHESH KUMAR (AV)", "punctual"),
    ("45", "VINAY SINGH (VS)", "normal"),
    ("167", "AMIT KUMAR VERMA (AT)", "chronic_late"),
    ("26", "VINOD (VN)", "normal"),
    ("35", "SURESH PRASAD YADAV (SP)", "normal"),
    ("197", "HEMANT (HN)", "absentee"),
]

PROFILES = {
    # (absent_prob, [(weight, low_offset, high_offset)])  offset = minutes vs 10:30
    "punctual":     (0.01, [(80, -15, 0), (15, 1, 12), (5, 13, 25)]),
    "normal":       (0.04, [(55, -12, 0), (25, 1, 14), (12, 15, 28), (6, 30, 55), (2, 60, 85)]),
    "chronic_late": (0.06, [(20, -8, 0), (25, 1, 14), (28, 15, 29), (17, 30, 59), (10, 60, 95)]),
    "absentee":     (0.14, [(60, -10, 5), (25, 1, 18), (15, 20, 50)]),
}

MONDAYS_OFF = True


def pick_offset(buckets):
    total = sum(w for w, _, _ in buckets)
    r = random.uniform(0, total)
    acc = 0
    for w, lo, hi in buckets:
        acc += w
        if r <= acc:
            return random.randint(lo, hi)
    return 0


def hhmm(mins):
    return f"{mins // 60:02d}:{mins % 60:02d}:00"


def hhmm_short(mins):
    return f"{mins // 60:02d}:{mins % 60:02d}"


def gen_month(year, month, *, raw_schema=True, days_limit=None):
    rows = []
    ndays = calendar.monthrange(year, month)[1]
    for day in range(1, ndays + 1):
        d = date(year, month, day)
        is_mon = d.weekday() == 0
        for code, name, profile in EMPLOYEES:
            absent_p, buckets = PROFILES[profile]

            # Monday = week off; most stay home, but demo one WOP (Vijay on 11 May)
            if is_mon and MONDAYS_OFF:
                if not (code == "27" and month == 5 and day == 11):
                    continue
                shift_start = 690  # 11:30 Monday
            else:
                shift_start = 630  # 10:30

            # absence?
            if random.random() < absent_p:
                continue

            # single-entry demo: Hemant on 8 May
            single_entry = (code == "197" and month == 5 and day == 8)
            # half-day-cut demo: Pradeep arrives 14:45 on 13 May
            half_day = (code == "37" and month == 5 and day == 13)

            if single_entry:
                in_min = 632
                in_t, out_t = hhmm(in_min), hhmm(in_min) + "(SE)"
                dur_min, dur_raw, status = 1, "00:01", "1/2P"
            elif half_day:
                in_min = 885  # 14:45
                out_min = 1290
                in_t, out_t = hhmm(in_min), hhmm(out_min)
                dur_min = out_min - in_min
                dur_raw, status = hhmm_short(dur_min), "P"
            else:
                in_min = shift_start + pick_offset(buckets)
                out_min = 1290 - random.choice([0, 0, 0, 0, 10, 25, 40])
                if out_min <= in_min:
                    out_min = in_min + 480
                in_t, out_t = hhmm(in_min), hhmm(out_min)
                dur_min = out_min - in_min
                dur_raw, status = hhmm_short(dur_min), "P"

            if raw_schema:
                rows.append({
                    "Upload_Date": "22/06/2026", "Month_Year": f"{month:02d}-{year}",
                    "Source_Location": "KAMLA NAGAR", "Upload_Frequency": "MONTHLY",
                    "Attendance_Date": f"{day:02d}/{month:02d}/{year}", "Emp_Code": code,
                    "Emp_Name": name, "Shift": "GS", "In_Time": in_t, "Out_Time": out_t,
                    "Total_Duration_Raw": dur_raw, "Total_Duration_Mins": dur_min,
                    "Status_Raw": status, "Single_Entry_Flag": "TRUE" if single_entry else "FALSE",
                    "Remarks": "",
                })
            else:  # upload-template format
                rows.append({
                    "Date": f"{day:02d}/{month:02d}/{year}", "Employee Code": code,
                    "Employee Name": name, "Shift": "GS", "In Time": in_t,
                    "Out Time": out_t, "Total Duration": dur_raw, "Status": status,
                    "Remarks": "",
                })
        if days_limit and day >= days_limit:
            break
    return rows


def write_csv(path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    RAW_COLS = ["Upload_Date", "Month_Year", "Source_Location", "Upload_Frequency",
                "Attendance_Date", "Emp_Code", "Emp_Name", "Shift", "In_Time", "Out_Time",
                "Total_Duration_Raw", "Total_Duration_Mins", "Status_Raw",
                "Single_Entry_Flag", "Remarks"]
    UPLOAD_COLS = ["Date", "Employee Code", "Employee Name", "Shift", "In Time",
                   "Out Time", "Total Duration", "Status", "Remarks"]

    may = gen_month(2026, 5, raw_schema=True)
    write_csv(SEED_DIR / "Biometric_Raw.csv", may, RAW_COLS)
    print(f"Wrote Biometric_Raw.csv: {len(may)} rows (May 2026)")

    # fresh random for the upload sample so it differs slightly
    random.seed(7)
    june = gen_month(2026, 6, raw_schema=False, days_limit=8)
    write_csv(SEED_DIR / "sample_upload_KN_June2026.csv", june, UPLOAD_COLS)
    print(f"Wrote sample_upload_KN_June2026.csv: {len(june)} rows (June 1-8 2026)")
