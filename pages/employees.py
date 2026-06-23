"""Page 2 — Employee Master."""
import pandas as pd
import streamlit as st

from modules import constants as C, sheets_sync as db, ui, utils

ui.page_header("Employee Master", "👥",
               "Add, edit and (soft) delete employees. Changes save to Google Sheets / local DB.")


def _validate(edited: pd.DataFrame) -> list:
    errs = []
    codes = [str(x).strip() for x in edited["Emp_Code"] if str(x).strip()]
    if len(codes) != len(set(utils.normalise_emp_code(c) for c in codes)):
        errs.append("Duplicate Emp_Code found — codes must be unique.")
    for _, r in edited.iterrows():
        if str(r["Emp_Code"]).strip() and utils.safe_float(r["Base_Salary"]) <= 0:
            errs.append(f"{r['Emp_Name'] or r['Emp_Code']}: Base salary must be positive.")
    return errs


loc = ui.active_location()
df = db.get_employees(location=loc)

st.caption(f"{len(df)} employees" + (f" in {st.session_state.location}" if loc else " (all locations)"))

tab_grid, tab_add = st.tabs(["📋 Edit grid", "➕ Add employee"])

# --------------------------------------------------------------------------- #
#  Editable grid
# --------------------------------------------------------------------------- #
with tab_grid:
    if df.empty:
        ui.empty("No employees yet. Use the ‘Add employee’ tab.")
    else:
        disp = df.copy()
        for col in ["Base_Salary", "EPF", "ESIC", "TG_Ladies_Bonus"]:
            disp[col] = pd.to_numeric(disp[col], errors="coerce").fillna(0).astype(int)
        disp["Is_Active"] = disp["Is_Active"].apply(utils.truthy)
        disp["Is_Permanent"] = disp["Is_Permanent"].apply(utils.truthy)
        edited = st.data_editor(
            disp, use_container_width=True, num_rows="dynamic", key="emp_editor",
            column_config={
                "Emp_Code": st.column_config.TextColumn("Code", width="small", required=True),
                "Emp_Name": st.column_config.TextColumn("Name", width="medium", required=True),
                "Gender": st.column_config.SelectboxColumn("Gender", options=C.GENDERS),
                "Location": st.column_config.SelectboxColumn("Location", options=C.LOCATIONS),
                "Department": st.column_config.SelectboxColumn("Dept", options=C.DEPARTMENTS),
                "Shift_Exception": st.column_config.SelectboxColumn("Shift Exc.", options=C.SHIFT_EXCEPTIONS),
                "Base_Salary": st.column_config.NumberColumn("Base ₹", min_value=0, step=100),
                "EPF": st.column_config.NumberColumn("EPF ₹", min_value=0),
                "ESIC": st.column_config.NumberColumn("ESIC ₹", min_value=0),
                "Week_Off_Default": st.column_config.SelectboxColumn("Week Off", options=C.WEEK_DAYS),
                "Is_Active": st.column_config.CheckboxColumn("Active"),
                "Is_Permanent": st.column_config.CheckboxColumn("Perm (EPF/ESIC)"),
            },
        )
        c1, c2 = st.columns([1, 3])
        if c1.button("💾 Save all changes", type="primary", use_container_width=True):
            errs = _validate(edited)
            if errs:
                for e in errs:
                    st.error(e)
            else:
                out = edited.copy()
                for flag in ["Is_Active", "Is_Permanent"]:
                    out[flag] = out[flag].apply(lambda b: "TRUE" if utils.truthy(b) else "FALSE")
                for col in ["Base_Salary", "EPF", "ESIC", "TG_Ladies_Bonus"]:
                    out[col] = out[col].apply(lambda v: str(utils.safe_int(v)))
                db.save_employees_bulk(out, st.session_state.admin)
                st.success("Saved. ✓")
                st.rerun()
        c2.caption("Tip: tick/untick **Active** to soft-delete. Add a row at the bottom to insert.")

# --------------------------------------------------------------------------- #
#  Add employee form
# --------------------------------------------------------------------------- #
with tab_add:
    with st.form("add_emp", clear_on_submit=True):
        a, b, c = st.columns(3)
        code = a.text_input("Emp Code *")
        name = b.text_input("Full Name *")
        short = c.text_input("Short Code (e.g. BM)")
        a, b, c = st.columns(3)
        gender = a.selectbox("Gender", C.GENDERS)
        location = b.selectbox("Location", C.LOCATIONS)
        dept = c.selectbox("Department", C.DEPARTMENTS)
        a, b, c = st.columns(3)
        shift_exc = a.selectbox("Shift Exception", C.SHIFT_EXCEPTIONS)
        base = b.number_input("Base Salary ₹", min_value=0, step=100, value=20000)
        weekoff = c.selectbox("Week Off", C.WEEK_DAYS)
        a, b, c = st.columns(3)
        epf = a.number_input("EPF ₹", min_value=0, value=1800)
        esic = b.number_input("ESIC ₹", min_value=0, value=0)
        tg = c.number_input("TG Ladies Bonus ₹", min_value=0, value=0)
        a, b, c = st.columns(3)
        bank = a.text_input("Bank Name")
        acct = b.text_input("Account Number")
        ifsc = c.text_input("IFSC")
        is_perm = st.checkbox("Permanent (EPF/ESIC apply)", value=epf > 0)
        submitted = st.form_submit_button("➕ Add employee", type="primary")
        if submitted:
            errs = []
            if not utils.valid_emp_code(code):
                errs.append("Emp Code is required and must be alphanumeric.")
            if db.get_employee(code):
                errs.append(f"Emp Code {code} already exists.")
            if not name.strip():
                errs.append("Name is required.")
            if not utils.valid_ifsc(ifsc):
                errs.append("IFSC format looks invalid (e.g. HDFC0001234).")
            if errs:
                for e in errs:
                    st.error(e)
            else:
                db.save_employee({
                    "Emp_Code": code, "Emp_Name": name, "Short_Code": short.upper(),
                    "Gender": gender, "Location": location, "Department": dept,
                    "Shift_Type": "GS", "Shift_Exception": shift_exc, "Base_Salary": base,
                    "EPF": epf, "ESIC": esic, "Bank_Name": bank, "Account_Number": acct,
                    "IFSC": ifsc.upper(), "TG_Ladies_Bonus": tg, "Week_Off_Default": weekoff,
                    "Is_Active": "TRUE", "Is_Permanent": "TRUE" if is_perm else "FALSE",
                    "Joined_Date": utils.fmt_date(utils.now_ist().date()), "Notes": "",
                }, st.session_state.admin)
                st.success(f"Added {name}. ✓")
                st.rerun()
