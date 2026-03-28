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
from datetime import datetime
from typing import Dict, Any, List
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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

# ========== ОБРАБОТКА СИГНАЛОВ ==========
def signal_handler(sig, frame):
    print('Остановка бота...')
    sys.exit(0)

try:
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
except AttributeError:
    pass

# ========== КЭШИРОВАНИЕ ДАННЫХ ==========
_data_cache = None
_cache_time = 0
CACHE_DURATION = 5

def load_data() -> Dict[str, Any]:
    global _data_cache, _cache_time
    current_time = time.time()
    if _data_cache and (current_time - _cache_time) < CACHE_DURATION:
        return _data_cache
    
    if not os.path.exists(DATA_FILE):
        default_data = {
            "games": [
                "Москва 28.02",
                "Москва 11.04",
                "Казань 11.03",
                "Краснодар 14.03"
            ], 
            "promo_registrations": [],
            "users": {},
            "registrations": []
        }
        save_data(default_data)
        _data_cache = default_data
        _cache_time = current_time
        return default_data
    
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "registrations" not in data:
                data["registrations"] = []
            if "promo_registrations" not in data:
                data["promo_registrations"] = []
            if "users" not in data:
                data["users"] = {}
            _data_cache = data
            _cache_time = current_time
            return data
    except Exception as e:
        logger.error(f"Ошибка загрузки данных: {e}")
        return {"games": [], "promo_registrations": [], "users": {}, "registrations": []}

def save_data(data: Dict[str, Any]):
    global _data_cache, _cache_time
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        _data_cache = data
        _cache_time = time.time()
    except Exception as e:
        logger.error(f"Ошибка сохранения данных: {e}")

# ========== ВЕБ-СЕРВЕР ==========
app = Flask('')

@app.route('/')
def home():
    return "OK"

def run_web():
    try:
        app.run(host='0.0.0.0', port=10000, debug=False, use_reloader=False, threaded=True)
    except Exception as e:
        print(f"⚠️ Ошибка веб-сервера: {e}")

# ========== НАСТРОЙКИ ==========
SESSION_TIMEOUT = 300

if sys.version_info >= (3, 12):
    print("Ошибка: Python 3.12+ не поддерживается. Используйте Python 3.11")
    sys.exit(1)

if os.environ.get('GOOGLE_CREDENTIALS_BASE64'):
    try:
        creds_base64 = os.environ.get('GOOGLE_CREDENTIALS_BASE64')
        creds_json = base64.b64decode(creds_base64).decode('utf-8')
        with open('credentials.json', 'w') as f:
            f.write(creds_json)
        print("✅ credentials.json восстановлен")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

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

# Отключаем лишние логи
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("flask").setLevel(logging.WARNING)
logging.getLogger("werkzeug").setLevel(logging.WARNING)

# Состояния
(
    MAIN_MENU,
    CITY_SELECTED,
    REGISTER_TEAM,
    REGISTER_PLAYERS,
    REGISTER_LEGIONER,
    REGISTER_CAPTAIN,
    PROMO_TEAM,
    PROMO_CLIENT_ID,
    PROMO_BET_NUMBER,
    PROMO_PHONE,
    HELP_MESSAGE,
) = range(11)

PHOTO_MOSCOW = "photo1.jpg"
PHOTO_KAZAN = "photo2.jpg"
PHOTO_KRASNODAR = "photo3.jpg"

GAME_INFO = {
    "Москва 28.02": {
        "full_date": "28 февраля (суббота)",
        "venue_short": "COiN HALL",
        "venue_full": "ул. Пятницкая 71/5с2",
        "time_open": "15:00",
        "time_start": "15:30",
        "price_jersey": "800₽",
        "price_regular": "1000₽",
        "city": "Москве",
        "city_prepositional": "Москве",
        "venue_prepositional": "COiN HALL",
        "photo": PHOTO_MOSCOW,
        "has_promo": False,
        "active": False
    },
    "Москва 11.04": {
        "full_date": "11 апреля (суббота)",
        "venue_short": "Бар «Золотая Вобла»",
        "venue_full": "Протоповоский пер, 3",
        "time_open": "16:00",
        "time_start": "16:20",
        "price_jersey": "800₽",
        "price_regular": "1000₽",
        "promo_period": "",
        "promo_deadline": "",
        "city": "Москве",
        "city_prepositional": "Москве",
        "venue_prepositional": "Баре «Золотая Вобла»",
        "photo": PHOTO_KAZAN,
        "has_promo": False,
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
        "promo_period": "с 24 февраля по 10 марта",
        "promo_deadline": "10 марта",
        "city": "Казани",
        "city_prepositional": "Казани",
        "venue_prepositional": "Ресторане MAXIMILIAN'S",
        "photo": PHOTO_KAZAN,
        "has_promo": True,
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
        "promo_period": "с 24 февраля по 13 марта",
        "promo_deadline": "13 марта",
        "city": "Краснодаре",
        "city_prepositional": "Краснодаре",
        "venue_prepositional": "баре NAMESTI",
        "photo": PHOTO_KRASNODAR,
        "has_promo": True,
        "active": False
    }
}

