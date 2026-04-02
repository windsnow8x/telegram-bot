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
VERSION = os.getenv("BOT_VERSION", "5.1")

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

# ===== PENDING =====
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

        await update.message.reply_text(f"📸 Chờ upload ảnh {site_name} | {hangmuc} (tối đa 5 ảnh / 5 phút)")
        return

    # ================= RECEIVE PHOTO =================
    if update.message.photo:
        if user_id not in pending_upload:
            await update.message.reply_text("❌ Chưa có lệnh _PIC")
            return

        pend = pending_upload[user_id]
        now = now_vn()

        # timeout
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

            # 🔥 FIX BYTEARRAY
            file_bytes = bytes(file_bytes)

            pend["count"] += 1

            filename = f"{now.strftime('%d%m')}_{pend['hangmuc']}_{pend['count']}.jpg"
            dropbox_path = f"/{pend['site']}/{pend['hangmuc']}/{filename}"

            log(f"UPLOAD: {dropbox_path}")

            dbx.files_upload(file_bytes, dropbox_path, mode=dropbox.files.WriteMode.overwrite)

            await update.message.reply_text(f"✅ Upload {pend['count']}/5")

        except Exception as e:
            log(f"ERROR: {e}")
            await update.message.reply_text(f"❌ Upload lỗi: {e}")

        return

    # ================= SHEET =================
    if "_" not in text:
        return

    parts = text.split(" ", 1)
    cmd_site = parts[0].upper()
    note = parts[1] if len(parts) > 1 else ""

    cmd_parts = cmd_site.split("_")
    hangmuc = cmd_parts[-2]
    action = cmd_parts[-1]
    site_name = "_".join(cmd_parts[:-2])

    for idx, sheet_site in enumerate(sites, start=1):
        if sheet_site.strip().upper() != site_name:
            continue

        if hangmuc not in COL_MAP:
            return

        cols = COL_MAP[hangmuc]

        col_bd = col2num(cols["BD"])
        col_kt = col2num(cols["KT"])
        col_user = col2num(cols["USER"])
        col_note = col2num(cols["GHICHU"])

        now_str = now_vn().strftime("%d/%m %H:%M")

        bd = sheet_progress.cell(idx, col_bd).value
        kt = sheet_progress.cell(idx, col_kt).value

        if action == "BD":
            sheet_progress.update_cell(idx, col_bd, now_str)
            if not kt:
                sheet_progress.update_cell(idx, col_user, user)

        elif action == "KT":
            sheet_progress.update_cell(idx, col_kt, now_str)
            sheet_progress.update_cell(idx, col_user, user)

        elif note:
            sheet_progress.update_cell(idx, col_note, note)

        await update.message.reply_text("✅ OK")
        return

# ===== RESET =====
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.full_name
    if user not in ADMINS:
        return
    pending_upload.clear()
    await update.message.reply_text("✅ Reset pending")

# ===== HANDLE =====
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    user = update.effective_user.full_name

    if chat_id != ALLOWED_GROUP and user not in ADMINS:
        return

    if "_" not in text:
        return

    parts = text.split(" ", 1)
    cmd_site = parts[0].upper()
    note_content = parts[1].strip() if len(parts) > 1 else ""

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

        site_name = cmd_site.split("_" + hangmuc)[0]

        for idx, sheet_site in enumerate(sites, start=1):
            if sheet_site.strip().upper() != site_name:
                continue

            now = datetime.now().strftime("%d/%m %H:%M")

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
    msg += f"📌 Hoàn thành hôm nay: {total_today_done}/{len(rows)-2} sites\n"
    msg += f"📌 Lũy kế hoàn thành: {total_done}/{len(rows)-2} sites\n\n"

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

    rows = sheet_progress.get_all_values()
    today = datetime.now().strftime("%d/%m")
    now_full = datetime.now().strftime("%d/%m %H:%M")

    total_sites = len(rows) - 2
    msg = f"📊 UPDATE TIẾN ĐỘ ({now_full})\n\n"

    for hangmuc, cols in COL_MAP.items():
        col_kt = col2num(cols["KT"])

        total_done = 0
        today_done = 0

        for row in rows[2:]:
            if len(row) < col_kt:
                continue

            kt = row[col_kt-1]

            if kt:
                total_done += 1
                if today in kt:
                    today_done += 1

        msg += f"- {hangmuc}: {today_done} / {total_done} / {total_sites}\n"

    await update.message.reply_text(msg)

# ===== RUN =====
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle))
app.add_handler(CommandHandler("reset", reset))

if __name__ == "__main__":
    log("Bot đang chạy...")
    app.run_polling()