"""
Headless verification: run app.py and every page through Streamlit's AppTest
harness against the seeded local DB, asserting no uncaught exceptions.
Run:  ./.venv/Scripts/python.exe tools/verify_app.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402

PAGES = ["dashboard", "employees", "biometric", "nashta", "overrides",
         "ledger", "payroll", "slips", "reports"]

failures = []


def check(label, at):
    excs = list(at.exception)
    if excs:
        failures.append(label)
        print(f"  ✗ {label}: {excs[0].value if hasattr(excs[0], 'value') else excs[0]}")
    else:
        print(f"  ok {label}")


print("Running app.py (entry + default page)…")
try:
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90)
    at.session_state["_auth_user"] = "admin"   # skip the login gate for the smoke test
    at.run()
    check("app.py", at)
except Exception as e:
    failures.append("app.py")
    print(f"  ✗ app.py raised: {e!r}")

print("\nRunning each page directly…")
for p in PAGES:
    try:
        at = AppTest.from_file(str(ROOT / "pages" / f"{p}.py"), default_timeout=90)
        at.session_state["month"] = "05-2026"
        at.session_state["location"] = "KAMLA NAGAR"
        at.session_state["admin"] = "Admin"
        at.run()
        check(p, at)
    except Exception as e:
        failures.append(p)
        print(f"  ✗ {p} raised: {type(e).__name__}: {e}")

print("\n" + ("FAILURES: " + ", ".join(failures) if failures else "ALL PAGES OK ✓"))
sys.exit(1 if failures else 0)
