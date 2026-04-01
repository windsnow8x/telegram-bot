from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from datetime import datetime, timedelta
import pytz
import os, json, difflib, tempfile, asyncio

# ===== VERSION =====
VERSION = os.getenv("BOT_VERSION", "4.0")

def log(msg):
    now = datetime.now(pytz.timezone("Asia/Ho_Chi_Minh")).strftime("%d/%m %H:%M:%S")
    print(f"[{now}] {msg}")

log(f"🚀 START BOT - VERSION {VERSION}")

# ===== CONFIG =====
TOKEN = os.getenv("TELEGRAM_TOKEN")
SHEET_ID = os.getenv("SHEET_ID")
ALLOWED_GROUP = -5229338785
ADMINS = ["Ngoc Anh"]

if not TOKEN:
    raise Exception("❌ TELEGRAM_TOKEN chưa set")

# ===== GOOGLE SHEET =====
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

google_cred = os.getenv("GOOGLE_CRED")
if not google_cred:
    raise Exception("❌ GOOGLE_CRED chưa được set")

try:
    cred_dict = json.loads(google_cred)
except Exception as e:
    raise Exception(f"❌ JSON GOOGLE_CRED lỗi: {e}")

creds = Credentials.from_service_account_info(cred_dict, scopes=scope)
client = gspread.authorize(creds)

try:
    sheet_progress = client.open_by_key(SHEET_ID).worksheet("Progress")
    log("✅ Kết nối Google Sheet OK")
except Exception as e:
    raise Exception(f"❌ Không mở được Google Sheet: {e}")

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

HANGMUC_LABEL = {
    "KS":"Survey", "CH":"Delivery", "LD":"Installation", "CM":"Commiss",
    "SW":"Swap","OA":"On-air","TD":"Dismantle","TH":"Return"
}

# ===== HELPER =====
def col2num(col):
    num = 0
    for c in col:
        num = num*26 + (ord(c.upper()) - ord("A")) + 1
    return num

# ===== PENDING UPLOAD =====
pending_uploads = {}  # user_id: {"site":..,"hangmuc":..,"expires":datetime}

MAX_PENDING_MINUTES = 15
MAX_IMAGES_PER_FOLDER = 5

def clean_expired_pending():
    now = datetime.now(pytz.timezone("Asia/Ho_Chi_Minh"))
    expired = [u for u,v in pending_uploads.items() if v['expires'] < now]
    for u in expired:
        del pending_uploads[u]

# ===== UPLOAD DRIVE =====
def get_or_create_folder(parent_id, name):
    query = f"'{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and name='{name}' and trashed=false"
    res = drive_service.files().list(q=query, fields='files(id, name)').execute()
    files = res.get('files', [])
    if files:
        return files[0]['id']
    # Create
    file_metadata = {"name": name, "mimeType":"application/vnd.google-apps.folder", "parents":[parent_id]}
    folder = drive_service.files().create(body=file_metadata, fields='id').execute()
    return folder['id']

def upload_image_to_drive(site, hangmuc, local_path, index=1):
    # Root folder: SITE
    root_folder_id = get_or_create_folder("root", site)
    sub_folder_id = get_or_create_folder(root_folder_id, hangmuc)
    date_str = datetime.now(pytz.timezone("Asia/Ho_Chi_Minh")).strftime("%d%m")
    filename = f"{date_str}_{hangmuc}_{index}_{site}.jpg"
    media = MediaFileUpload(local_path, mimetype='image/jpeg')
    file_metadata = {"name": filename, "parents":[sub_folder_id]}
    drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()

def count_uploaded_images(site, hangmuc):
    try:
        root_folder_id = get_or_create_folder("root", site)
        sub_folder_id = get_or_create_folder(root_folder_id, hangmuc)
        query = f"'{sub_folder_id}' in parents and mimeType='image/jpeg' and trashed=false"
        res = drive_service.files().list(q=query, fields='files(id)').execute()
        return len(res.get('files',[]))
    except:
        return 0

