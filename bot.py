import json
import logging
import os
import sys
import time
import base64
import requests
import gspread
import asyncio
import signal
from threading import Thread
from datetime import datetime, timedelta
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
REGISTER_CONFIRM = 7  # Добавляем новое состояние для подтверждения

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
ADMIN_IDS_STR = os.environ.get('ADMIN_ID', '')
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
(
    MAIN_MENU,
    CITY_SELECTED,
    REGISTER_TEAM,
    REGISTER_PLAYERS,
    REGISTER_LEGIONER,
    REGISTER_CAPTAIN,
    HELP_MESSAGE,
    REGISTER_CONFIRM,  # Новое состояние
) = range(8)

# Фотографии
PHOTO_MOSCOW = "photo1.jpg"
PHOTO_KAZAN = "photo2.jpg"
PHOTO_KRASNODAR = "photo3.jpg"

# Кэш для информации об играх
class GameInfoCache:
    _cache = {}
    
    @classmethod
    def get(cls, game_key):
        if game_key not in cls._cache:
            cls._cache[game_key] = GAME_INFO.get(game_key, {})
        return cls._cache[game_key]
    
    @classmethod
    def clear(cls):
        cls._cache.clear()

GAME_INFO = {
    "Москва 11.04": {
        "full_date": "11 апреля (суббота)",
        "venue_short": "Бар «Золотая Вобла»",
        "venue_full": "Протоповоский пер, 3",
        "time_open": "16:00",
        "time_start": "16:20",
        "price_jersey": "800₽",
        "price_regular": "1000₽",
        "city": "Москве",
        "city_prepositional": "Москве",
        "venue_prepositional": "баре «Золотая Вобла»",
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
        "city": "Казани",
        "city_prepositional": "Казани",
        "venue_prepositional": "Ресторане MAXIMILIAN'S",
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
        "city": "Краснодаре",
        "city_prepositional": "Краснодаре",
        "venue_prepositional": "баре NAMESTI",
        "photo": PHOTO_KRASNODAR,
        "active": False
    }
}

def get_admin_ids() -> List[int]:
    admin_ids = [SPECIFIC_ADMIN_ID, SECOND_ADMIN_ID]
    if ADMIN_IDS_STR:
        if isinstance(ADMIN_IDS_STR, str):
            try:
                additional_ids = [int(id_str.strip()) for id_str in ADMIN_IDS_STR.split(',') if id_str.strip()]
                admin_ids.extend(additional_ids)
            except ValueError:
                logger.error(f"Ошибка преобразования ADMIN_ID: {ADMIN_IDS_STR}")
        else:
            admin_ids.append(ADMIN_IDS_STR)
    return list(set(admin_ids))

def get_help_admin_ids() -> List[int]:
    return [HELP_ADMIN_ID]

def get_registration_admin_ids() -> List[int]:
    return [SPECIFIC_ADMIN_ID, SECOND_ADMIN_ID]

DATA_FILE = "data.json"

def load_data() -> Dict[str, Any]:
    if not os.path.exists(DATA_FILE):
        default_data = {
            "games": [
                "Москва 11.04",
                "Казань 11.03",
                "Краснодар 14.03"
            ], 
            "promo_registrations": [],
            "users": {},
            "registrations": []
        }
        save_data(default_data)
        return default_data
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Ошибка загрузки данных: {e}")
        return {"games": [], "promo_registrations": [], "users": {}, "registrations": []}

def save_data(data: Dict[str, Any]):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Ошибка сохранения данных: {e}")

async def save_to_google_sheets_async(registration: Dict[str, Any], retry=3):
    """Асинхронное сохранение с повторными попытками"""
    for attempt in range(retry):
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
                    registration.get('name', ''),
                    registration.get('phone', ''),
                    registration.get('client_id', ''),
                    registration.get('bet_number', ''),
                    registration.get('player_count', ''),
                    registration.get('legioner', ''),
                    registration.get('captain_info', '')
                ]
                sheet.append_row(row)
                logger.info(f"✅ Данные сохранены в Google Sheets")
                
                # Удаляем credentials.json после использования
                if os.path.exists('credentials.json') and os.environ.get('GOOGLE_CREDENTIALS_BASE64'):
                    os.remove('credentials.json')
                    logger.info("🧹 credentials.json удален")
                break
            else:
                logger.warning(f"Файл credentials.json не найден")
                break
        except Exception as e:
            logger.error(f"Попытка {attempt+1} сохранения в Google Sheets не удалась: {e}")
            if attempt == retry-1:
                logger.error("❌ Не удалось сохранить в Google Sheets")
            await asyncio.sleep(2)

