import json
import logging
import os
import base64
import gspread
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Переменные окружения
BOT_TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_IDS = [286355827, 1323001282]
HELP_ADMIN_ID = 8735141206
SPREADSHEET_ID = "1PCGcpWlACOpvs90NjKenKu8lhPF1aoMpUUp6SBlLGXM"

if not BOT_TOKEN:
    print("ERROR: BOT_TOKEN is not set")
    exit(1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Восстановление credentials.json
if os.environ.get('GOOGLE_CREDENTIALS_BASE64'):
    creds_json = base64.b64decode(os.environ.get('GOOGLE_CREDENTIALS_BASE64')).decode('utf-8')
    with open('credentials.json', 'w') as f:
        f.write(creds_json)
    print("✅ credentials.json восстановлен")

DATA_FILE = "data.json"

def load_data():
    if not os.path.exists(DATA_FILE):
        return {"registrations": []}
    with open(DATA_FILE, 'r') as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

async def save_to_google_sheets(reg):
    try:
        from oauth2client.service_account import ServiceAccountCredentials
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SPREADSHEET_ID).sheet1
        row = [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), reg['team'], reg['players'], reg['legioner'], reg['captain'], reg['user_name']]
        sheet.append_row(row)
        logger.info("✅ Сохранено в Google Sheets")
    except Exception as e:
        logger.error(f"Ошибка Google Sheets: {e}")

