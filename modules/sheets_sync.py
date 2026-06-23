"""
sheets_sync.py
==============
The data layer. Presents ONE interface to the rest of the app and transparently
talks to whichever backend is configured:

  * GSpreadBackend  — real Google Sheets via a service account (production).
  * LocalBackend    — CSV files under local_db/ (offline / demo / pilot before
                      Sheets is wired up). Auto-seeds from seed_data/ on first run.

The app picks the backend automatically:
  credentials present  -> Google Sheets
  no credentials       -> Local files  (a banner tells the admin they're offline)

Every public read returns a pandas DataFrame whose columns exactly match
constants.COLUMNS[tab]. Every write goes straight to the backend and clears the
in-process TTL cache so the next read is fresh.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pandas as pd

from . import constants as C
from . import utils

# --------------------------------------------------------------------------- #
#  Paths
# --------------------------------------------------------------------------- #
ROOT = Path(__file__).resolve().parent.parent
SECRETS_DIR = ROOT / "secrets"
LOCAL_DB_DIR = ROOT / "local_db"
SEED_DIR = ROOT / "seed_data"
SERVICE_ACCOUNT_FILE = SECRETS_DIR / "service_account.json"
CONFIG_FILE = SECRETS_DIR / "config.toml"

LOCAL_DB_DIR.mkdir(exist_ok=True)

# --------------------------------------------------------------------------- #
#  Tiny module-level TTL cache (persists across Streamlit reruns in-process)
# --------------------------------------------------------------------------- #
_CACHE: dict = {}
_DEFAULT_TTL = 120  # seconds


def _cache_get(key, ttl=_DEFAULT_TTL):
    e = _CACHE.get(key)
    if e and (time.time() - e[0]) < ttl:
        return e[1].copy() if isinstance(e[1], pd.DataFrame) else e[1]
    return None


def _cache_put(key, value):
    _CACHE[key] = (time.time(), value)


def clear_cache():
    _CACHE.clear()


# --------------------------------------------------------------------------- #
#  Backends
# --------------------------------------------------------------------------- #
class LocalBackend:
    """CSV-file backed store. Each tab => local_db/<tab>.csv (all values str)."""

    mode = "LOCAL"

    def __init__(self):
        self._seed_if_empty()

    def _path(self, tab: str) -> Path:
        return LOCAL_DB_DIR / f"{tab}.csv"

    def _seed_path(self, tab: str) -> Path:
        return SEED_DIR / f"{tab}.csv"

    def _seed_if_empty(self):
        for tab, cols in C.COLUMNS.items():
            p = self._path(tab)
            if p.exists():
                continue
            seed = self._seed_path(tab)
            if seed.exists():
                df = pd.read_csv(seed, dtype=str, keep_default_na=False)
                df = _ensure_cols(df, cols)
            else:
                df = pd.DataFrame(columns=cols)
            df.to_csv(p, index=False)

    def read_tab(self, tab: str) -> pd.DataFrame:
        p = self._path(tab)
        cols = C.COLUMNS[tab]
        if not p.exists():
            return pd.DataFrame(columns=cols)
        df = pd.read_csv(p, dtype=str, keep_default_na=False)
        return _ensure_cols(df, cols)

    def write_tab(self, tab: str, df: pd.DataFrame):
        cols = C.COLUMNS[tab]
        out = _ensure_cols(df.copy(), cols)
        out.to_csv(self._path(tab), index=False)

    def append_rows(self, tab: str, rows: list[dict]):
        if not rows:
            return
        cur = self.read_tab(tab)
        add = _ensure_cols(pd.DataFrame(rows), C.COLUMNS[tab])
        out = pd.concat([cur, add], ignore_index=True)
        self.write_tab(tab, out)

    def modified_time(self) -> float:
        times = [self._path(t).stat().st_mtime for t in C.COLUMNS if self._path(t).exists()]
        return max(times) if times else 0.0


class GSpreadBackend:
    """Google Sheets backend via a service account (gspread)."""

    mode = "GOOGLE_SHEETS"

    def __init__(self, creds_dict: dict, salary_db_id: str, kn_sales_id: str = ""):
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        self._gc = gspread.authorize(creds)
        self._salary_db_id = salary_db_id
        self._kn_sales_id = kn_sales_id or salary_db_id
        self._sh = self._gc.open_by_key(salary_db_id)

    def _ws(self, tab: str):
        try:
            return self._sh.worksheet(tab)
        except Exception:
            ws = self._sh.add_worksheet(title=tab, rows=200, cols=len(C.COLUMNS[tab]))
            ws.update([C.COLUMNS[tab]])
            return ws

    def read_tab(self, tab: str) -> pd.DataFrame:
        ws = self._ws(tab)
        records = ws.get_all_records()
        df = pd.DataFrame(records)
        return _ensure_cols(df, C.COLUMNS[tab])

    def write_tab(self, tab: str, df: pd.DataFrame):
        ws = self._ws(tab)
        cols = C.COLUMNS[tab]
        out = _ensure_cols(df.copy(), cols).astype(str)
        ws.clear()
        ws.update([cols] + out.values.tolist(), value_input_option="USER_ENTERED")

    def append_rows(self, tab: str, rows: list[dict]):
        if not rows:
            return
        ws = self._ws(tab)
        cols = C.COLUMNS[tab]
        body = [[str(r.get(c, "")) for c in cols] for r in rows]
        ws.append_rows(body, value_input_option="USER_ENTERED")

    def modified_time(self) -> float:
        try:
            return time.time()  # Drive API optional; treat as always-fresh
        except Exception:
            return 0.0


def _ensure_cols(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Guarantee df has exactly `cols` (order preserved, missing -> '')."""
    if df is None or df.empty:
        return pd.DataFrame(columns=cols)
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    return df[cols]


