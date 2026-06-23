"""
constants.py
============
Single source of truth for:
  * Google-Sheet tab names + their exact column schemas (must match the
    Apps Script setup script and what sheets_sync reads/writes).
  * Master enumerations (locations, departments, shift exceptions).
  * UI theme colours.

Everything else in the app imports column lists from here so a schema change
happens in exactly one place.
"""

APP_NAME = "Gupta Creations Pvt. Ltd. — Salary Management"
APP_VERSION = "2.0 (real-slip engine + config)"
COMPANY_NAME = "GUPTA CREATIONS PVT. LTD."

# --------------------------------------------------------------------------- #
#  Tab names
# --------------------------------------------------------------------------- #
TAB_EMPLOYEE = "Employee_Master"
TAB_BIOMETRIC = "Biometric_Raw"
TAB_ATTENDANCE = "Attendance_Processed"
TAB_NASHTA_LEDGER = "Nashta_Ledger"
TAB_NASHTA_SUMMARY = "Nashta_Monthly_Summary"
TAB_OVERRIDES = "Manual_Overrides"
TAB_LEDGER = "Variable_Ledger"
TAB_SALES_KN = "SALE_REPORT_KN"
TAB_PAYROLL = "Payroll_Final"
TAB_HOLIDAYS = "Holidays"
TAB_CONFIG = "Config"
TAB_SYNC_LOG = "Sync_Log"

# --------------------------------------------------------------------------- #
#  Column schemas — order matters (matches the Apps Script header rows).
# --------------------------------------------------------------------------- #
COLUMNS = {
    TAB_EMPLOYEE: [
        "Emp_Code", "Emp_Name", "Short_Code", "Gender", "Location", "Department",
        "Shift_Type", "Shift_Exception", "Base_Salary", "EPF", "ESIC", "Bank_Name",
        "Account_Number", "IFSC", "TG_Ladies_Bonus", "Week_Off_Default", "Is_Active",
        "Is_Permanent", "Joined_Date", "Notes",
    ],
    TAB_BIOMETRIC: [
        "Upload_Date", "Month_Year", "Source_Location", "Upload_Frequency",
        "Attendance_Date", "Emp_Code", "Emp_Name", "Shift", "In_Time", "Out_Time",
        "Total_Duration_Raw", "Total_Duration_Mins", "Status_Raw",
        "Single_Entry_Flag", "Remarks",
    ],
    TAB_ATTENDANCE: [
        "Month_Year", "Emp_Code", "Emp_Name", "Attendance_Date", "Day_Type",
        "Raw_Status", "Manual_Override", "Override_Applied_By", "Final_Status",
        "Attendance_Value", "Punch_In", "Punch_Out", "Duration_Mins",
        "Late_Fine_Amount", "Nashta_Daily", "Nashta_Sign", "Daily_Wage_Rate",
        "Day_Deduction", "Notes",
    ],
    TAB_NASHTA_LEDGER: [
        "Month_Year", "Emp_Code", "Emp_Name", "Location", "Attendance_Date",
        "Day_Of_Week", "Punch_In_Time", "Biometric_Status", "Late_Fine_Slab",
        "Nashta_Base", "Nashta_Daily", "Nashta_Sign", "Notes",
    ],
    TAB_NASHTA_SUMMARY: [
        "Month_Year", "Emp_Code", "Emp_Name", "Location", "Total_Present_Days",
        "OnTime_Days", "Late_Days_16", "Late_Days_32", "Late_Days_48",
        "Late_Days_64", "Late_Days_80", "Nashta_Earned_Positive",
        "Nashta_Deducted_Negative", "Net_Monthly_Nashta", "Monthly_Result",
    ],
    TAB_OVERRIDES: [
        "Override_ID", "Month_Year", "Emp_Code", "Emp_Name", "Override_Date",
        "Override_Date_End", "Override_Type", "New_Week_Off_Day", "Notes",
        "Applied_By", "Applied_At", "Is_Active",
    ],
    TAB_LEDGER: [
        "Ledger_ID", "Month_Year", "Emp_Code", "Emp_Name", "Entry_Date",
        "Entry_Type", "Amount", "Notes", "Entered_By", "Entered_At",
    ],
    TAB_SALES_KN: [
        "Month_Year", "Emp_Code", "Emp_Name", "Short_Code", "S_Com", "B_Com",
        "L_Com", "Total_Commission", "Notes",
    ],
    TAB_PAYROLL: [
        "Payroll_ID", "Month_Year", "Run_Date", "Emp_Code", "Emp_Name", "Is_Permanent",
        "Base_Salary", "Calendar_Days", "Daily_Rate", "Present_Days", "Extra_Present_Days",
        "Attendance_Fraction", "Earned_Salary", "S_Com", "B_Com", "L_Com",
        "TG_Bonus", "Extra_Present_Pay", "Nashta_Total", "Nashta_Result",
        "BF_From_Previous", "Gross_Earnings", "EPF", "ESIC", "Late_Fine_Total",
        "Nashta_Deduction", "Advance_Cash_Total", "Advance_Bank_Total", "Jama_Total",
        "Interest", "Absent_Deduction", "Total_Deductions", "Dena_Amount", "Net_Payable",
        "HDFC_Amount", "Result_Type", "Cash_Dena_Amount", "Lena_Amount", "Bank_Account",
        "Slip_Generated", "Notes",
    ],
    TAB_HOLIDAYS: ["Holiday_Date", "Holiday_Name", "Applicable_To"],
    TAB_CONFIG: ["Scope", "Key", "Value", "Value_Type", "Group", "Label", "Notes"],
    TAB_SYNC_LOG: ["Timestamp", "Action", "Details", "Admin"],
}

