import os
import sqlite3
import re
import threading
from datetime import datetime
from flask import Flask
from telegram import Update, BotCommand, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters
import logging

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# --- FLASK WEB SERVER (Render Sleep မသွားစေရန်) ---
app_flask = Flask(__name__)

@app_flask.route('/')
def home():
    return "Archive Bot is alive and running!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app_flask.run(host='0.0.0.0', port=port)
# ------------------------------------------------

def init_db():
    conn = sqlite3.connect('archive.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            search_text TEXT,
            original_caption TEXT,
            file_id TEXT,
            local_path TEXT,
            sender TEXT,
            file_date TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

async def post_init(application):
    commands = [
        BotCommand("s", "အကြောင်းအရာဖြင့် ရှာရန် (ဥပမာ: /s meeting)"),
        BotCommand("d", "ရက်စွဲဖြင့် ရှာရန် (ဥပမာ: /d 2026-08-30)"),
        BotCommand("dr", "ပြက္ခဒိန်ဖြင့် ရက်အကွာအဝေးရှာရန်"),
        BotCommand("user", "ဝန်ထမ်းအမည်ဖြင့် ရှာရန် (ဥပမာ: /user Kyaw)"),
        BotCommand("stats", "အကျဉ်းချုပ် စာရင်းအင်း ကြည့်ရန်")
    ]
    await application.bot.set_my_commands(commands)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "မင်္ဂလာပါ! Archive & Local Save Bot အသင့်ဖြစ်ပါပြီ။\n\n"
        "👉 ရက်အကွာအဝေးဖြင့် ရှာရန် `/dr` ကို နှိပ်၍ ပြက္ခဒိန်မှ ရက်စွဲများကို ရွေးချယ်နိုင်ပါသည်။"
    )

async def capture_group_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or message.chat.type not in ['group', 'supergroup']:
        return
     
    file_obj = None
    file_name = ""
    if message.document:
        file_obj = message.document
        file_name = file_obj.file_name or "document"
    elif message.photo:
        file_obj = message.photo[-1]
        file_name = f"photo_{file_obj.file_unique_id}.jpg"
    elif message.video:
        file_obj = message.video
        file_name = file_obj.file_name or f"video_{file_obj.file_unique_id}.mp4"
    elif message.audio:
        file_obj = message.audio
        file_name = file_obj.file_name or "audio"
    elif message.animation:
        file_obj = message.animation
        file_name = file_obj.file_name or "animation.mp4"
     
    if file_obj:
        caption = message.caption or ""
        combined_text = f"{file_name} {caption}".strip()
        original_caption = f"📁 {file_name}\n📝 {caption}" if caption else f"📁 {file_name}"
        sender = message.from_user.first_name if message.from_user else "Unknown"
         
        date_match = re.search(r'\d{4}-\d{2}-\d{2}', combined_text)
        file_date = date_match.group(0) if date_match else datetime.now().strftime('%Y-%m-%d')
         
        local_path = None
        if "#save" in caption.lower():
            try:
                file = await context.bot.get_file(file_obj.file_id)
                local_path = os.path.join(DOWNLOAD_DIR, file_name)
                await file.download_to_drive(local_path)
            except Exception as e:
                logging.error(f"Local save error: {e}")
         
        try:
            conn = sqlite3.connect('archive.db')
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO files (search_text, original_caption, file_id, local_path, sender, file_date)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (combined_text.lower(), original_caption, file_obj.file_id, local_path, sender, file_date))
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"Database error: {e}")

async def search_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ ရှာလိုသည့် စကားလုံးထည့်ပါ။ ဥပမာ: /s meeting")
        return
    keyword = " ".join(context.args).lower()
    conn = sqlite3.connect('archive.db')
    cursor = conn.cursor()
    cursor.execute('SELECT original_caption, file_id, sender FROM files WHERE search_text LIKE ?', (f'%{keyword}%',))
    results = cursor.fetchall()
    conn.close()
     
    if not results:
        await update.message.reply_text("❌ အဲ့ဒီစကားလုံးဖြင့် ရှာမတွေ့ပါ။")
        return
     
    for row in results:
        original_caption, file_id, sender = row
        text = f"👤 တင်သူ: {sender}\n📝 အချက်အလက်:\n{original_caption}"
        await update.message.reply_document(document=file_id, caption=text)

async def search_by_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ ရက်စွဲထည့်ပါ။ ဥပမာ: /d 2026-08-30")
        return
    target_date = context.args[0].lower()
    conn = sqlite3.connect('archive.db')
    cursor = conn.cursor()
    cursor.execute('SELECT original_caption, file_id, sender FROM files WHERE file_date = ?', (target_date,))
    results = cursor.fetchall()
    conn.close()
     
    if not results:
        await update.message.reply_text("❌ အဲ့ဒီရက်စွဲဖြင့် ရှာမတွေ့ပါ။")
        return
     
    for row in results:
        original_caption, file_id, sender = row
        text = f"📅 ရက်စွဲကိုက်ညီသော ဖိုင်:\n👤 တင်သူ: {sender}\n📝 အချက်အလက်:\n{original_caption}"
        await update.message.reply_document(document=file_id, caption=text)

