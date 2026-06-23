"""
biometric_parser.py
===================
Turns a biometric export (CSV or PDF) from any of the 5 machines into clean
Biometric_Raw rows. Built to be forgiving about column naming because every
biometric machine labels its columns slightly differently.

Canonical importable shape (any header synonyms below are auto-mapped):
    Date | Employee Code | Employee Name | Shift | In Time | Out Time |
    Total Duration | Status | Remarks

If a file has no per-row Date column (a single-day report), pass `default_date`
and every row is stamped with it. '(SE)' in Out Time -> Single_Entry_Flag.
"""
from __future__ import annotations

import io
import re

import pandas as pd

from . import constants as C
from . import utils

# --------------------------------------------------------------------------- #
#  Header synonym mapping
# --------------------------------------------------------------------------- #
COLUMN_SYNONYMS = {
    "emp_code": ["employee code", "emp code", "empcode", "code", "e code", "e. code",
                 "card no", "cardno", "enroll no", "enrollno", "id", "emp id", "emp_code",
                 "ecode", "user id", "userid"],
    "emp_name": ["employee name", "emp name", "name", "empname", "emp_name", "person name"],
    "shift": ["shift", "shift type", "shift name"],
    "in_time": ["in time", "intime", "in", "punch in", "first in", "in_time", "first punch",
                "time in"],
    "out_time": ["out time", "outtime", "out", "punch out", "last out", "out_time",
                 "last punch", "time out"],
    "duration": ["total duration", "duration", "total", "working hours", "work duration",
                 "total hrs", "work hrs", "tot dur", "total_duration", "hours", "worked"],
    "status": ["status", "att status", "attendance status", "status_raw", "present status"],
    "date": ["date", "att date", "attendance date", "punch date", "attendance_date",
             "att. date", "dt"],
    "remarks": ["remarks", "remark", "note", "notes", "comment"],
}

# Canonical template columns (used to generate a blank import template)
TEMPLATE_COLUMNS = ["Date", "Employee Code", "Employee Name", "Shift", "In Time",
                    "Out Time", "Total Duration", "Status", "Remarks"]


def _norm_header(h: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", str(h).strip().lower()).strip()


def _match_columns(columns) -> dict:
    """Map our canonical field -> the actual column name found in the file."""
    norm_map = {_norm_header(c): c for c in columns}
    mapping = {}
    for field, syns in COLUMN_SYNONYMS.items():
        for syn in syns:
            if syn in norm_map:
                mapping[field] = norm_map[syn]
                break
        else:
            # loose contains-match fallback
            for nh, orig in norm_map.items():
                if any(s == nh or s in nh.split() for s in syns):
                    mapping[field] = orig
                    break
    return mapping


# --------------------------------------------------------------------------- #
#  File readers
# --------------------------------------------------------------------------- #
def _read_csv(file_like) -> pd.DataFrame:
    """Read a CSV, tolerating junk header rows above the real header."""
    if hasattr(file_like, "seek"):
        try:
            file_like.seek(0)
        except Exception:
            pass
    data = file_like.read() if hasattr(file_like, "read") else open(file_like, "rb").read()
    text = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data

    # find the header line: the one mentioning a code/name column
    lines = text.splitlines()
    header_idx = 0
    for i, ln in enumerate(lines[:25]):
        low = ln.lower()
        if ("code" in low or "name" in low) and ("in" in low or "status" in low or "time" in low):
            header_idx = i
            break
    cleaned = "\n".join(lines[header_idx:])
    try:
        return pd.read_csv(io.StringIO(cleaned), dtype=str, keep_default_na=False,
                           skip_blank_lines=True)
    except Exception:
        return pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)


def _read_pdf(file_like) -> pd.DataFrame:
    """Best-effort PDF table extraction (flagged less reliable than CSV)."""
    import pdfplumber

    if hasattr(file_like, "seek"):
        try:
            file_like.seek(0)
        except Exception:
            pass
    data = file_like.read() if hasattr(file_like, "read") else open(file_like, "rb").read()
    rows = []
    header = None
    with pdfplumber.open(io.BytesIO(data) if isinstance(data, bytes) else file_like) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                if not table:
                    continue
                if header is None:
                    header = [str(c or "").strip() for c in table[0]]
                    body = table[1:]
                else:
                    body = table
                for r in body:
                    if r and any(c for c in r):
                        rows.append([str(c or "").strip() for c in r])
    if not header or not rows:
        raise ValueError("Could not extract a table from this PDF — please use CSV.")
    width = len(header)
    rows = [r[:width] + [""] * (width - len(r)) for r in rows]
    return pd.DataFrame(rows, columns=header)


