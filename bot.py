from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone
import os, json
import difflib

# ===== VERSION =====
VERSION = os.getenv("BOT_VERSION", "3.2")

# ===== TIMEZONE VN (KHÔNG LỆCH) =====
VN_TZ = timezone(timedelta(hours=7))

def now_vn():
    return datetime.now(VN_TZ)

def log(msg):
    now = now_vn().strftime("%d/%m %H:%M:%S")
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

cred_dict = json.loads(google_cred)
creds = Credentials.from_service_account_info(cred_dict, scopes=scope)
client = gspread.authorize(creds)

sheet_progress = client.open_by_key(SHEET_ID).worksheet("Progress")
log("✅ Kết nối Google Sheet OK")

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

            now_str = now_vn().strftime("%d/%m %H:%M")

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
                new_note = f"[{now_vn().strftime('%d/%m')}]: {note_content}"
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
            await update.message.reply_text(f"❌ Gợi ý site: {', '.join(close_matches)}")
        else:
            await update.message.reply_text("❌ Sai cú pháp hoặc không tìm thấy site")

# ===== STATUS =====
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.full_name
    if user not in ADMINS:
        return

    hangmuc = update.message.text.upper().split("_")[1]

    col_bd = col2num(COL_MAP[hangmuc]["BD"])
    col_kt = col2num(COL_MAP[hangmuc]["KT"])
    col_user = col2num(COL_MAP[hangmuc]["USER"])

    rows = sheet_progress.get_all_values()

    now = now_vn()
    today = now.strftime("%d/%m")
    current_time = now.strftime("%d/%m %H:%M")

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

    msg = f"📊 {hangmuc} ({current_time})\n\n"
    msg += f"📌 Today Done: {total_today_done}\n"
    msg += f"📌 Total Done: {total_done}\n\n"

    if doing_list:
        msg += "🟡 DOING\n" + "\n".join(doing_list) + "\n\n"

    if done_list:
        msg += "✅ DONE\n" + "\n".join(done_list)

    await update.message.reply_text(msg)

# ===== REPORT =====
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.full_name
    if user not in ADMINS:
        return

    rows = sheet_progress.get_all_values()

    now = now_vn()
    today = now.strftime("%d/%m")
    current_time = now.strftime("%d/%m %H:%M")

    total_sites = len(rows) - 2

    NAME_MAP = {
        "KS": "Survey",
        "CH": "Delivery",
        "LD": "Installation",
        "CM": "Commiss",
        "SW": "Swap",
        "OA": "On-air",
        "TD": "Dismantle",
        "TH": "Return"
    }

    msg = f"📊 Update Progress ({current_time})\n\n"

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

        percent = (total_done / total_sites * 100) if total_sites else 0

        msg += f"- {NAME_MAP[hangmuc]}: {today_done} / {total_done} / {total_sites} ({percent:.1f}%)\n"

    await update.message.reply_text(msg)

# ===== RUN =====
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle))
app.add_handler(CommandHandler("report", report))

for h in COL_MAP.keys():
    app.add_handler(CommandHandler(f"status_{h}", status))

if __name__ == "__main__":
    log("Bot đang chạy...")
    app.run_polling()