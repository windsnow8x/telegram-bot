from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from datetime import datetime
import pytz
import os, json
import difflib
import io

# ===== TIMEZONE VN =====
VN_TZ = pytz.timezone("Asia/Ho_Chi_Minh")
def now_vn():
    return datetime.now(VN_TZ)

# ===== VERSION =====
VERSION = os.getenv("BOT_VERSION", "5.0")

def log(msg):
    now = now_vn().strftime("%d/%m %H:%M:%S")
    print(f"[{now}] {msg}")

log(f"🚀 START BOT - VERSION {VERSION}")

# ===== CONFIG =====
TOKEN = os.getenv("TELEGRAM_TOKEN")
SHEET_ID = os.getenv("SHEET_ID")
DRIVE_ROOT_FOLDER_ID = os.getenv("DRIVE_ROOT_FOLDER_ID")  # 👉 folder gốc trên Drive
ALLOWED_GROUP = -5229338785
ADMINS = ["Ngoc Anh", "Admin BOT", "MBF BOT", "Le Giang"]

if not TOKEN or not SHEET_ID or not DRIVE_ROOT_FOLDER_ID:
    raise Exception("❌ Thiếu ENV")

# ===== GOOGLE =====
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

google_cred = os.getenv("GOOGLE_CRED")
cred_dict = json.loads(google_cred)

creds = Credentials.from_service_account_info(cred_dict, scopes=scope)
client = gspread.authorize(creds)
sheet_progress = client.open_by_key(SHEET_ID).worksheet("Progress")

drive_service = build('drive', 'v3', credentials=creds)

log("✅ Google OK")

# ===== CỘT =====
COL_MAP = {
    "KS": {"BD":"Q", "KT":"R", "USER":"S", "GHICHU":"T"},
    "CH": {"BD":"W", "KT":"X", "USER":"Y", "GHICHU":"Z"},
    "LD": {"BD":"AC", "KT":"AD", "USER":"AE", "GHICHU":"AF"},
    "CM": {"BD":"AI", "KT":"AJ", "USER":"AK", "GHICHU":"AL"},
}

def col2num(col):
    num = 0
    for c in col:
        num = num*26 + (ord(c.upper()) - ord("A")) + 1
    return num

# ===== PENDING =====
pending_upload = {}
PENDING_TIMEOUT = 5 * 60
MAX_UPLOAD = 5

# ===== DRIVE =====
def get_or_create_folder(name, parent_id):
    query = f"mimeType='application/vnd.google-apps.folder' and name='{name}' and '{parent_id}' in parents and trashed=false"
    res = drive_service.files().list(q=query, fields="files(id)").execute()
    files = res.get("files", [])
    if files:
        return files[0]["id"]

    file_metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id]
    }
    file = drive_service.files().create(body=file_metadata, fields="id").execute()
    return file["id"]

def upload_file(file_bytes, filename, folder_id):
    media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype='image/jpeg')
    drive_service.files().create(
        body={"name": filename, "parents":[folder_id]},
        media_body=media
    ).execute()

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
    if text and text.upper().endswith("_PIC"):
        cmd = text.upper().split("_")

        if len(cmd) < 3:
            await update.message.reply_text("❌ Sai cú pháp _PIC")
            return

        hangmuc = cmd[-2]
        site_name = "_".join(cmd[:-2])

        if site_name not in sites_upper:
            await update.message.reply_text("❌ Không tìm thấy site")
            return

        if user_id in pending_upload:
            await update.message.reply_text("❌ Bạn đang có lệnh pending")
            return

        pending_upload[user_id] = {
            "site": site_name,
            "hangmuc": hangmuc,
            "time": now_vn(),
            "count": 0
        }

        await update.message.reply_text(f"📸 Đã nhận lệnh upload {site_name} | {hangmuc} (tối đa 5 ảnh trong 5 phút)")
        return

    # ===== RECEIVE PHOTO =====
    if update.message.photo:
        if user_id not in pending_upload:
            return

        pend = pending_upload[user_id]

        if (now_vn() - pend["time"]).total_seconds() > PENDING_TIMEOUT:
            del pending_upload[user_id]
            await update.message.reply_text("❌ Hết thời gian upload")
            return

        if pend["count"] >= MAX_UPLOAD:
            await update.message.reply_text("❌ Đã đủ 5 ảnh")
            return

        file = await update.message.photo[-1].get_file()
        file_bytes = await file.download_as_bytearray()

        pend["count"] += 1

        # tạo folder
        folder_site = get_or_create_folder(pend["site"], DRIVE_ROOT_FOLDER_ID)
        folder_hm = get_or_create_folder(pend["hangmuc"], folder_site)

        filename = f"{now_vn().strftime('%d%m')}_{pend['count']}.jpg"

        upload_file(file_bytes, filename, folder_hm)

        await update.message.reply_text(f"✅ Upload {pend['count']}/5")
        return

    # ===== SHEET LOGIC (GIỮ NGUYÊN) =====
    if not text or "_" not in text:
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

        if action == "BD":
            if bd_val:
                await update.message.reply_text("Đã BD")
                return
            sheet_progress.update_cell(idx, col_bd, now_str)
            if not kt_val:
                sheet_progress.update_cell(idx, col_user, user)
            await update.message.reply_text("BD OK")

        elif action == "KT":
            if kt_val:
                await update.message.reply_text("Đã KT")
                return
            sheet_progress.update_cell(idx, col_kt, now_str)
            sheet_progress.update_cell(idx, col_user, user)
            await update.message.reply_text("KT OK")

        elif note_content:
            old = sheet_progress.cell(idx, col_ghichu).value
            new = f"[{now_vn().strftime('%d/%m')}]: {note_content}"
            sheet_progress.update_cell(idx, col_ghichu, f"{old}\n{new}" if old else new)
            await update.message.reply_text("✅ Ghi chú OK")

        found = True
        break

    if not found:
        close = difflib.get_close_matches(site_name, sites_upper, n=3)
        await update.message.reply_text(f"❌ Không tìm thấy. Gợi ý: {', '.join(close)}" if close else "❌ Không tìm thấy")

# ===== RESET =====
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.full_name
    if user not in ADMINS:
        return
    pending_upload.clear()
    await update.message.reply_text("✅ Đã reset pending")

# ===== RUN =====
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle))
app.add_handler(CommandHandler("reset", reset))

if __name__ == "__main__":
    log("Bot đang chạy...")
    app.run_polling()