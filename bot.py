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
VERSION = os.getenv("BOT_VERSION", "6.0")

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
TIMEOUT = 5  # phút

# ===== HANDLE =====
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    chat_id = update.effective_chat.id
    user = update.effective_user.full_name
    user_id = update.effective_user.id
    text = update.message.text.strip() if update.message.text else ""

    if chat_id != ALLOWED_GROUP and user not in ADMINS:
        return

    sites = sheet_progress.col_values(4)
    sites_upper = [s.strip().upper() for s in sites if s.strip()]

    # ================= PIC COMMAND =================
    if text.upper().endswith("_PIC"):
        cmd = text.upper().split("_")
        if len(cmd) < 3:
            await update.message.reply_text("❌ Sai cú pháp _PIC")
            return

        hangmuc = cmd[-2]
        site_name = "_".join(cmd[:-2])

        if site_name not in sites_upper:
            close = difflib.get_close_matches(site_name, sites_upper, n=3, cutoff=0.5)
            if close:
                await update.message.reply_text(f"❌ Sai site. Gợi ý: {', '.join(close)}")
            else:
                await update.message.reply_text("❌ Không tìm thấy site")
            return

        pending_upload[user_id] = {
            "site": site_name,
            "hangmuc": hangmuc,
            "time": now_vn(),
            "count": 0
        }

        await update.message.reply_text(f"📸 Chờ upload {site_name} | {hangmuc} (tối đa 5 ảnh / 5 phút)")
        return

    # ================= RECEIVE PHOTO =================
    if update.message.photo:
        if user_id not in pending_upload:
            return

        pend = pending_upload[user_id]
        now = now_vn()

        if (now - pend["time"]).total_seconds() > TIMEOUT*60:
            del pending_upload[user_id]
            await update.message.reply_text("❌ Hết hạn upload")
            return

        if pend["count"] >= MAX_UPLOAD:
            await update.message.reply_text("❌ Đã đủ 5 ảnh")
            return

        try:
            file = await update.message.photo[-1].get_file()
            file_bytes = bytes(await file.download_as_bytearray())

            pend["count"] += 1
            filename = f"{now.strftime('%d%m')}_{pend['hangmuc']}_{pend['count']}.jpg"
            path = f"/{pend['site']}/{pend['hangmuc']}/{filename}"

            dbx.files_upload(file_bytes, path, mode=dropbox.files.WriteMode.overwrite)

            await update.message.reply_text(f"✅ Upload {pend['count']}/5")

        except Exception as e:
            log(f"ERROR: {e}")
            await update.message.reply_text(f"❌ Upload lỗi")

        return

    # ================= SHEET =================
    if "_" not in text:
        return

    parts = text.split(" ", 1)
    cmd_site = parts[0].upper()
    note = parts[1] if len(parts) > 1 else ""

    cmd_parts = cmd_site.split("_")
    if len(cmd_parts) < 3:
        return

    hangmuc = cmd_parts[-2]
    action = cmd_parts[-1]
    site_name = "_".join(cmd_parts[:-2])

    if hangmuc not in COL_MAP:
        await update.message.reply_text("❌ Sai hạng mục")
        return

    for idx, sheet_site in enumerate(sites, start=1):
        if sheet_site.strip().upper() != site_name:
            continue

        cols = COL_MAP[hangmuc]

        col_bd = col2num(cols["BD"])
        col_kt = col2num(cols["KT"])
        col_user = col2num(cols["USER"])
        col_note = col2num(cols["GHICHU"])

        now_str = now_vn().strftime("%d/%m %H:%M")

        bd = sheet_progress.cell(idx, col_bd).value
        kt = sheet_progress.cell(idx, col_kt).value

        # ===== NOTE =====
        if note:
            old = sheet_progress.cell(idx, col_note).value
            new = f"[{now_vn().strftime('%d/%m')}]: {note}"
            combined = f"{old}\n{new}" if old else new
            sheet_progress.update_cell(idx, col_note, combined)
            await update.message.reply_text("✅ Đã ghi chú")
            return

        # ===== BD =====
        if action == "BD":
            if bd:
                await update.message.reply_text("❌ Đã BD trước đó")
                return

            sheet_progress.update_cell(idx, col_bd, now_str)
            sheet_progress.update_cell(idx, col_user, user)

        # ===== KT =====
        elif action == "KT":
            if kt:
                await update.message.reply_text("❌ Đã KT trước đó")
                return

            sheet_progress.update_cell(idx, col_kt, now_str)
            if not sheet_progress.cell(idx, col_user).value:
                sheet_progress.update_cell(idx, col_user, user)

        await update.message.reply_text("✅ OK")
        return

    # ===== NOT FOUND =====
    close = difflib.get_close_matches(site_name, sites_upper, n=3, cutoff=0.5)
    if close:
        await update.message.reply_text(f"❌ Không thấy site. Gợi ý: {', '.join(close)}")
    else:
        await update.message.reply_text("❌ Sai cú pháp")

# ===== UNDO =====
async def undo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.full_name
    parts = update.message.text.split()

    if len(parts) < 2:
        await update.message.reply_text("Dùng: /undo SITE_HM")
        return

    cmd = parts[1].upper().split("_")
    if len(cmd) < 2:
        return

    hangmuc = cmd[-1]
    site_name = "_".join(cmd[:-1])

    sites = sheet_progress.col_values(4)

    for idx, sheet_site in enumerate(sites, start=1):
        if sheet_site.strip().upper() != site_name:
            continue

        cols = COL_MAP.get(hangmuc)
        if not cols:
            return

        sheet_progress.update_cell(idx, col2num(cols["BD"]), "")
        sheet_progress.update_cell(idx, col2num(cols["KT"]), "")
        sheet_progress.update_cell(idx, col2num(cols["USER"]), "")
        sheet_progress.update_cell(idx, col2num(cols["GHICHU"]), "")

        await update.message.reply_text("✅ Undo OK")
        return

# ===== STATUS =====
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.full_name
    if user not in ADMINS:
        return

    text = update.message.text.upper()
    if "_" not in text:
        return

    hangmuc = text.split("_")[1]
    if hangmuc not in COL_MAP:
        return

    rows = sheet_progress.get_all_values()
    today = now_vn().strftime("%d/%m")

    col_kt = col2num(COL_MAP[hangmuc]["KT"])

    total = len(rows) - 2
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

    await update.message.reply_text(
        f"📊 {hangmuc}\nHôm nay: {today_done}/{total}\nLũy kế: {done}/{total}"
    )

# ===== REPORT =====
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.full_name
    if user not in ADMINS:
        return

    rows = sheet_progress.get_all_values()
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

app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle))
app.add_handler(CommandHandler("undo", undo))
app.add_handler(CommandHandler("status", status))
app.add_handler(CommandHandler("report", report))
app.add_handler(CommandHandler("reset", reset))

if __name__ == "__main__":
    log("Bot đang chạy...")
    app.run_polling()