# --------------------------------------------------------------------------- #
#  Normalisation -> Biometric_Raw rows
# --------------------------------------------------------------------------- #
def normalise(df: pd.DataFrame, *, source_location: str, month_year: str,
              frequency: str = "MONTHLY", default_date=None,
              from_pdf: bool = False) -> tuple[list[dict], list[str]]:
    warnings = []
    mapping = _match_columns(df.columns)

    if "emp_code" not in mapping:
        return [], [f"No employee-code column found. Columns seen: {list(df.columns)}"]
    if "date" not in mapping and default_date is None:
        warnings.append("No Date column and no default date supplied — rows may be undated.")

    upload_date = utils.fmt_date(utils.now_ist().date())
    rows = []
    for _, r in df.iterrows():
        code = str(r.get(mapping["emp_code"], "")).strip()
        if not code or not utils.valid_emp_code(code):
            continue

        # date
        if "date" in mapping and str(r.get(mapping["date"], "")).strip():
            d = utils.parse_date(r.get(mapping["date"]))
        else:
            d = utils.parse_date(default_date)
        att_date = utils.fmt_date(d) if d else ""
        my = utils.month_year_str(d) if d else month_year

        # times
        in_raw = str(r.get(mapping.get("in_time", ""), "")).strip()
        out_raw_full = str(r.get(mapping.get("out_time", ""), "")).strip()
        out_clean, se_flag = utils.clean_time_str(out_raw_full)
        in_clean, se_in = utils.clean_time_str(in_raw)
        se_flag = se_flag or se_in

        dur_raw = str(r.get(mapping.get("duration", ""), "")).strip()
        dur_mins = utils.duration_to_minutes(dur_raw)
        # If single-entry (only one punch) duration is effectively ~0
        if se_flag and dur_mins == 0:
            dur_mins = 1

        status = str(r.get(mapping.get("status", ""), "")).strip()
        remarks = str(r.get(mapping.get("remarks", ""), "")).strip()
        if from_pdf:
            remarks = (remarks + " [PDF-extracted: verify]").strip()

        rows.append({
            "Upload_Date": upload_date,
            "Month_Year": my,
            "Source_Location": source_location,
            "Upload_Frequency": frequency,
            "Attendance_Date": att_date,
            "Emp_Code": code,
            "Emp_Name": str(r.get(mapping.get("emp_name", ""), "")).strip(),
            "Shift": str(r.get(mapping.get("shift", ""), "")).strip() or "GS",
            "In_Time": in_clean,
            "Out_Time": out_clean,
            "Total_Duration_Raw": dur_raw,
            "Total_Duration_Mins": dur_mins,
            "Status_Raw": status,
            "Single_Entry_Flag": "TRUE" if se_flag else "FALSE",
            "Remarks": remarks,
        })

    if not rows:
        warnings.append("No valid employee rows parsed from this file.")
    return rows, warnings


# --------------------------------------------------------------------------- #
#  e-SSL / e-Smart "Daily Summary Report" parser (the real biometric export)
# --------------------------------------------------------------------------- #
_ESMART_DATE = re.compile(
    r"attendance\s*date\s*[-:]\s*(\d{1,2}[-/ ][A-Za-z]{3,9}[-/ ]\d{4})", re.I)
_ESMART_NOISE = re.compile(
    r"(generated|page\s+\d+\s+of|daily summary|defaultcompany|department\s*:|"
    r"s\.?\s*no\s+employee|to\s+\d{1,2}-[a-z]{3,9}-\d{4})", re.I)
_ESMART_ROW = re.compile(
    r"^\d+\s+"                                       # S.No
    r"(?P<code>\S+)\s+"                              # Emp Code
    r"(?P<name>.+?)\s+"                              # Name (lazy; may have wrapped)
    r"(?P<shift>GS|WO|NA)\s+"                        # Shift
    r"(?P<intime>\d{1,2}:\d{2}(?::\d{2})?)\s+"       # In Time
    r"(?P<outtime>\d{1,2}:\d{2}(?::\d{2})?)(?P<se>\(SE\))?\s+"  # Out (+ optional (SE))
    r"(?P<dur>\d{1,2}:\d{2}(?::\d{2})?)\s+"          # Total Duration
    r"(?P<status>\S+)"                               # P/A/WO/WOP/½P/½P(WO)
    r"(?:\s+(?P<remarks>.*))?$")


def _pdf_text(file_like) -> str:
    import pdfplumber
    if hasattr(file_like, "seek"):
        try:
            file_like.seek(0)
        except Exception:
            pass
    data = file_like.read() if hasattr(file_like, "read") else open(file_like, "rb").read()
    src = io.BytesIO(data) if isinstance(data, bytes) else file_like
    pages = []
    with pdfplumber.open(src) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    return "\n".join(pages)


