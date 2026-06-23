"""
pdf_generator.py
===============
ReportLab PDF output:
  * slips_pdf()  -> print-ready salary slips, 6 per A4 (2 cols x 3 rows) with
                    dotted cut lines, exactly like the handwritten paper chits.
  * table_pdf()  -> generic landscape table (used by Reports & Nashta summary).

Built-in Helvetica has no Rupee glyph, so amounts are prefixed 'Rs' in PDFs.
The on-screen Streamlit UI still uses the proper ₹ symbol.
"""
from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from . import constants as C
from . import utils

GREEN = colors.HexColor("#2E7D32")
RED = colors.HexColor("#C62828")
EARN_TINT = colors.HexColor("#F1F8E9")
DED_TINT = colors.HexColor("#FFEBEE")
GREY = colors.HexColor("#9E9E9E")
DARK = colors.HexColor("#202124")


def _money(v) -> str:
    """Indian-grouped amount, no symbol; 0 -> '-'."""
    n = utils.safe_float(v)
    if round(n) == 0:
        return "-"
    return utils.fmt_inr(n, symbol=False)


def _next_month_label(month_year: str) -> str:
    y, m = utils.parse_month_year(month_year)
    nm = 1 if m == 12 else m + 1
    ny = y + 1 if m == 12 else y
    return utils.month_label(f"{nm:02d}-{ny}").title()


