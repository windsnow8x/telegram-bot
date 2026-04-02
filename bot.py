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
ADMINS = ["Ngoc Anh", "Admin BOT", "MBF BOT", "Le Giang", "Mai Trang"]

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
    "CH": {"BD":"AP", "KT":"AQ", "USER":"AR", "GHICHU":"AS"},
    "SW": {"BD":"AT", "KT":"AU", "USER":"AV", "GHICHU":"AW"},
    "OA": {"BD":"AX", "KT":"AY", "USER":"AZ", "GHICHU":"BA"},
    "TD": {"BD":"BB", "KT":"BC", "USER":"BD", "GHICHU":"BE"},
    "TH": {"BD":"BF", "KT":"BG", "USER":"BH", "GHICHU":"BI"},
}

# ===== DISPLAY NAME =====
HM_DISPLAY = {
    "KS": "Survey",
    "CH": "Delivery",
    "LD": "Installation",
    "CM": "Commiss",
    "SW": "Swap",
    "OA": "On-Air",
    "TD": "Dismantle",
    "TH": "Return"
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
            "count": 0
        }
        await update.message.reply_text(f"📸 Chờ upload {site_name} | {hangmuc} (5 ảnh / 5 phút)")
        return

    # ================= RECEIVE PHOTO =================
    if update.message.photo:
        if user_id not in pending_upload:
            await update.message.reply_text("❌ Chưa có lệnh _PIC")
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
            await update.message.reply_text("⏳ Đang upload Dropbox...")
            file = await update.message.photo[-1].get_file()
            file_bytes = await file.download_as_bytearray()
            file_bytes = bytes(file_bytes)
            pend["count"] += 1
            filename = f"{now.strftime('%d%m')}_{pend['hangmuc']}_{pend['count']}.jpg"
            dropbox_path = f"/MBF HW/{pend['site']}/{pend['hangmuc']}/{filename}"
            log(f"UPLOAD: {dropbox_path}")
            dbx.files_upload(file_bytes, dropbox_path, mode=dropbox.files.WriteMode.overwrite)
            await update.message.reply_text(f"✅ Upload {pend['count']}/5")
        except Exception as e:
            log(f"ERROR: {e}")
            await update.message.reply_text(f"❌ Upload lỗi: {e}")
        return

    # ================= UPDATE SHEET =================
    if text.startswith("/") or "_" not in text:
        return

    parts = text.split(" ", 1)
    cmd_site = parts[0].upper()
    note = parts[1] if len(parts) > 1 else ""
    cmd = cmd_site.split("_")
    if len(cmd) < 2:
        return
    hangmuc = cmd[-1]
    site_name = "_".join(cmd[:-1])
    action = None
    if hangmuc not in COL_MAP:
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
            await update.message.reply_text("✅ Đã ghi chú")
            return
        # BD
        if action == "BD":
            sheet_progress.update_cell(idx, col_bd, now_str)
            sheet_progress.update_cell(idx, col_user, user)
            clear_cache()
            await update.message.reply_text("✅ BD OK")
            return
        # KT
        elif action == "KT":
            sheet_progress.update_cell(idx, col_kt, now_str)
            clear_cache()
            await update.message.reply_text("✅ KT OK")
            return

    close = difflib.get_close_matches(site_name, sites_upper, n=3, cutoff=0.5)
    await update.message.reply_text(f"❌ Sai site. Gợi ý: {', '.join(close)}")

# ===== DAILY =====
async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.full_name not in ADMINS:
        return
    if not context.args:
        await update.message.reply_text("Dùng: /daily KS/CH/LD/CM/SW/OA/TD/TH")
        return
    hm = context.args[0].upper()
    if hm not in COL_MAP:
        await update.message.reply_text("❌ Sai hạng mục")
        return
    rows = get_sheet_data()
    today = now_vn().strftime("%d/%m")
    total = len(rows) - 2
    cols = COL_MAP[hm]
    col_bd = col2num(cols["BD"])
    col_kt = col2num(cols["KT"])
    col_user = col2num(cols["USER"])
    done_today, done_total = 0, 0
    doing_list, done_list = [], []
    for row in rows[2:]:
        if len(row) < col_kt:
            continue
        site = row[3]
        bd = row[col_bd-1]
        kt = row[col_kt-1]
        user = row[col_user-1] if len(row) >= col_user else ""
        if kt:
            done_total += 1
            if today in kt:
                done_today += 1
                done_list.append((site, user, kt))
        elif bd and today in bd:
            doing_list.append((site, user, bd))

    display_name = HM_DISPLAY.get(hm, hm)
    msg = f"📊 {display_name} TODAY ({today})\n\n"
    msg += f"📌 FINISHED TODAY: {done_today}/{total}\n"
    msg += f"📌 Total: {done_total}/{total}\n\n"
    msg += "✅ Done\n"
    msg += "\n".join([f"{s} | ✅ {u or 'N/A'} ({t})" for s,u,t in done_list]) or "Không có"
    msg += "\n\n🟡 DOING\n"
    msg += "\n".join([f"{s} | 🟡 {u or 'N/A'} ({t})" for s,u,t in doing_list]) or "Không có"
    await update.message.reply_text(msg)

# ===== REPORT =====
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.full_name not in ADMINS:
        return
    rows = get_sheet_data()
    today = now_vn().strftime("%d/%m")
    total = len(rows) - 2
    msg = f"📊 REPORT ({today})\n\n"
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
        display_name = HM_DISPLAY.get(hm, hm)
        msg += f"{display_name}: {today_done}/{done}/{total}\n"
    await update.message.reply_text(msg)

# ===== UNDO =====
async def undo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.full_name
    if user not in ADMINS:
        return
    if not context.args:
        await update.message.reply_text("Dùng: /undo SITE_HM")
        return
    cmd = context.args[0].upper().split("_")
    if len(cmd) < 2:
        return
    hm = cmd[-1]
    site_name = "_".join(cmd[:-1])
    if hm not in COL_MAP:
        return
    sites = sheet_progress.col_values(4)
    for idx, s in enumerate(sites, start=1):
        if s.strip().upper() != site_name:
            continue
        cols = COL_MAP[hm]
        sheet_progress.update_cell(idx, col2num(cols["BD"]), "")
        sheet_progress.update_cell(idx, col2num(cols["KT"]), "")
        sheet_progress.update_cell(idx, col2num(cols["USER"]), "")
        sheet_progress.update_cell(idx, col2num(cols["GHICHU"]), "")
        clear_cache()
        await update.message.reply_text(f"✅ Undo {site_name}_{hm}")
        return

# ===== RESET =====
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pending_upload.clear()
    await update.message.reply_text("✅ Reset pending")

# ===== RUN =====
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("daily", daily))  # Thay status bằng daily
app.add_handler(CommandHandler("report", report))
app.add_handler(CommandHandler("undo", undo))
app.add_handler(CommandHandler("reset", reset))
app.add_handler(MessageHandler(filters.ALL, handle))

if __name__ == "__main__":
    log("Bot đang chạy...")
    app.run_polling()