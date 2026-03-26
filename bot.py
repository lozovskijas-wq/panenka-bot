import json
import logging
import os
import sys
import time
import base64
import gspread
import signal
from threading import Thread
from datetime import datetime
from typing import Dict, Any, List
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)
from flask import Flask

# Константы
SESSION_TIMEOUT = 300

def signal_handler(sig, frame):
    print('Остановка бота...')
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

app = Flask('')

@app.route('/')
def home():
    return "OK"

def run_web():
    app.run(host='0.0.0.0', port=10000)

if sys.version_info >= (3, 12):
    print("Ошибка: Python 3.12+ не поддерживается. Используйте Python 3.11")
    sys.exit(1)

# Восстановление credentials.json из переменной окружения
if os.environ.get('GOOGLE_CREDENTIALS_BASE64'):
    try:
        creds_base64 = os.environ.get('GOOGLE_CREDENTIALS_BASE64')
        creds_json = base64.b64decode(creds_base64).decode('utf-8')
        with open('credentials.json', 'w') as f:
            f.write(creds_json)
        print("✅ credentials.json восстановлен из переменной окружения")
    except Exception as e:
        print(f"❌ Ошибка восстановления credentials.json: {e}")

# Переменные окружения
BOT_TOKEN = os.environ.get('BOT_TOKEN')
SPECIFIC_ADMIN_ID = 286355827
SECOND_ADMIN_ID = 1323001282
HELP_ADMIN_ID = 8735141206
SPREADSHEET_ID = "1PCGcpWlACOpvs90NjKenKu8lhPF1aoMpUUp6SBlLGXM"

if not BOT_TOKEN:
    print("ERROR: BOT_TOKEN is not set")
    sys.exit(1)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния диалога
MAIN_MENU, CITY_MENU, TEAM_NAME, PLAYER_COUNT, LEGIONER, CAPTAIN_INFO = range(6)

# Фотографии
PHOTO_MOSCOW = "photo1.jpg"
PHOTO_KAZAN = "photo2.jpg"
PHOTO_KRASNODAR = "photo3.jpg"

GAME_INFO = {
    "Москва 11.04": {
        "full_date": "11 апреля (суббота)",
        "venue_short": "Бар «Золотая Вобла»",
        "venue_full": "Протоповоский пер, 3",
        "time_open": "16:00",
        "time_start": "16:20",
        "price_jersey": "800₽",
        "price_regular": "1000₽",
        "photo": PHOTO_MOSCOW,
        "active": True
    },
    "Казань 11.03": {
        "full_date": "11 марта (среда)",
        "venue_short": "Ресторан MAXIMILIAN'S",
        "venue_full": "ул. Спартаковская, 6",
        "time_open": "19:00",
        "time_start": "19:30",
        "price_jersey": "700₽",
        "price_regular": "900₽",
        "photo": PHOTO_KAZAN,
        "active": False
    },
    "Краснодар 14.03": {
        "full_date": "14 марта (суббота)",
        "venue_short": "Бар NAMESTI",
        "venue_full": "ул. Красноармейская, 55/2",
        "time_open": "17:00",
        "time_start": "17:30",
        "price_jersey": "700₽",
        "price_regular": "900₽",
        "photo": PHOTO_KRASNODAR,
        "active": False
    }
}

def get_registration_admin_ids() -> List[int]:
    return [SPECIFIC_ADMIN_ID, SECOND_ADMIN_ID]

def get_help_admin_ids() -> List[int]:
    return [HELP_ADMIN_ID]

DATA_FILE = "data.json"

def load_data() -> Dict[str, Any]:
    if not os.path.exists(DATA_FILE):
        default_data = {
            "games": ["Москва 11.04", "Казань 11.03", "Краснодар 14.03"],
            "registrations": [],
            "users": {}
        }
        save_data(default_data)
        return default_data
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Ошибка загрузки данных: {e}")
        return {"games": [], "registrations": [], "users": {}}

def save_data(data: Dict[str, Any]):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Ошибка сохранения данных: {e}")