# --------------------------------------------------------------------------- #
#  Salary slips — 6 per A4
# --------------------------------------------------------------------------- #
def slips_pdf(rows: list[dict], month_year: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    margin = 8 * mm
    cols, nrows = 2, 3
    per_page = cols * nrows
    cell_w = (W - 2 * margin) / cols
    cell_h = (H - 2 * margin) / nrows

    rows = list(rows)
    for i, row in enumerate(rows):
        slot = i % per_page
        if i > 0 and slot == 0:
            _cut_lines(c, W, H, margin, cell_w, cell_h, cols, nrows)
            c.showPage()
        cidx, ridx = slot % cols, slot // cols
        x = margin + cidx * cell_w
        y = H - margin - (ridx + 1) * cell_h
        _draw_slip(c, x + 3 * mm, y + 3 * mm, cell_w - 6 * mm, cell_h - 6 * mm,
                   row, month_year)
    _cut_lines(c, W, H, margin, cell_w, cell_h, cols, nrows)
    c.showPage()
    c.save()
    return buf.getvalue()


def _cut_lines(c, W, H, margin, cell_w, cell_h, cols, nrows):
    c.saveState()
    c.setDash(2, 2)
    c.setStrokeColor(GREY)
    c.setLineWidth(0.4)
    for ci in range(1, cols):
        x = margin + ci * cell_w
        c.line(x, margin, x, H - margin)
    for ri in range(1, nrows):
        y = margin + ri * cell_h
        c.line(margin, y, W - margin, y)
    c.restoreState()


def _dd_mm(s) -> str:
    """'01/05/2026' -> '01/05'."""
    s = str(s or "")
    return s[:5] if len(s) >= 5 else s


def _left_items(row: dict) -> list[tuple]:
    """LEFT column = earnings (full base, commissions, TG, extra-present, jama)."""
    items = [("S", row.get("Base_Salary")), ("C", row.get("S_Com")),
             ("B", row.get("B_Com")), ("L", row.get("L_Com"))]
    if utils.safe_float(row.get("TG_Bonus")):
        items.append(("T.G.Ladies", row.get("TG_Bonus")))
    for ln in row.get("_extra_present_lines", []):
        items.append((f"{_dd_mm(ln['date'])} P", ln["amount"]))
    if str(row.get("Nashta_Result")) == "EARNING":
        items.append(("Nashta", row.get("Nashta_Total")))
    for ln in row.get("_jama_lines", []):
        items.append((f"{_dd_mm(ln['date'])} jama", ln["amount"]))
    if not row.get("_jama_lines") and utils.safe_float(row.get("Jama_Total")):
        items.append(("Jama", row.get("Jama_Total")))
    return items


def _cut_caption(run: dict) -> str:
    lbl = run.get("label", "A")
    if run.get("days", 1) > 1:
        return f"{_dd_mm(run['start'])}-{_dd_mm(run['end'])} {lbl}{run['days']}"
    return f"{_dd_mm(run['start'])} {lbl}"


def _right_items(row: dict) -> list[tuple]:
    """RIGHT column = deductions (EPF/ESIC, B/F, interest, dated cuts, advances)."""
    items = []
    permanent = utils.truthy(row.get("Is_Permanent", "TRUE"))
    if permanent:
        items.append(("EPF", row.get("EPF")))
        if utils.safe_float(row.get("ESIC")):
            items.append(("ESIC", row.get("ESIC")))
    if utils.safe_float(row.get("BF_From_Previous")):
        items.append(("B/F", row.get("BF_From_Previous")))
    if utils.safe_float(row.get("Interest")):
        items.append(("Intt.", row.get("Interest")))
    for run in row.get("_cut_lines", []):
        items.append((_cut_caption(run), run["amount"]))
    for ln in row.get("_advance_cash_lines", []):
        items.append((f"{_dd_mm(ln['date'])} cash", ln["amount"]))
    for ln in row.get("_advance_bank_lines", []):
        items.append((f"{_dd_mm(ln['date'])} bank", ln["amount"]))
    if utils.safe_float(row.get("Late_Fine_Total")):
        items.append(("L Fine", row.get("Late_Fine_Total")))
    return items


def _draw_column(c, items, x_label, x_amt, y_top, fnt=5.7, line_h=7.4):
    c.setFont("Helvetica", fnt)
    c.setFillColor(DARK)
    yy, total = y_top, 0.0
    for label, amt in items:
        c.drawString(x_label, yy, str(label)[:24])
        c.drawRightString(x_amt, yy, _money(amt))
        total += utils.safe_float(amt)
        yy -= line_h
    return yy, utils.round_half_up(total)


def _draw_slip(c, x, y, w, h, row: dict, month_year: str):
    is_lena = str(row.get("Result_Type", "")).upper() == "LENA"
    accent = RED if is_lena else GREEN

    c.saveState()
    c.setStrokeColor(accent)
    c.setLineWidth(1.1)
    c.roundRect(x, y, w, h, 3, stroke=1, fill=0)
    c.restoreState()

    pad = 2.5 * mm
    L, R = x + pad, x + w - pad
    midx = x + w / 2
    top = y + h - pad

    # header: Name (code) ............ pay-date
    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(L, top - 7, str(row.get("Emp_Name", ""))[:34])
    c.setFont("Helvetica", 6)
    pay_date = utils.fmt_date(utils.parse_date(row.get("Run_Date")) or utils.now_ist().date())
    c.drawRightString(R, top - 7, pay_date)
    hy = top - 11
    c.setStrokeColor(accent)
    c.setLineWidth(0.6)
    c.line(L, hy, R, hy)

    # two columns
    col_top = hy - 9
    ly, ltot = _draw_column(c, _left_items(row), L + 1, midx - 3, col_top)
    ry, rtot = _draw_column(c, _right_items(row), midx + 4, R - 1, col_top)

    c.setStrokeColor(colors.HexColor("#D7D7D7"))
    c.setLineWidth(0.4)
    c.line(midx, hy, midx, min(ly, ry) - 1)

    # column totals
    tot_y = min(ly, ry) - 1
    c.setStrokeColor(colors.HexColor("#888888"))
    c.setLineWidth(0.4)
    c.line(L + 1, tot_y + 8, midx - 3, tot_y + 8)
    c.line(midx + 4, tot_y + 8, R - 1, tot_y + 8)
    c.setFont("Helvetica-Bold", 6.2)
    c.setFillColor(DARK)
    c.drawRightString(midx - 3, tot_y, _money(ltot))
    c.drawRightString(R - 1, tot_y, _money(rtot))

    # footer band: Dena / Cash dena / HDFC / Lena + bank a/c
    fy = tot_y - 12
    c.setStrokeColor(accent)
    c.setLineWidth(0.5)
    c.line(L, fy + 7, R, fy + 7)

    dena = utils.safe_float(row.get("Dena_Amount", row.get("Net_Payable")))
    hdfc = utils.safe_float(row.get("HDFC_Amount"))
    cash = utils.safe_float(row.get("Cash_Dena_Amount"))
    lena = utils.safe_float(row.get("Lena_Amount"))

    foot = []
    if dena > 0:
        foot.append(("Dena", dena, DARK))
        foot.append(("Cash dena", cash, GREEN))
        if hdfc > 0:
            foot.append(("HDFC", hdfc, DARK))
    if lena > 0:
        foot.append((f"Lena → {_next_month_label(month_year)[:3]}", lena, RED))

    yy = fy
    for label, amt, col in foot:
        c.setFont("Helvetica-Bold", 7)
        c.setFillColor(col)
        c.drawString(L, yy, label)
        c.drawRightString(R, yy, _money(amt))
        yy -= 8.6

    bank = str(row.get("Bank_Account", "")).strip()
    if bank:
        c.setFont("Helvetica-Oblique", 5.4)
        c.setFillColor(DARK)
        c.drawCentredString((L + R) / 2, max(yy, y + pad), f"hdfc Bank A/c {bank}")


# --------------------------------------------------------------------------- #
#  Generic landscape table PDF (Reports / Nashta monthly summary)
# --------------------------------------------------------------------------- #
def table_pdf(title: str, df, subtitle: str = "", money_cols: list | None = None) -> bytes:
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph,
                                    Spacer)
    from reportlab.lib.styles import getSampleStyleSheet

    money_cols = money_cols or []
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=12 * mm,
                            rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm)
    styles = getSampleStyleSheet()
    story = [Paragraph(f"<b>{title}</b>", styles["Title"])]
    if subtitle:
        story.append(Paragraph(subtitle, styles["Normal"]))
    story.append(Spacer(1, 8))

    cols = list(df.columns)
    header = list(cols)
    body = []
    for _, r in df.iterrows():
        line = []
        for ccol in cols:
            v = r[ccol]
            line.append(_money(v) if ccol in money_cols else str(v))
        body.append(line)

    table = Table([header] + body, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#263238")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CFD8DC")),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(table)
    doc.build(story)
    return buf.getvalue()