DATA_FILE = "data.json"

def get_admin_ids() -> List[int]:
    admin_ids = [SPECIFIC_ADMIN_ID, SECOND_ADMIN_ID]
    if ADMIN_IDS_STR:
        try:
            for id_str in ADMIN_IDS_STR.split(','):
                if id_str.strip():
                    admin_ids.append(int(id_str.strip()))
        except ValueError:
            logger.error(f"Ошибка ADMIN_ID: {ADMIN_IDS_STR}")
    return list(set(admin_ids))

def get_help_admin_ids() -> List[int]:
    return [HELP_ADMIN_ID]

def get_registration_admin_ids() -> List[int]:
    return [SPECIFIC_ADMIN_ID, SECOND_ADMIN_ID]

def save_to_google_sheets(registration: Dict[str, Any]):
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
                registration.get('bet_number', '')
            ]
            sheet.append_row(row)
            logger.info(f"✅ Данные сохранены в Google Sheets")
    except Exception as e:
        logger.error(f"Ошибка Google Sheets: {e}")

# ========== ОСНОВНЫЕ ОБРАБОТЧИКИ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        print(f"📥 /start от {update.effective_user.id}")
        
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
        
        print(f"✅ Ответ отправлен")
        return MAIN_MENU
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        await update.message.reply_text("Произошла ошибка. Попробуйте позже.")
        return MAIN_MENU

