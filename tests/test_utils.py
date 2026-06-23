"""Unit tests for utils helpers."""
from modules import utils


def test_time_to_minutes():
    assert utils.time_to_minutes("10:30") == 630
    assert utils.time_to_minutes("10:47") == 647
    assert utils.time_to_minutes("11:30:00") == 690
    assert utils.time_to_minutes("") is None
    assert utils.time_to_minutes("21:00:00 (SE)") == 1260


def test_duration_to_minutes():
    assert utils.duration_to_minutes("10:53") == 653
    assert utils.duration_to_minutes("08:00") == 480
    assert utils.duration_to_minutes("0:00") == 0
    assert utils.duration_to_minutes("480") == 480


def test_clean_time_str_single_entry():
    clean, se = utils.clean_time_str("21:30:00(SE)")
    assert clean == "21:30:00" and se is True
    clean, se = utils.clean_time_str("10:30:00")
    assert clean == "10:30:00" and se is False


def test_calendar_days():
    assert utils.calendar_days_in_month("05-2026") == 31
    assert utils.calendar_days_in_month("06-2026") == 30
    assert utils.calendar_days_in_month("02-2024") == 29
    assert utils.calendar_days_in_month("02-2026") == 28


def test_month_year_parse():
    assert utils.parse_month_year("05-2026") == (2026, 5)
    assert utils.month_label("05-2026") == "MAY 2026"


def test_indian_number_format():
    assert utils.fmt_inr(710, symbol=False) == "710"
    assert utils.fmt_inr(22000, symbol=False) == "22,000"
    assert utils.fmt_inr(123456, symbol=False) == "1,23,456"
    assert utils.fmt_inr(15234, symbol=False) == "15,234"
    assert utils.fmt_inr(-8450, symbol=False) == "-8,450"


def test_normalise_emp_code():
    assert utils.normalise_emp_code("02") == "2"
    assert utils.normalise_emp_code("27") == "27"
    assert utils.normalise_emp_code(" bm ") == "BM"


def test_day_code_known_dates():
    # 1 May 2026 is a Friday; 4 May 2026 is a Monday
    assert utils.day_code("01/05/2026") == "FRI"
    assert utils.day_code("04/05/2026") == "MON"


def test_truthy():
    assert utils.truthy("TRUE") and utils.truthy("1") and utils.truthy("Yes")
    assert not utils.truthy("FALSE") and not utils.truthy("")
