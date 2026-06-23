"""
utils.py
========
Date / time helpers, number formatting (Indian rupee grouping), parsers and
validators used across the whole app. No Streamlit or gspread imports here so
this module stays trivially unit-testable.
"""
from __future__ import annotations

import calendar
import re
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

import pytz

IST = pytz.timezone("Asia/Kolkata")


def round_half_up(value) -> int:
    """
    Round to the nearest whole rupee with HALF-UP rounding (0.5 -> 1), matching
    the handwritten chits. Python's built-in round() uses banker's rounding
    (0.5 -> nearest even), which mis-rounds e.g. 330.5 -> 330; the chits need 331.
    """
    try:
        return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except Exception:
        return 0

WEEKDAY_CODES = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]  # Mon=0 .. Sun=6


# --------------------------------------------------------------------------- #
#  Time-of-day
# --------------------------------------------------------------------------- #
def now_ist() -> datetime:
    """Current timezone-aware datetime in IST."""
    return datetime.now(IST)


def now_ist_str(fmt: str = "%d/%m/%Y %I:%M %p") -> str:
    return now_ist().strftime(fmt)


def now_ist_iso() -> str:
    return now_ist().strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------------- #
#  Date parsing / formatting  (DD/MM/YYYY is the canonical display format)
# --------------------------------------------------------------------------- #
def parse_date(value) -> date | None:
    """Parse many date shapes into a date. Returns None if unparseable/blank."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s:
        return None
    # try a sequence of common formats
    fmts = (
        "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y",
        "%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y",
        "%d-%b-%Y", "%d-%B-%Y", "%d %b %Y", "%d %B %Y",  # e-Smart: 01-May-2026
    )
    for f in fmts:
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            continue
    return None


def fmt_date(d) -> str:
    """Format a date as DD/MM/YYYY. Accepts date/datetime/str."""
    if d is None or d == "":
        return ""
    if isinstance(d, str):
        d = parse_date(d)
        if d is None:
            return ""
    if isinstance(d, datetime):
        d = d.date()
    return d.strftime("%d/%m/%Y")


def day_code(d) -> str:
    """Return MON/TUE/... for a date."""
    d = parse_date(d) if not isinstance(d, (date, datetime)) else d
    if isinstance(d, datetime):
        d = d.date()
    return WEEKDAY_CODES[d.weekday()]


def date_range(start, end) -> list[date]:
    """Inclusive list of dates from start to end."""
    start = parse_date(start) if not isinstance(start, date) else start
    end = parse_date(end) if not isinstance(end, date) else end
    if start is None or end is None or end < start:
        return []
    out, cur = [], start
    while cur <= end:
        out.append(cur)
        cur += timedelta(days=1)
    return out


# --------------------------------------------------------------------------- #
#  Month-Year helpers  (canonical string format: "MM-YYYY", e.g. "05-2026")
# --------------------------------------------------------------------------- #
def month_year_str(d) -> str:
    d = parse_date(d) if not isinstance(d, (date, datetime)) else d
    if isinstance(d, datetime):
        d = d.date()
    return f"{d.month:02d}-{d.year}"


def parse_month_year(my: str) -> tuple[int, int]:
    """'05-2026' -> (2026, 5).  Also tolerates '2026-05' and 'May 2026'."""
    my = str(my).strip()
    m = re.match(r"^(\d{1,2})-(\d{4})$", my)
    if m:
        return int(m.group(2)), int(m.group(1))
    m = re.match(r"^(\d{4})-(\d{1,2})$", my)
    if m:
        return int(m.group(1)), int(m.group(2))
    # "May 2026"
    try:
        dt = datetime.strptime(my, "%b %Y")
        return dt.year, dt.month
    except ValueError:
        pass
    try:
        dt = datetime.strptime(my, "%B %Y")
        return dt.year, dt.month
    except ValueError:
        pass
    raise ValueError(f"Unrecognised Month_Year: {my!r}")


def calendar_days_in_month(my: str) -> int:
    """Number of calendar days in a 'MM-YYYY' month (28/29/30/31)."""
    year, month = parse_month_year(my)
    return calendar.monthrange(year, month)[1]


def dates_in_month(my: str) -> list[date]:
    year, month = parse_month_year(my)
    n = calendar.monthrange(year, month)[1]
    return [date(year, month, d) for d in range(1, n + 1)]


def month_label(my: str) -> str:
    """'05-2026' -> 'MAY 2026' (for slips / headers)."""
    year, month = parse_month_year(my)
    return f"{calendar.month_name[month].upper()} {year}"


def month_options(back: int = 6, fwd: int = 1) -> list[str]:
    """List of 'MM-YYYY' strings around the current IST month for dropdowns."""
    base = now_ist().date().replace(day=1)
    out = []
    for off in range(-back, fwd + 1):
        y = base.year + (base.month - 1 + off) // 12
        m = (base.month - 1 + off) % 12 + 1
        out.append(f"{m:02d}-{y}")
    return out


# --------------------------------------------------------------------------- #
#  Time string -> minutes since midnight
# --------------------------------------------------------------------------- #
def clean_time_str(t: str) -> tuple[str, bool]:
    """
    Clean a biometric time cell. Strips a trailing '(SE)' single-entry marker.
    Returns (clean_time_string, single_entry_flag).
    """
    if t is None:
        return "", False
    s = str(t).strip()
    se = "(SE)" in s.upper()
    s = re.sub(r"\(SE\)", "", s, flags=re.IGNORECASE).strip()
    return s, se


def time_to_minutes(t) -> int | None:
    """
    'HH:MM' or 'HH:MM:SS' (24h clock) -> minutes since midnight.
    Returns None for blank/invalid.
    """
    if t is None or t == "":
        return None
    if isinstance(t, time):
        return t.hour * 60 + t.minute
    if isinstance(t, datetime):
        return t.hour * 60 + t.minute
    s, _ = clean_time_str(str(t))
    if not s:
        return None
    m = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$", s)
    if not m:
        return None
    hh, mm = int(m.group(1)), int(m.group(2))
    if hh > 23 or mm > 59:
        return None
    return hh * 60 + mm


def minutes_to_hhmm(mins) -> str:
    if mins is None or mins == "":
        return ""
    mins = int(mins)
    return f"{mins // 60:02d}:{mins % 60:02d}"


def duration_to_minutes(dur) -> int:
    """
    Total-duration cell -> integer minutes.
    Accepts 'HH:MM', 'HH:MM:SS', plain minutes, or '10h 53m' style.
    """
    if dur is None or dur == "":
        return 0
    if isinstance(dur, (int, float)):
        return int(dur)
    s = str(dur).strip()
    if not s:
        return 0
    m = re.match(r"^(\d{1,3}):(\d{2})(?::(\d{2}))?$", s)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    # "10h 53m" / "10h53"
    m = re.match(r"^(\d{1,3})\s*h\s*(\d{1,2})?", s, re.IGNORECASE)
    if m:
        return int(m.group(1)) * 60 + (int(m.group(2)) if m.group(2) else 0)
    try:
        return int(float(s))
    except ValueError:
        return 0


# --------------------------------------------------------------------------- #
#  Number parsing / formatting
# --------------------------------------------------------------------------- #
def safe_float(value, default: float = 0.0) -> float:
    """Robustly coerce a sheet cell to float ('₹1,234', '', '-', None…)."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if s in ("", "-", "—", "NA", "N/A", "None", "nan"):
        return default
    s = s.replace("₹", "").replace(",", "").replace("Rs.", "").replace("Rs", "").strip()
    try:
        return float(s)
    except ValueError:
        return default


