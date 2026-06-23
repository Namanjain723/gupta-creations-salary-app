# 🚀 Deployment Guide

Two parts: **(A)** connect Google Sheets, **(B)** put the app online (free).
The app runs fine in **Local mode** without any of this — do this when you want
real, shareable, persistent data.

---

## A. Connect Google Sheets (the database)

### 1. Create the spreadsheet + tabs
1. Create a new Google Sheet, name it **`Gupta Creations Salary DB`**.
2. **Extensions → Apps Script**, delete the boilerplate, and paste the contents
   of [`google_apps_script/setup_sheets.gs`](google_apps_script/setup_sheets.gs).
3. Run `setupGuptaCreationsSalaryDB` and authorise it. This creates all **11
   colour-coded tabs** with the exact headers the app expects.
4. Copy the **Spreadsheet ID** from the URL:
   `https://docs.google.com/spreadsheets/d/`**`THIS_PART`**`/edit`

### 2. Create a Service Account (the app's login)
1. Go to <https://console.cloud.google.com/> → create/select a project.
2. **APIs & Services → Library** → enable **Google Sheets API** *and* **Google Drive API**.
3. **APIs & Services → Credentials → Create Credentials → Service Account.**
4. Open the new service account → **Keys → Add Key → JSON**. A `.json` downloads.
5. **Share the Google Sheet** with the service account's `client_email`
   (found in the JSON, looks like `…@…iam.gserviceaccount.com`) as **Editor**.

### 3. Point the app at it (local run)
```
secrets/
├── service_account.json     <- rename your downloaded JSON to exactly this
└── config.toml              <- copy from config.toml.example, fill in the ID
```
`secrets/config.toml`:
```toml
[sheets]
salary_db_id = "PASTE_YOUR_SPREADSHEET_ID_HERE"
kn_sales_id  = ""        # leave blank — SALE_REPORT_KN lives in the same sheet

[app]
default_location = "KAMLA NAGAR"
admin_name = "Naman"
```
Restart the app. The sidebar should now read **🟢 Connected to Google Sheets**.
(Both `secrets/` files are gitignored — they are never committed.)

> **Migrating your seed data up:** with Sheets connected, the local CSVs aren't
> read. Paste your `seed_data/Employee_Master.csv` + `SALE_REPORT_KN.csv` rows
> into the matching tabs, or re-enter via the app.

---

## B. Put it online — Streamlit Community Cloud (free)

1. Push this folder to a **private GitHub repo** (the `.gitignore` already keeps
   `secrets/` and `local_db/` out — verify before pushing).
2. Go to <https://share.streamlit.io> → **New app** → pick the repo →
   main file = `app.py`.
3. **Advanced settings → Python version → 3.12** (recommended for all wheels).
4. **Advanced settings → Secrets** — paste this (TOML), using your real values:

```toml
[sheets]
salary_db_id = "YOUR_SPREADSHEET_ID"
kn_sales_id  = ""

[app]
default_location = "KAMLA NAGAR"
admin_name = "Naman"

[gcp_service_account]
type = "service_account"
project_id = "your-project-id"
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "salary-app@your-project-id.iam.gserviceaccount.com"
client_id = "..."
token_uri = "https://oauth2.googleapis.com/token"
```
> Copy each field from your downloaded `service_account.json`. Keep the `\n`
> escapes in `private_key` exactly as they appear in the JSON.

5. **Deploy.** Streamlit installs `requirements.txt` and runs `app.py`. Share the
   URL with managers. Add a password via Streamlit's app settings if desired.

---

## Switching back to Local mode
Remove/rename `secrets/service_account.json` (or clear the cloud secrets). The
app falls back to CSV files under `local_db/` automatically — nothing else to do.

## Troubleshooting
| Symptom | Fix |
|---|---|
| Sidebar shows 💾 *Local mode* unexpectedly | Check `salary_db_id` is set & not the `PASTE_…` placeholder; check the JSON key is valid |
| `PermissionError` / 403 from Sheets | You forgot to **share the sheet** with the service-account email |
| A page shows "API not enabled" | Enable **both** Google Sheets API and Google Drive API |
| Wheels fail to build on deploy | Set Python to **3.12** in Streamlit Cloud advanced settings |