# --------------------------------------------------------------------------- #
#  Backend selection
# --------------------------------------------------------------------------- #
_BACKEND = None
_BACKEND_INFO = {"mode": "LOCAL", "reason": ""}


def _load_config() -> dict:
    cfg = {}
    # 1) Streamlit secrets (cloud deploy)
    try:
        import streamlit as st
        if hasattr(st, "secrets") and len(st.secrets):
            cfg["sheets"] = dict(st.secrets.get("sheets", {}))
            if "gcp_service_account" in st.secrets:
                cfg["gcp_service_account"] = dict(st.secrets["gcp_service_account"])
            cfg["app"] = dict(st.secrets.get("app", {}))
    except Exception:
        pass
    # 2) local config.toml
    if CONFIG_FILE.exists():
        try:
            import toml
            local = toml.load(CONFIG_FILE)
            for k, v in local.items():
                cfg.setdefault(k, v)
        except Exception:
            pass
    return cfg


def get_backend():
    global _BACKEND, _BACKEND_INFO
    if _BACKEND is not None:
        return _BACKEND

    cfg = _load_config()
    creds_dict, salary_id, kn_id = None, "", ""

    sheets_cfg = cfg.get("sheets", {})
    salary_id = sheets_cfg.get("salary_db_id", "") or ""
    kn_id = sheets_cfg.get("kn_sales_id", "") or ""

    if cfg.get("gcp_service_account"):
        creds_dict = cfg["gcp_service_account"]
    elif SERVICE_ACCOUNT_FILE.exists():
        try:
            creds_dict = json.loads(SERVICE_ACCOUNT_FILE.read_text(encoding="utf-8"))
            creds_dict.pop("_README", None)
        except Exception as e:
            _BACKEND_INFO = {"mode": "LOCAL", "reason": f"bad service_account.json: {e}"}

    placeholder = (not salary_id) or salary_id.startswith("PASTE_") or \
        (creds_dict or {}).get("private_key", "").find("REPLACE_WITH_REAL_KEY") >= 0

    if creds_dict and salary_id and not placeholder:
        try:
            _BACKEND = GSpreadBackend(creds_dict, salary_id, kn_id)
            _BACKEND_INFO = {"mode": "GOOGLE_SHEETS", "reason": "service account OK"}
            return _BACKEND
        except Exception as e:
            _BACKEND_INFO = {"mode": "LOCAL", "reason": f"Sheets connect failed: {e}"}
    else:
        _BACKEND_INFO = {"mode": "LOCAL",
                         "reason": "no credentials configured — running on local files"}

    _BACKEND = LocalBackend()
    return _BACKEND


def backend_mode() -> str:
    get_backend()
    return _BACKEND_INFO["mode"]


def backend_reason() -> str:
    get_backend()
    return _BACKEND_INFO["reason"]


def reset_backend():
    """Force re-detection (e.g. after credentials are added)."""
    global _BACKEND
    _BACKEND = None
    clear_cache()


