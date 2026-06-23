/**
 * Gupta Creations Salary DB — one-time sheet setup.
 *
 * HOW TO USE:
 *   1. Create a new Google Sheet, name it "Gupta Creations Salary DB".
 *   2. Extensions -> Apps Script. Delete any boilerplate, paste this whole file.
 *   3. Run  setupGuptaCreationsSalaryDB  (authorise when prompted).
 *   4. It creates all 11 colour-coded tabs with the exact headers the app expects.
 *
 * Re-running is safe: existing tabs keep their data; only headers/format refresh.
 */
function setupGuptaCreationsSalaryDB() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();

  // [name, tabColor, headers]  — MUST match modules/constants.py COLUMNS exactly.
  var tabs = [
    ["Employee_Master", "#4285F4", ["Emp_Code","Emp_Name","Short_Code","Gender","Location","Department","Shift_Type","Shift_Exception","Base_Salary","EPF","ESIC","Bank_Name","Account_Number","IFSC","TG_Ladies_Bonus","Week_Off_Default","Is_Active","Is_Permanent","Joined_Date","Notes"]],
    ["Biometric_Raw", "#FF6D00", ["Upload_Date","Month_Year","Source_Location","Upload_Frequency","Attendance_Date","Emp_Code","Emp_Name","Shift","In_Time","Out_Time","Total_Duration_Raw","Total_Duration_Mins","Status_Raw","Single_Entry_Flag","Remarks"]],
    ["Attendance_Processed", "#0F9D58", ["Month_Year","Emp_Code","Emp_Name","Attendance_Date","Day_Type","Raw_Status","Manual_Override","Override_Applied_By","Final_Status","Attendance_Value","Punch_In","Punch_Out","Duration_Mins","Late_Fine_Amount","Nashta_Daily","Nashta_Sign","Daily_Wage_Rate","Day_Deduction","Notes"]],
    ["Nashta_Ledger", "#76FF03", ["Month_Year","Emp_Code","Emp_Name","Location","Attendance_Date","Day_Of_Week","Punch_In_Time","Biometric_Status","Late_Fine_Slab","Nashta_Base","Nashta_Daily","Nashta_Sign","Notes"]],
    ["Nashta_Monthly_Summary", "#CCFF90", ["Month_Year","Emp_Code","Emp_Name","Location","Total_Present_Days","OnTime_Days","Late_Days_16","Late_Days_32","Late_Days_48","Late_Days_64","Late_Days_80","Nashta_Earned_Positive","Nashta_Deducted_Negative","Net_Monthly_Nashta","Monthly_Result"]],
    ["Manual_Overrides", "#F4B400", ["Override_ID","Month_Year","Emp_Code","Emp_Name","Override_Date","Override_Date_End","Override_Type","New_Week_Off_Day","Notes","Applied_By","Applied_At","Is_Active"]],
    ["Variable_Ledger", "#7B1FA2", ["Ledger_ID","Month_Year","Emp_Code","Emp_Name","Entry_Date","Entry_Type","Amount","Notes","Entered_By","Entered_At"]],
    ["SALE_REPORT_KN", "#00897B", ["Month_Year","Emp_Code","Emp_Name","Short_Code","S_Com","B_Com","L_Com","Total_Commission","Notes"]],
    ["Payroll_Final", "#DB4437", ["Payroll_ID","Month_Year","Run_Date","Emp_Code","Emp_Name","Is_Permanent","Base_Salary","Calendar_Days","Daily_Rate","Present_Days","Extra_Present_Days","Attendance_Fraction","Earned_Salary","S_Com","B_Com","L_Com","TG_Bonus","Extra_Present_Pay","Nashta_Total","Nashta_Result","BF_From_Previous","Gross_Earnings","EPF","ESIC","Late_Fine_Total","Nashta_Deduction","Advance_Cash_Total","Advance_Bank_Total","Jama_Total","Interest","Absent_Deduction","Total_Deductions","Dena_Amount","Net_Payable","HDFC_Amount","Result_Type","Cash_Dena_Amount","Lena_Amount","Bank_Account","Slip_Generated","Notes"]],
    ["Holidays", "#E91E63", ["Holiday_Date","Holiday_Name","Applicable_To"]],
    ["Config", "#455A64", ["Scope","Key","Value","Value_Type","Group","Label","Notes"]],
    ["Sync_Log", "#9E9E9E", ["Timestamp","Action","Details","Admin"]]
  ];

  tabs.forEach(function(tab) {
    var name = tab[0], color = tab[1], headers = tab[2];
    var sheet = ss.getSheetByName(name);
    if (!sheet) sheet = ss.insertSheet(name);

    sheet.setTabColor(color);

    var headerRange = sheet.getRange(1, 1, 1, headers.length);
    headerRange.setValues([headers]);
    headerRange.setBackground("#263238");
    headerRange.setFontColor("#FFFFFF");
    headerRange.setFontWeight("bold");
    headerRange.setFontSize(10);

    sheet.setFrozenRows(1);
    sheet.autoResizeColumns(1, headers.length);

    for (var r = 2; r <= 200; r++) {
      var rowColor = (r % 2 === 0) ? "#F5F5F5" : "#FFFFFF";
      sheet.getRange(r, 1, 1, headers.length).setBackground(rowColor);
    }
  });

  // Remove the default "Sheet1" if it's still empty.
  var def = ss.getSheetByName("Sheet1");
  if (def && ss.getSheets().length > 1) {
    try { ss.deleteSheet(def); } catch (e) {}
  }

  SpreadsheetApp.getUi().alert("All 11 tabs created for Gupta Creations Salary DB.");
}
