import json
import logging
import os
import base64
import gspread
import asyncio
import sys
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from flask import Flask

# Переменные окружения
BOT_TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_IDS = [286355827, 1323001282]
HELP_ADMIN_ID = 8735141206
SPREADSHEET_ID = "1PCGcpWlACOpvs90NjKenKu8lhPF1aoMpUUp6SBlLGXM"

if not BOT_TOKEN:
    print("ERROR: BOT_TOKEN is not set")
    sys.exit(1)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Flask приложение для health check
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
    """Команда /start"""
    context.user_data.clear()
    logger.info(f"Пользователь {update.effective_user.id} запустил /start")
    
    text = "Привет! На связи футбольный квиз «Паненка» ✌🏻\n\nВыберите город:"
    keyboard = [[InlineKeyboardButton("Москва 11.04", callback_data="city_moscow")]]
    
    if os.path.exists('logo.jpg'):
        with open('logo.jpg', 'rb') as photo:
            await update.message.reply_photo(photo, caption=text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик всех кнопок"""
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
800₽ – в джерси любого клуба или сборной
1 000₽ – в обычной одежде

Если команда уже заявлена другим способом – повторная регистрация не нужна.

Если команда ещё не заявлена – сейчас самое время это сделать."""
        
        keyboard = [
            [InlineKeyboardButton("📄 Заявить команду", callback_data="register")],
            [InlineKeyboardButton("❓ Помощь", callback_data="help"), InlineKeyboardButton("🔙 Назад", callback_data="back")]
        ]
        
        if os.path.exists('photo1.jpg'):
            with open('photo1.jpg', 'rb') as photo:
                await query.message.reply_photo(photo, caption=text, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif action == "back":
        text = "Выберите город:"
        keyboard = [[InlineKeyboardButton("Москва 11.04", callback_data="city_moscow")]]
        
        if os.path.exists('logo.jpg'):
            with open('logo.jpg', 'rb') as photo:
                await query.message.reply_photo(photo, caption=text, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif action == "help":
        context.user_data['help_mode'] = True
        logger.info("Включен режим помощи")
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_city")]]
        await query.message.reply_text("❓ Напишите ваш вопрос одним сообщением:", reply_markup=InlineKeyboardMarkup(keyboard))
    
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
        
        if os.path.exists('photo1.jpg'):
            with open('photo1.jpg', 'rb') as photo:
                await query.message.reply_photo(photo, caption=text, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif action == "register":
        context.user_data['reg'] = {}
        context.user_data['step'] = 'team'
        logger.info("Начата регистрация, шаг: team")
        await query.message.reply_text("Введите название команды 👇")
    
    elif action == "legioner_yes":
        if 'reg' not in context.user_data:
            context.user_data['reg'] = {}
        context.user_data['reg']['legioner'] = "Да"
        context.user_data['step'] = 'captain'
        logger.info(f"Выбран легионер: Да, переходим к шагу: captain")
        await query.message.reply_text("Напишите имя и номер телефона капитана 👇")
    
    elif action == "legioner_no":
        if 'reg' not in context.user_data:
            context.user_data['reg'] = {}
        context.user_data['reg']['legioner'] = "Нет"
        context.user_data['step'] = 'captain'
        logger.info(f"Выбран легионер: Нет, переходим к шагу: captain")
        await query.message.reply_text("Напишите имя и номер телефона капитана 👇")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    user = update.effective_user
    text = update.message.text.strip()
    
    logger.info(f"Получено сообщение от {user.id}: '{text}'")
    logger.info(f"Текущие данные пользователя: {context.user_data}")
    
    # Режим помощи
    if context.user_data.get('help_mode'):
        logger.info("Режим помощи: отправка вопроса админу")
        msg = f"❓ Вопрос от {user.full_name} (@{user.username})\n\n{text}"
        await context.bot.send_message(chat_id=HELP_ADMIN_ID, text=msg)
        await update.message.reply_text("✅ Вопрос отправлен! Мы ответим в ближайшее время.")
        context.user_data.pop('help_mode', None)
        return
    
    # Режим регистрации
    if 'reg' in context.user_data:
        reg = context.user_data['reg']
        step = context.user_data.get('step')
        
        logger.info(f"Режим регистрации, текущий шаг: {step}")
        
        # Шаг 1: название команды
        if step == 'team':
            if len(text) > 50:
                await update.message.reply_text("Название слишком длинное (до 50 символов). Попробуйте еще:")
                return
            if not text:
                await update.message.reply_text("Название не может быть пустым. Введите название:")
                return
            reg['team'] = text
            context.user_data['step'] = 'players'
            logger.info(f"Шаг team завершен, переходим к шагу players")
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
            logger.info(f"Шаг players завершен, переходим к шагу legioner")
            keyboard = [
                [InlineKeyboardButton("✅ Да", callback_data="legioner_yes")],
                [InlineKeyboardButton("❌ Нет", callback_data="legioner_no")]
            ]
            await update.message.reply_text("Готовы взять легионера (человека без команды)?", reply_markup=InlineKeyboardMarkup(keyboard))
        
        # Шаг 3: данные капитана
        elif step == 'captain':
            logger.info(f"Шаг captain: получены данные капитана: {text}")
            
            if len(text) > 200:
                await update.message.reply_text("Данные слишком длинные. Введите короче:")
                return
            if not text:
                await update.message.reply_text("Пожалуйста, введите имя и телефон капитана:")
                return
            
            # Сохраняем данные
            reg['captain'] = text
            reg['user_id'] = user.id
            reg['user_name'] = user.full_name
            reg['date'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            logger.info(f"Сохранение регистрации: {reg}")
            
            # Сохраняем в JSON
            data = load_data()
            data['registrations'].append(reg)
            save_data(data)
            logger.info("✅ Сохранено в JSON")
            
            # Сохраняем в Google Sheets
            await save_to_google_sheets(reg)
            
            # Уведомление админам
            admin_msg = f"🔔 НОВАЯ РЕГИСТРАЦИЯ!\n\nКоманда: {reg['team']}\nИгроков: {reg['players']}\nЛегионер: {reg['legioner']}\nКапитан: {reg['captain']}\nОт: {user.full_name}"
            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(chat_id=admin_id, text=admin_msg)
                    logger.info(f"Уведомление отправлено админу {admin_id}")
                except Exception as e:
                    logger.error(f"Ошибка отправки админу {admin_id}: {e}")
            
            # Ответ пользователю
            result = f"✅ Команда зарегистрирована!\n\n🏆 {reg['team']}\n👥 {reg['players']} игроков\n🌟 Легионер: {reg['legioner']}\n👨‍💼 Капитан: {reg['captain']}\n\nЖдем вас!"
            keyboard = [[InlineKeyboardButton("🔙 В главное меню", callback_data="back")]]
            await update.message.reply_text(result, reply_markup=InlineKeyboardMarkup(keyboard))
            
            # Очищаем данные
            context.user_data.clear()
            logger.info("Регистрация завершена, данные очищены")
        
        else:
            logger.warning(f"Неизвестный шаг: {step}")
            # Если шаг неизвестен, сбрасываем
            context.user_data.clear()
            await update.message.reply_text("Что-то пошло не так. Начните заново с /start")
    
    else:
        logger.info("Нет активного режима, показываем главное меню")
        # Если ничего не ожидаем, показываем главное меню
        text = "Выберите город:"
        keyboard = [[InlineKeyboardButton("Москва 11.04", callback_data="city_moscow")]]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔️ Доступ запрещен")
        return
    data = load_data()
    count = len(data.get('registrations', []))
    await update.message.reply_text(f"📊 Всего зарегистрировано команд: {count}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Отменено")
    await start(update, context)

# ============ ЗАПУСК ============

async def main():
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
    print(f"📁 Текущая директория: {os.getcwd()}")
    print("=" * 50)
    
    # Запускаем бота с очисткой вебхука
    await app.bot.delete_webhook(drop_pending_updates=True)
    
    # Запускаем polling
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    
    # Держим бота запущенным
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await app.stop()

if __name__ == "__main__":
    # Запускаем Flask в отдельном потоке
    from threading import Thread
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Запускаем бота
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен")
    except Exception as e:
        print(f"Ошибка: {e}")