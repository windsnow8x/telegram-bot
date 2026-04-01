from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from datetime import datetime
import pytz, gspread, os, json, io, difflib

# ===== VERSION =====
VERSION = os.getenv("BOT_VERSION", "4.4")

# ===== LOGGING =====
def log(msg):
    now = datetime.now().strftime("%d/%m %H:%M:%S")
    print(f"[{now}] {msg}")

log(f"🚀 START BOT - VERSION {VERSION}")

# ===== CONFIG =====
TOKEN = os.getenv("TELEGRAM_TOKEN")
SHEET_ID = os.getenv("SHEET_ID")
DRIVE_ROOT_FOLDER_ID = os.getenv("DRIVE_ROOT_FOLDER_ID")
ALLOWED_GROUP = -5229338785
ADMINS = ["Ngoc Anh"]

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
pending_upload = {}  # user_id -> {"site":..., "hangmuc":..., "time": datetime, "count":0}
PENDING_TIMEOUT = 15  # phút
MAX_UPLOAD = 5

# ===== HELPER DRIVE =====
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

# ===== HANDLE MESSAGE =====
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

    # ==== Upload ảnh _PIC ====
    if text.upper().endswith("_PIC"):
        cmd_site = text.upper()
        try:
            hangmuc = cmd_site.split("_")[-2]
            site_name = "_".join(cmd_site.split("_")[:-2])
        except:
            await update.message.reply_text("❌ Sai cú pháp lệnh _PIC")
            return

        if site_name.upper() not in sites_upper:
            close = difflib.get_close_matches(site_name.upper(), sites_upper, n=3, cutoff=0.5)
            if close:
                await update.message.reply_text(f"❌ Không tìm thấy site. Gợi ý: {', '.join(close)}")
            else:
                await update.message.reply_text("❌ Không tìm thấy site")
            return

        if user_id in pending_upload:
            await update.message.reply_text("❌ Bạn đang có lệnh upload đang chờ. Hãy gửi ảnh hoặc đợi 15 phút.")
            return

        pending_upload[user_id] = {
            "site": site_name,
            "hangmuc": hangmuc,
            "time": datetime.now(pytz.timezone("Asia/Ho_Chi_Minh")),
            "count": 0
        }
        await update.message.reply_text(f"✅ Chuẩn bị nhận ảnh cho {site_name} | {hangmuc}. Bạn có 15 phút để gửi tối đa 5 ảnh.")
        return

    # ==== Nhận ảnh ====
    if update.message.photo:
        if user_id not in pending_upload:
            await update.message.reply_text("❌ Bạn chưa gửi lệnh _PIC trước khi gửi ảnh.")
            return
        pend = pending_upload[user_id]
        now = datetime.now(pytz.timezone("Asia/Ho_Chi_Minh"))
        if (now - pend["time"]).total_seconds() > PENDING_TIMEOUT*60:
            del pending_upload[user_id]
            await update.message.reply_text("❌ Lệnh upload đã hết hạn. Vui lòng gửi lệnh mới.")
            return
        if pend["count"] >= MAX_UPLOAD:
            await update.message.reply_text(f"❌ Bạn đã upload tối đa {MAX_UPLOAD} ảnh. Gửi lệnh mới để tiếp tục.")
            return

        file = await update.message.photo[-1].get_file()
        file_bytes = await file.download_as_bytearray()
        pend["count"] += 1

        try:
            folder_site = get_or_create_folder(pend["site"], DRIVE_ROOT_FOLDER_ID)
            folder_hangmuc = get_or_create_folder(pend["hangmuc"], folder_site)
            today_str = now.strftime("%d%m")
            filename = f"{today_str}_{pend['hangmuc']}_{pend['count']}_{pend['site']}.jpg"
            upload_file_to_drive(file_bytes, filename, folder_hangmuc)
            await update.message.reply_text(f"✅ Upload thành công {pend['count']} / {MAX_UPLOAD} cho {pend['site']} | {pend['hangmuc']}")
        except Exception as e:
            del pending_upload[user_id]
            await update.message.reply_text(f"❌ Upload thất bại: {e}")
            return

    # ==== Xử lý Google Sheet như cũ ====
    if "_" not in text or text.upper().endswith("_PIC"):
        return

    parts = text.split(" ", 1)
    cmd_site = parts[0].upper()
    note_content = parts[1].strip() if len(parts) > 1 else ""
    found = False

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

            now_str = datetime.now().strftime("%d/%m %H:%M")

            if cmd_site.endswith("_BD"):
                if sheet_progress.cell(idx, col_bd).value:
                    await update.message.reply_text(f"{sheet_site} đã BD trước đó")
                    return
                sheet_progress.update_cell(idx, col_bd, now_str)
                sheet_progress.update_cell(idx, col_user, user)
                await update.message.reply_text(f"{cmd_site} BẮT ĐẦU OK")

            elif cmd_site.endswith("_KT"):
                if sheet_progress.cell(idx, col_kt).value:
                    await update.message.reply_text(f"{sheet_site} đã KT trước đó")
                    return
                sheet_progress.update_cell(idx, col_kt, now_str)
                if not sheet_progress.cell(idx, col_user).value:
                    sheet_progress.update_cell(idx, col_user, user)
                await update.message.reply_text(f"{cmd_site} KẾT THÚC OK")

            elif note_content:
                old_note = sheet_progress.cell(idx, col_ghichu).value
                new_note = f"[{datetime.now().strftime('%d/%m')}]: {note_content}"
                combined = f"{old_note}\n{new_note}" if old_note else new_note
                sheet_progress.update_cell(idx, col_ghichu, combined)
                await update.message.reply_text("✅ Đã ghi chú")

            found = True
            break
        if found:
            break

    if not found:
        close_matches = difflib.get_close_matches(site_name, sites_upper, n=3, cutoff=0.5)
        if close_matches:
            await update.message.reply_text(f"❌ Không tìm thấy site. Gợi ý: {', '.join(close_matches)}")
        else:
            await update.message.reply_text("❌ Sai cú pháp hoặc không tìm thấy site")