async def save_to_google_sheets(registration: Dict[str, Any]):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_file = "credentials.json"
        if os.path.exists(creds_file):
            creds = ServiceAccountCredentials.from_json_keyfile_name(creds_file, scope)
            client = gspread.authorize(creds)
            sheet = client.open_by_key(SPREADSHEET_ID).sheet1
            now = datetime.now()
            row = [
                now.strftime("%Y-%m-%d"),
                now.strftime("%H:%M"),
                registration.get('selected_game', ''),
                registration.get('team_name', ''),
                registration.get('captain_name', ''),
                registration.get('captain_phone', ''),
                str(registration.get('user_id', '')),
                registration.get('player_count', ''),
                registration.get('legioner', ''),
                registration.get('full_name', '')
            ]
            sheet.append_row(row)
            logger.info(f"✅ Данные сохранены в Google Sheets")
    except Exception as e:
        logger.error(f"Ошибка сохранения в Google Sheets: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    
    # Сохраняем пользователя
    data = load_data()
    if "users" not in data:
        data["users"] = {}
    data["users"][str(user_id)] = update.effective_chat.id
    save_data(data)
    
    # Очищаем данные пользователя
    context.user_data.clear()
    
    welcome_text = (
        "Привет! На связи футбольный квиз «Паненка» ✌🏻\n\n"
        "Этот бот поможет вашей команде попасть на ближайший квиз.\n\n"
        "Выберите город и дату 👇"
    )
    
    # Создаем кнопки с активными играми
    games = load_data().get("games", [])
    keyboard = []
    
    for game in games:
        if GAME_INFO.get(game, {}).get("active", False):
            keyboard.append([InlineKeyboardButton(game, callback_data=f"city_{game}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if os.path.exists('logo.jpg'):
        with open('logo.jpg', 'rb') as photo:
            await update.message.reply_photo(
                photo=photo,
                caption=welcome_text,
                reply_markup=reply_markup
            )
    else:
        await update.message.reply_text(
            text=welcome_text,
            reply_markup=reply_markup
        )
    
    return MAIN_MENU

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик всех кнопок"""
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    logger.info(f"Нажата кнопка: {callback_data}")
    
    # Обработка выбора города
    if callback_data.startswith("city_"):
        city = callback_data.replace("city_", "")
        context.user_data["selected_city"] = city
        await show_city_info(update, context)
        return CITY_MENU
    
    # Обработка кнопки "Заявить команду"
    elif callback_data == "register_team":
        await query.message.reply_text(
            "Отлично! ✌🏻\n\nДавайте зарегистрируем команду.\n\nВведите название команды 👇"
        )
        return TEAM_NAME
    
    # Обработка кнопки "Помощь"
    elif callback_data == "help_city":
        help_text = (
            "❓ Есть вопрос?\n\n"
            "Напишите ваш вопрос одним сообщением, и мы ответим в ближайшее время."
        )
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_city")]]
        await query.message.reply_text(
            help_text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return CITY_MENU
    
    # Обработка кнопки "Назад в главное меню"
    elif callback_data == "back_to_main":
        games = load_data().get("games", [])
        keyboard = []
        for game in games:
            if GAME_INFO.get(game, {}).get("active", False):
                keyboard.append([InlineKeyboardButton(game, callback_data=f"city_{game}")])
        
        welcome_text = (
            "Привет! На связи футбольный квиз «Паненка» ✌🏻\n\n"
            "Выберите город и дату 👇"
        )
        
        await query.message.reply_text(
            text=welcome_text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return MAIN_MENU
    
    # Обработка кнопки "Назад" в меню города
    elif callback_data == "back_to_city":
        await show_city_info(update, context)
        return CITY_MENU
    
    # Обработка кнопок легионера
    elif callback_data == "legioner_yes":
        context.user_data["legioner"] = "Да"
        await query.message.reply_text(
            "Напишите имя и номер телефона капитана 👇\n\nПример: Иван Иванов, +7 999 123-45-67"
        )
        return CAPTAIN_INFO
    
    elif callback_data == "legioner_no":
        context.user_data["legioner"] = "Нет"
        await query.message.reply_text(
            "Напишите имя и номер телефона капитана 👇\n\nПример: Иван Иванов, +7 999 123-45-67"
        )
        return CAPTAIN_INFO
    
    return MAIN_MENU

async def show_city_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает информацию о городе"""
    query = update.callback_query
    selected_city = context.user_data.get("selected_city", "Москва 11.04")
    game_info = GAME_INFO.get(selected_city, {})
    
    menu_text = (
        f"📍 Москва – 11 апреля (суббота)\n\n"
        f"🏟️ Бар «Золотая Вобла»\n"
        f"📫 Протоповоский пер, 3\n\n"
        f"🕖 Двери открыты с 16:00\n"
        f"⚽️ Старт игры – 16:20\n\n"
        f"💰 Стоимость участия:\n"
        f"800₽ – в джерси любого клуба или сборной,\n"
        f"1 000₽ – в обычной одежде\n\n"
        f"Если команда уже заявлена другим способом – повторная регистрация не нужна.\n\n"
        f"Если команда ещё не заявлена – сейчас самое время это сделать."
    )
    
    keyboard = [
        [InlineKeyboardButton("📄 Заявить команду", callback_data="register_team")],
        [
            InlineKeyboardButton("❓ Помощь", callback_data="help_city"),
            InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    photo_file = game_info.get('photo')
    if os.path.exists(photo_file):
        with open(photo_file, 'rb') as photo:
            # Отправляем новое сообщение с фото
            await query.message.reply_photo(
                photo=photo,
                caption=menu_text,
                reply_markup=reply_markup
            )
    else:
        # Отправляем новое текстовое сообщение
        await query.message.reply_text(
            text=menu_text,
            reply_markup=reply_markup
        )

async def team_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение названия команды"""
    if update.message.text.startswith('/'):
        await update.message.reply_text("Пожалуйста, введите название команды.")
        return TEAM_NAME
    
    team_name = update.message.text.strip()
    if not team_name or len(team_name) > 50:
        await update.message.reply_text("Пожалуйста, введите корректное название команды (до 50 символов):")
        return TEAM_NAME
    
    context.user_data["team_name"] = team_name
    logger.info(f"Название команды: {team_name}")
    
    await update.message.reply_text("Сколько игроков будет в команде? (от 3 до 10 человек)")
    return PLAYER_COUNT

async def player_count_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение количества игроков"""
    if update.message.text.startswith('/'):
        await update.message.reply_text("Пожалуйста, введите количество игроков.")
        return PLAYER_COUNT
    
    player_count = update.message.text.strip()
    
    if not player_count.isdigit():
        await update.message.reply_text("Пожалуйста, введите число (от 3 до 10):")
        return PLAYER_COUNT
    
    count = int(player_count)
    if count < 3 or count > 10:
        await update.message.reply_text("Количество игроков должно быть от 3 до 10. Введите число:")
        return PLAYER_COUNT
    
    context.user_data["player_count"] = player_count
    logger.info(f"Количество игроков: {player_count}")
    
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
    return LEGIONER

async def captain_info_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение информации о капитане и сохранение регистрации"""
    if update.message.text.startswith('/'):
        await update.message.reply_text("Пожалуйста, введите данные капитана.")
        return CAPTAIN_INFO
    
    captain_info = update.message.text.strip()
    if not captain_info:
        await update.message.reply_text("Пожалуйста, введите имя и телефон капитана:")
        return CAPTAIN_INFO
    
    # Разделяем имя и телефон
    captain_parts = captain_info.split(',')
    captain_name = captain_parts[0].strip() if len(captain_parts) > 0 else captain_info
    captain_phone = captain_parts[1].strip() if len(captain_parts) > 1 else "не указан"
    
    user = update.effective_user
    selected_city = context.user_data.get("selected_city", "Москва 11.04")
    
    registration = {
        "user_id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "selected_game": selected_city,
        "team_name": context.user_data.get("team_name"),
        "player_count": context.user_data.get("player_count"),
        "legioner": context.user_data.get("legioner", "Не указано"),
        "captain_name": captain_name,
        "captain_phone": captain_phone,
        "captain_info": captain_info,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    # Сохраняем в JSON
    data = load_data()
    if "registrations" not in data:
        data["registrations"] = []
    data["registrations"].append(registration)
    save_data(data)
    logger.info(f"Новая регистрация: {registration}")
    
    # Сохраняем в Google Sheets
    await save_to_google_sheets(registration)
    
    # Отправляем подтверждение пользователю
    final_message = (
        f"✅ Команда зарегистрирована!\n\n"
        f"Ждем вас в субботу в баре «Золотая Вобла»\n\n"
        f"Мы свяжемся с капитаном при необходимости."
    )
    
    keyboard = [[InlineKeyboardButton("🔙 В главное меню", callback_data="back_to_main")]]
    await update.message.reply_text(final_message, reply_markup=InlineKeyboardMarkup(keyboard))
    
    # Отправляем уведомление администраторам
    admin_message = (
        f"🔔 Новая регистрация!\n\n"
        f"🎮 Игра: {selected_city}\n"
        f"🏆 Команда: {context.user_data.get('team_name')}\n"
        f"👥 Игроков: {context.user_data.get('player_count')}\n"
        f"🌟 Легионер: {context.user_data.get('legioner', 'Не указано')}\n"
        f"👨‍💼 Капитан: {captain_name}\n"
        f"📞 Телефон: {captain_phone}\n"
        f"👤 От: {user.full_name}\n"
        f"🆔 Username: @{user.username if user.username else 'нет'}"
    )
    
    for admin_id in get_registration_admin_ids():
        try:
            await context.bot.send_message(chat_id=admin_id, text=admin_message)
            logger.info(f"Уведомление отправлено админу {admin_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки админу {admin_id}: {e}")
    
    # Очищаем данные
    context.user_data.clear()
    return MAIN_MENU

async def help_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик сообщений с вопросами"""
    if update.message.text.startswith('/'):
        return
    
    help_text = update.message.text.strip()
    user = update.effective_user
    
    await update.message.reply_text(
        "✅ Ваш вопрос отправлен! Мы ответим в ближайшее время.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 В главное меню", callback_data="back_to_main")
        ]])
    )
    
    admin_message = (
        f"❓ Вопрос от пользователя\n\n"
        f"🆔 ID: {user.id}\n"
        f"👤 Имя: {user.full_name}\n"
        f"📱 Username: @{user.username if user.username else 'нет'}\n"
        f"------------------------\n"
        f"{help_text}"
    )
    
    for admin_id in get_help_admin_ids():
        try:
            await context.bot.send_message(chat_id=admin_id, text=admin_message)
            logger.info(f"Вопрос отправлен админу {admin_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки вопроса: {e}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена текущего действия"""
    context.user_data.clear()
    await update.message.reply_text("❌ Действие отменено")
    return await start(update, context)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика для админов"""
    user_id = update.effective_user.id
    if user_id not in get_registration_admin_ids():
        await update.message.reply_text("⛔️ У вас нет доступа")
        return
    
    data = load_data()
    registrations = data.get("registrations", [])
    
    stats = "📊 Статистика регистраций:\n\n"
    total = 0
    for game in data.get("games", []):
        count = len([r for r in registrations if r.get("selected_game") == game])
        if count > 0:
            stats += f"🏆 {game}: {count} команд\n"
            total += count
    
    stats += f"\n📈 Всего команд: {total}"
    
    await update.message.reply_text(stats)

def main():
    # Запускаем веб-сервер
    Thread(target=run_web, daemon=True).start()
    logger.info("🌐 Веб-сервер запущен")
    
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Создаем ConversationHandler
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("start", start)],
            states={
                MAIN_MENU: [
                    CallbackQueryHandler(button_callback),
                ],
                CITY_MENU: [
                    CallbackQueryHandler(button_callback),
                ],
                TEAM_NAME: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, team_name_received),
                ],
                PLAYER_COUNT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, player_count_received),
                ],
                LEGIONER: [
                    CallbackQueryHandler(button_callback),
                ],
                CAPTAIN_INFO: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, captain_info_received),
                ],
            },
            fallbacks=[
                CommandHandler("cancel", cancel),
                CommandHandler("start", start),
            ],
        )
        
        application.add_handler(conv_handler)
        application.add_handler(CommandHandler("stats", stats_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, help_message_handler))
        
        print("✅ Бот запущен и готов к работе!")
        print(f"👑 Админы для регистраций: {get_registration_admin_ids()}")
        print(f"👑 Админ для вопросов: {get_help_admin_ids()}")
        
        application.run_polling(drop_pending_updates=True)
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        time.sleep(5)
        os.execl(sys.executable, sys.executable, *sys.argv)

if __name__ == "__main__":
    main()