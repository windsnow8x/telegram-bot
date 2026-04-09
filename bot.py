from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import pytz
import os, json, difflib, dropbox
import requests

# ===== TIMEZONE VN =====
VN_TZ = pytz.timezone("Asia/Ho_Chi_Minh")

def now_vn():
    return datetime.now(VN_TZ)

# ===== VERSION =====
VERSION = os.getenv("BOT_VERSION", "8.2")

def log(msg):
    now = now_vn().strftime("%d/%m %H:%M:%S")
    print(f"[{now}] {msg}")

log(f"🚀 START BOT - VERSION {VERSION}")

# ===== CONFIG =====
TOKEN = os.getenv("TELEGRAM_TOKEN")
SHEET_ID = os.getenv("SHEET_ID")

DROPBOX_APP_KEY = os.getenv("DROPBOX_APP_KEY")
DROPBOX_APP_SECRET = os.getenv("DROPBOX_APP_SECRET")
DROPBOX_REFRESH_TOKEN = os.getenv("DROPBOX_REFRESH_TOKEN")

ALLOWED_GROUP = -5229338785
ADMINS = ["Ngoc Anh", "Admin BOT", "MBF BOT", "Le Giang", "Mai Trang"]

if not TOKEN or not SHEET_ID:
    raise Exception("❌ Thiếu ENV")

if not DROPBOX_APP_KEY or not DROPBOX_APP_SECRET or not DROPBOX_REFRESH_TOKEN:
    raise Exception("❌ Thiếu ENV Dropbox")

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

# ===== DROPBOX AUTO REFRESH =====
dbx = None
dbx_token_expire = None

def get_dropbox_client():
    global dbx, dbx_token_expire

    now = now_vn()

    if dbx and dbx_token_expire and now < dbx_token_expire:
        return dbx

    log("🔄 Refresh Dropbox token...")

    url = "https://api.dropbox.com/oauth2/token"

    data = {
        "grant_type": "refresh_token",
        "refresh_token": DROPBOX_REFRESH_TOKEN,
        "client_id": DROPBOX_APP_KEY,
        "client_secret": DROPBOX_APP_SECRET
    }

    res = requests.post(url, data=data)
    result = res.json()

    if "access_token" not in result:
        raise Exception(f"❌ Refresh token lỗi: {result}")

    access_token = result["access_token"]
    expires_in = result.get("expires_in", 14400)

    dbx_token_expire = now + timedelta(seconds=expires_in - 60)
    dbx = dropbox.Dropbox(access_token)

    log("✅ Dropbox token refreshed")

    return dbx

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

# ===== PENDING UPLOAD =====
pending_upload = {}
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

    # PIC COMMAND
    if text.upper().endswith("_PIC"):
        cmd = text.upper().split("_")
        if len(cmd) < 3:
            return
        hangmuc = cmd[-2]
        site_name = "_".join(cmd[:-2])

        if site_name not in sites_upper:
            await update.message.reply_text("❌ Không tìm thấy site")
            return

        pending_upload[user_id] = {
            "site": site_name,
            "hangmuc": hangmuc,
            "time": now_vn(),
            "last_update": now_vn(),
            "count": 0,
            "msg_id": None,
            "chat_id": chat_id
        }

        await update.message.reply_text(f"📸 Chờ upload {site_name} | {hangmuc}")
        return

    # RECEIVE PHOTO
    if update.message.photo:
        if user_id not in pending_upload:
            await update.message.reply_text("❌ Chưa có lệnh _PIC")
            return

        pend = pending_upload[user_id]
        now = now_vn()

        try:
            # Tạo message 1 lần
            if not pend["msg_id"]:
                msg = await update.message.reply_text(f"📤 Uploading...\n0/{MAX_UPLOAD} ảnh")
                pend["msg_id"] = msg.message_id

            file = await update.message.photo[-1].get_file()
            file_bytes = await file.download_as_bytearray()
            file_bytes = bytes(file_bytes)

            pend["count"] += 1
            pend["last_update"] = now_vn()

            filename = f"{now.strftime('%d%m')}_{pend['hangmuc']}_{pend['count']}.jpg"
            dropbox_path = f"/MBF HW/{pend['site']}/{pend['hangmuc']}/{filename}"

            dbx_client = get_dropbox_client()
            dbx_client.files_upload(file_bytes, dropbox_path, mode=dropbox.files.WriteMode.overwrite)

            # Update message duy nhất
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=pend["msg_id"],
                text=f"📤 Uploading...\n{pend['count']}/{MAX_UPLOAD} ảnh"
            )

            # Nếu đủ 5 ảnh → kết thúc luôn
            if pend["count"] == MAX_UPLOAD:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=pend["msg_id"],
                    text=f"✅ Upload xong {MAX_UPLOAD}/{MAX_UPLOAD} ảnh"
                )
                del pending_upload[user_id]

        except Exception as e:
            log(f"ERROR: {e}")
            await update.message.reply_text(f"❌ Upload lỗi: {e}")

        return

# ===== AUTO TIMEOUT CHECK =====
async def check_timeout(context: ContextTypes.DEFAULT_TYPE):
    now = now_vn()
    remove_list = []

    for user_id, pend in pending_upload.items():
        if (now - pend["last_update"]).total_seconds() > 60:
            try:
                await context.bot.edit_message_text(
                    chat_id=pend["chat_id"],
                    message_id=pend["msg_id"],
                    text=f"✅ Upload xong {pend['count']}/{MAX_UPLOAD} ảnh"
                )
            except:
                pass
            remove_list.append(user_id)

    for uid in remove_list:
        del pending_upload[uid]

# ===== RUN =====
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(MessageHandler(filters.ALL, handle))

# chạy check timeout mỗi 30s
app.job_queue.run_repeating(check_timeout, interval=30, first=30)

if __name__ == "__main__":
    log("Bot đang chạy...")
    app.run_polling()