# --------------------------------------------------------------------------- #
#  Generic cached read
# --------------------------------------------------------------------------- #
def read(tab: str, ttl=_DEFAULT_TTL) -> pd.DataFrame:
    key = f"tab::{tab}"
    cached = _cache_get(key, ttl)
    if cached is not None:
        return cached
    df = get_backend().read_tab(tab)
    _cache_put(key, df)
    return df.copy()


def write(tab: str, df: pd.DataFrame):
    get_backend().write_tab(tab, df)
    clear_cache()


def append(tab: str, rows: list[dict]):
    get_backend().append_rows(tab, rows)
    clear_cache()


# --------------------------------------------------------------------------- #
#  EMPLOYEE MASTER
# --------------------------------------------------------------------------- #
def get_employees(location: str | None = None, active_only: bool = False) -> pd.DataFrame:
    df = read(C.TAB_EMPLOYEE)
    if active_only and "Is_Active" in df.columns:
        df = df[df["Is_Active"].apply(utils.truthy)]
    if location and location not in ("ALL", "", None):
        df = df[df["Location"].str.upper() == str(location).upper()]
    return df.reset_index(drop=True)


def get_employee(emp_code: str) -> dict | None:
    df = read(C.TAB_EMPLOYEE)
    target = utils.normalise_emp_code(emp_code)
    for _, row in df.iterrows():
        if utils.normalise_emp_code(row["Emp_Code"]) == target:
            return row.to_dict()
    return None


def save_employee(emp: dict, admin: str = "Admin"):
    """Insert or update by Emp_Code."""
    df = read(C.TAB_EMPLOYEE)
    code = utils.normalise_emp_code(emp.get("Emp_Code"))
    mask = df["Emp_Code"].apply(utils.normalise_emp_code) == code
    new_row = {c: str(emp.get(c, "")) for c in C.COLUMNS[C.TAB_EMPLOYEE]}
    if mask.any():
        for c in C.COLUMNS[C.TAB_EMPLOYEE]:
            df.loc[mask, c] = new_row[c]
        action = "EMPLOYEE_EDIT"
    else:
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        action = "EMPLOYEE_ADD"
    write(C.TAB_EMPLOYEE, df)
    log_sync(action, f"{emp.get('Emp_Name')} ({emp.get('Emp_Code')})", admin)


def save_employees_bulk(df_new: pd.DataFrame, admin: str = "Admin"):
    write(C.TAB_EMPLOYEE, df_new)
    log_sync("EMPLOYEE_BULK_SAVE", f"{len(df_new)} rows", admin)


def soft_delete_employee(emp_code: str, admin: str = "Admin"):
    df = read(C.TAB_EMPLOYEE)
    code = utils.normalise_emp_code(emp_code)
    mask = df["Emp_Code"].apply(utils.normalise_emp_code) == code
    df.loc[mask, "Is_Active"] = "FALSE"
    write(C.TAB_EMPLOYEE, df)
    log_sync("EMPLOYEE_DELETE", f"soft-deleted {emp_code}", admin)


# --------------------------------------------------------------------------- #
#  BIOMETRIC (with dedup by Emp_Code + Date + Month + Location)
# --------------------------------------------------------------------------- #
def get_biometric(month_year: str | None = None, location: str | None = None) -> pd.DataFrame:
    df = read(C.TAB_BIOMETRIC)
    if month_year:
        df = df[df["Month_Year"] == month_year]
    if location and location not in ("ALL", None, ""):
        df = df[df["Source_Location"].str.upper() == str(location).upper()]
    return df.reset_index(drop=True)


def save_biometric_rows(rows: list[dict], admin: str = "Admin") -> dict:
    """Append biometric rows, skipping exact duplicates. Returns counts."""
    existing = read(C.TAB_BIOMETRIC)
    seen = set()
    for _, r in existing.iterrows():
        seen.add(_bio_key(r["Emp_Code"], r["Attendance_Date"], r["Month_Year"],
                          r["Source_Location"]))
    fresh, dupes = [], 0
    for row in rows:
        k = _bio_key(row.get("Emp_Code"), row.get("Attendance_Date"),
                     row.get("Month_Year"), row.get("Source_Location"))
        if k in seen:
            dupes += 1
            continue
        seen.add(k)
        fresh.append({c: row.get(c, "") for c in C.COLUMNS[C.TAB_BIOMETRIC]})
    if fresh:
        append(C.TAB_BIOMETRIC, fresh)
    log_sync("BIOMETRIC_UPLOAD", f"{len(fresh)} new, {dupes} dupes skipped", admin)
    return {"inserted": len(fresh), "skipped": dupes}


