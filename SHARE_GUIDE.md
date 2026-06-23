# 📱 Share the app with your team (phones + laptops, free)

Two ways to run it. Pick based on what you need.

---

## Option 1 — On your shop PC only (data never leaves the computer)
**Best for: maximum privacy, zero cost, no internet needed.**

1. Double-click **`Start-Salary-App.bat`** → the app opens in your browser.
2. Log in (default **admin / gupta123**).
3. Use it. Every upload is saved in the `local_db` folder *on this PC* and stays there forever.
4. Click **`Backup.bat`** weekly → copies all data to a `Backups` folder (then copy that to a pen-drive).

**Phones / other counters on the SAME shop WiFi** can also open it:
- On the PC, find its IP: press `Win+R`, type `cmd`, run `ipconfig`, note the **IPv4 Address** (e.g. `192.168.1.43`).
- On any phone/laptop on the shop WiFi, open **`http://192.168.1.43:8501`**.
- Data still lives only on the PC — nothing goes to the internet. (The PC must be on.)

---

## Option 2 — One shareable link for everyone, anywhere (free cloud)
**Best for: seniors who need it on their own phones/laptops from home or other shops.**
The app is hosted free; data lives in **your own Google account** (login-protected). This is the trade for "open from anywhere".

### A. Put your data in Google Sheets (one time)
1. Create a Google Sheet named **Gupta Creations Salary DB**.
2. **Extensions → Apps Script**, paste `google_apps_script/setup_sheets.gs`, run it → it builds all 12 tabs.
3. Make a Google **service account** (console.cloud.google.com → Sheets API + Drive API → Credentials → Service Account → JSON key). Share the Sheet with the service account's email as **Editor**.
4. Locally: save the JSON as `secrets/service_account.json`, put the Sheet ID in `secrets/config.toml`, then run **`python tools/push_seed_to_sheets.py`** → all employees + commissions land in your Sheet.

### B. Host it free on Streamlit Community Cloud
1. Push this folder to a **private GitHub repo** (`.gitignore` already keeps `secrets/` and `local_db/` out).
2. Go to **share.streamlit.io → New app**, pick the repo, main file `app.py`, **Python 3.12**.
3. **Advanced → Secrets**: paste your `config.toml` block **including the `[auth.users]` logins** and the `[gcp_service_account]` JSON (see `secrets/config.toml.example`).
4. **Deploy.** You get a link like `https://gupta-salary.streamlit.app` — **share this with your team.**

### C. Make it feel like a real app (no Play Store needed)
On each phone, open the link once, then:
- **Android (Chrome):** ⋮ menu → **Add to Home screen**.
- **iPhone (Safari):** Share → **Add to Home Screen**.

It gets an app icon and opens full-screen — exactly like a Play Store app, instantly, for free. (A true Play Store app needs a paid developer account + weeks of review; this gives the same result today.)

---

## Logins (who can open the link)
Set them under `[auth.users]` in your secrets (one line per person). Add `viewers = ["name"]` to make someone **read-only** (can see, can't edit/run payroll).
- **Change the default `admin / gupta123` before sharing any link.**

## Privacy summary
| | Data location | Link works on phones from anywhere? |
|---|---|---|
| Option 1 (PC / shop WiFi) | **Only your PC** | Only on shop WiFi |
| Option 2 (cloud) | Your Google account (login-protected) | **Yes, anywhere** |

You can start with Option 1 today and switch to Option 2 anytime — the app code is identical; only where the data lives changes.
