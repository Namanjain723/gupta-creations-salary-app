"""Page 7 — Salary Slips (two-sided dated chit: preview + per-employee PDF + 6-per-A4)."""
import streamlit as st

from modules import pdf_generator as pdf
from modules import reporting, sheets_sync as db, ui, utils

ui.page_header("Salary Slips", "📄",
               "Two-sided dated chits — LEFT = earnings, RIGHT = deductions — exactly like "
               "the paper slips. Preview, download per-employee, or print 6 per A4.")

month = st.session_state.month
loc = ui.active_location()


def _col_html(items, accent):
    body = "".join(
        f"<tr><td style='padding:1px 4px'>{k}</td>"
        f"<td style='padding:1px 4px;text-align:right'>{ui.money(v, dash=True)}</td></tr>"
        for k, v in items)
    total = utils.round_half_up(sum(utils.safe_float(v) for _, v in items))
    return (f"<table style='width:100%;border-collapse:collapse'>{body}"
            f"<tr style='border-top:1px solid #bbb;font-weight:700'>"
            f"<td style='padding:2px 4px'></td>"
            f"<td style='padding:2px 4px;text-align:right;color:{accent}'>{ui.money(total)}</td>"
            f"</tr></table>")


def _slip_html(r) -> str:
    is_lena = str(r.get("Result_Type")) == "LENA"
    accent = "#C62828" if is_lena else "#2E7D32"
    left = _col_html(pdf._left_items(r), accent)
    right = _col_html(pdf._right_items(r), accent)

    foot = []
    if utils.safe_float(r.get("Dena_Amount")) > 0:
        foot.append(("Dena", r.get("Dena_Amount"), "#202124"))
        foot.append(("Cash dena", r.get("Cash_Dena_Amount"), "#2E7D32"))
        if utils.safe_float(r.get("HDFC_Amount")) > 0:
            foot.append(("HDFC", r.get("HDFC_Amount"), "#202124"))
    if utils.safe_float(r.get("Lena_Amount")) > 0:
        foot.append(("Lena (carry forward)", r.get("Lena_Amount"), "#C62828"))
    foot_html = "".join(
        f"<div style='display:flex;justify-content:space-between;font-weight:700;color:{col}'>"
        f"<span>{k}</span><span>{ui.money(v)}</span></div>" for k, v, col in foot)
    bank = str(r.get("Bank_Account", "")).strip()
    bank_html = (f"<div style='text-align:center;font-style:italic;color:#666;font-size:11px;"
                 f"margin-top:4px'>hdfc Bank A/c {bank}</div>" if bank else "")

    return f"""
    <div style="border:2px solid {accent};border-radius:10px;padding:12px;max-width:460px;
                font-size:12px;background:#fff;box-shadow:0 1px 6px rgba(0,0,0,.08)">
      <div style="display:flex;justify-content:space-between;font-weight:700;font-size:13px">
        <span>{r.get('Emp_Name')}</span><span>{r.get('Emp_Code')}</span></div>
      <hr style="border:none;border-top:1.5px solid {accent};margin:4px 0">
      <div style="display:flex;gap:14px">
        <div style="width:50%">{left}</div>
        <div style="width:50%;border-left:1px solid #e0e0e0;padding-left:8px">{right}</div>
      </div>
      <hr style="border:none;border-top:1.5px solid {accent};margin:6px 0">
      {foot_html}{bank_html}
    </div>"""


# --- always render from LIVE enriched records (dated lines present) ----------
pay_df, _ = reporting.build_payroll_rows(month, loc)
rows = pay_df.to_dict("records") if not pay_df.empty else []
if db.get_payroll(month).empty:
    st.info("Live preview — payroll not locked yet. Run payroll to save this month.")
else:
    st.caption("✓ Payroll is locked for this month (slips reflect the latest data).")

if not rows:
    ui.empty("No payroll data for this month. Add employees / upload biometric, then run payroll.")
    st.stop()

c1, c2 = st.columns(2)
rtype = c1.selectbox("Result type", ["ALL", "CASH_DENA", "LENA"])
names = ["ALL"] + [r.get("Emp_Name") for r in rows]
who = c2.selectbox("Employee", names)
view = [r for r in rows
        if (rtype == "ALL" or r.get("Result_Type") == rtype)
        and (who == "ALL" or r.get("Emp_Name") == who)]

ui.section("Bulk Print (6 per A4)", "🖨️")
st.download_button(f"⬇️ Generate Print Sheet — {len(view)} slips",
                   pdf.slips_pdf(view, month),
                   f"Slips_{utils.month_label(month).replace(' ', '')}.pdf",
                   "application/pdf", type="primary", disabled=not view)
st.divider()

tabA, tabB = st.tabs(["🟢 Cash Dena", "🔴 Lena"])
for tab, rt in [(tabA, "CASH_DENA"), (tabB, "LENA")]:
    with tab:
        group = [r for r in view if r.get("Result_Type") == rt]
        if not group:
            st.info(f"No {rt.replace('_', ' ').title()} employees in this view.")
        for r in group:
            label = (ui.money(r.get("Cash_Dena_Amount")) if rt == "CASH_DENA"
                     else ui.money(r.get("Lena_Amount")))
            with st.expander(f"{r.get('Emp_Name')} — {label} ({rt.replace('_', ' ').title()})"):
                st.markdown(_slip_html(r), unsafe_allow_html=True)
                st.download_button("⬇️ Download this slip (PDF)",
                                   pdf.slips_pdf([r], month),
                                   f"Slip_{r.get('Emp_Code')}_{utils.month_label(month).replace(' ', '')}.pdf",
                                   "application/pdf", key=f"slip_{r.get('Emp_Code')}")
