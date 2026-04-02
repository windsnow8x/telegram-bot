from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import pytz
import os, json, difflib, dropbox

# ===== TIMEZONE VN =====
VN_TZ = pytz.timezone("Asia/Ho_Chi_Minh")

def now_vn():
    return datetime.now(VN_TZ)

# ===== VERSION =====
VERSION = os.getenv("BOT_VERSION", "7.0")

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

if not TOKEN or not SHEET_ID or not DROPBOX_TOKEN:
    raise Exception("❌ Thiếu ENV")

# ===== GOOGLE SHEET =====
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

google_cred = os.getenv("GOOGLE_CRED")
cred_dict = json.loads(google_cred)
creds = Credentials.from_service_account_info(cred_dict, scopes=scope)
client = gspread.authorize(creds)
sheet_progress = client.open_by_key(SHEET_ID).worksheet("Progress")

log("✅ Sheet OK")

# ===== DROPBOX =====
dbx = dropbox.Dropbox(DROPBOX_TOKEN)

# ===== CACHE =====
cache_data = None
cache_time = None
CACHE_TTL = 15

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

# ===== CỘT =====
COL_MAP = {
    "KS": {"BD":"Q", "KT":"R", "USER":"S", "GHICHU":"T"},
    "LD": {"BD":"AC", "KT":"AD", "USER":"AE", "GHICHU":"AF"},
    "CM": {"BD":"AI", "KT":"AJ", "USER":"AK", "GHICHU":"AL"},
}

def col2num(col):
    num = 0
    for c in col:
        num = num*26 + (ord(c.upper()) - ord("A")) + 1
    return num

# ===== PENDING UPLOAD =====
pending_upload = {}
MAX_UPLOAD = 5
TIMEOUT = 5

# ===== HANDLE =====
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    text = update.message.text.strip() if update.message.text else ""

    # 🔥 bỏ qua command
    if text.startswith("/"):
        return

    chat_id = update.effective_chat.id
    user = update.effective_user.full_name
    user_id = update.effective_user.id

    if chat_id != ALLOWED_GROUP and user not in ADMINS:
        return

    sites = sheet_progress.col_values(4)
    sites_upper = [s.strip().upper() for s in sites if s.strip()]

    # ===== PIC =====
    if text.upper().endswith("_PIC"):
        cmd = text.upper().split("_")

        if len(cmd) < 3:
            await update.message.reply_text("❌ Sai cú pháp _PIC")
            return

        hangmuc = cmd[-2]
        site_name = "_".join(cmd[:-2])

        if site_name not in sites_upper:
            close = difflib.get_close_matches(site_name, sites_upper, n=3, cutoff=0.5)
            await update.message.reply_text(f"❌ Sai site. Gợi ý: {', '.join(close)}")
            return

        pending_upload[user_id] = {
            "site": site_name,
            "hangmuc": hangmuc,
            "time": now_vn(),
            "count": 0
        }

        await update.message.reply_text(f"📸 Chờ upload {site_name}")
        return

    # ===== PHOTO =====
    if update.message.photo:
        if user_id not in pending_upload:
            return

        pend = pending_upload[user_id]
        now = now_vn()

        if (now - pend["time"]).total_seconds() > TIMEOUT*60:
            del pending_upload[user_id]
            await update.message.reply_text("❌ Hết hạn")
            return

        file = await update.message.photo[-1].get_file()
        file_bytes = bytes(await file.download_as_bytearray())

        pend["count"] += 1
        path = f"/{pend['site']}/{pend['hangmuc']}/{pend['count']}.jpg"

        dbx.files_upload(file_bytes, path, mode=dropbox.files.WriteMode.overwrite)
        await update.message.reply_text(f"✅ Upload {pend['count']}/5")
        return

    # ===== SHEET =====
    if "_" not in text:
        return

    parts = text.split(" ", 1)
    cmd_site = parts[0].upper()
    note = parts[1] if len(parts) > 1 else ""

    cmd = cmd_site.split("_")
    if len(cmd) < 3:
        return

    hangmuc = cmd[-2]
    action = cmd[-1]
    site_name = "_".join(cmd[:-2])

    if hangmuc not in COL_MAP:
        await update.message.reply_text("❌ Sai hạng mục")
        return

    for idx, sheet_site in enumerate(sites, start=1):
        if sheet_site.strip().upper() != site_name:
            continue

        cols = COL_MAP[hangmuc]
        now_str = now_vn().strftime("%d/%m %H:%M")

        # ===== NOTE =====
        if note:
            old = sheet_progress.cell(idx, col2num(cols["GHICHU"])).value
            new = f"[{now_vn().strftime('%d/%m')}]: {note}"
            sheet_progress.update_cell(idx, col2num(cols["GHICHU"]), f"{old}\n{new}" if old else new)
            clear_cache()
            await update.message.reply_text("✅ Đã ghi chú")
            return

        # ===== BD =====
        if action == "BD":
            sheet_progress.update_cell(idx, col2num(cols["BD"]), now_str)
            sheet_progress.update_cell(idx, col2num(cols["USER"]), user)
            clear_cache()

        # ===== KT =====
        elif action == "KT":
            sheet_progress.update_cell(idx, col2num(cols["KT"]), now_str)
            clear_cache()

        await update.message.reply_text("✅ OK")
        return

    close = difflib.get_close_matches(site_name, sites_upper, n=3, cutoff=0.5)
    await update.message.reply_text(f"❌ Không thấy site. Gợi ý: {', '.join(close)}")

