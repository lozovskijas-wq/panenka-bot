import json
import logging
import os
import base64
import gspread
import sys
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from flask import Flask
from threading import Thread

# Переменные окружения
BOT_TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_IDS = [286355827, 1323001282]
HELP_ADMIN_ID = 8735141206
SPREADSHEET_ID = "1PCGcpWlACOpvs90NjKenKu8lhPF1aoMpUUp6SBlLGXM"

if not BOT_TOKEN:
    print("ERROR: BOT_TOKEN is not set")
    sys.exit(1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask для health check
flask_app = Flask('')

@flask_app.route('/')
def home():
    return "OK"

def run_flask():
    flask_app.run(host='0.0.0.0', port=10000)

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
    """Старт бота"""
    context.user_data.clear()
    text = "Привет! На связи футбольный квиз «Паненка» ✌🏻\n\nВыберите город и дату 👇"
    keyboard = [[InlineKeyboardButton("Москва 11.04", callback_data="city_moscow")]]
    
    if os.path.exists('logo.jpg'):
        with open('logo.jpg', 'rb') as photo:
            await update.message.reply_photo(photo, caption=text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    action = query.data
    logger.info(f"Нажата кнопка: {action}")
    
    if action == "city_moscow":
        text = """📍 Москва – 11 апреля (суббота)

🏟️ Бар «Золотая Вобла»
📫 Протоповоский пер, 3

🕖 Двери открыты с 16:00
⚽️ Старт игры – 16:20

💰 Стоимость участия:
800₽ – в джерси любого клуба или сборной,
1 000₽ – в обычной одежде

Если команда уже заявлена другим способом – повторная регистрация не нужна.

Если команда ещё не заявлена – сейчас самое время это сделать."""
        
        keyboard = [
            [InlineKeyboardButton("📄 Заявить команду", callback_data="register")],
            [
                InlineKeyboardButton("❓ Помощь", callback_data="help"),
                InlineKeyboardButton("🔙 Назад", callback_data="back")
            ]
        ]
        
        if os.path.exists('photo1.jpg'):
            with open('photo1.jpg', 'rb') as photo:
                await query.message.reply_photo(photo, caption=text, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif action == "back":
        text = "Привет! На связи футбольный квиз «Паненка» ✌🏻\n\nВыберите город и дату 👇"
        keyboard = [[InlineKeyboardButton("Москва 11.04", callback_data="city_moscow")]]
        
        if os.path.exists('logo.jpg'):
            with open('logo.jpg', 'rb') as photo:
                await query.message.reply_photo(photo, caption=text, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        context.user_data.clear()
    
    elif action == "help":
        context.user_data['help_mode'] = True
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_city")]]
        await query.message.reply_text(
            "❓ Есть вопрос?\n\nНапишите его сюда и мы ответим в ближайшее время.\n\nВаш вопрос:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif action == "back_to_city":
        text = """📍 Москва – 11 апреля (суббота)

🏟️ Бар «Золотая Вобла»
📫 Протоповоский пер, 3

🕖 Двери открыты с 16:00
⚽️ Старт игры – 16:20

💰 Стоимость участия:
800₽ – в джерси любого клуба или сборной,
1 000₽ – в обычной одежде

Если команда уже заявлена другим способом – повторная регистрация не нужна.

Если команда ещё не заявлена – сейчас самое время это сделать."""
        
        keyboard = [
            [InlineKeyboardButton("📄 Заявить команду", callback_data="register")],
            [
                InlineKeyboardButton("❓ Помощь", callback_data="help"),
                InlineKeyboardButton("🔙 Назад", callback_data="back")
            ]
        ]
        
        if os.path.exists('photo1.jpg'):
            with open('photo1.jpg', 'rb') as photo:
                await query.message.reply_photo(photo, caption=text, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif action == "register":
        context.user_data.clear()
        context.user_data['step'] = 'team'
        context.user_data['registration_data'] = {}
        await query.message.reply_text(
            "Отлично! ✌🏻\n\nДавайте зарегистрируем команду на игру в Москве — 11 апреля.\n\nВведите название команды 👇"
        )
    
    elif action == "legioner_yes":
        if 'registration_data' not in context.user_data:
            context.user_data['registration_data'] = {}
        context.user_data['registration_data']['legioner'] = "Да"
        context.user_data['step'] = 'captain'
        await query.message.reply_text("Напишите имя и номер телефона капитана 👇")
    
    elif action == "legioner_no":
        if 'registration_data' not in context.user_data:
            context.user_data['registration_data'] = {}
        context.user_data['registration_data']['legioner'] = "Нет"
        context.user_data['step'] = 'captain'
        await query.message.reply_text("Напишите имя и номер телефона капитана 👇")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений"""
    user = update.effective_user
    text = update.message.text.strip()
    
    logger.info(f"Сообщение от {user.id}: '{text}', step={context.user_data.get('step')}")
    
    # Режим помощи
    if context.user_data.get('help_mode'):
        msg = f"❓ Вопрос от {user.full_name} (@{user.username})\n\n{text}"
        await context.bot.send_message(chat_id=HELP_ADMIN_ID, text=msg)
        await update.message.reply_text(
            "✅ Ваш вопрос отправлен! Мы ответим в ближайшее время.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 В главное меню", callback_data="back")
            ]])
        )
        context.user_data.pop('help_mode', None)
        return
    
    # Режим регистрации
    step = context.user_data.get('step')
    
    # Если нет активного шага - показываем главное меню
    if not step:
        text = "Привет! На связи футбольный квиз «Паненка» ✌🏻\n\nВыберите город и дату 👇"
        keyboard = [[InlineKeyboardButton("Москва 11.04", callback_data="city_moscow")]]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    # Получаем или создаем данные регистрации
    if 'registration_data' not in context.user_data:
        context.user_data['registration_data'] = {}
    
    reg_data = context.user_data['registration_data']
    
    # Шаг 1: Название команды
    if step == 'team':
        if not text:
            await update.message.reply_text("Введите название команды 👇")
            return
        
        reg_data['team'] = text
        context.user_data['step'] = 'players'
        await update.message.reply_text("Сколько игроков будет в команде? (от 3 до 10 человек)")
        return
    
    # Шаг 2: Количество игроков
    if step == 'players':
        if not text.isdigit():
            await update.message.reply_text("Пожалуйста, введите число (от 3 до 10):")
            return
        count = int(text)
        if count < 3 or count > 10:
            await update.message.reply_text("Количество игроков должно быть от 3 до 10. Введите число:")
            return
        
        reg_data['players'] = text
        context.user_data['step'] = 'legioner'
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Да", callback_data="legioner_yes"),
                InlineKeyboardButton("❌ Нет", callback_data="legioner_no")
            ]
        ]
        await update.message.reply_text(
            "Готовы ли взять в команду «легионера» (человека без команды)?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # Шаг 3: Данные капитана (принимаем ЛЮБОЙ текст)
    if step == 'captain':
        if not text:
            await update.message.reply_text("Напишите имя и номер телефона капитана 👇")
            return
        
        # Сохраняем всё, что ввел пользователь
        reg_data['captain'] = text
        
        # Формируем регистрацию
        registration = {
            'team': reg_data.get('team', ''),
            'players': reg_data.get('players', ''),
            'legioner': reg_data.get('legioner', 'Не указано'),
            'captain': text,
            'user_id': user.id,
            'user_name': user.full_name,
            'date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Сохраняем в JSON
        data = load_data()
        data['registrations'].append(registration)
        save_data(data)
        
        # Сохраняем в Google Sheets
        await save_to_google_sheets(registration)
        
        # Уведомление админам
        admin_msg = f"🔔 НОВАЯ РЕГИСТРАЦИЯ!\n\nКоманда: {registration['team']}\nИгроков: {registration['players']}\nЛегионер: {registration['legioner']}\nКапитан: {registration['captain']}\nОт: {user.full_name}"
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(chat_id=admin_id, text=admin_msg)
            except:
                pass
        
        # Ответ пользователю
        result = f"✅ Команда зарегистрирована!\n\n🏆 {registration['team']}\n👥 {registration['players']} игроков\n🌟 Легионер: {registration['legioner']}\n👨‍💼 Капитан: {registration['captain']}\n\nЖдем вас!"
        keyboard = [[InlineKeyboardButton("🔙 В главное меню", callback_data="back")]]
        await update.message.reply_text(result, reply_markup=InlineKeyboardMarkup(keyboard))
        
        # Очищаем данные
        context.user_data.clear()
        return

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔️ У вас нет доступа к этой команде")
        return
    data = load_data()
    count = len(data.get('registrations', []))
    await update.message.reply_text(f"📊 Всего зарегистрировано команд: {count}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Действие отменено")
    await start(update, context)

# ============ ЗАПУСК ============

def main():
    # Запускаем Flask в отдельном потоке
    Thread(target=run_flask, daemon=True).start()
    
    # Создаем приложение
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Добавляем обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CallbackQueryHandler(button_click))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("=" * 50)
    print("✅ БОТ ЗАПУЩЕН!")
    print("=" * 50)
    
    # Запускаем бота
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()