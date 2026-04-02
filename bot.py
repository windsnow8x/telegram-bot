from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from datetime import datetime
import pytz, gspread, os, json, io, difflib

# ===== TIMEZONE VN =====
VN_TZ = pytz.timezone("Asia/Ho_Chi_Minh")
def now_vn():
    return datetime.now(VN_TZ)

# ===== VERSION =====
VERSION = os.getenv("BOT_VERSION", "4.5")

# ===== LOGGING =====
def log(msg):
    now = now_vn().strftime("%d/%m %H:%M:%S")
    print(f"[{now}] {msg}")

log(f"🚀 START BOT - VERSION {VERSION}")

# ===== CONFIG =====
TOKEN = os.getenv("TELEGRAM_TOKEN")
SHEET_ID = os.getenv("SHEET_ID")
DRIVE_ROOT_FOLDER_ID = os.getenv("DRIVE_ROOT_FOLDER_ID")
ALLOWED_GROUP = -5229338785

# ✅ ADMIN
ADMINS = ["Ngoc Anh", "Le Giang", "Admin BOT", "MBF BOT"]

if not TOKEN or not SHEET_ID or not DRIVE_ROOT_FOLDER_ID:
    raise Exception("❌ Vui lòng set TELEGRAM_TOKEN, SHEET_ID, DRIVE_ROOT_FOLDER_ID")

# ===== GOOGLE SHEET =====
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

google_cred = os.getenv("GOOGLE_CRED")
if not google_cred:
    raise Exception("❌ GOOGLE_CRED chưa được set")

cred_dict = json.loads(google_cred)
creds = Credentials.from_service_account_info(cred_dict, scopes=scope)
client = gspread.authorize(creds)
sheet_progress = client.open_by_key(SHEET_ID).worksheet("Progress")
log("✅ Kết nối Google Sheet OK")

# ===== GOOGLE DRIVE =====
drive_service = build('drive', 'v3', credentials=creds)

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
PENDING_TIMEOUT = 15
MAX_UPLOAD = 5

# ===== DRIVE =====
def get_or_create_folder(name, parent_id):
    query = f"mimeType='application/vnd.google-apps.folder' and trashed=false and name='{name}' and '{parent_id}' in parents"
    results = drive_service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])
    if files:
        return files[0]['id']
    file_metadata = {'name': name, 'mimeType': 'application/vnd.google-apps.folder', 'parents':[parent_id]}
    file = drive_service.files().create(body=file_metadata, fields='id').execute()
    return file.get('id')

def upload_file_to_drive(file_bytes, filename, folder_id):
    media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype='image/jpeg')
    file_metadata = {'name': filename, 'parents':[folder_id]}
    drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()

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

    # ===== PIC =====
    if text.upper().endswith("_PIC"):
        cmd_site = text.upper()
        try:
            hangmuc = cmd_site.split("_")[-2]
            site_name = "_".join(cmd_site.split("_")[:-2])
        except:
            await update.message.reply_text("❌ Sai cú pháp _PIC")
            return

        if site_name.upper() not in sites_upper:
            close = difflib.get_close_matches(site_name.upper(), sites_upper, n=3, cutoff=0.5)
            await update.message.reply_text(f"❌ Không tìm thấy site. Gợi ý: {', '.join(close)}" if close else "❌ Không tìm thấy site")
            return

        pending_upload[user_id] = {
            "site": site_name,
            "hangmuc": hangmuc,
            "time": now_vn(),
            "count": 0
        }

        await update.message.reply_text(f"📸 Upload {site_name} | {hangmuc}")
        return

    # ===== RECEIVE PHOTO =====
    if update.message.photo:
        if user_id not in pending_upload:
            await update.message.reply_text("❌ Chưa có lệnh _PIC")
            return

        pend = pending_upload[user_id]
        now = now_vn()

        if (now - pend["time"]).total_seconds() > PENDING_TIMEOUT*60:
            del pending_upload[user_id]
            await update.message.reply_text("❌ Hết hạn upload")
            return

        if pend["count"] >= MAX_UPLOAD:
            await update.message.reply_text("❌ Đã đủ 5 ảnh")
            return

        file = await update.message.photo[-1].get_file()
        file_bytes = await file.download_as_bytearray()
        pend["count"] += 1

        folder_site = get_or_create_folder(pend["site"], DRIVE_ROOT_FOLDER_ID)
        folder_hangmuc = get_or_create_folder(pend["hangmuc"], folder_site)

        filename = f"{now.strftime('%d%m')}_{pend['hangmuc']}_{pend['count']}_{pend['site']}.jpg"
        upload_file_to_drive(file_bytes, filename, folder_hangmuc)

        await update.message.reply_text(f"✅ Upload {pend['count']}/5")
        return

    # ===== SHEET =====
    if "_" not in text or text.upper().endswith("_PIC"):
        return

    parts = text.split(" ", 1)
    cmd_site = parts[0].upper()
    note_content = parts[1].strip() if len(parts) > 1 else ""

    for hangmuc, cols in COL_MAP.items():
        if hangmuc not in cmd_site:
            continue

        col_bd = col2num(cols["BD"])
        col_kt = col2num(cols["KT"])
        col_user = col2num(cols["USER"])
        col_ghichu = col2num(cols["GHICHU"])
        site_name = cmd_site.split("_" + hangmuc)[0]

        for idx, sheet_site in enumerate(sites, start=1):
            if sheet_site.strip().upper() != site_name:
                continue

            now_str = now_vn().strftime("%d/%m %H:%M")

            bd_val = sheet_progress.cell(idx, col_bd).value
            kt_val = sheet_progress.cell(idx, col_kt).value

            # ===== BD =====
            if cmd_site.endswith("_BD"):
                if bd_val:
                    await update.message.reply_text(f"{sheet_site} đã BD trước đó")
                    return

                sheet_progress.update_cell(idx, col_bd, now_str)

                if not kt_val:
                    sheet_progress.update_cell(idx, col_user, user)

                await update.message.reply_text(f"{cmd_site} BẮT ĐẦU OK")
                return

            # ===== KT =====
            elif cmd_site.endswith("_KT"):
                if kt_val:
                    await update.message.reply_text(f"{sheet_site} đã KT trước đó")
                    return

                sheet_progress.update_cell(idx, col_kt, now_str)

                # 🔥 LUÔN ghi đè USER = người KT
                sheet_progress.update_cell(idx, col_user, user)

                await update.message.reply_text(f"{cmd_site} KẾT THÚC OK")
                return

            # ===== NOTE =====
            elif note_content:
                old_note = sheet_progress.cell(idx, col_ghichu).value
                new_note = f"[{now_vn().strftime('%d/%m')}]: {note_content}"
                combined = f"{old_note}\n{new_note}" if old_note else new_note

                sheet_progress.update_cell(idx, col_ghichu, combined)
                await update.message.reply_text("✅ Đã ghi chú")
                return

    await update.message.reply_text("❌ Không tìm thấy site")

# ===== RUN =====
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle))

if __name__ == "__main__":
    log("Bot đang chạy...")
    app.run_polling()