async def game_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    logger.info(f"Нажата кнопка: {callback_data}")
    
    context.user_data["last_action"] = datetime.now().timestamp()
    
    # ========== ОБРАБОТКА КНОПОК НАВИГАЦИИ ==========
    if callback_data == "back_to_main":
        context.user_data.clear()
        return await start(update, context)
    
    elif callback_data == "back_to_city":
        if not context.user_data.get("selected_game"):
            return await start(update, context)
        await show_city_menu(update, context)
        return CITY_SELECTED
    
    # ========== ОБРАБОТКА ВЫБОРА ИГРЫ ==========
    elif callback_data.startswith("game_"):
        try:
            game_index = int(callback_data.replace("game_", ""))
            games = load_data().get("games", [])
            
            if 0 <= game_index < len(games):
                selected_game = games[game_index]
                
                if not GAME_INFO.get(selected_game, {}).get("active", False):
                    await query.message.reply_text("❌ Эта игра уже недоступна.")
                    return MAIN_MENU
                
                context.user_data["selected_game"] = selected_game
                await show_city_menu(update, context)
                return CITY_SELECTED
            else:
                await query.message.reply_text("Ошибка: игра не найдена")
                return MAIN_MENU
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            await query.message.reply_text("Ошибка при выборе города")
            return MAIN_MENU
    
    # ========== ОБРАБОТКА КНОПКИ ПОМОЩИ ==========
    elif callback_data == "help":
        help_text = (
            "❓ Есть вопрос?\n\n"
            "Напишите его сюда @Panenka_Registration — поможем разобраться."
        )
        await query.message.reply_text(
            help_text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="back_to_city")
            ]])
        )
        return HELP_MESSAGE
    
    # ========== ОБРАБОТКА РЕГИСТРАЦИИ ==========
    elif callback_data == "start_registration":
        city_name = context.user_data.get("selected_game", "")
        logger.info(f"Начало регистрации для {city_name}")
        
        if city_name == "Москва 11.04":
            await query.message.reply_text(
                "Отлично! ✌🏻\n\n"
                "Давайте зарегистрируем команду на игру в Москве — 11 апреля.\n\n"
                "Введите название команды 👇"
            )
        else:
            await query.message.reply_text("Введите название команды 👇")
        
        return REGISTER_TEAM
    
    # ========== ОБРАБОТКА ПРОМО ==========
    elif callback_data == "promo_yes":
        await query.message.reply_text("Из какой вы команды?")
        return PROMO_TEAM
    
    elif callback_data == "promo_no":
        await query.message.reply_text(
            "Сначала необходимо зарегистрировать команду. 👇\n\n"
            "После этого вы сможете оформить участие по ставке.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📄 Заявить команду", callback_data="register_team")
            ]])
        )
        return CITY_SELECTED
    
    elif callback_data == "start_promo_registration":
        promo_text = (
            "🎟️ Участие по ставке предоставляется игроку, с аккаунта которого было заключено пари\n\n"
            "Ваша команда уже зарегистрирована?"
        )
        keyboard = [
            [
                InlineKeyboardButton("✅ Да", callback_data="promo_yes"),
                InlineKeyboardButton("❌ Нет", callback_data="promo_no")
            ],
            [
                InlineKeyboardButton("📋 Условия акции", callback_data="promo_terms"),
                InlineKeyboardButton("🔙 Назад", callback_data="back_to_city")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text(promo_text, reply_markup=reply_markup)
        return CITY_SELECTED
    
    elif callback_data == "promo_terms":
        await show_terms_menu(update, context)
        return CITY_SELECTED
    
    # ========== ОБРАБОТКА ЛЕГИОНЕРА ==========
    elif callback_data in ["legioner_yes", "legioner_no"]:
        legioner_answer = "Да" if callback_data == "legioner_yes" else "Нет"
        context.user_data["legioner"] = legioner_answer
        logger.info(f"Легионер: {legioner_answer}")
        
        await query.message.reply_text(
            text="Напишите имя и номер телефона капитана 👇"
        )
        return REGISTER_CAPTAIN
    
    # ========== ОБРАБОТКА РЕГИСТРАЦИИ КОМАНДЫ ==========
    elif callback_data == "register_team":
        await query.message.reply_text("Введите название команды 👇")
        return REGISTER_TEAM
    
    else:
        logger.warning(f"Неизвестная кнопка: {callback_data}")
        return await start(update, context)

async def show_city_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    selected_game = context.user_data.get("selected_game")
    
    if not selected_game:
        await query.message.reply_text("Ошибка: город не выбран")
        return MAIN_MENU
    
    game_info = GAME_INFO.get(selected_game, {})
    photo_file = game_info.get('photo')
    
    menu_text = (
        f"📍 {selected_game}\n\n"
        f"🏟️ {game_info['venue_short']}\n"
        f"📫 {game_info['venue_full']}\n\n"
        f"🕖 Двери открыты с {game_info['time_open']}\n"
        f"⚽ Старт игры – {game_info['time_start']}\n\n"
        f"💰 Стоимость участия:\n"
        f"{game_info['price_jersey']} – в джерси любого клуба или сборной,\n"
        f"{game_info['price_regular']} – в обычной одежде\n\n"
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
            await query.message.reply_photo(
                photo=photo,
                caption=menu_text,
                reply_markup=reply_markup
            )
    else:
        await query.message.reply_text(
            text=menu_text,
            reply_markup=reply_markup
        )

async def show_terms_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    terms_text = (
        "📋 Условия участия по ставке\n\n"
        "1. Минимальная сумма пари - 700₽.\n"
        "2. Тип пари - ординар, коэффициент - от 1.5 до 3.\n"
        "3. Пари должно быть заключено в период с 24 февраля по 13 марта.\n"
        "4. Бесплатное участие предоставляется игроку, с аккаунта которого было заключено пари.\n"
        "5. Для оформления необходимо указать:\n"
        "   — ID клиента\n"
        "   — Номер пари\n"
        "6. Команда должна быть зарегистрирована на игру.\n"
        "7. Организатор вправе проверить корректность предоставленных данных."
    )
    
    keyboard = [
        [
            InlineKeyboardButton("📄 Заявить команду", callback_data="start_registration"),
            InlineKeyboardButton("🎟️ Прийти по ставке", callback_data="start_promo_registration")
        ],
        [
            InlineKeyboardButton("❓ Помощь", callback_data="help"),
            InlineKeyboardButton("🔙 Назад", callback_data="back_to_city")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.reply_text(terms_text, reply_markup=reply_markup)

# ========== ТЕКСТОВЫЕ ОБРАБОТЧИКИ ==========

async def team_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Обработка команды /start
    if update.message.text == '/start':
        return await start(update, context)
    
    if update.message.text.startswith('/'):
        await update.message.reply_text("Пожалуйста, введите название команды.")
        return REGISTER_TEAM
    
    team_name = update.message.text.strip()
    if not team_name:
        await update.message.reply_text("Название команды не может быть пустым.")
        return REGISTER_TEAM
    
    context.user_data["team_name"] = team_name
    context.user_data["last_action"] = datetime.now().timestamp()
    logger.info(f"Название команды: {team_name}")
    
    await update.message.reply_text("Сколько игроков будет в команде? (от 3 до 10 человек)")
    return REGISTER_PLAYERS

async def player_count_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Обработка команды /start
    if update.message.text == '/start':
        return await start(update, context)
    
    if update.message.text.startswith('/'):
        await update.message.reply_text("Пожалуйста, введите количество игроков.")
        return REGISTER_PLAYERS
    
    player_count = update.message.text.strip()
    if not player_count:
        await update.message.reply_text("Введите число от 3 до 10:")
        return REGISTER_PLAYERS
    
    if not player_count.isdigit():
        await update.message.reply_text("Пожалуйста, введите число (от 3 до 10):")
        return REGISTER_PLAYERS
    
    count = int(player_count)
    if count < 3 or count > 10:
        await update.message.reply_text("Количество игроков должно быть от 3 до 10.")
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

async def captain_info_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Обработка команды /start
    if update.message.text == '/start':
        return await start(update, context)
    
    if update.message.text.startswith('/'):
        await update.message.reply_text("Пожалуйста, введите данные капитана.")
        return REGISTER_CAPTAIN
    
    captain_info = update.message.text.strip()
    if not captain_info:
        await update.message.reply_text("Введите имя и телефон капитана 👇")
        return REGISTER_CAPTAIN
    
    user = update.effective_user
    selected_game = context.user_data.get("selected_game", "")
    team_name = context.user_data.get("team_name", "")
    game_info = GAME_INFO.get(selected_game, {})

    registration = {
        "user_id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "selected_game": selected_game,
        "team_name": team_name,
        "player_count": context.user_data.get("player_count"),
        "legioner": context.user_data.get("legioner", "Не указано"),
        "captain_info": captain_info,
        "date": str(update.message.date)
    }

    data = load_data()
    if "registrations" not in data:
        data["registrations"] = []
    data["registrations"].append(registration)
    save_data(data)
    logger.info(f"Новая регистрация: {registration}")

    venue_prepositional = game_info.get('venue_prepositional', game_info.get('venue_short', ''))
    full_date = game_info.get('full_date', '')
    
    final_message = (
        f"✅ Команда зарегистрирована!\n\n"
        f"Ждем вас {full_date} в {venue_prepositional}\n\n"
        f"Мы свяжемся с капитаном при необходимости."
    )
    
    keyboard = [
        [
            InlineKeyboardButton("❓ Помощь", callback_data="help"),
            InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(final_message, reply_markup=reply_markup)

    registration_admin_ids = get_registration_admin_ids()
    admin_message = (
        f"🔔 Новая регистрация!\n"
        f"Игра: {selected_game}\n"
        f"Команда: {team_name}\n"
        f"Игроков: {context.user_data.get('player_count')}\n"
        f"Легионер: {context.user_data.get('legioner', 'Не указано')}\n"
        f"Капитан: {captain_info}\n"
        f"От: {user.full_name} (@{user.username})"
    )
    
    for admin_id in registration_admin_ids:
        try:
            await context.bot.send_message(chat_id=admin_id, text=admin_message)
        except Exception as e:
            logger.error(f"Ошибка админу {admin_id}: {e}")

    return MAIN_MENU

# ========== ПРОМО ОБРАБОТЧИКИ ==========

async def promo_team_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Обработка команды /start
    if update.message.text == '/start':
        return await start(update, context)
    
    if update.message.text.startswith('/'):
        await update.message.reply_text("Пожалуйста, введите название команды.")
        return PROMO_TEAM
    
    team_name = update.message.text.strip()
    if not team_name:
        await update.message.reply_text("Название команды не может быть пустым.")
        return PROMO_TEAM
    
    context.user_data["promo_team"] = team_name
    context.user_data["last_action"] = datetime.now().timestamp()
    logger.info(f"Команда для акции: {team_name}")
    
    selected_game = context.user_data.get("selected_game")
    game_info = GAME_INFO.get(selected_game, {})
    
    promo_rules = (
        f"Чтобы оформить участие по ставке:\n\n"
        f"— ставка должна быть от 700₽\n"
        f"— тип ставки - ординар, коэффициент - от 1.5 до 3\n"
        f"— сделана в период {game_info.get('promo_period', '')}\n"
        f"— участие возможно для игрока, с аккаунта которого была сделана ставка\n\n"
        f"Введите ID клиента в FONBET.\n"
        f"Найти его можно в разделе «Мой профиль» 👇"
    )
    
    await update.message.reply_text(promo_rules)
    return PROMO_CLIENT_ID

async def client_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Обработка команды /start
    if update.message.text == '/start':
        return await start(update, context)
    
    if update.message.text.startswith('/'):
        await update.message.reply_text("Пожалуйста, введите ID клиента.")
        return PROMO_CLIENT_ID
    
    client_id = update.message.text.strip()
    if not client_id:
        await update.message.reply_text("ID клиента не может быть пустым.")
        return PROMO_CLIENT_ID
    
    context.user_data["client_id"] = client_id
    context.user_data["last_action"] = datetime.now().timestamp()
    logger.info(f"ID клиента: {client_id}")
    
    await update.message.reply_text(
        "Введите номер пари.\n"
        "Посмотреть можно в разделе «Мои пари» 👇"
    )
    return PROMO_BET_NUMBER

async def bet_number_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Обработка команды /start
    if update.message.text == '/start':
        return await start(update, context)
    
    if update.message.text.startswith('/'):
        await update.message.reply_text("Пожалуйста, введите номер пари.")
        return PROMO_BET_NUMBER
    
    bet_number = update.message.text.strip()
    if not bet_number:
        await update.message.reply_text("Номер пари не может быть пустым.")
        return PROMO_BET_NUMBER
    
    context.user_data["bet_number"] = bet_number
    context.user_data["last_action"] = datetime.now().timestamp()
    logger.info(f"Номер пари: {bet_number}")
    
    await update.message.reply_text("Напишите имя и номер телефона 👇")
    return PROMO_PHONE

async def promo_phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Обработка команды /start
    if update.message.text == '/start':
        return await start(update, context)
    
    if update.message.text.startswith('/'):
        await update.message.reply_text("Пожалуйста, введите имя и телефон.")
        return PROMO_PHONE
    
    phone_info = update.message.text.strip()
    if not phone_info:
        await update.message.reply_text("Введите имя и телефон 👇")
        return PROMO_PHONE
    
    user = update.effective_user
    selected_game = context.user_data.get("selected_game", "")
    team_name = context.user_data.get("promo_team", "")
    game_info = GAME_INFO.get(selected_game, {})

    promo_registration = {
        "user_id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "selected_game": selected_game,
        "team_name": team_name,
        "name": user.full_name,
        "phone": phone_info,
        "client_id": context.user_data.get("client_id"),
        "bet_number": context.user_data.get("bet_number"),
        "date": str(update.message.date)
    }

    data = load_data()
    if "promo_registrations" not in data:
        data["promo_registrations"] = []
    data["promo_registrations"].append(promo_registration)
    save_data(data)
    logger.info(f"Новое участие в акции: {promo_registration}")

    save_to_google_sheets(promo_registration)

    venue_prepositional = game_info.get('venue_prepositional', game_info.get('venue_short', ''))
    full_date = game_info.get('full_date', '')
    
    final_text = f"✅ Участие по ставке подтверждено.\n\nЖдём вас {full_date} в {venue_prepositional}.\nДо встречи на квизе!"
    
    await update.message.reply_text(
        final_text,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 В главное меню", callback_data="back_to_main")
        ]])
    )

    registration_admin_ids = get_registration_admin_ids()
    admin_message = (
        f"🎁 Новое участие в акции FONBET!\n"
        f"Игра: {selected_game}\n"
        f"Команда: {team_name}\n"
        f"Имя: {user.full_name}\n"
        f"Телефон: {phone_info}\n"
        f"ID клиента: {context.user_data.get('client_id')}\n"
        f"Номер пари: {context.user_data.get('bet_number')}\n"
        f"От: {user.full_name} (@{user.username})"
    )
    
    for admin_id in registration_admin_ids:
        try:
            await context.bot.send_message(chat_id=admin_id, text=admin_message)
        except Exception as e:
            logger.error(f"Ошибка админу {admin_id}: {e}")

    context.user_data.clear()
    return MAIN_MENU

async def help_message_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Обработка callback кнопки "Назад" из помощи
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        if query.data == "back_to_city":
            if not context.user_data.get("selected_game"):
                return await start(update, context)
            await show_city_menu(update, context)
            return CITY_SELECTED
        return MAIN_MENU
    
    # Обработка команды /start
    if update.message and update.message.text == '/start':
        return await start(update, context)
    
    if update.message and update.message.text.startswith('/'):
        await update.message.reply_text("Пожалуйста, напишите ваш вопрос.")
        return HELP_MESSAGE
    
    help_text = update.message.text.strip()
    user = update.effective_user
    
    await update.message.reply_text(
        "✅ Ваш вопрос отправлен! Мы ответим в ближайшее время.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Назад", callback_data="back_to_city")
        ]])
    )

    help_admin_ids = get_help_admin_ids()
    for admin_id in help_admin_ids:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"❓ Вопрос от пользователя\n"
                     f"ID: {user.id}\n"
                     f"Имя: {user.full_name}\n"
                     f"Username: @{user.username}\n"
                     f"------------------------\n"
                     f"{help_text}"
            )
        except Exception as e:
            logger.error(f"Ошибка админу {admin_id}: {e}")
    
    return HELP_MESSAGE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Действие отменено")
    return await start(update, context)

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("🔄 Состояние сброшено. Нажмите /start")
    return await start(update, context)