def _bio_key(emp_code, date, month, location) -> str:
    return f"{utils.normalise_emp_code(emp_code)}|{utils.fmt_date(date)}|{month}|{str(location).upper()}"


# --------------------------------------------------------------------------- #
#  ATTENDANCE_PROCESSED (upsert by Emp_Code + Date + Month)
# --------------------------------------------------------------------------- #
def get_attendance(month_year: str | None = None, emp_codes: list | None = None) -> pd.DataFrame:
    df = read(C.TAB_ATTENDANCE)
    if month_year:
        df = df[df["Month_Year"] == month_year]
    if emp_codes:
        norm = {utils.normalise_emp_code(c) for c in emp_codes}
        df = df[df["Emp_Code"].apply(utils.normalise_emp_code).isin(norm)]
    return df.reset_index(drop=True)


def upsert_attendance(rows: list[dict], month_year: str, admin: str = "Admin"):
    """Replace existing (emp, date) rows for the month, keep others."""
    df = read(C.TAB_ATTENDANCE)
    keys = {(utils.normalise_emp_code(r["Emp_Code"]), utils.fmt_date(r["Attendance_Date"]),
             r["Month_Year"]) for r in rows}
    if not df.empty:
        df = df[~df.apply(lambda r: (utils.normalise_emp_code(r["Emp_Code"]),
                                     utils.fmt_date(r["Attendance_Date"]),
                                     r["Month_Year"]) in keys, axis=1)]
    add = pd.DataFrame([{c: r.get(c, "") for c in C.COLUMNS[C.TAB_ATTENDANCE]} for r in rows])
    out = pd.concat([df, add], ignore_index=True)
    write(C.TAB_ATTENDANCE, out)
    log_sync("ATTENDANCE_PROCESSED", f"{len(rows)} rows for {month_year}", admin)


# --------------------------------------------------------------------------- #
#  MANUAL OVERRIDES
# --------------------------------------------------------------------------- #
def get_overrides(month_year: str | None = None, active_only: bool = True,
                  emp_code: str | None = None) -> pd.DataFrame:
    df = read(C.TAB_OVERRIDES)
    if active_only and not df.empty:
        df = df[df["Is_Active"].apply(utils.truthy)]
    if month_year:
        df = df[df["Month_Year"] == month_year]
    if emp_code:
        df = df[df["Emp_Code"].apply(utils.normalise_emp_code) == utils.normalise_emp_code(emp_code)]
    return df.reset_index(drop=True)


def next_id(tab: str, col: str) -> int:
    df = read(tab)
    if df.empty:
        return 1
    vals = [utils.safe_int(x) for x in df[col] if str(x).strip()]
    return (max(vals) + 1) if vals else 1


def save_override(ov: dict, admin: str = "Admin"):
    ov = dict(ov)
    ov.setdefault("Override_ID", next_id(C.TAB_OVERRIDES, "Override_ID"))
    ov.setdefault("Applied_By", admin)
    ov.setdefault("Applied_At", utils.now_ist_iso())
    ov.setdefault("Is_Active", "TRUE")
    append(C.TAB_OVERRIDES, [{c: ov.get(c, "") for c in C.COLUMNS[C.TAB_OVERRIDES]}])
    log_sync("MANUAL_OVERRIDE",
             f"{ov.get('Override_Type')} {ov.get('Emp_Name')} {ov.get('Override_Date')}", admin)


def delete_override(override_id, admin: str = "Admin"):
    df = read(C.TAB_OVERRIDES)
    mask = df["Override_ID"].apply(utils.safe_int) == utils.safe_int(override_id)
    df.loc[mask, "Is_Active"] = "FALSE"
    write(C.TAB_OVERRIDES, df)
    log_sync("MANUAL_OVERRIDE", f"deactivated override {override_id}", admin)


# --------------------------------------------------------------------------- #
#  VARIABLE LEDGER  (advances / interest / B-F / TG bonus / commissions)
# --------------------------------------------------------------------------- #
def get_ledger(month_year: str | None = None, emp_code: str | None = None,
               entry_types: list | None = None) -> pd.DataFrame:
    df = read(C.TAB_LEDGER)
    if month_year:
        df = df[df["Month_Year"] == month_year]
    if emp_code:
        df = df[df["Emp_Code"].apply(utils.normalise_emp_code) == utils.normalise_emp_code(emp_code)]
    if entry_types:
        df = df[df["Entry_Type"].isin(entry_types)]
    return df.reset_index(drop=True)