def parse_esmart(text: str, *, source_location: str,
                 frequency: str = "MONTHLY") -> tuple[list[dict], list[str]]:
    """
    Parse an e-SSL/e-Smart 'Daily Summary Report'. Dates appear as section
    headers ('Attendance Date - 01-May-2026') that apply to every row beneath
    until the next header. Tolerates names wrapped over 2-3 lines and the
    WO / WOP / A / P / ½P / ½P(WO) statuses. Works for a single day (daily
    upload) or a whole month — any number of date sections.
    """
    rows, warnings = [], []
    upload_date = utils.fmt_date(utils.now_ist().date())
    current_date = None
    buf: list[str] = []

    def is_block_start(ln: str) -> bool:
        return bool(re.match(r"^\d+\s+\S", ln)) and not _ESMART_DATE.search(ln) \
            and not _ESMART_NOISE.search(ln)

    def flush():
        if not buf:
            return
        line = re.sub(r"\s+", " ", " ".join(buf)).strip()
        buf.clear()
        m = _ESMART_ROW.match(line)
        if not m or current_date is None:
            return
        code = m.group("code").strip()
        if not utils.valid_emp_code(code):
            return
        status = m.group("status").strip()
        se = bool(m.group("se")) or ("½" in status)
        in_raw, out_raw = m.group("intime"), m.group("outtime")
        dur_mins = utils.duration_to_minutes(m.group("dur"))
        if se and dur_mins == 0:
            dur_mins = 1
        rows.append({
            "Upload_Date": upload_date, "Month_Year": utils.month_year_str(current_date),
            "Source_Location": source_location, "Upload_Frequency": frequency,
            "Attendance_Date": utils.fmt_date(current_date), "Emp_Code": code,
            "Emp_Name": m.group("name").strip(), "Shift": m.group("shift"),
            "In_Time": "" if in_raw.startswith("00:00") else in_raw,
            "Out_Time": "" if out_raw.startswith("00:00") else out_raw,
            "Total_Duration_Raw": m.group("dur"), "Total_Duration_Mins": dur_mins,
            "Status_Raw": status, "Single_Entry_Flag": "TRUE" if se else "FALSE",
            "Remarks": (m.group("remarks") or "").strip(),
        })

    for raw in text.splitlines():
        ln = raw.strip()
        if not ln:
            continue
        d = _ESMART_DATE.search(ln)
        if d:
            flush()
            current_date = utils.parse_date(d.group(1).replace("/", "-").replace(" ", "-"))
        elif _ESMART_NOISE.search(ln):
            flush()
        elif is_block_start(ln):
            flush()
            buf.append(ln)
        elif buf:
            buf.append(ln)   # continuation line (name wrapped onto next line)
    flush()

    if not rows:
        warnings.append("No rows parsed from this e-Smart report — check the file & location.")
    return rows, warnings


def parse_biometric(file_like, filename: str, *, source_location: str,
                    month_year: str, frequency: str = "MONTHLY",
                    default_date=None) -> tuple[list[dict], list[str]]:
    """
    Detect the file type and return (Biometric_Raw rows, warnings). Handles the
    real e-Smart 'Daily Summary Report' PDF AND the simple Date/Code/In/Out CSV
    template. Re-uploads are deduped downstream, so the same file can be sent
    daily / weekly / monthly safely.
    """
    name = (filename or "").lower()
    try:
        if name.endswith(".pdf"):
            text = _pdf_text(file_like)
            if _ESMART_DATE.search(text):
                return parse_esmart(text, source_location=source_location, frequency=frequency)
            df = _read_pdf(file_like)
            return normalise(df, source_location=source_location, month_year=month_year,
                             frequency=frequency, default_date=default_date, from_pdf=True)
        # CSV / text
        if hasattr(file_like, "seek"):
            try:
                file_like.seek(0)
            except Exception:
                pass
        data = file_like.read() if hasattr(file_like, "read") else open(file_like, "rb").read()
        raw_text = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else str(data)
        if _ESMART_DATE.search(raw_text):
            return parse_esmart(raw_text, source_location=source_location, frequency=frequency)
        df = _read_csv(io.StringIO(raw_text))
        return normalise(df, source_location=source_location, month_year=month_year,
                         frequency=frequency, default_date=default_date)
    except Exception as e:
        return [], [f"Failed to parse {filename}: {e}"]


# --------------------------------------------------------------------------- #
#  Helpers for the upload page
# --------------------------------------------------------------------------- #
def unmatched_codes(rows: list[dict], employee_df: pd.DataFrame) -> list[str]:
    """Emp codes present in the file but missing from Employee_Master."""
    master = {utils.normalise_emp_code(c) for c in employee_df.get("Emp_Code", [])}
    seen, missing = set(), []
    for r in rows:
        code = utils.normalise_emp_code(r.get("Emp_Code"))
        if code not in master and code not in seen:
            seen.add(code)
            missing.append(r.get("Emp_Code"))
    return missing


def date_range_covered(rows: list[dict]) -> tuple[str, str]:
    dates = sorted(d for d in (utils.parse_date(r.get("Attendance_Date")) for r in rows) if d)
    if not dates:
        return "", ""
    return utils.fmt_date(dates[0]), utils.fmt_date(dates[-1])


def template_dataframe() -> pd.DataFrame:
    return pd.DataFrame(columns=TEMPLATE_COLUMNS)
