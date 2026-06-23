"""Page 3 — Biometric Upload (multi-location, CSV/PDF, dedup, SE review)."""
import pandas as pd
import streamlit as st

from modules import biometric_parser as bp
from modules import constants as C, processing, reporting, sheets_sync as db, ui, utils

ui.page_header("Biometric Upload", "📤",
               "Upload daily / weekly / monthly biometric exports (CSV or PDF). "
               "Re-uploading is safe — duplicates are skipped automatically.")

month = st.session_state.month
admin = st.session_state.admin


def _resolve_single_entry(item, choice, month, admin):
    """Edit the underlying biometric row to reflect the admin's decision."""
    if choice == "(keep ABSENT)":
        return
    dur = {"Full Present": 600, "Half Day": 300, "Quarter Day": 150}[choice]
    df = db.read(C.TAB_BIOMETRIC)
    code = utils.normalise_emp_code(item["Emp_Code"])
    mask = (df["Emp_Code"].apply(utils.normalise_emp_code) == code) & \
           (df["Attendance_Date"].apply(utils.fmt_date) == item["Attendance_Date"])
    df.loc[mask, "Total_Duration_Mins"] = str(dur)
    df.loc[mask, "Single_Entry_Flag"] = "FALSE"
    df.loc[mask, "Out_Time"] = "21:30:00"
    df.loc[mask, "Remarks"] = f"SE resolved → {choice} by {admin}"
    db.write(C.TAB_BIOMETRIC, df)
    db.log_sync("MANUAL_OVERRIDE", f"SE {item['Emp_Code']} {item['Attendance_Date']} → {choice}", admin)
    reporting.persist_month(month, ui.active_location(), admin)
    st.success(f"Resolved {item['Emp_Name']} {item['Attendance_Date']} → {choice}")

# --------------------------------------------------------------------------- #
#  Upload form
# --------------------------------------------------------------------------- #
st.markdown("#### 1 · Upload files")
c1, c2, c3 = st.columns(3)
location = c1.selectbox("Location (machine)", C.LOCATIONS, index=0)
frequency = c2.selectbox("Upload frequency", ["MONTHLY", "WEEKLY", "DAILY"])
default_date = c3.date_input("Default date (for files with no Date column)",
                             value=utils.now_ist().date(), format="DD/MM/YYYY")

with st.expander("📄 Need the import format? Download a blank template"):
    st.dataframe(bp.template_dataframe(), use_container_width=True, hide_index=True)
    st.download_button("⬇️ Template CSV", bp.template_dataframe().to_csv(index=False).encode(),
                       "biometric_template.csv", "text/csv")
    st.caption("A sample is in the repo: seed_data/sample_upload_KN_June2026.csv")

files = st.file_uploader("Drag & drop CSV / PDF files (multiple allowed)",
                         type=["csv", "pdf"], accept_multiple_files=True)

if files:
    all_rows, summaries = [], []
    for f in files:
        rows, warns = bp.parse_biometric(
            f, f.name, source_location=location, month_year=month,
            frequency=frequency, default_date=utils.fmt_date(default_date))
        all_rows += rows
        d0, d1 = bp.date_range_covered(rows)
        summaries.append({"File": f.name, "Rows": len(rows),
                          "Dates": f"{d0} → {d1}" if d0 else "—",
                          "Warnings": " | ".join(warns) if warns else "OK"})

    st.markdown("#### 2 · Preview")
    st.dataframe(pd.DataFrame(summaries), use_container_width=True, hide_index=True)

    # unmatched codes
    missing = bp.unmatched_codes(all_rows, db.get_employees())
    if missing:
        st.warning(f"⚠️ {len(missing)} code(s) in the file are NOT in Employee Master: "
                   f"{', '.join(map(str, missing[:20]))}. Add them on the Employees page.")

    if all_rows:
        st.dataframe(pd.DataFrame(all_rows).head(100), use_container_width=True, hide_index=True)

        st.markdown("#### 3 · Save & process")
        if st.button(f"💾 Process & Save {len(all_rows)} rows", type="primary"):
            res = db.save_biometric_rows(all_rows, admin)
            stats = reporting.persist_month(month, location, admin)
            st.success(
                f"✅ {res['inserted']} new rows saved, {res['skipped']} duplicates skipped. "
                f"Processed {stats['rows']} attendance rows for {stats['employees']} employees · "
                f"{stats['overrides']} overrides applied · {stats['single_entries']} single-entries flagged.")
            st.cache_data.clear() if hasattr(st, "cache_data") else None

st.divider()

# --------------------------------------------------------------------------- #
#  Single-entry review panel
# --------------------------------------------------------------------------- #
st.markdown("#### 🔎 Single-Entry (½P) Review")
st.caption("Punches with only one entry default to ABSENT until you decide. "
           "Resolving updates the biometric record and re-processes the month.")

emps = db.get_employees(ui.active_location(), active_only=True)
bio = db.get_biometric(month)
flagged = processing.single_entry_reviews(emps, month, bio, db.get_overrides(month),
                                          db.holiday_dates())

if not flagged:
    st.success("No single-entry rows pending review. 🎉")
else:
    for i, item in enumerate(flagged):
        cols = st.columns([3, 2, 2, 2, 3])
        cols[0].markdown(f"**{item['Emp_Name']}** ({item['Emp_Code']})")
        cols[1].write(item["Attendance_Date"])
        cols[2].write(f"In: {item['In_Time'] or '—'}")
        cols[3].write(f"Out: {item['Out_Time'] or '—'}")
        choice = cols[4].selectbox("Resolve", ["(keep ABSENT)", "Full Present", "Half Day",
                                   "Quarter Day"], key=f"se_{i}", label_visibility="collapsed")
        if cols[4].button("Apply", key=f"seapply_{i}"):
            _resolve_single_entry(item, choice, month, admin)
            st.rerun()