async def check_session_timeout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверяет, не истекло ли время сессии"""
    last_action = context.user_data.get("last_action", 0)
    if last_action and datetime.now().timestamp() - last_action > SESSION_TIMEOUT:
        context.user_data.clear()
        message = "⏰ Сессия истекла из-за неактивности. Начните заново с /start"
        
        if update.callback_query:
            await update.callback_query.edit_message_text(message)
        elif update.message:
            await update.message.reply_text(message)
        
        return True
    return False

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статистику регистраций для админов"""
    user_id = update.effective_user.id
    if user_id not in get_registration_admin_ids():
        await update.message.reply_text("⛔️ У вас нет доступа к этой команде")
        return
    
    data = load_data()
    registrations = data.get("registrations", [])
    
    stats = "📊 Статистика регистраций:\n\n"
    total_teams = 0
    
    for game in data.get("games", []):
        count = len([r for r in registrations if r.get("selected_game") == game])
        if count > 0:
            stats += f"🏆 {game}: {count} команд\n"
            total_teams += count
    
    stats += f"\n📈 Всего команд: {total_teams}"
    
    if total_teams == 0:
        stats += "\n\nПока нет регистраций"
    
    await update.message.reply_text(stats)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    data = load_data()
    if "users" not in data:
        data["users"] = {}
    data["users"][str(user_id)] = chat_id
    save_data(data)
    
    context.user_data.clear()
    context.user_data["last_action"] = datetime.now().timestamp()
    
    welcome_text = (
        "Привет! На связи футбольный квиз «Паненка» ✌🏻\n\n"
        "Этот бот поможет вашей команде попасть на ближайший квиз.\n\n"
        "Выберите город и дату 👇"
    )
    
    games = load_data().get("games", [])
    keyboard = []
    
    for i, game in enumerate(games):
        if GAME_INFO.get(game, {}).get("active", False):
            keyboard.append([InlineKeyboardButton(game, callback_data=f"game_{i}")])
    
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

