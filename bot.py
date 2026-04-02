from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import pytz
import os, json, difflib, dropbox, threading

from flask import Flask, jsonify

# ===== TIMEZONE VN =====
VN_TZ = pytz.timezone("Asia/Ho_Chi_Minh")

def now_vn():
    return datetime.now(VN_TZ)

# ===== VERSION =====
VERSION = os.getenv("BOT_VERSION", "8.0")

def log(msg):
    now = now_vn().strftime("%d/%m %H:%M:%S")
    print(f"[{now}] {msg}")

log(f"🚀 START BOT - VERSION {VERSION}")

# ===== CONFIG =====
TOKEN = os.getenv("TELEGRAM_TOKEN")
SHEET_ID = os.getenv("SHEET_ID")
DROPBOX_TOKEN = os.getenv("DROPBOX_TOKEN")

ALLOWED_GROUP = -5229338785
ADMINS = ["Ngoc Anh", "Admin BOT", "MBF BOT", "Le Giang"]

# ===== GOOGLE SHEET =====
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

cred_dict = json.loads(os.getenv("GOOGLE_CRED"))
creds = Credentials.from_service_account_info(cred_dict, scopes=scope)
client = gspread.authorize(creds)
sheet_progress = client.open_by_key(SHEET_ID).worksheet("Progress")

# ===== DROPBOX =====
dbx = dropbox.Dropbox(DROPBOX_TOKEN)

# ===== CACHE =====
cache_data = None
cache_time = None
CACHE_TTL = 10

def get_sheet_data():
    global cache_data, cache_time
    now = now_vn()

    if cache_data and cache_time:
        if (now - cache_time).total_seconds() < CACHE_TTL:
            return cache_data

    cache_data = sheet_progress.get_all_values()
    cache_time = now
    return cache_data

def clear_cache():
    global cache_data
    cache_data = None

# ===== COLUMN =====
COL_MAP = {
    "KS": {"BD":"Q", "KT":"R", "USER":"S", "GHICHU":"T"},
    "LD": {"BD":"AC", "KT":"AD", "USER":"AE", "GHICHU":"AF"},
    "CH": {"BD":"AG", "KT":"AH", "USER":"AI", "GHICHU":"AJ"},
    "CM": {"BD":"AK", "KT":"AL", "USER":"AM", "GHICHU":"AN"},
    "OA": {"BD":"AO", "KT":"AP", "USER":"AQ", "GHICHU":"AR"},
    "TD": {"BD":"AS", "KT":"AT", "USER":"AU", "GHICHU":"AV"},
    "TH": {"BD":"AW", "KT":"AX", "USER":"AY", "GHICHU":"AZ"},
}

def col2num(col):
    num = 0
    for c in col:
        num = num*26 + (ord(c.upper()) - ord("A")) + 1
    return num

# ===== HANDLE (GIỮ NGUYÊN LOGIC) =====
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    text = update.message.text.strip() if update.message.text else ""

    if text.startswith("/"):
        return

    chat_id = update.effective_chat.id
    user = update.effective_user.full_name

    if chat_id != ALLOWED_GROUP and user not in ADMINS:
        return

    sites = sheet_progress.col_values(4)

    if "_" not in text:
        return

    parts = text.split(" ", 1)
    cmd_site = parts[0].upper()
    note = parts[1] if len(parts) > 1 else ""

    cmd = cmd_site.split("_")

    hangmuc = cmd[-1]
    site_name = "_".join(cmd[:-1])
    action = None

    if hangmuc not in COL_MAP:
        hangmuc = cmd[-2]
        action = cmd[-1]
        site_name = "_".join(cmd[:-2])

    for idx, sheet_site in enumerate(sites, start=1):
        if sheet_site.strip().upper() != site_name:
            continue

        cols = COL_MAP[hangmuc]
        now_str = now_vn().strftime("%d/%m %H:%M")

        col_bd = col2num(cols["BD"])
        col_kt = col2num(cols["KT"])
        col_user = col2num(cols["USER"])
        col_note = col2num(cols["GHICHU"])

        # NOTE
        if note and not action:
            old = sheet_progress.cell(idx, col_note).value
            new = f"[{now_vn().strftime('%d/%m')}]: {note}"
            sheet_progress.update_cell(idx, col_note, f"{old}\n{new}" if old else new)
            clear_cache()
            await update.message.reply_text("✅ Note OK")
            return

        # BD
        if action == "BD":
            sheet_progress.update_cell(idx, col_bd, now_str)
            sheet_progress.update_cell(idx, col_user, user)

            if note:
                old = sheet_progress.cell(idx, col_note).value
                new = f"[{now_vn().strftime('%d/%m')}]: {note}"
                sheet_progress.update_cell(idx, col_note, f"{old}\n{new}" if old else new)

            clear_cache()
            await update.message.reply_text("✅ BD OK")
            return

        # KT
        elif action == "KT":
            sheet_progress.update_cell(idx, col_kt, now_str)

            if note:
                old = sheet_progress.cell(idx, col_note).value
                new = f"[{now_vn().strftime('%d/%m')}]: {note}"
                sheet_progress.update_cell(idx, col_note, f"{old}\n{new}" if old else new)

            clear_cache()
            await update.message.reply_text("✅ KT OK")
            return

# ===== STATUS API =====
def build_dashboard_data():
    rows = get_sheet_data()
    today = now_vn().strftime("%d/%m")
    total = len(rows) - 2

    data = {}

    for hm, cols in COL_MAP.items():
        col_bd = col2num(cols["BD"])
        col_kt = col2num(cols["KT"])

        doing = 0
        done_today = 0
        done_total = 0

        for row in rows[2:]:
            if len(row) < col_kt:
                continue

            bd = row[col_bd-1]
            kt = row[col_kt-1]

            if kt:
                done_total += 1
                if today in kt:
                    done_today += 1
            elif bd and today in bd:
                doing += 1

        data[hm] = {
            "doing": doing,
            "today": done_today,
            "total_done": done_total,
            "total": total
        }

    return data

# ===== FLASK DASHBOARD =====
app_web = Flask(__name__)

@app_web.route("/")
def home():
    return """
    <html>
    <head>
        <title>Dashboard</title>
        <script>
        async function load(){
            let res = await fetch('/data');
            let data = await res.json();

            let html = "<h2>📊 DASHBOARD</h2>";

            for (let k in data){
                let v = data[k];
                html += `<p><b>${k}</b>: 🟡 ${v.doing} | ✅ ${v.today}/${v.total_done}/${v.total}</p>`;
            }

            document.getElementById("app").innerHTML = html;
        }

        setInterval(load, 5000);
        </script>
    </head>
    <body onload="load()">
        <div id="app">Loading...</div>
    </body>
    </html>
    """

@app_web.route("/data")
def data():
    return jsonify(build_dashboard_data())

def run_web():
    app_web.run(host="0.0.0.0", port=8080)

# ===== RUN BOT =====
def run_bot():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT, handle))

    log("🤖 Bot running...")
    app.run_polling()

# ===== MAIN =====
if __name__ == "__main__":
    threading.Thread(target=run_web).start()
    run_bot()