# ===== UNDO =====
async def undo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.full_name
    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text("Dùng: /undo SITE_HẠNGMỤC")
        return

    cmd_site = parts[1].upper()
    sites = sheet_progress.col_values(4)

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
            current_user = sheet_progress.cell(idx, col_user).value
            if current_user and current_user != user and user not in ADMINS:
                await update.message.reply_text("❌ Không có quyền undo")
                return
            sheet_progress.update_cell(idx, col_bd, "")
            sheet_progress.update_cell(idx, col_kt, "")
            sheet_progress.update_cell(idx, col_user, "")
            sheet_progress.update_cell(idx, col_ghichu, "")
            await update.message.reply_text(f"✅ Undo {cmd_site}")
            return
    await update.message.reply_text("❌ Không tìm thấy")

# ===== STATUS =====
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.full_name
    if user not in ADMINS:
        return
    text = update.message.text.upper()
    hangmuc = text.split("_")[1]
    col_bd = col2num(COL_MAP[hangmuc]["BD"])
    col_kt = col2num(COL_MAP[hangmuc]["KT"])
    col_user = col2num(COL_MAP[hangmuc]["USER"])
    rows = sheet_progress.get_all_values()
    today = datetime.now().strftime("%d/%m")
    doing_list = []
    done_list = []
    total_done = 0
    total_today_done = 0

    for row in rows[2:]:
        if len(row) < col_kt: continue
        site = row[3]
        bd = row[col_bd-1]
        kt = row[col_kt-1]
        user_val = row[col_user-1] or "N/A"
        if kt: total_done += 1
        if kt and today in kt:
            total_today_done += 1
            done_list.append(f"{site} | ✅ {user_val} ({kt})")
        elif bd and today in bd:
            doing_list.append(f"{site} | 🟡 {user_val} ({bd})")

    msg = f"📊 {hangmuc} HÔM NAY ({today})\n\n"
    msg += f"📌 Hoàn thành hôm nay: {total_today_done}/{len(rows)-2} sites\n"
    msg += f"📌 Lũy kế hoàn thành: {total_done}/{len(rows)-2} sites\n\n"
    if doing_list: msg += "🟡 ĐANG LÀM\n" + "\n".join(doing_list) + "\n\n"
    if done_list: msg += "✅ HOÀN THÀNH\n" + "\n".join(done_list)
    await update.message.reply_text(msg)

# ===== REPORT =====
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.full_name
    if user not in ADMINS: return
    rows = sheet_progress.get_all_values()
    today = datetime.now().strftime("%d/%m")
    now_full = datetime.now().strftime("%d/%m %H:%M")
    total_sites = len(rows)-2
    msg = f"📊 UPDATE TIẾN ĐỘ ({now_full})\n\n"
    for hangmuc, cols in COL_MAP.items():
        col_kt = col2num(cols["KT"])
        total_done = 0
        today_done = 0
        for row in rows[2:]:
            if len(row) < col_kt: continue
            kt = row[col_kt-1]
            if kt:
                total_done += 1
                if today in kt: today_done += 1
        msg += f"- {hangmuc}: {today_done} / {total_done} / {total_sites}\n"
    await update.message.reply_text(msg)

# ===== RESET PENDING (ADMIN) =====
async def reset_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.full_name
    if user not in ADMINS:
        await update.message.reply_text("❌ Chỉ admin mới có quyền reset.")
        return
    pending_upload.clear()
    await update.message.reply_text("✅ Đã reset tất cả lệnh pending.")

# ===== VERSION COMMAND =====
async def bot_version(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Bot đang chạy version {VERSION}")

# ===== RUN BOT =====
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle))
app.add_handler(CommandHandler("undo", undo))
app.add_handler(CommandHandler("report", report))
app.add_handler(CommandHandler("reset", reset_pending))
app.add_handler(CommandHandler("ver", bot_version))
for h in COL_MAP.keys():
    app.add_handler(CommandHandler(f"status_{h}", status))

if __name__ == "__main__":
    log("Bot đang chạy...")
    app.run_polling()