# ===== HANDLE MESSAGE =====
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clean_expired_pending()
    if not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    user = update.effective_user.full_name
    user_id = update.effective_user.id

    if chat_id != ALLOWED_GROUP and user not in ADMINS:
        return

    # IMAGE PENDING CHECK
    if user_id in pending_uploads and update.message.photo:
        info = pending_uploads[user_id]
        site = info['site']
        hangmuc = info['hangmuc']
        # Count existing images
        existing = count_uploaded_images(site, hangmuc)
        images = update.message.photo[:MAX_IMAGES_PER_FOLDER-existing]
        for idx, p in enumerate(images, start=existing+1):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
                await p.get_file().download_to_drive(tmp.name)
                upload_image_to_drive(site, hangmuc, tmp.name, idx)
        del pending_uploads[user_id]
        await update.message.reply_text(f"✅ Upload {len(images)} ảnh cho {site} ({hangmuc}) xong")
        return

    if "_" not in text:
        return

    parts = text.split(" ",1)
    cmd_site = parts[0].upper()
    note_content = parts[1].strip() if len(parts)>1 else ""

    # HANDLE IMAGE COMMAND
    if cmd_site.endswith("_PIC"):
        segments = cmd_site.split("_")
        if len(segments)<3:
            await update.message.reply_text("❌ Sai cú pháp. Ví dụ: H2_BVI_AO_VUA_KS_PIC")
            return
        site_name = "_".join(segments[:-2])
        hangmuc = segments[-2]
        pending_uploads[user_id] = {
            "site": site_name,
            "hangmuc": hangmuc,
            "expires": datetime.now(pytz.timezone("Asia/Ho_Chi_Minh")) + timedelta(minutes=MAX_PENDING_MINUTES)
        }
        await update.message.reply_text(f"🟡 Đang chờ ảnh cho {site_name} ({hangmuc}), tối đa 15 phút")
        return

    # ===== CẬP NHẬT SHEET GIỮ NGUYÊN =====
    sites = sheet_progress.col_values(4)
    sites_upper = [s.strip().upper() for s in sites if s.strip()]
    found = False

    for hangmuc, cols in COL_MAP.items():
        if hangmuc not in cmd_site:
            continue
        col_bd = col2num(cols["BD"])
        col_kt = col2num(cols["KT"])
        col_user = col2num(cols["USER"])
        col_ghichu = col2num(cols["GHICHU"])
        site_name = cmd_site.split("_"+hangmuc)[0]
        for idx, sheet_site in enumerate(sites, start=1):
            if sheet_site.strip().upper() != site_name:
                continue
            now = datetime.now(pytz.timezone("Asia/Ho_Chi_Minh")).strftime("%d/%m %H:%M")
            if cmd_site.endswith("_BD"):
                if sheet_progress.cell(idx, col_bd).value:
                    await update.message.reply_text(f"{sheet_site} đã BD trước đó")
                    return
                sheet_progress.update_cell(idx, col_bd, now)
                sheet_progress.update_cell(idx, col_user, user)
                await update.message.reply_text(f"{cmd_site} BẮT ĐẦU OK")
            elif cmd_site.endswith("_KT"):
                if sheet_progress.cell(idx, col_kt).value:
                    await update.message.reply_text(f"{sheet_site} đã KT trước đó")
                    return
                sheet_progress.update_cell(idx, col_kt, now)
                if not sheet_progress.cell(idx, col_user).value:
                    sheet_progress.update_cell(idx, col_user, user)
                await update.message.reply_text(f"{cmd_site} KẾT THÚC OK")
            elif note_content:
                old_note = sheet_progress.cell(idx, col_ghichu).value
                new_note = f"[{datetime.now(pytz.timezone('Asia/Ho_Chi_Minh')).strftime('%d/%m')}]: {note_content}"
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
            await update.message.reply_text(f"❌ Không tìm thấy site. Gợi ý gần đúng: {', '.join(close_matches)}")
        else:
            await update.message.reply_text("❌ Sai cú pháp hoặc không tìm thấy site")

