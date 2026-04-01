from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import os, json

# ===== CONFIG =====
TOKEN = os.getenv("TELEGRAM_TOKEN")
SHEET_ID = os.getenv("SHEET_ID")
ALLOWED_GROUP = -5229338785
ADMINS = ["Ngoc Anh"]

# ===== GOOGLE SHEET =====
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

cred_dict = json.loads(os.getenv("GOOGLE_CRED"))
creds = Credentials.from_service_account_info(cred_dict, scopes=scope)
client = gspread.authorize(creds)

sheet_progress = client.open_by_key(SHEET_ID).worksheet("Progress")

# ===== CỘT HẠNG MỤC =====
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

    # chặn ngoài group
    if chat_id != ALLOWED_GROUP and user not in ADMINS:
        return

    if "_" not in text:
        return

    parts = text.split(" ", 1)
    cmd_site = parts[0].upper()
    note_content = parts[1].strip() if len(parts) > 1 else ""

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

            now = datetime.now().strftime("%d/%m %H:%M")

            # ===== BD =====
            if cmd_site.endswith("_BD"):
                if sheet_progress.cell(idx, col_bd).value:
                    await update.message.reply_text(f"{sheet_site} đã BD trước đó, dùng /undo")
                    return
                sheet_progress.update_cell(idx, col_bd, now)
                sheet_progress.update_cell(idx, col_user, user)
                await update.message.reply_text(f"{cmd_site} BẮT ĐẦU OK")

            # ===== KT =====
            elif cmd_site.endswith("_KT"):
                if sheet_progress.cell(idx, col_kt).value:
                    await update.message.reply_text(f"{sheet_site} đã KT trước đó, dùng /undo")
                    return
                sheet_progress.update_cell(idx, col_kt, now)
                if not sheet_progress.cell(idx, col_user).value:
                    sheet_progress.update_cell(idx, col_user, user)
                await update.message.reply_text(f"{cmd_site} KẾT THÚC OK")

            # ===== GHI CHÚ =====
            elif note_content:
                old_note = sheet_progress.cell(idx, col_ghichu).value
                new_note = f"[{datetime.now().strftime('%d/%m')}]: {note_content}"
                combined = f"{old_note}\n{new_note}" if old_note else new_note
                sheet_progress.update_cell(idx, col_ghichu, combined)
                await update.message.reply_text("✅ Đã cập nhật ghi chú")

            return

    await update.message.reply_text("❌ Không tìm thấy site hoặc sai cú pháp")

# ===== UNDO =====
async def undo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

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

            await update.message.reply_text(f"✅ Đã undo {cmd_site}")
            return

    await update.message.reply_text("❌ Không tìm thấy")

# ===== STATUS =====
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.full_name
    if user not in ADMINS:
        return

    text = update.message.text.upper()
    hangmuc = text.split("_")[1]

    if hangmuc not in COL_MAP:
        await update.message.reply_text("Sai hạng mục")
        return

    col_bd = col2num(COL_MAP[hangmuc]["BD"])
    col_kt = col2num(COL_MAP[hangmuc]["KT"])
    col_user = col2num(COL_MAP[hangmuc]["USER"])

    rows = sheet_progress.get_all_values()
    today = datetime.now().strftime("%d/%m")

    doing, done = [], []
    cumulative_done = 0

    for row in rows[2:]:
        if len(row) < col_kt:
            continue

        site = row[3]
        bd = row[col_bd-1]
        kt = row[col_kt-1]
        user_val = row[col_user-1]

        if kt:
            cumulative_done += 1
            if today in kt:
                done.append(f"{site} | {user_val}")
        elif bd and today in bd:
            doing.append(f"{site} | {user_val}")

    msg = f"📊 {hangmuc} ({today})\n"
    msg += f"🟡 Đang làm: {len(doing)}\n"
    msg += f"✅ Hoàn thành: {len(done)}\n"
    msg += f"📈 Lũy kế: {cumulative_done}\n\n"

    if doing:
        msg += "🟡\n" + "\n".join(doing) + "\n\n"
    if done:
        msg += "✅\n" + "\n".join(done)

    await update.message.reply_text(msg)

# ===== RUN =====
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle))
app.add_handler(CommandHandler("undo", undo))

for h in COL_MAP.keys():
    app.add_handler(CommandHandler(f"status_{h}", status))

if __name__ == "__main__":
    print("Bot đang chạy...")
    app.run_polling()