# ========== ЗАПУСК ==========

def main():
    print("🚀 Запуск бота...")
    
    try:
        web_thread = Thread(target=run_web, daemon=True)
        web_thread.start()
        print("🌐 Веб-сервер запущен")
    except Exception as e:
        print(f"⚠️ Ошибка веб-сервера: {e}")

    try:
        application = Application.builder().token(BOT_TOKEN).build()
        print("✅ Приложение создано")

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
                    CallbackQueryHandler(game_selected),
                ],
                REGISTER_PLAYERS: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, player_count_received),
                    CallbackQueryHandler(game_selected),
                ],
                REGISTER_LEGIONER: [
                    CallbackQueryHandler(game_selected),
                ],
                REGISTER_CAPTAIN: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, captain_info_received),
                    CallbackQueryHandler(game_selected),
                ],
                PROMO_TEAM: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, promo_team_received),
                    CallbackQueryHandler(game_selected),
                ],
                PROMO_CLIENT_ID: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, client_id_received),
                    CallbackQueryHandler(game_selected),
                ],
                PROMO_BET_NUMBER: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, bet_number_received),
                    CallbackQueryHandler(game_selected),
                ],
                PROMO_PHONE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, promo_phone_received),
                    CallbackQueryHandler(game_selected),
                ],
                HELP_MESSAGE: [
                    CallbackQueryHandler(help_message_received),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, help_message_received),
                ],
            },
            fallbacks=[
                CommandHandler("start", start),
                CommandHandler("cancel", cancel),
                CommandHandler("reset", reset),
            ],
            allow_reentry=True,
        )

        application.add_handler(conv_handler)

        print("✅ Бот настроен!")
        print(f"👑 Админы: {get_registration_admin_ids()}")
        print("🤖 Бот запущен!")
        
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            timeout=10,
            drop_pending_updates=True,
            poll_interval=0.5,
            read_timeout=10,
            write_timeout=10
        )
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        logger.error(f"Ошибка: {e}")
        time.sleep(5)
        os.execl(sys.executable, sys.executable, *sys.argv)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        time.sleep(5)
        os.execl(sys.executable, sys.executable, *sys.argv)