# ============ ОБРАБОТЧИКИ ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    context.user_data.clear()
    text = "Привет! На связи футбольный квиз «Паненка» ✌🏻\n\nВыберите город:"
    keyboard = [[InlineKeyboardButton("Москва 11.04", callback_data="city_moscow")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик всех кнопок"""
    query = update.callback_query
    await query.answer()
    action = query.data
    logger.info(f"Кнопка: {action}")
    
    # ===== КНОПКА ГОРОДА =====
    if action == "city_moscow":
        text = """📍 Москва – 11 апреля (суббота)

🏟️ Бар «Золотая Вобла»
📫 Протоповоский пер, 3

🕖 Двери открыты с 16:00
⚽️ Старт игры – 16:20

💰 Стоимость участия:
800₽ – в джерси любого клуба или сборной
1 000₽ – в обычной одежде

Если команда уже заявлена другим способом – повторная регистрация не нужна.

Если команда ещё не заявлена – сейчас самое время это сделать."""
        
        keyboard = [
            [InlineKeyboardButton("📄 Заявить команду", callback_data="register")],
            [InlineKeyboardButton("❓ Помощь", callback_data="help"), InlineKeyboardButton("🔙 Назад", callback_data="back")]
        ]
        await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    
    # ===== КНОПКА НАЗАД В ГЛАВНОЕ МЕНЮ =====
    elif action == "back":
        text = "Выберите город:"
        keyboard = [[InlineKeyboardButton("Москва 11.04", callback_data="city_moscow")]]
        await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    
    # ===== КНОПКА ПОМОЩЬ =====
    elif action == "help":
        context.user_data['help_mode'] = True
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_city")]]
        await query.message.reply_text("❓ Напишите ваш вопрос одним сообщением:", reply_markup=InlineKeyboardMarkup(keyboard))
    
    # ===== КНОПКА НАЗАД К ГОРОДУ =====
    elif action == "back_to_city":
        text = """📍 Москва – 11 апреля (суббота)

🏟️ Бар «Золотая Вобла»
📫 Протоповоский пер, 3

🕖 Двери открыты с 16:00
⚽️ Старт игры – 16:20

💰 Стоимость участия:
800₽ – в джерси любого клуба или сборной
1 000₽ – в обычной одежде"""
        
        keyboard = [
            [InlineKeyboardButton("📄 Заявить команду", callback_data="register")],
            [InlineKeyboardButton("❓ Помощь", callback_data="help"), InlineKeyboardButton("🔙 Назад", callback_data="back")]
        ]
        await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    
    # ===== КНОПКА РЕГИСТРАЦИЯ =====
    elif action == "register":
        context.user_data['reg'] = {}
        context.user_data['step'] = 'team'
        await query.message.reply_text("Введите название команды 👇")
    
    # ===== КНОПКИ ЛЕГИОНЕРА =====
    elif action == "legioner_yes":
        context.user_data['reg']['legioner'] = "Да"
        context.user_data['step'] = 'captain'
        await query.message.reply_text("Напишите имя и номер телефона капитана 👇\n\nПример: Иван Иванов, +7 999 123-45-67")
    
    elif action == "legioner_no":
        context.user_data['reg']['legioner'] = "Нет"
        context.user_data['step'] = 'captain'
        await query.message.reply_text("Напишите имя и номер телефона капитана 👇\n\nПример: Иван Иванов, +7 999 123-45-67")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    user = update.effective_user
    text = update.message.text.strip()
    
    # ===== РЕЖИМ ПОМОЩИ =====
    if context.user_data.get('help_mode'):
        msg = f"❓ Вопрос от {user.full_name} (@{user.username})\n\n{text}"
        await context.bot.send_message(chat_id=HELP_ADMIN_ID, text=msg)
        await update.message.reply_text("✅ Вопрос отправлен! Мы ответим в ближайшее время.")
        context.user_data.pop('help_mode', None)
        return
    
    # ===== РЕЖИМ РЕГИСТРАЦИИ =====
    if 'reg' in context.user_data:
        reg = context.user_data['reg']
        step = context.user_data.get('step')
        
        # Шаг 1: название команды
        if step == 'team':
            if len(text) > 50:
                await update.message.reply_text("Название слишком длинное (до 50 символов). Попробуйте еще:")
                return
            reg['team'] = text
            context.user_data['step'] = 'players'
            await update.message.reply_text("Сколько игроков? (от 3 до 10)")
        
        # Шаг 2: количество игроков
        elif step == 'players':
            if not text.isdigit():
                await update.message.reply_text("Введите число от 3 до 10:")
                return
            count = int(text)
            if count < 3 or count > 10:
                await update.message.reply_text("От 3 до 10 игроков. Попробуйте еще:")
                return
            reg['players'] = text
            context.user_data['step'] = 'legioner'
            keyboard = [
                [InlineKeyboardButton("✅ Да", callback_data="legioner_yes")],
                [InlineKeyboardButton("❌ Нет", callback_data="legioner_no")]
            ]
            await update.message.reply_text("Готовы взять легионера (человека без команды)?", reply_markup=InlineKeyboardMarkup(keyboard))
        
        # Шаг 4: данные капитана
        elif step == 'captain':
            reg['captain'] = text
            reg['user_id'] = user.id
            reg['user_name'] = user.full_name
            reg['date'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Сохраняем
            data = load_data()
            data['registrations'].append(reg)
            save_data(data)
            
            # Сохраняем в Google Sheets
            await save_to_google_sheets(reg)
            
            # Уведомление админам
            admin_msg = f"🔔 НОВАЯ РЕГИСТРАЦИЯ!\n\nКоманда: {reg['team']}\nИгроков: {reg['players']}\nЛегионер: {reg['legioner']}\nКапитан: {reg['captain']}\nОт: {user.full_name}"
            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(chat_id=admin_id, text=admin_msg)
                except:
                    pass
            
            # Ответ пользователю
            result = f"✅ Команда зарегистрирована!\n\n🏆 {reg['team']}\n👥 {reg['players']} игроков\n🌟 Легионер: {reg['legioner']}\n👨‍💼 Капитан: {reg['captain']}\n\nЖдем вас!"
            keyboard = [[InlineKeyboardButton("🔙 В главное меню", callback_data="back")]]
            await update.message.reply_text(result, reply_markup=InlineKeyboardMarkup(keyboard))
            
            # Очищаем
            context.user_data.clear()

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика для админов"""
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔️ Доступ запрещен")
        return
    data = load_data()
    count = len(data.get('registrations', []))
    await update.message.reply_text(f"📊 Всего зарегистрировано команд: {count}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена"""
    context.user_data.clear()
    await update.message.reply_text("❌ Отменено")
    await start(update, context)

# ============ ЗАПУСК ============

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CallbackQueryHandler(button_click))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("✅ БОТ ЗАПУЩЕН! Все кнопки работают!")
    
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()