def save_ledger_entry(entry: dict, admin: str = "Admin"):
    entry = dict(entry)
    entry.setdefault("Ledger_ID", next_id(C.TAB_LEDGER, "Ledger_ID"))
    entry.setdefault("Entered_By", admin)
    entry.setdefault("Entered_At", utils.now_ist_iso())
    append(C.TAB_LEDGER, [{c: entry.get(c, "") for c in C.COLUMNS[C.TAB_LEDGER]}])
    log_sync("LEDGER_ENTRY",
             f"{entry.get('Entry_Type')} {utils.fmt_inr(entry.get('Amount'))} "
             f"{entry.get('Emp_Name')}", admin)


def delete_ledger_entry(ledger_id, admin: str = "Admin"):
    df = read(C.TAB_LEDGER)
    df = df[df["Ledger_ID"].apply(utils.safe_int) != utils.safe_int(ledger_id)]
    write(C.TAB_LEDGER, df)
    log_sync("LEDGER_ENTRY", f"deleted ledger {ledger_id}", admin)


def advances_for(emp_code: str, month_year: str) -> dict:
    df = get_ledger(month_year, emp_code)

    def _sum(t):
        return df[df["Entry_Type"] == t]["Amount"].apply(utils.safe_float).sum()

    def _lines(t):
        """Dated detail lines for the slip: [{date, amount}], date ascending."""
        sub = df[df["Entry_Type"] == t]
        out = [{"date": utils.fmt_date(r.get("Entry_Date")) or r.get("Entry_Date", ""),
                "amount": utils.round_half_up(r.get("Amount"))}
               for _, r in sub.iterrows() if utils.safe_float(r.get("Amount"))]
        return sorted(out, key=lambda x: utils.parse_date(x["date"]) or utils.now_ist().date())

    cash, bank = _sum("ADVANCE_CASH"), _sum("ADVANCE_BANK")
    return {
        "cash": cash, "bank": bank, "hdfc": _sum("HDFC_BANK"), "jama": _sum("JAMA"),
        "interest": _sum("INTEREST"), "bf": _sum("B_FORWARD"), "tg": _sum("TG_BONUS"),
        "total": cash + bank,
        "cash_lines": _lines("ADVANCE_CASH"), "bank_lines": _lines("ADVANCE_BANK"),
        "jama_lines": _lines("JAMA"),
    }


# --------------------------------------------------------------------------- #
#  COMMISSIONS (SALE_REPORT_KN)
# --------------------------------------------------------------------------- #
def get_sales_kn(month_year: str | None = None) -> pd.DataFrame:
    df = read(C.TAB_SALES_KN)
    if month_year:
        df = df[df["Month_Year"] == month_year]
    return df.reset_index(drop=True)


# Commission scale. The owner's live payroll sheet AND the printed slips both
# carry commissions in FULL RUPEES (e.g. PK S.Com 1547, RJ 2653/165/856), so the
# default is 1 (as-entered). The raw KN team export uses a ×100 2-decimal format
# (28.30 = ₹2,830); set this to 100 (or per-location in Config) only when
# importing that raw report. ONE place does the conversion.
COMMISSION_SCALE = 1


def commission_to_rupees(value, scale: float | None = None) -> int:
    """Commission cell -> whole rupees, multiplying by COMMISSION_SCALE (default 1)."""
    s = COMMISSION_SCALE if scale is None else scale
    return utils.round_half_up(utils.safe_float(value) * s)


def get_commissions_kn(month_year: str) -> dict:
    """Return {short_code/emp_code: {s_com,b_com,l_com}} for the month, in ₹."""
    df = get_sales_kn(month_year)
    out = {}
    for _, row in df.iterrows():
        rec = {
            "s_com": commission_to_rupees(row.get("S_Com")),
            "b_com": commission_to_rupees(row.get("B_Com")),
            "l_com": commission_to_rupees(row.get("L_Com")),
        }
        sc = str(row.get("Short_Code", "")).strip().upper()
        ec = utils.normalise_emp_code(row.get("Emp_Code", ""))
        if sc:
            out[sc] = rec
        if ec:
            out[ec] = rec
    return out