async def search_by_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ ဝန်ထမ်းအမည် ထည့်ပါ။ ဥပမာ: /user Kyaw")
        return
    username_keyword = " ".join(context.args).lower()
    conn = sqlite3.connect('archive.db')
    cursor = conn.cursor()
    cursor.execute('SELECT original_caption, file_id, sender FROM files WHERE LOWER(sender) LIKE ?', (f'%{username_keyword}%',))
    results = cursor.fetchall()
    conn.close()
     
    if not results:
        await update.message.reply_text(f"❌ '{username_keyword}' အမည်ဖြင့် တင်ထားသော ဖိုင် မတွေ့ရှိပါ။")
        return
     
    for row in results:
        original_caption, file_id, sender = row
        text = f"👤 ဝန်ထမ်းအမည်: {sender}\n📝 အချက်အလက်:\n{original_caption}"
        await update.message.reply_document(document=file_id, caption=text)

async def stats_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('archive.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM files')
    total_files = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM files WHERE local_path IS NOT NULL')
    local_saved_files = cursor.fetchone()[0]
    conn.close()
     
    stats_text = (
        f"📊 **Archive Database အကျဉ်းချုပ် စာရင်းအင်း**\n\n"
        f"📁 စုစုပေါင်း သိမ်းဆည်းထားသည့် ဖိုင်: `{total_files}` ခု\n"
        f"💻 ကွန်ပျူတာအတွင်း သိမ်းထားသည့် ဖိုင်: `{local_saved_files}` ခု"
    )
    await update.message.reply_text(stats_text, parse_mode="Markdown")

# --- CALENDAR UI FOR DATE RANGE ---
def create_calendar(year=None, month=None):
    now = datetime.now()
    if year is None: year = now.year
    if month is None: month = now.month
     
    keyboard = []
    keyboard.append([InlineKeyboardButton(f"🗓 {year}-{month:02d}", callback_data="IGNORE")])
     
    week_days = ["မန", "အင်", "ဗု", "ကြာ", "သော", "စ", "နာ"]
    keyboard.append([InlineKeyboardButton(day, callback_data="IGNORE") for day in week_days])
     
    days_in_month = 31 if month in [1,3,5,7,8,10,12] else (30 if month in [4,6,9,11] else 28)
     
    week = []
    for day in range(1, days_in_month + 1):
        date_str = f"{year}-{month:02d}-{day:02d}"
        week.append(InlineKeyboardButton(str(day), callback_data=f"CAL_DATE:{date_str}"))
        if len(week) == 7:
            keyboard.append(week)
            week = []
    if week:
        keyboard.append(week)
         
    return InlineKeyboardMarkup(keyboard)

async def calendar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['dr_state'] = 'WAIT_START'
    reply_markup = create_calendar()
    await update.message.reply_text("📅 **စတင်မည့်ရက် (Start Date)** ကို ရွေးချယ်ပါ -", reply_markup=reply_markup, parse_mode="Markdown")

async def inline_calendar_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
     
    data = query.data
    if data == "IGNORE":
        return
     
    if data.startswith("CAL_DATE:"):
        selected_date = data.split(":")[1]
        state = context.user_data.get('dr_state', 'WAIT_START')
         
        if state == 'WAIT_START':
            context.user_data['start_date'] = selected_date
            context.user_data['dr_state'] = 'WAIT_END'
            reply_markup = create_calendar()
            await query.edit_message_text(
                text=f"✅ စတင်ရက်: `{selected_date}`\n\n📅 **ပြီးဆုံးမည့်ရက် (End Date)** ကို ဆက်လက်ရွေးချယ်ပါ -",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        elif state == 'WAIT_END':
            start_date = context.user_data.get('start_date')
            end_date = selected_date
             
            if start_date > end_date:
                start_date, end_date = end_date, start_date
                 
            await query.edit_message_text(text=f"🔍 ရှာဖွေနေသည်... ({start_date} မှ {end_date} ထိ)")
             
            conn = sqlite3.connect('archive.db')
            cursor = conn.cursor()
            cursor.execute('SELECT original_caption, file_id, sender FROM files WHERE file_date BETWEEN ? AND ?', (start_date, end_date))
            results = cursor.fetchall()
            conn.close()
             
            if not results:
                await context.bot.send_message(chat_id=query.message.chat_id, text=f"❌ {start_date} မှ {end_date} အတွင်း ဖိုင်ရှာမတွေ့ပါ။")
                return
             
            for row in results:
                original_caption, file_id, sender = row
                text = f"📅 ရက်အကွာအဝေး ကိုက်ညီသော ဖိုင်:\n👤 တင်သူ: {sender}\n📝 အချက်အလက်:\n{original_caption}"
                await context.bot.send_document(chat_id=query.message.chat_id, document=file_id, caption=text)

if __name__ == '__main__':
    # Flask ဆာဗာကို Background တွင် စတင်ခြင်း (Render Sleep မသွားစေရန်)
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    # Render Environment Variable ထဲကနေ TOKEN ကို လှမ်းယူပါမည်
    TOKEN = os.environ.get("BOT_TOKEN")
    
    application = ApplicationBuilder().token(TOKEN).post_init(post_init).build()
     
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('s', search_data))
    application.add_handler(CommandHandler('d', search_by_date))
    application.add_handler(CommandHandler('dr', calendar_command))
    application.add_handler(CommandHandler('user', search_by_user))
    application.add_handler(CommandHandler('stats', stats_data))
    application.add_handler(CallbackQueryHandler(inline_calendar_handler, pattern="^(CAL_DATE:|IGNORE)"))
     
    media_filter = filters.PHOTO | filters.Document.ALL | filters.VIDEO | filters.AUDIO | filters.ANIMATION
    application.add_handler(MessageHandler(media_filter, capture_group_media))
     
    print("Archive Bot (Calendar UI & Flask Keep-Alive Added) စတင် အလုပ်လုပ်နေပါပြီ...")
    application.run_polling(drop_pending_updates=True)
