from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import difflib

# ===== CONFIG =====
TOKEN = "8717652059:AAEXbfS-JE162l3koYR8pCpJWNX_uUiNd0c"
SHEET_ID = "1LD6mS59-jX7gpntKuqKonfsK9iFBQEG7t_q5Ghz7318"
ALLOWED_GROUP = -5229338785
ADMINS = ["Ngoc Anh"]

# ===== GOOGLE SHEET =====
scope = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file("cred.json", scopes=scope)
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

# ===== XỬ LÝ BD/KT/GHI CHÚ VỚI GỢI Ý =====
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

    parts = text.split(" ",1)
    cmd_site = parts[0].upper()
    note_content = parts[1].strip() if len(parts)>1 else ""

    sites = sheet_progress.col_values(4)
    sites_upper = [s.upper() for s in sites]

    # tách site và hạng mục
    found_hangmuc = None
    for hangmuc in COL_MAP.keys():
        if hangmuc in cmd_site:
            found_hangmuc = hangmuc
            break

    if not found_hangmuc:
        await update.message.reply_text("Cú pháp gõ sai, vui lòng dùng Site_HANGMUC_BD hoặc Site_HANGMUC_KT")
        return

    hangmuc = found_hangmuc
    site_name = cmd_site.split("_" + hangmuc)[0]

    # check xem site có tồn tại
    if site_name.upper() not in sites_upper:
        close = difflib.get_close_matches(site_name.upper(), sites_upper, n=3, cutoff=0.5)
        suggestion = f" Gợi ý: {', '.join(close)}" if close else ""
        await update.message.reply_text(f"Mã trạm bạn gõ bị sai.{suggestion}")
        return

    # check cú pháp BD / KT
    if not (cmd_site.endswith("_BD") or cmd_site.endswith("_KT")) and not note_content:
        await update.message.reply_text(f"Cú pháp gõ sai. Cú pháp đúng: {site_name}_{hangmuc}_BD hoặc {site_name}_{hangmuc}_KT")
        return

    # tìm cột
    cols = COL_MAP[hangmuc]
    col_bd = col2num(cols["BD"])
    col_kt = col2num(cols["KT"])
    col_user = col2num(cols["USER"])
    col_ghichu = col2num(cols["GHICHU"])

    # tìm idx của site
    idx = sites_upper.index(site_name.upper()) + 1

    # BD / KT / ghi chú
    if cmd_site.endswith("_BD"):
        if sheet_progress.cell(idx,col_bd).value:
            await update.message.reply_text(f"{site_name} đã BD trước đó, muốn cập nhật lại phải /undo")
            return
        now = datetime.now().strftime("%d/%m %H:%M")
        sheet_progress.update_cell(idx,col_bd,now)
        sheet_progress.update_cell(idx,col_user,user)
        await update.message.reply_text(f"{cmd_site} BẮT ĐẦU OK")
    elif cmd_site.endswith("_KT"):
        if sheet_progress.cell(idx,col_kt).value:
            await update.message.reply_text(f"{site_name} đã KT trước đó, muốn cập nhật lại phải /undo")
            return
        now = datetime.now().strftime("%d/%m %H:%M")
        sheet_progress.update_cell(idx,col_kt,now)
        if not sheet_progress.cell(idx,col_user).value:
            sheet_progress.update_cell(idx,col_user,user)
        await update.message.reply_text(f"{cmd_site} KẾT THÚC OK")
    else:
        if note_content:
            old_note = sheet_progress.cell(idx,col_ghichu).value
            new_note = f"[{datetime.now().strftime('%d/%m')}]: {note_content}"
            combined = f"{old_note}\n{new_note}" if old_note else new_note
            sheet_progress.update_cell(idx,col_ghichu,combined)
            await update.message.reply_text(f"Ghi chú đã cập nhật: {note_content}")

# ===== UNDO =====
async def undo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    chat_id = update.effective_chat.id
    user = update.effective_user.full_name
    if chat_id != ALLOWED_GROUP and user not in ADMINS:
        return

    parts = update.message.text.split()
    if len(parts)<2:
        await update.message.reply_text("Dùng: /undo SiteID_HẠNGMỤC")
        return

    cmd_site = parts[1].upper()
    sites = sheet_progress.col_values(4)
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
            current_user = sheet_progress.cell(idx,col_user).value
            if current_user and current_user != user and user not in ADMINS:
                await update.message.reply_text("Bạn không có quyền undo")
                return
            sheet_progress.update_cell(idx,col_bd,"")
            sheet_progress.update_cell(idx,col_kt,"")
            sheet_progress.update_cell(idx,col_user,"")
            sheet_progress.update_cell(idx,col_ghichu,"")
            await update.message.reply_text(f"Đã undo {cmd_site}")
            found = True
            break
        if found:
            break

    if not found:
        await update.message.reply_text("Không tìm thấy site/hạng mục để undo")

# ===== STATUS =====
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    user = update.effective_user.full_name
    if user not in ADMINS:
        await update.message.reply_text("Chỉ admin mới xem được status")
        return

    text = update.message.text.strip().upper()
    if not text.startswith("/STATUS_"):
        return
    hangmuc = text.split("_")[1]
    if hangmuc not in COL_MAP:
        await update.message.reply_text("Hạng mục không hợp lệ")
        return

    col_bd = col2num(COL_MAP[hangmuc]["BD"])
    col_kt = col2num(COL_MAP[hangmuc]["KT"])
    col_user = col2num(COL_MAP[hangmuc]["USER"])

    rows = sheet_progress.get_all_values()
    today = datetime.now().strftime("%d/%m")

    doing_today = []
    done_today = []
    cumulative_done = 0
    total_sites = len([r[3] for r in rows[2:] if r[3]])  # từ hàng 3 trở đi

    for idx, row in enumerate(rows[2:], start=3):
        site_id = row[3]
        bd_val = row[col_bd-1]
        kt_val = row[col_kt-1]
        user_val = row[col_user-1]

        if kt_val:
            cumulative_done += 1
            if today in kt_val:
                done_today.append(f"{site_id} | ✅ {user_val} ({kt_val})")
        elif bd_val and today in bd_val:
            doing_today.append(f"{site_id} | 🟡 {user_val} ({bd_val})")

    total_today = len(done_today) + len(doing_today)

    msg = f"📊 {hangmuc} HÔM NAY ({today})\n\n"
    msg += f"📌 Hoàn thành hôm nay: {len(done_today)}/{total_today} sites\n"
    msg += f"📌 Lũy kế hoàn thành: {cumulative_done}/{total_sites} sites\n"
    msg += f"🟡 Đang làm: {len(doing_today)}\n"
    msg += f"✅ Hoàn thành: {len(done_today)}\n\n"

    if doing_today:
        msg += "🟡 ĐANG LÀM\n" + "\n".join(doing_today) + "\n\n"
    if done_today:
        msg += "✅ HOÀN THÀNH\n" + "\n".join(done_today)

    await update.message.reply_text(msg)

# ===== RUN BOT =====
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle))
app.add_handler(CommandHandler("undo", undo))
for h in COL_MAP.keys():
    app.add_handler(CommandHandler(f"status_{h}", status))

print("Bot đang chạy...")
app.run_polling()