# ===== UNDO =====
async def undo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    user = update.effective_user.full_name
    parts = update.message.text.split()
    if len(parts)<2:
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
        site_name = cmd_site.split("_"+hangmuc)[0]
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
    parts = text.split("_")
    if len(parts)<2:
        await update.message.reply_text("Sai cú pháp")
        return
    hangmuc = parts[1]
    if hangmuc not in COL_MAP:
        await update.message.reply_text("Sai hạng mục")
        return
    col_bd = col2num(COL_MAP[hangmuc]["BD"])
    col_kt = col2num(COL_MAP[hangmuc]["KT"])
    col_user = col2num(COL_MAP[hangmuc]["USER"])
    rows = sheet_progress.get_all_values()
    today = datetime.now(pytz.timezone("Asia/Ho_Chi_Minh")).strftime("%d/%m")
    doing_list, done_list, total_done = [], [], 0
    for row in rows[2:]:
        if len(row) < col_kt: continue
        site = row[3]; bd=row[col_bd-1]; kt=row[col_kt-1]; u=row[col_user-1] or "N/A"
        if kt:
            total_done +=1
            if today in kt:
                done_list.append(f"{site} | ✅ {u} ({kt})")
        elif bd and today in bd:
            doing_list.append(f"{site} | 🟡 {u} ({bd})")
    msg=f"📊 {hangmuc} HÔM NAY ({today})\n🟡 {len(doing_list)} | ✅ {len(done_list)} | 📈 {total_done}\n\n"
    if doing_list: msg+="🟡 ĐANG LÀM\n"+ "\n".join(doing_list) + "\n\n"
    if done_list: msg+="✅ HOÀN THÀNH\n"+ "\n".join(done_list)
    await update.message.reply_text(msg)

# ===== REPORT THEO NGƯỜI DÙNG =====
async def report_hangmuc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.full_name
    if user not in ADMINS: return
    text = update.message.text.upper()
    parts = text.split("_")
    if len(parts)<2:
        await update.message.reply_text("❌ Sai cú pháp. Ví dụ: /report_KS")
        return
    hangmuc = parts[1]
    if hangmuc not in COL_MAP:
        await update.message.reply_text("❌ Hạng mục không hợp lệ")
        return
    col_kt = col2num(COL_MAP[hangmuc]['KT'])
    col_user = col2num(COL_MAP[hangmuc]['USER'])
    rows = sheet_progress.get_all_values()
    today = datetime.now(pytz.timezone("Asia/Ho_Chi_Minh")).strftime("%d/%m/%Y")
    user_stats = {}
    total_done = 0
    for row in rows[2:]:
        if len(row) < col_kt: continue
        kt = row[col_kt-1]
        user_val = row[col_user-1] or "N/A"
        site = row[3]
        if kt and today[:5] in kt:
            total_done +=1
            if user_val not in user_stats:
                user_stats[user_val] = {"done":0,"upload":0}
            user_stats[user_val]["done"] +=1
            uploaded = count_uploaded_images(site, hangmuc)
            user_stats[user_val]["upload"] += uploaded
    total_team = len(user_stats)
    label = HANGMUC_LABEL.get(hangmuc, hangmuc)
    msg = f"📊 Detail {label} Done by Team\nNgày {today}\nTotal Done: {total_done} sites ({total_team} Team)\n--------------\n"
    for u, stat in user_stats.items():
        msg += f"- {u} ({label}: {stat['done']} site, upload: {stat['upload']} site)\n"
    await update.message.reply_text(msg)

# ===== RUN APP =====
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle))
app.add_handler(CommandHandler("undo", undo))
for h in COL_MAP.keys():
    app.add_handler(CommandHandler(f"status_{h}", status))
app.add_handler(CommandHandler("report_KS", report_hangmuc))
app.add_handler(CommandHandler("report_LD", report_hangmuc))
app.add_handler(CommandHandler("report_CM", report_hangmuc))

if __name__=="__main__":
    log("Bot đang chạy...")
    app.run_polling()