def safe_int(value, default: int = 0) -> int:
    return int(round(safe_float(value, default)))


def fmt_inr(amount, *, decimals: bool = False, symbol: bool = True) -> str:
    """
    Format a number with Indian digit grouping (e.g. 1,23,456).
    fmt_inr(123456) -> '₹1,23,456'
    """
    if amount is None or amount == "":
        amount = 0
    amount = safe_float(amount)
    neg = amount < 0
    amount = abs(amount)
    if decimals:
        whole = int(amount)
        frac = f"{amount - whole:.2f}"[2:]
    else:
        whole = int(round(amount))
        frac = None
    s = str(whole)
    # Indian grouping: last 3 digits, then groups of 2
    if len(s) > 3:
        last3 = s[-3:]
        rest = s[:-3]
        rest = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", rest)
        grouped = f"{rest},{last3}"
    else:
        grouped = s
    out = grouped + (f".{frac}" if frac is not None else "")
    if symbol:
        out = "₹" + out
    return ("-" + out) if neg else out


def fmt_inr_or_dash(amount, **kw) -> str:
    """Like fmt_inr but renders 0 as '-' (matches the paper-chit style)."""
    if safe_float(amount) == 0:
        return "-"
    return fmt_inr(amount, **kw)


# --------------------------------------------------------------------------- #
#  Validators
# --------------------------------------------------------------------------- #
def valid_emp_code(code) -> bool:
    """Emp codes are short alphanumerics ('1', '02', '300', '78')."""
    s = str(code).strip()
    return bool(s) and len(s) <= 8 and re.match(r"^[A-Za-z0-9]+$", s) is not None


def normalise_emp_code(code) -> str:
    """
    Normalise codes for matching: strip, drop leading zeros so '02' == '2',
    upper-case. Biometric machines and the master sheet disagree on padding.
    """
    s = str(code).strip().upper()
    if s.isdigit():
        return str(int(s))
    return s


def valid_account_number(acct) -> bool:
    s = re.sub(r"\s", "", str(acct))
    return s.isdigit() and 6 <= len(s) <= 20 if s else True  # blank allowed


def valid_ifsc(ifsc) -> bool:
    s = str(ifsc).strip().upper()
    if not s:
        return True  # blank allowed
    return re.match(r"^[A-Z]{4}0[A-Z0-9]{6}$", s) is not None


def truthy(value) -> bool:
    """Interpret sheet booleans: TRUE/True/1/yes -> True."""
    if isinstance(value, bool):
        return value
    return str(value).strip().upper() in ("TRUE", "1", "YES", "Y", "T")