async def game_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик всех кнопок"""
    # Проверка таймаута сессии
    if await check_session_timeout(update, context):
        return MAIN_MENU
    
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    logger.info(f"Нажата кнопка: {callback_data}")
    
    context.user_data["last_action"] = datetime.now().timestamp()
    
    if callback_data.startswith("game_"):
        try:
            game_index = int(callback_data.replace("game_", ""))
            games = load_data().get("games", [])
            
            if 0 <= game_index < len(games):
                selected_game = games[game_index]
                
                if not GAME_INFO.get(selected_game, {}).get("active", False):
                    await query.edit_message_text("Эта игра уже недоступна для регистрации.")
                    return MAIN_MENU
                
                context.user_data["selected_game"] = selected_game
                logger.info(f"Выбран город: {selected_game}")
                
                await show_city_menu(update, context)
                return CITY_SELECTED
            else:
                await query.edit_message_text("Ошибка: игра не найдена")
                return MAIN_MENU
        except Exception as e:
            logger.error(f"Ошибка выбора игры: {e}")
            await query.edit_message_text("Ошибка при выборе города")
            return MAIN_MENU
    
    elif callback_data == "back_to_main":
        context.user_data.clear()
        await start(update, context)
        return MAIN_MENU
    
    elif callback_data == "back_to_city":
        if not context.user_data.get("selected_game"):
            await start(update, context)
            return MAIN_MENU
        await show_city_menu(update, context)
        return CITY_SELECTED
    
    elif callback_data == "help":
        help_text = (
            "❓ Есть вопрос?\n\n"
            "Напишите его сюда и мы ответим в ближайшее время.\n\n"
            "Ваш вопрос:"
        )
        keyboard = [
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_city")]
        ]
        await query.edit_message_text(
            help_text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return HELP_MESSAGE
    
    elif callback_data == "start_registration":
        await query.edit_message_text(
            f"Отлично! ✌🏻\n\nДавайте зарегистрируем команду на игру в Москве — 11 апреля.\n\nВведите название команды 👇"
        )
        return REGISTER_TEAM
    
    elif callback_data == "confirm_registration":
        # Подтверждение регистрации
        return await save_registration(update, context)
    
    elif callback_data == "edit_registration":
        # Редактирование - начинаем заново
        await query.edit_message_text(
            "Давайте начнем регистрацию заново.\n\nВведите название команды 👇"
        )
        return REGISTER_TEAM
    
    elif callback_data in ["legioner_yes", "legioner_no"]:
        legioner_answer = "Да" if callback_data == "legioner_yes" else "Нет"
        context.user_data["legioner"] = legioner_answer
        logger.info(f"Легионер: {legioner_answer}")
        
        await query.edit_message_text(
            text="Напишите имя и номер телефона капитана 👇\n\nПример: Иван Иванов, +7 999 123-45-67"
        )
        return REGISTER_CAPTAIN
    
    else:
        logger.warning(f"Неизвестная кнопка: {callback_data}")
        await start(update, context)
        return MAIN_MENU

async def show_city_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает меню для выбранного города"""
    query = update.callback_query
    selected_game = context.user_data.get("selected_game")
    
    if not selected_game:
        await query.edit_message_text("Ошибка: город не выбран")
        return MAIN_MENU
    
    game_info = GameInfoCache.get(selected_game)
    photo_file = game_info.get('photo')
    
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
        [InlineKeyboardButton("📄 Заявить команду", callback_data="start_registration")],
        [
            InlineKeyboardButton("❓ Помощь", callback_data="help"),
            InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if os.path.exists(photo_file):
        with open(photo_file, 'rb') as photo:
            await query.edit_message_media(
                media=InputMediaPhoto(media=photo, caption=menu_text),
                reply_markup=reply_markup
            )
    else:
        await query.edit_message_text(
            text=menu_text,
            reply_markup=reply_markup
        )

async def team_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик названия команды"""
    # Проверка таймаута
    if await check_session_timeout(update, context):
        return ConversationHandler.END
    
    if update.message.text.startswith('/'):
        await update.message.reply_text("Пожалуйста, введите название команды, а не команду.")
        return REGISTER_TEAM
    
    team_name = update.message.text.strip()
    if not team_name:
        await update.message.reply_text("Название команды не может быть пустым. Введите название 👇")
        return REGISTER_TEAM
    
    if len(team_name) > 50:
        await update.message.reply_text("Название команды слишком длинное (максимум 50 символов). Введите название 👇")
        return REGISTER_TEAM
    
    context.user_data["team_name"] = team_name
    context.user_data["last_action"] = datetime.now().timestamp()
    logger.info(f"Название команды: {team_name}")
    
    await update.message.reply_text("Сколько игроков будет в команде? (от 3 до 10 человек)")
    return REGISTER_PLAYERS

async def player_count_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик количества игроков"""
    # Проверка таймаута
    if await check_session_timeout(update, context):
        return ConversationHandler.END
    
    if update.message.text.startswith('/'):
        await update.message.reply_text("Пожалуйста, введите количество игроков, а не команду.")
        return REGISTER_PLAYERS
    
    player_count = update.message.text.strip()
    if not player_count:
        await update.message.reply_text("Количество игроков не может быть пустым. Введите число от 3 до 10:")
        return REGISTER_PLAYERS
    
    if not player_count.isdigit():
        await update.message.reply_text("Пожалуйста, введите число (от 3 до 10):")
        return REGISTER_PLAYERS
    
    count = int(player_count)
    if count < 3 or count > 10:
        await update.message.reply_text("Количество игроков должно быть от 3 до 10. Введите число:")
        return REGISTER_PLAYERS
    
    context.user_data["player_count"] = player_count
    context.user_data["last_action"] = datetime.now().timestamp()
    logger.info(f"Количество игроков: {player_count}")
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Да", callback_data="legioner_yes"),
            InlineKeyboardButton("❌ Нет", callback_data="legioner_no")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Готовы ли взять в команду «легионера» (человека без команды)?",
        reply_markup=reply_markup
    )
    return REGISTER_LEGIONER