# ===== STATUS =====
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.full_name
    if user not in ADMINS:
        return

    text = update.message.text.upper()

    if context.args:
        hangmuc = context.args[0].upper()
    elif "_" in text:
        hangmuc = text.split("_")[1]
    else:
        await update.message.reply_text("Dùng: /status KS hoặc /status_KS")
        return

    if hangmuc not in COL_MAP:
        await update.message.reply_text("❌ Hạng mục không hợp lệ")
        return

    rows = get_sheet_data()
    today = now_vn().strftime("%d/%m")

    col_bd = col2num(COL_MAP[hangmuc]["BD"])
    col_kt = col2num(COL_MAP[hangmuc]["KT"])
    col_user = col2num(COL_MAP[hangmuc]["USER"])

    doing_list = []
    done_list = []
    total_done = 0
    total_today_done = 0
    total_sites = len(rows) - 2

    for row in rows[2:]:
        if len(row) < col_kt:
            continue

        site = row[3]
        bd = row[col_bd-1]
        kt = row[col_kt-1]
        user_val = row[col_user-1] or "N/A"

        if kt:
            total_done += 1

        if kt and today in kt:
            total_today_done += 1
            done_list.append(f"{site} | ✅ {user_val} ({kt})")
        elif bd and today in bd:
            doing_list.append(f"{site} | 🟡 {user_val} ({bd})")

    msg = f"📊 {hangmuc} HÔM NAY ({today})\n\n"
    msg += f"📌 Hoàn thành hôm nay: {total_today_done}/{total_sites}\n"
    msg += f"📌 Lũy kế hoàn thành: {total_done}/{total_sites}\n\n"

    if doing_list:
        msg += "🟡 ĐANG LÀM\n" + "\n".join(doing_list) + "\n\n"

    if done_list:
        msg += "✅ HOÀN THÀNH\n" + "\n".join(done_list)

    await update.message.reply_text(msg)

# ===== REPORT =====
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.full_name
    if user not in ADMINS:
        return

    rows = get_sheet_data()
    today = now_vn().strftime("%d/%m")

    msg = f"📊 REPORT {today}\n\n"

    for hm, cols in COL_MAP.items():
        col_kt = col2num(cols["KT"])

        done = 0
        today_done = 0

        for row in rows[2:]:
            if len(row) < col_kt:
                continue

            kt = row[col_kt-1]
            if kt:
                done += 1
                if today in kt:
                    today_done += 1

        msg += f"{hm}: {today_done}/{done}\n"

    await update.message.reply_text(msg)

# ===== RESET =====
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.full_name
    if user not in ADMINS:
        return

    pending_upload.clear()
    await update.message.reply_text("✅ Reset pending")

# ===== RUN =====
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("status", status))
app.add_handler(CommandHandler("report", report))
app.add_handler(CommandHandler("reset", reset))

app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle))

if __name__ == "__main__":
    log("Bot đang chạy...")
    app.run_polling()