def commissions_for(emp: dict, comm_map: dict) -> dict:
    """Look up an employee's commission by short code, then emp code."""
    sc = str(emp.get("Short_Code", "")).strip().upper()
    ec = utils.normalise_emp_code(emp.get("Emp_Code", ""))
    return comm_map.get(sc) or comm_map.get(ec) or {"s_com": 0, "b_com": 0, "l_com": 0}


def save_sales_kn(df_new: pd.DataFrame, admin: str = "Admin"):
    write(C.TAB_SALES_KN, df_new)
    log_sync("SHEET_EDIT_DETECTED", f"SALE_REPORT_KN saved ({len(df_new)} rows)", admin)


# --------------------------------------------------------------------------- #
#  PAYROLL
# --------------------------------------------------------------------------- #
def get_payroll(month_year: str | None = None) -> pd.DataFrame:
    df = read(C.TAB_PAYROLL)
    if month_year:
        df = df[df["Month_Year"] == month_year]
    return df.reset_index(drop=True)


def save_payroll(rows: list[dict], month_year: str, admin: str = "Admin"):
    """Replace the whole month's payroll with a fresh run."""
    df = read(C.TAB_PAYROLL)
    if not df.empty:
        df = df[df["Month_Year"] != month_year]
    add = pd.DataFrame([{c: r.get(c, "") for c in C.COLUMNS[C.TAB_PAYROLL]} for r in rows])
    out = pd.concat([df, add], ignore_index=True)
    write(C.TAB_PAYROLL, out)
    log_sync("PAYROLL_RUN", f"{len(rows)} employees, {month_year}", admin)


def get_previous_lena(emp_code: str, month_year: str) -> float:
    """Lena (carry-forward) owed from the immediately previous month."""
    year, month = utils.parse_month_year(month_year)
    pm = 12 if month == 1 else month - 1
    py = year - 1 if month == 1 else year
    prev_my = f"{pm:02d}-{py}"
    df = get_payroll(prev_my)
    if df.empty:
        return 0.0
    norm = utils.normalise_emp_code(emp_code)
    for _, row in df.iterrows():
        if utils.normalise_emp_code(row["Emp_Code"]) == norm:
            return utils.safe_float(row.get("Lena_Amount"))
    return 0.0


# --------------------------------------------------------------------------- #
#  NASHTA tabs
# --------------------------------------------------------------------------- #
def save_nashta_summary(rows: list[dict], month_year: str, admin: str = "Admin"):
    df = read(C.TAB_NASHTA_SUMMARY)
    if not df.empty:
        df = df[df["Month_Year"] != month_year]
    add = pd.DataFrame([{c: r.get(c, "") for c in C.COLUMNS[C.TAB_NASHTA_SUMMARY]} for r in rows])
    out = pd.concat([df, add], ignore_index=True)
    write(C.TAB_NASHTA_SUMMARY, out)


# --------------------------------------------------------------------------- #
#  HOLIDAYS
# --------------------------------------------------------------------------- #
def get_holidays() -> pd.DataFrame:
    return read(C.TAB_HOLIDAYS)


def holiday_dates() -> set:
    df = get_holidays()
    out = set()
    for _, row in df.iterrows():
        d = utils.parse_date(row.get("Holiday_Date"))
        if d:
            out.add(d)
    return out


def save_holiday(holiday: dict, admin: str = "Admin"):
    append(C.TAB_HOLIDAYS, [{c: holiday.get(c, "") for c in C.COLUMNS[C.TAB_HOLIDAYS]}])
    log_sync("HOLIDAY_ADD", f"{holiday.get('Holiday_Name')} {holiday.get('Holiday_Date')}", admin)


# --------------------------------------------------------------------------- #
#  SYNC LOG
# --------------------------------------------------------------------------- #
def log_sync(action: str, details: str, admin: str = "Admin"):
    try:
        get_backend().append_rows(C.TAB_SYNC_LOG, [{
            "Timestamp": utils.now_ist_iso(), "Action": action,
            "Details": details, "Admin": admin,
        }])
    except Exception:
        pass  # logging must never break a real write


def get_sync_log(limit: int = 200) -> pd.DataFrame:
    df = read(C.TAB_SYNC_LOG, ttl=10)
    return df.tail(limit).iloc[::-1].reset_index(drop=True)


def last_sync_str() -> str:
    df = read(C.TAB_SYNC_LOG, ttl=10)
    if df.empty:
        return "never"
    return str(df.iloc[-1]["Timestamp"])