async def legioner_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора легионера"""
    # Проверка таймаута
    if await check_session_timeout(update, context):
        return ConversationHandler.END
    
    query = update.callback_query
    await query.answer()
    
    legioner_answer = "Да" if query.data == "legioner_yes" else "Нет"
    context.user_data["legioner"] = legioner_answer
    context.user_data["last_action"] = datetime.now().timestamp()
    logger.info(f"Легионер: {legioner_answer}")
    
    await query.edit_message_text(
        text="Напишите имя и номер телефона капитана 👇\n\nПример: Иван Иванов, +7 999 123-45-67"
    )
    return REGISTER_CAPTAIN

async def captain_info_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик информации о капитане"""
    # Проверка таймаута
    if await check_session_timeout(update, context):
        return ConversationHandler.END
    
    if update.message.text.startswith('/'):
        await update.message.reply_text("Пожалуйста, введите данные капитана, а не команду.")
        return REGISTER_CAPTAIN
    
    captain_info = update.message.text.strip()
    if not captain_info:
        await update.message.reply_text("Данные капитана не могут быть пустыми. Введите имя и телефон 👇")
        return REGISTER_CAPTAIN
    
    if len(captain_info) > 100:
        await update.message.reply_text("Данные капитана слишком длинные. Введите имя и телефон короче 👇")
        return REGISTER_CAPTAIN
    
    context.user_data["captain_info"] = captain_info
    context.user_data["last_action"] = datetime.now().timestamp()
    
    # Показываем сводку для подтверждения
    summary = (
        f"📋 Проверьте данные регистрации:\n\n"
        f"🏆 Команда: {context.user_data['team_name']}\n"
        f"👥 Количество игроков: {context.user_data['player_count']}\n"
        f"🌟 Легионер: {context.user_data.get('legioner', 'Не указано')}\n"
        f"👨‍💼 Капитан: {captain_info}\n\n"
        f"✅ Всё верно?"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Да, всё верно", callback_data="confirm_registration"),
            InlineKeyboardButton("✏️ Заполнить заново", callback_data="edit_registration")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(summary, reply_markup=reply_markup)
    return REGISTER_CONFIRM

async def save_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохраняет регистрацию после подтверждения"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    selected_game = context.user_data.get("selected_game", "")
    team_name = context.user_data.get("team_name", "")
    game_info = GameInfoCache.get(selected_game)
    city_name = selected_game.split()[0] if selected_game else ""

    registration = {
        "user_id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "selected_game": selected_game,
        "team_name": team_name,
        "player_count": context.user_data.get("player_count"),
        "legioner": context.user_data.get("legioner", "Не указано"),
        "captain_info": context.user_data.get("captain_info"),
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "registration_time": datetime.now().timestamp()
    }

    # Сохраняем в JSON
    data = load_data()
    if "registrations" not in data:
        data["registrations"] = []
    data["registrations"].append(registration)
    save_data(data)
    logger.info(f"Новая регистрация: {registration}")

    # Сохраняем в Google Sheets асинхронно
    asyncio.create_task(save_to_google_sheets_async(registration))

    venue_prepositional = game_info.get('venue_prepositional', game_info.get('venue_short', ''))
    
    final_message = (
        f"✅ Команда зарегистрирована!\n\n"
        f"Ждем вас в субботу в {venue_prepositional}\n\n"
        f"📌 Если у вас возникнут вопросы, нажмите кнопку «Помощь»\n\n"
        f"Мы свяжемся с капитаном при необходимости."
    )
    
    keyboard = [
        [InlineKeyboardButton("🔙 В главное меню", callback_data="back_to_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(final_message, reply_markup=reply_markup)

    # Отправляем уведомление администраторам
    registration_admin_ids = get_registration_admin_ids()
    admin_message = (
        f"🔔 Новая регистрация!\n\n"
        f"🎮 Игра: {selected_game}\n"
        f"🏆 Команда: {team_name}\n"
        f"👥 Игроков: {context.user_data.get('player_count')}\n"
        f"🌟 Легионер: {context.user_data.get('legioner', 'Не указано')}\n"
        f"👨‍💼 Капитан: {context.user_data.get('captain_info')}\n"
        f"👤 От: {user.full_name}\n"
        f"🆔 Username: @{user.username}\n"
        f"🕐 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    
    for admin_id in registration_admin_ids:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=admin_message
            )
            logger.info(f"Уведомление отправлено админу {admin_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки админу {admin_id}: {e}")

    # Очищаем данные пользователя
    context.user_data.clear()
    return MAIN_MENU

async def help_message_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик сообщения с вопросом"""
    # Проверка таймаута
    if await check_session_timeout(update, context):
        return ConversationHandler.END
    
    if update.message.text.startswith('/'):
        await update.message.reply_text("Пожалуйста, напишите ваш вопрос текстом.")
        return HELP_MESSAGE
    
    help_text = update.message.text.strip()
    if not help_text:
        await update.message.reply_text("Пожалуйста, напишите ваш вопрос.")
        return HELP_MESSAGE
    
    user = update.effective_user
    
    await update.message.reply_text(
        "✅ Ваш вопрос отправлен! Мы ответим в ближайшее время.\n\n"
        "Вы можете продолжить пользоваться ботом, нажав кнопку «Назад»",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Назад", callback_data="back_to_city")
        ]])
    )

    help_admin_ids = get_help_admin_ids()
    admin_message = (
        f"❓ Новый вопрос от пользователя\n\n"
        f"🆔 ID: {user.id}\n"
        f"👤 Имя: {user.full_name}\n"
        f"📱 Username: @{user.username}\n"
        f"🎮 Игра: {context.user_data.get('selected_game', 'Не выбрана')}\n"
        f"------------------------\n"
        f"💬 Вопрос:\n{help_text}"
    )
    
    for admin_id in help_admin_ids:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=admin_message
            )
            logger.info(f"Вопрос отправлен админу {admin_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки вопроса админу {admin_id}: {e}")
    
    return MAIN_MENU

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена текущего действия"""
    context.user_data.clear()
    await update.message.reply_text("❌ Действие отменено")
    return await start(update, context)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = (
        "🤖 Помощь по боту:\n\n"
        "/start - начать работу с ботом\n"
        "/cancel - отменить текущее действие\n"
        "/stats - статистика регистраций (только для админов)\n\n"
        "❓ Если у вас есть вопросы, нажмите кнопку «Помощь» в меню города"
    )
    await update.message.reply_text(help_text)

def main():
    # Запускаем веб-сервер для Render
    Thread(target=run_web, daemon=True).start()
    logger.info("🌐 Веб-сервер запущен на порту 10000")

    try:
        application = Application.builder().token(BOT_TOKEN).build()

        # Добавляем команды
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("cancel", cancel))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("stats", stats_command))

        # Основной ConversationHandler
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("start", start)],
            states={
                MAIN_MENU: [
                    CallbackQueryHandler(game_selected),
                ],
                CITY_SELECTED: [
                    CallbackQueryHandler(game_selected),
                ],
                REGISTER_TEAM: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, team_name_received),
                ],
                REGISTER_PLAYERS: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, player_count_received),
                ],
                REGISTER_LEGIONER: [
                    CallbackQueryHandler(legioner_received),
                ],
                REGISTER_CAPTAIN: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, captain_info_received),
                ],
                REGISTER_CONFIRM: [
                    CallbackQueryHandler(game_selected),
                ],
                HELP_MESSAGE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, help_message_received),
                    CallbackQueryHandler(game_selected),
                ],
            },
            fallbacks=[
                CommandHandler("cancel", cancel),
                CommandHandler("start", start),
                CommandHandler("help", help_command),
            ],
            per_message=False,
        )

        application.add_handler(conv_handler)

        print("✅ Бот запущен!")
        print(f"👑 Админы для регистраций: {get_registration_admin_ids()}")
        print(f"👑 Админ для вопросов: {get_help_admin_ids()}")
        print(f"🕐 Таймаут сессии: {SESSION_TIMEOUT} секунд")
        
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            timeout=30,
            drop_pending_updates=True,
            poll_interval=1.0
        )
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        time.sleep(5)
        os.execl(sys.executable, sys.executable, *sys.argv)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        time.sleep(5)
        os.execl(sys.executable, sys.executable, *sys.argv)