# Tab colours (used by the Apps Script and shown as legend in-app)
TAB_COLORS = {
    TAB_EMPLOYEE: "#4285F4", TAB_BIOMETRIC: "#FF6D00", TAB_ATTENDANCE: "#0F9D58",
    TAB_NASHTA_LEDGER: "#76FF03", TAB_NASHTA_SUMMARY: "#CCFF90",
    TAB_OVERRIDES: "#F4B400", TAB_LEDGER: "#7B1FA2", TAB_SALES_KN: "#00897B",
    TAB_PAYROLL: "#DB4437", TAB_HOLIDAYS: "#E91E63", TAB_CONFIG: "#455A64",
    TAB_SYNC_LOG: "#9E9E9E",
}

ALL_TABS = list(COLUMNS.keys())

# --------------------------------------------------------------------------- #
#  Master enumerations
# --------------------------------------------------------------------------- #
LOCATIONS = [
    "KAMLA NAGAR", "ROHINI", "MDO", "WAREHOUSE", "MERCHANDISER",
    "GUPTA GARMENTS", "SUITS HIM",
]
# Phase-1 configured locations (others show a "not yet configured" placeholder)
ACTIVE_LOCATIONS = ["KAMLA NAGAR"]
DEFAULT_LOCATION = "KAMLA NAGAR"

DEPARTMENTS = [
    "SALES STAFF", "FLOOR INCHARGE", "CASH COUNTER", "MASTER", "OPERATOR",
    "ACCOUNT", "WAREHOUSE", "MDO", "MERCHANDISER",
]

GENDERS = ["Male", "Female"]

SHIFT_TYPES = ["GS", "Custom"]
SHIFT_EXCEPTIONS = ["None", "Warehouse", "Neha_Munjal", "Naman_Jain", "MDO"]

WEEK_DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
WEEK_OFF_DEFAULT = "MON"

OVERRIDE_TYPES = ["WEEK_OFF_CHANGE", "SINGLE_ABSENT", "DOUBLE_ABSENT", "LONG_LEAVE"]
LEDGER_ENTRY_TYPES = [
    "ADVANCE_CASH", "ADVANCE_BANK", "HDFC_BANK", "JAMA", "INTEREST", "B_FORWARD",
    "TG_BONUS", "S_COM", "B_COM", "L_COM",
]

# Final attendance statuses produced by the engine
FINAL_STATUSES = [
    "PRESENT", "ABSENT", "WEEK_OFF", "EXTRA_PRESENT", "HALF_DAY", "QUARTER_DAY",
    "THIRD_DAY", "SEMI_DAY", "DOUBLE_ABSENT", "SINGLE_ENTRY_REVIEW",
]

# --------------------------------------------------------------------------- #
#  UI Theme
# --------------------------------------------------------------------------- #
THEME = {
    "background": "#F8F9FA", "card_bg": "#FFFFFF", "sidebar_bg": "#F0F2F6",
    "primary": "#1A73E8", "success": "#34A853", "danger": "#EA4335",
    "warning": "#FBBC04", "text_primary": "#202124", "text_secondary": "#5F6368",
    "border": "#E8EAED", "tab_a_bg": "#E8F5E9", "tab_b_bg": "#FFEBEE",
    "shadow": "0 1px 3px rgba(0,0,0,0.12)",
}
