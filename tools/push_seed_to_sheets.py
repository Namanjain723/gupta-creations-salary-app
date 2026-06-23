"""
Push the loaded seed data (employee directory + commissions) into your
connected Google Sheet. Run this ONCE after you've added
secrets/service_account.json + secrets/config.toml (see DEPLOY.md).

Run:  ./.venv/Scripts/python.exe tools/push_seed_to_sheets.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
from modules import sheets_sync as db, constants as C  # noqa: E402

SEED = Path(__file__).resolve().parent.parent / "seed_data"

db.reset_backend()
mode = db.backend_mode()
print(f"Backend: {mode} — {db.backend_reason()}")
if mode != "GOOGLE_SHEETS":
    print("\nNot connected to Google Sheets. Add secrets/service_account.json + "
          "secrets/config.toml (with your salary_db_id), then re-run. See DEPLOY.md.")
    sys.exit(1)

pushed = []
for tab, fname in [(C.TAB_EMPLOYEE, "Employee_Master.csv"),
                   (C.TAB_SALES_KN, "SALE_REPORT_KN.csv")]:
    fp = SEED / fname
    if not fp.exists():
        continue
    df = pd.read_csv(fp, dtype=str, keep_default_na=False)
    existing = db.read(tab)
    if not existing.empty:
        ans = input(f"{tab} already has {len(existing)} rows — overwrite? [y/N] ").strip().lower()
        if ans != "y":
            print(f"  skipped {tab}")
            continue
    db.write(tab, df)
    pushed.append(f"{tab}: {len(df)} rows")

print("\nPushed to Google Sheets:")
for p in pushed:
    print(f"  ✓ {p}")
print("\nDone. Open the app — the sidebar should read 'Connected to Google Sheets'.")
