"""Page 1 — Manager Dashboard."""
import pandas as pd
import plotly.express as px
import streamlit as st

from modules import reporting, ui, utils
from modules import salary_engine as eng

ui.page_header("Manager Dashboard", "🏠",
               "Live attendance & payroll overview — filtered by the month/location in the sidebar.")

month = st.session_state.month
loc = ui.active_location()
loc_label = st.session_state.location

with st.spinner("Crunching attendance & payroll…"):
    m = reporting.dashboard_metrics(month, loc)

st.markdown(f"**{utils.month_label(month)} · {loc_label}**")

ui.kpi_row([
    ("👥 Active Employees", m["active"]),
    (f"✅ Present ({m['ref_day']})", m["present_today"]),
    (f"❌ Absent ({m['ref_day']})", m["absent_today"]),
    ("🛌 On Week Off", m["weekoff_today"]),
])
ui.kpi_row([
    ("💵 Total Cash Dena", ui.money(m["total_payroll"])),
    ("📕 Total Lena", ui.money(m["total_lena"])),
    ("⏰ Late Fine Collected", ui.money(m["late_fine"])),
    ("🍵 Net Nashta", ui.money(m["nashta_expense"])),
])
ui.kpi_row([
    ("🏦 EPF Liability", ui.money(m["epf"])),
    ("🩺 ESIC Liability", ui.money(m["esic"])),
    ("💸 Advances", ui.money(m["advances"])),
    ("🔎 Pending SE Reviews", m["pending_se"]),
])

st.divider()
processed = m["processed"]

if not processed:
    ui.empty("No active employees / data for this month & location yet. "
             "Add employees and upload biometric data to get started.")
    st.stop()

# --- Build chart data from processed days -----------------------------------
absent_rows, status_counts = [], {"Present": 0, "Absent": 0, "Week Off Present": 0}
daily_present = {}
for code, (emp, days) in processed.items():
    a = sum(1 for r in days if r.final_status in ("ABSENT", "DOUBLE_ABSENT"))
    absent_rows.append({"Employee": emp.get("Emp_Name", ""), "Absent Days": a})
    for r in days:
        if r.final_status in eng.PRESENT_STATUSES and r.final_status != "EXTRA_PRESENT":
            status_counts["Present"] += 1
        elif r.final_status == "EXTRA_PRESENT":
            status_counts["Week Off Present"] += 1
        elif r.final_status in ("ABSENT", "DOUBLE_ABSENT"):
            status_counts["Absent"] += 1
        if r.final_status in eng.PRESENT_STATUSES:
            daily_present[r.attendance_date] = daily_present.get(r.attendance_date, 0) + 1

c1, c2 = st.columns(2)
with c1:
    ui.section("Top Absences", "📉")
    adf = pd.DataFrame(absent_rows).sort_values("Absent Days", ascending=False).head(10)
    fig = px.bar(adf, x="Absent Days", y="Employee", orientation="h",
                 color="Absent Days", color_continuous_scale="Reds")
    fig.update_layout(height=320, margin=dict(l=0, r=0, t=10, b=0), yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, use_container_width=True)
with c2:
    ui.section("Attendance Split", "🥧")
    sdf = pd.DataFrame({"Status": list(status_counts), "Days": list(status_counts.values())})
    fig = px.pie(sdf, names="Status", values="Days", hole=0.45,
                 color="Status", color_discrete_map={"Present": "#34A853",
                 "Absent": "#EA4335", "Week Off Present": "#1A73E8"})
    fig.update_layout(height=320, margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig, use_container_width=True)

ui.section("Daily Present Count", "📈")
ddf = pd.DataFrame([{"Date": k, "Present": v} for k, v in daily_present.items()])
if not ddf.empty:
    ddf["_d"] = ddf["Date"].apply(utils.parse_date)
    ddf = ddf.sort_values("_d")
    fig = px.line(ddf, x="Date", y="Present", markers=True)
    fig.update_layout(height=260, margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig, use_container_width=True)

# --- Alerts -----------------------------------------------------------------
st.divider()
ui.section("Alerts", "🚨")
emps = {code: emp for code, (emp, _) in processed.items()}
chronic = [emps[c].get("Emp_Name") for c, n in m["late_counts"].items() if n >= 5]
a1, a2, a3 = st.columns(3)
with a1:
    st.markdown("**🟠 5+ late arrivals**")
    st.write("\n".join(f"- {n}" for n in chronic) or "None 🎉")
with a2:
    st.markdown("**🟡 Single-entry reviews**")
    st.write(f"{m['pending_se']} pending — see Biometric Upload page")
with a3:
    st.markdown("**🔴 High advances (>2× salary)**")
    flagged = []
    for code, (emp, _) in processed.items():
        adv = reporting.db.advances_for(code, month)
        if adv["total"] > 2 * utils.safe_float(emp.get("Base_Salary")) and adv["total"] > 0:
            flagged.append(emp.get("Emp_Name"))
    st.write("\n".join(f"- {n}" for n in flagged) or "None")

# --- Cash Dena / Lena tabs --------------------------------------------------
st.divider()
pay = m["payroll_df"]
tabA, tabB = st.tabs(["🟢 Cash Dena (pay out)", "🔴 Lena (recover)"])
with tabA:
    if not pay.empty:
        dena = pay[pay["Result_Type"] == "CASH_DENA"][
            ["Emp_Name", "Net_Payable", "Bank_Account"]].copy()
        dena["Net_Payable"] = dena["Net_Payable"].apply(ui.money)
        st.dataframe(dena.rename(columns={"Emp_Name": "Name", "Net_Payable": "Net Amount",
                     "Bank_Account": "Bank A/C"}), use_container_width=True, hide_index=True)
with tabB:
    if not pay.empty:
        lena = pay[pay["Result_Type"] == "LENA"][["Emp_Name", "Lena_Amount"]].copy()
        if lena.empty:
            st.success("No Lena this month — everyone is Cash Dena. 🎉")
        else:
            lena["Lena_Amount"] = lena["Lena_Amount"].apply(ui.money)
            st.dataframe(lena.rename(columns={"Emp_Name": "Name", "Lena_Amount": "Lena Amount"}),
                         use_container_width=True, hide_index=True)
