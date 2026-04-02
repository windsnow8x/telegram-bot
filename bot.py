from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import pytz
import os, json
import difflib
import dropbox

# ===== TIMEZONE VN =====
VN_TZ = pytz.timezone("Asia/Ho_Chi_Minh")

def now_vn():
    return datetime.now(VN_TZ)

# ===== VERSION =====
VERSION = os.getenv("BOT_VERSION", "3.0")

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
    raise Exception("❌ Thiếu TOKEN / SHEET_ID / DROPBOX_TOKEN")

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
log("✅ Kết nối Google Sheet OK")

# ===== DROPBOX =====
dbx = dropbox.Dropbox(DROPBOX_TOKEN)

def create_folder_if_not_exists(path):
    try:
        dbx.files_create_folder_v2(path)
    except Exception as e:
        if "conflict" not in str(e):
            log(f"❌ Lỗi tạo folder: {e}")

def upload_to_dropbox(file_bytes, path):
    try:
        dbx.files_upload(file_bytes, path)
        return True, "OK"
    except Exception as e:
        return False, str(e)

# ===== CỘT =====
COL_MAP = {
    "KS": {"BD":"Q", "KT":"R", "USER":"S", "GHICHU":"T"},
    "CH": {"BD":"W", "KT":"X", "USER":"Y", "GHICHU":"Z"},
    "LD": {"BD":"AC", "KT":"AD", "USER":"AE", "GHICHU":"AF"},
    "CM": {"BD":"AI", "KT":"AJ", "USER":"AK", "GHICHU":"AL"},
    "SW": {"BD":"AO", "KT":"AP", "USER":"AQ", "GHICHU":"AR"},
    "OA": {"BD":"AU", "KT":"AV", "USER":"AW", "GHICHU":"AX"},
    "TD": {"BD":"BA", "KT":"BB", "USER":"BC", "GHICHU":"BD"},
    "TH": {"BD":"BG", "KT":"BH", "USER":"BI", "GHICHU":"BJ"},
}

def col2num(col):
    num = 0
    for c in col:
        num = num*26 + (ord(c.upper()) - ord("A")) + 1
    return num

# ===== PENDING UPLOAD =====
pending_upload = {}
PENDING_TIMEOUT = 5  # phút
MAX_UPLOAD = 5

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

    # ===== PIC COMMAND =====
    if text.upper().endswith("_PIC"):
        cmd = text.upper().split("_")
        hangmuc = cmd[-2]
        site_name = "_".join(cmd[:-2])

        if site_name not in sites_upper:
            close = difflib.get_close_matches(site_name, sites_upper, n=3, cutoff=0.5)
            await update.message.reply_text(f"❌ Không tìm thấy site. Gợi ý: {', '.join(close)}" if close else "❌ Không tìm thấy site")
            return

        if user_id in pending_upload:
            await update.message.reply_text("❌ Bạn đang có lệnh upload đang chờ")
            return

        pending_upload[user_id] = {
            "site": site_name,
            "hangmuc": hangmuc,
            "time": now_vn(),
            "count": 0
        }

        await update.message.reply_text(f"📸 Chờ upload ảnh {site_name} | {hangmuc} (tối đa 5 ảnh trong 5 phút)")
        return

    # ===== RECEIVE PHOTO =====
    if update.message.photo:
        if user_id not in pending_upload:
            await update.message.reply_text("❌ Chưa có lệnh _PIC")
            return

        pend = pending_upload[user_id]
        now = now_vn()

        if (now - pend["time"]).total_seconds() > PENDING_TIMEOUT * 60:
            del pending_upload[user_id]
            await update.message.reply_text("❌ Hết thời gian upload")
            return

        if pend["count"] >= MAX_UPLOAD:
            await update.message.reply_text("❌ Đã đủ 5 ảnh")
            return

        await update.message.reply_text("⏳ Đang upload Dropbox...")

        try:
            file = await update.message.photo[-1].get_file()
            file_bytes = await file.download_as_bytearray()

            pend["count"] += 1

            site = pend["site"]
            hangmuc = pend["hangmuc"]

            create_folder_if_not_exists(f"/{site}")
            create_folder_if_not_exists(f"/{site}/{hangmuc}")

            filename = f"{now.strftime('%d%m')}_{hangmuc}_{pend['count']}_{site}.jpg"
            path = f"/{site}/{hangmuc}/{filename}"

            success, msg = upload_to_dropbox(file_bytes, path)

            if success:
                await update.message.reply_text(f"✅ Upload {pend['count']}/5 OK")
            else:
                await update.message.reply_text(f"❌ Upload lỗi: {msg}")
                log(msg)

        except Exception as e:
            await update.message.reply_text(f"❌ Lỗi xử lý ảnh: {e}")
            log(e)

        return

    # ===== TEXT COMMAND (SHEET) =====
    if "_" not in text or text.upper().endswith("_PIC"):
        return

    parts = text.split(" ", 1)
    cmd_site = parts[0].upper()
    note_content = parts[1].strip() if len(parts) > 1 else ""

    cmd_parts = cmd_site.split("_")
    if len(cmd_parts) < 3:
        return

    hangmuc = cmd_parts[-2]
    action = cmd_parts[-1]
    site_name = "_".join(cmd_parts[:-2])

    found = False

    for idx, sheet_site in enumerate(sites, start=1):
        if sheet_site.strip().upper() != site_name:
            continue

        if hangmuc not in COL_MAP:
            continue

        cols = COL_MAP[hangmuc]

        col_bd = col2num(cols["BD"])
        col_kt = col2num(cols["KT"])
        col_user = col2num(cols["USER"])
        col_ghichu = col2num(cols["GHICHU"])

        now_str = now_vn().strftime("%d/%m %H:%M")

        bd_val = sheet_progress.cell(idx, col_bd).value
        kt_val = sheet_progress.cell(idx, col_kt).value

        # ===== BD =====
        if action == "BD":
            if bd_val:
                await update.message.reply_text(f"{sheet_site} đã BD trước đó")
                return

            sheet_progress.update_cell(idx, col_bd, now_str)

            if not kt_val:
                sheet_progress.update_cell(idx, col_user, user)

            await update.message.reply_text(f"{cmd_site} BẮT ĐẦU OK")

        # ===== KT =====
        elif action == "KT":
            if kt_val:
                await update.message.reply_text(f"{sheet_site} đã KT trước đó")
                return

            sheet_progress.update_cell(idx, col_kt, now_str)
            sheet_progress.update_cell(idx, col_user, user)

            await update.message.reply_text(f"{cmd_site} KẾT THÚC OK")

        # ===== NOTE =====
        elif note_content:
            old_note = sheet_progress.cell(idx, col_ghichu).value
            new_note = f"[{now_vn().strftime('%d/%m')}]: {note_content}"
            combined = f"{old_note}\n{new_note}" if old_note else new_note

            sheet_progress.update_cell(idx, col_ghichu, combined)
            await update.message.reply_text("✅ Đã ghi chú")

        found = True
        break

    if not found:
        close_matches = difflib.get_close_matches(site_name, sites_upper, n=3, cutoff=0.5)
        await update.message.reply_text(f"❌ Không tìm thấy site. Gợi ý: {', '.join(close_matches)}" if close_matches else "❌ Không tìm thấy site")

# ===== RESET PENDING =====
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.full_name
    if user not in ADMINS:
        return

    pending_upload.clear()
    await update.message.reply_text("✅ Đã reset toàn bộ pending")

# ===== RUN =====
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle))
app.add_handler(CommandHandler("reset", reset))

if __name__ == "__main__":
    log("Bot đang chạy...")
    app.run_polling()