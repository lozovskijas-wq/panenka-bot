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

# Обработка сигналов для корректного завершения
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

if os.environ.get('GOOGLE_CREDENTIALS_BASE64'):
    try:
        creds_base64 = os.environ.get('GOOGLE_CREDENTIALS_BASE64')
        creds_json = base64.b64decode(creds_base64).decode('utf-8')
        with open('credentials.json', 'w') as f:
            f.write(creds_json)
        print("✅ credentials.json восстановлен из переменной окружения")
    except Exception as e:
        print(f"❌ Ошибка восстановления credentials.json: {e}")

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

(
    SELECTING_GAME,
    TYPING_TEAM_NAME,
    TYPING_PLAYER_COUNT,
    ASKING_LEGIONER,
    TYPING_CAPTAIN_INFO,
    ASKING_MESSAGE_TO_ADMIN,
    REPLYING_TO_USER,
    SHOWING_CITY_MENU,
    SHOWING_REGISTER_MENU,
    SHOWING_PROMO_MENU,
    SHOWING_TERMS_MENU,
    ASKING_PROMO_TEAM,
    ASKING_CLIENT_ID,
    ASKING_BET_NUMBER,
    ASKING_PROMO_PHONE,
    ASKING_HELP_MESSAGE,
) = range(16)
ASKING_GAME_NAME = range(16, 17)
ASKING_GAME_TO_DELETE = range(17, 18)

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
        "has_promo": False
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
        "has_promo": True
    },
    "Краснодар 14.03": {
        "full_date": "14 марта (суббота)",
        "venue_short": "NAMESTI",
        "venue_full": "ул. Красноармейская, 55/2",
        "time_open": "17:00",
        "time_start": "17:30",
        "price_jersey": "700₽",
        "price_regular": "900₽",
        "promo_period": "с 24 февраля по 13 марта",
        "promo_deadline": "13 марта",
        "city": "Краснодаре",
        "city_prepositional": "Краснодаре",
        "venue_prepositional": "баре Namesti",
        "photo": PHOTO_KRASNODAR,
        "has_promo": True
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
                "Москва 28.02",
                "Казань 11.03",
                "Краснодар 14.03"
            ], 
            "promo_registrations": [],
            "users": {}
        }
        save_data(default_data)
        return default_data
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Ошибка загрузки данных: {e}")
        return {"games": [], "promo_registrations": [], "users": {}}

def save_data(data: Dict[str, Any]):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Ошибка сохранения данных: {e}")

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
        else:
            logger.warning(f"Файл credentials.json не найден")
    except Exception as e:
        logger.error(f"Ошибка сохранения в Google Sheets: {e}")

async def send_city_photo(update: Update, context: ContextTypes.DEFAULT_TYPE, game_key: str, caption: str, reply_markup=None):
    game_info = GAME_INFO.get(game_key, {})
    photo_file = game_info.get('photo')
    
    try:
        with open(photo_file, 'rb') as photo:
            if update.callback_query:
                await update.callback_query.message.reply_photo(
                    photo=photo,
                    caption=caption,
                    reply_markup=reply_markup
                )
            else:
                await update.message.reply_photo(
                    photo=photo,
                    caption=caption,
                    reply_markup=reply_markup
                )
        logger.info(f"Фото для {game_key} отправлено")
    except Exception as e:
        logger.error(f"Ошибка отправки фото: {e}")
        if update.callback_query:
            await update.callback_query.message.reply_text(
                text=caption,
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                text=caption,
                reply_markup=reply_markup
            )

async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    data = load_data()
    games = data.get("games", [])
    
    games_keyboard = []
    if games:
        for i, game in enumerate(games):
            callback_data = f"game_{i}"
            games_keyboard.append([InlineKeyboardButton(game, callback_data=callback_data)])
    
    reply_markup = InlineKeyboardMarkup(games_keyboard)
    clean_text = text.replace('*', '')
    
    try:
        if os.path.exists('logo.jpg'):
            with open('logo.jpg', 'rb') as photo:
                if update.callback_query:
                    await update.callback_query.message.reply_photo(
                        photo=photo,
                        caption=clean_text,
                        reply_markup=reply_markup
                    )
                else:
                    await update.message.reply_photo(
                        photo=photo,
                        caption=clean_text,
                        reply_markup=reply_markup
                    )
            logger.info("Главное меню с фото отправлено")
        else:
            logger.warning("Файл logo.jpg не найден, отправляем без фото")
            if update.callback_query:
                await update.callback_query.message.reply_text(
                    text=clean_text,
                    reply_markup=reply_markup
                )
            else:
                await update.message.reply_text(
                    text=clean_text,
                    reply_markup=reply_markup
                )
    except Exception as e:
        logger.error(f"Ошибка отправки фото: {e}")
        if update.callback_query:
            await update.callback_query.message.reply_text(
                text=clean_text,
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                text=clean_text,
                reply_markup=reply_markup
            )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    data = load_data()
    if "users" not in data:
        data["users"] = {}
    data["users"][str(user_id)] = chat_id
    save_data(data)
    
    welcome_text = (
        "Привет! На связи футбольный квиз «Паненка» 🎉\n\n"
        "Этот бот поможет вашей команде попасть на ближайший квиз.\n\n"
        "Выберите город и дату 🌍"
    )
    
    await update.message.reply_text(welcome_text)
    
    # Показываем главное меню с выбором города
    await send_main_menu(update, context, "")
    return SELECTING_GAME

async def game_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    callback_data = query.data
    logger.info(f"Нажата кнопка: {callback_data}")
    
    if callback_data == "back_to_main":
        context.user_data.clear()
        welcome_text = (
            "Привет! На связи футбольный квиз «Паненка» 🎉\n\n"
            "Этот бот поможет вашей команде попасть на ближайший квиз.\n\n"
            "Выберите город и дату 🌍"
        )
        await send_main_menu(update, context, welcome_text)
        return SELECTING_GAME
    
    elif callback_data == "back_to_city":
        await show_city_menu(update, context)
        return SHOWING_CITY_MENU
    
    elif callback_data == "register_team":
        await show_register_menu(update, context)
        return SHOWING_REGISTER_MENU
    
    elif callback_data == "join_promo":
        await show_promo_menu(update, context)
        return SHOWING_PROMO_MENU
    
    elif callback_data == "promo_terms":
        await show_terms_menu(update, context)
        return SHOWING_TERMS_MENU
    
    elif callback_data == "help":
        await query.message.reply_text(
            "❓ Есть вопрос?\n\n"
            "Напишите его прямо здесь — поможем разобраться.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="back_to_city")
            ]])
        )
        return ASKING_HELP_MESSAGE
    
    elif callback_data == "promo_yes":
        await query.message.reply_text("Из какой вы команды?")
        return ASKING_PROMO_TEAM
    
    elif callback_data == "promo_no":
        await query.message.reply_text(
            "Сначала необходимо зарегистрировать команду. 👇\n\n"
            "После этого вы сможете оформить участие по ставке.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📄 Заявить команду", callback_data="register_team")
            ]])
        )
        return SHOWING_CITY_MENU
    
    elif callback_data == "start_registration":
        city_name = context.user_data.get("selected_game", "")
        city_part = city_name.split()[0] if city_name else ""
        
        welcome_texts = {
            "Москва": f"Отлично! ✌🏻\n\nДавайте зарегистрируем команду на игру в Москве — 28 февраля.\n\nВведите название команды 👇",
            "Казань": f"Давайте зарегистрируем команду на игру в Казани — 11 марта.\n\nВведите название команды 👇",
            "Краснодар": f"Отлично! ✌🏻\n\nДавайте зарегистрируем команду на игру в Краснодаре – 14 марта.\n\nВведите название команды 👇"
        }
        
        await query.message.reply_text(welcome_texts.get(city_part, "Введите название команды 👇"))
        return TYPING_TEAM_NAME
    
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
        return SHOWING_PROMO_MENU
    
    elif callback_data.startswith("game_"):
        try:
            game_index = int(callback_data.replace("game_", ""))
            data = load_data()
            games = data.get("games", [])
            
            if 0 <= game_index < len(games):
                selected_game = games[game_index]
                context.user_data["selected_game"] = selected_game
                
                await show_city_menu(update, context)
                return SHOWING_CITY_MENU
            else:
                await query.message.reply_text("Ошибка: игра не найдена")
                return SELECTING_GAME
        except Exception as e:
            logger.error(f"Ошибка выбора игры: {e}")
            await query.message.reply_text("Ошибка при выборе игры")
            return SELECTING_GAME

async def show_city_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    selected_game = context.user_data.get("selected_game")
    game_info = GAME_INFO.get(selected_game, {})
    
    if selected_game == "Москва 28.02":
        menu_text = (
            f"📍 Москва – 28 февраля (суббота)\n\n"
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
    
    elif selected_game == "Казань 11.03":
        menu_text = (
            f"📍 Казань – 11 марта (среда)\n\n"
            f"🏟️ {game_info['venue_short']}\n"
            f"📫 {game_info['venue_full']}\n\n"
            f"🕖 Двери открыты с {game_info['time_open']}\n"
            f"⚽ Старт игры – {game_info['time_start']}\n\n"
            f"💰 Стоимость участия:\n"
            f"{game_info['price_jersey']} – в джерси любого клуба или сборной,\n"
            f"{game_info['price_regular']} – в обычной одежде\n\n"
            f"🎟️ Можно сделать ставку от 700₽ в FONBET и участвовать в игре бесплатно.\n\n"
            f"Если команда уже заявлена – каждый игрок может оформить участие по ставке отдельно.\n\n"
            f"Если команда ещё не заявлена – сейчас самое время это сделать."
        )
        keyboard = [
            [InlineKeyboardButton("📄 Заявить команду", callback_data="start_registration")],
            [InlineKeyboardButton("🎟️ Прийти по ставке", callback_data="start_promo_registration")],
            [
                InlineKeyboardButton("📋 Условия акции", callback_data="promo_terms"),
                InlineKeyboardButton("❓ Помощь", callback_data="help")
            ],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
        ]
    
    else:  # Краснодар
        menu_text = (
            f"📍 Краснодар – 14 марта (суббота)\n\n"
            f"🏟️ {game_info['venue_short']}\n"
            f"📫 {game_info['venue_full']}\n\n"
            f"🕖 Двери открыты с {game_info['time_open']}\n"
            f"⚽ Старт игры – {game_info['time_start']}\n\n"
            f"💰 Стоимость участия:\n"
            f"{game_info['price_jersey']} – в джерси любого клуба или сборной,\n"
            f"{game_info['price_regular']} – в обычной одежде\n\n"
            f"🎟️ Можно сделать ставку от 700₽ в FONBET и участвовать в игре бесплатно.\n\n"
            f"Если команда уже заявлена – каждый игрок может оформить участие по ставке отдельно.\n\n"
            f"Если команда ещё не заявлена – сейчас самое время это сделать."
        )
        keyboard = [
            [InlineKeyboardButton("📄 Заявить команду", callback_data="start_registration")],
            [InlineKeyboardButton("🎟️ Прийти по ставке", callback_data="start_promo_registration")],
            [
                InlineKeyboardButton("📋 Условия акции", callback_data="promo_terms"),
                InlineKeyboardButton("❓ Помощь", callback_data="help")
            ],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_city_photo(update, context, selected_game, menu_text, reply_markup)

async def show_register_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.message.reply_text("Введите название команды 👇")
    return TYPING_TEAM_NAME

async def show_promo_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
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

async def show_terms_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    selected_game = context.user_data.get("selected_game")
    
    if selected_game == "Казань 11.03":
        period_text = "с 24 февраля по 10 марта"
    else:  # Краснодар
        period_text = "с 24 февраля по 13 марта"
    
    terms_text = (
        "📋 Условия участия по ставке\n\n"
        "1. Минимальная сумма пари - 700₽.\n"
        "2. Тип пари - ординар, коэффициент - от 1.5 до 3.\n"
        f"3. Пари должно быть заключено в период {period_text}.\n"
        "4. Бесплатное участие предоставляется игроку, с аккаунта которого было заключено пари.\n"
        "5. Для оформления необходимо указать:\n"
        "   — ID клиента\n"
        "   — Номер пари\n"
        "6. Команда должна быть зарегистрирована на игру.\n"
        "7. Организатор вправе проверить корректность предоставленных данных."
    )
    
    keyboard = [
        [
            InlineKeyboardButton("📄 Заявить команду", callback_data="register_team"),
            InlineKeyboardButton("🎟️ Прийти по ставке", callback_data="join_promo")
        ],
        [
            InlineKeyboardButton("❓ Помощь", callback_data="help"),
            InlineKeyboardButton("🔙 Назад", callback_data="back_to_city")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text(terms_text, reply_markup=reply_markup)

async def team_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"ПОЛУЧЕНО НАЗВАНИЕ КОМАНДЫ: {update.message.text}")
    
    if update.message.text.startswith('/'):
        await update.message.reply_text("Пожалуйста, введите название команды, а не команду.")
        return TYPING_TEAM_NAME
    
    team_name = update.message.text.strip()
    if not team_name:
        await update.message.reply_text("Название команды не может быть пустым. Введите название 👇")
        return TYPING_TEAM_NAME
        
    context.user_data["team_name"] = team_name
    logger.info(f"Название команды сохранено: {team_name}")
    
    await update.message.reply_text("Сколько игроков будет в команде? (от 3 до 10 человек)")
    return TYPING_PLAYER_COUNT

async def player_count_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"ПОЛУЧЕНО КОЛИЧЕСТВО: {update.message.text}")
    
    if update.message.text.startswith('/'):
        await update.message.reply_text("Пожалуйста, введите количество игроков, а не команду.")
        return TYPING_PLAYER_COUNT
    
    player_count = update.message.text.strip()
    if not player_count:
        await update.message.reply_text("Количество игроков не может быть пустым. Введите число от 3 до 10:")
        return TYPING_PLAYER_COUNT
    
    if not player_count.isdigit():
        await update.message.reply_text("Пожалуйста, введите число (от 3 до 10):")
        return TYPING_PLAYER_COUNT
    
    count = int(player_count)
    if count < 3 or count > 10:
        await update.message.reply_text("Количество игроков должно быть от 3 до 10. Введите число:")
        return TYPING_PLAYER_COUNT
    
    context.user_data["player_count"] = player_count
    logger.info(f"Количество сохранено: {player_count}")
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Да", callback_data="legioner_yes"),
            InlineKeyboardButton("❌ Нет", callback_data="legioner_no")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Готовы ли взять «Легионера» в команду?",
        reply_markup=reply_markup
    )
    return ASKING_LEGIONER

async def legioner_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    legioner_answer = "Да" if query.data == "legioner_yes" else "Нет"
    context.user_data["legioner"] = legioner_answer
    logger.info(f"Легионер: {legioner_answer}")
    
    await query.message.reply_text(
        text="Напишите имя и номер телефона капитана 👇"
    )
    return TYPING_CAPTAIN_INFO

async def captain_info_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"ПОЛУЧЕНЫ ДАННЫЕ КАПИТАНА: {update.message.text}")
    
    if update.message.text.startswith('/'):
        await update.message.reply_text("Пожалуйста, введите данные капитана, а не команду.")
        return TYPING_CAPTAIN_INFO
    
    captain_info = update.message.text.strip()
    if not captain_info:
        await update.message.reply_text("Данные капитана не могут быть пустыми. Введите имя и телефон 👇")
        return TYPING_CAPTAIN_INFO
    
    user = update.effective_user
    selected_game = context.user_data.get("selected_game", "")
    team_name = context.user_data.get("team_name", "")
    game_info = GAME_INFO.get(selected_game, {})
    city_name = selected_game.split()[0] if selected_game else ""

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
    
    if city_name == "Москва":
        final_message = f"Команда зарегистрирована ✅ Ждем вас в субботу в {venue_prepositional}\n\nМы свяжемся с капитаном при необходимости."
        keyboard = [
            [InlineKeyboardButton("🔙 В главное меню", callback_data="back_to_main")]
        ]
    elif city_name == "Казань":
        final_message = (
            f"Команда зарегистрирована ✅\n\n"
            f"Мы свяжемся с капитаном при необходимости.\n\n"
            f"Если кто-то из игроков хочет пойти бесплатно — можно оформить участие по ставке прямо здесь 👇"
        )
        keyboard = [
            [InlineKeyboardButton("🎟️ Прийти по ставке", callback_data="start_promo_registration")],
            [InlineKeyboardButton("📋 Условия акции", callback_data="promo_terms")],
            [
                InlineKeyboardButton("❓ Помощь", callback_data="help"),
                InlineKeyboardButton("🔙 Назад", callback_data="back_to_city")
            ]
        ]
    else:  # Краснодар
        final_message = (
            f"Команда зарегистрирована ✅\n\n"
            f"Мы свяжемся с капитаном при необходимости.\n\n"
            f"Если кто-то из игроков хочет пойти бесплатно — можно оформить участие по ставке прямо здесь 👇"
        )
        keyboard = [
            [InlineKeyboardButton("🎟️ Прийти по ставке", callback_data="start_promo_registration")],
            [InlineKeyboardButton("📋 Условия акции", callback_data="promo_terms")],
            [
                InlineKeyboardButton("❓ Помощь", callback_data="help"),
                InlineKeyboardButton("🔙 Назад", callback_data="back_to_city")
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
            await context.bot.send_message(
                chat_id=admin_id,
                text=admin_message
            )
        except Exception as e:
            logger.error(f"Ошибка отправки админу {admin_id}: {e}")

    return SELECTING_GAME

async def promo_team_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"ПОЛУЧЕНО НАЗВАНИЕ КОМАНДЫ ДЛЯ АКЦИИ: {update.message.text}")
    
    if update.message.text.startswith('/'):
        await update.message.reply_text("Пожалуйста, введите название команды.")
        return ASKING_PROMO_TEAM
    
    team_name = update.message.text.strip()
    if not team_name:
        await update.message.reply_text("Название команды не может быть пустым. Введите название 👇")
        return ASKING_PROMO_TEAM
    
    context.user_data["promo_team"] = team_name
    logger.info(f"Название команды для акции сохранено: {team_name}")
    
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
    return ASKING_CLIENT_ID

async def client_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"ПОЛУЧЕН ID КЛИЕНТА: {update.message.text}")
    
    if update.message.text.startswith('/'):
        await update.message.reply_text("Пожалуйста, введите ID клиента.")
        return ASKING_CLIENT_ID
    
    client_id = update.message.text.strip()
    if not client_id:
        await update.message.reply_text("ID клиента не может быть пустым. Введите ID 👇")
        return ASKING_CLIENT_ID
    
    context.user_data["client_id"] = client_id
    logger.info(f"ID клиента сохранен: {client_id}")
    
    await update.message.reply_text(
        "Введите номер пари.\n"
        "Посмотреть можно в разделе «Мои пари» 👇"
    )
    return ASKING_BET_NUMBER

async def bet_number_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"ПОЛУЧЕН НОМЕР ПАРИ: {update.message.text}")
    
    if update.message.text.startswith('/'):
        await update.message.reply_text("Пожалуйста, введите номер пари.")
        return ASKING_BET_NUMBER
    
    bet_number = update.message.text.strip()
    if not bet_number:
        await update.message.reply_text("Номер пари не может быть пустым. Введите номер 👇")
        return ASKING_BET_NUMBER
    
    context.user_data["bet_number"] = bet_number
    logger.info(f"Номер пари сохранен: {bet_number}")
    
    await update.message.reply_text("Напишите имя и номер телефона 👇")
    return ASKING_PROMO_PHONE

async def promo_phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"ПОЛУЧЕН ТЕЛЕФОН: {update.message.text}")
    
    if update.message.text.startswith('/'):
        await update.message.reply_text("Пожалуйста, введите имя и телефон.")
        return ASKING_PROMO_PHONE
    
    phone_info = update.message.text.strip()
    if not phone_info:
        await update.message.reply_text("Данные не могут быть пустыми. Введите имя и телефон 👇")
        return ASKING_PROMO_PHONE
    
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
    city_name = selected_game.split()[0] if selected_game else ""
    
    if city_name == "Казань":
        final_text = f"✅ Участие по ставке подтверждено.\n\nЖдём вас 11 марта в {venue_prepositional}.\nДо встречи на квизе!"
    elif city_name == "Краснодар":
        final_text = f"✅ Участие по ставке подтверждено.\n\nЖдём вас 14 марта в {venue_prepositional}.\nДо встречи на квизе!"
    else:
        final_text = "✅ Участие по ставке подтверждено.\n\nДо встречи на квизе!"
    
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
            await context.bot.send_message(
                chat_id=admin_id,
                text=admin_message
            )
        except Exception as e:
            logger.error(f"Ошибка отправки админу {admin_id}: {e}")

    context.user_data.clear()
    return SELECTING_GAME

async def help_message_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"ПОЛУЧЕН ВОПРОС: {update.message.text}")
    
    if update.message.text.startswith('/'):
        await update.message.reply_text("Пожалуйста, напишите ваш вопрос.")
        return ASKING_HELP_MESSAGE
    
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
            logger.error(f"Ошибка отправки вопроса админу {admin_id}: {e}")
    
    return SELECTING_GAME

async def message_to_admin_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    admin_ids = get_admin_ids()
    
    await update.message.reply_text(
        "✅ Ваше сообщение отправлено нам!\n\nОжидайте ответа, мы свяжемся с вами в ближайшее время."
    )
    
    welcome_text = (
        "Привет! На связи футбольный квиз «Паненка» 🎉\n\n"
        "Этот бот поможет вашей команде попасть на ближайший квиз.\n\n"
        "Выберите город и дату 🌍"
    )
    await send_main_menu(update, context, welcome_text)
    
    for admin_id in admin_ids:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"📨 Сообщение от пользователя\n"
                     f"ID: {user.id}\n"
                     f"Имя: {user.full_name}\n"
                     f"Username: @{user.username}\n"
                     f"------------------------\n"
                     f"Чат пользователя: {user.id}"
            )
            
            if update.message.text:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=f"📝 Текст:\n{update.message.text}"
                )
            elif update.message.photo:
                photo = update.message.photo[-1]
                await context.bot.send_photo(
                    chat_id=admin_id,
                    photo=photo.file_id,
                    caption=f"📸 Фото от пользователя"
                )
            elif update.message.voice:
                await context.bot.send_voice(
                    chat_id=admin_id,
                    voice=update.message.voice.file_id
                )
            
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения админу {admin_id}: {e}")
    
    return SELECTING_GAME

async def admin_reply_from_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    
    admin_id = update.effective_user.id
    if admin_id not in get_admin_ids() and admin_id not in get_help_admin_ids():
        return
    
    if not update.message.reply_to_message:
        return
    
    replied_text = update.message.reply_to_message.text or ""
    
    import re
    user_id_match = re.search(r'ID: (\d+)', replied_text)
    if not user_id_match:
        return
    
    user_id = int(user_id_match.group(1))
    
    data = load_data()
    users = data.get("users", {})
    chat_id = users.get(str(user_id))
    
    if not chat_id:
        return
    
    try:
        if update.message.text:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✉️ Ответ от организаторов:\n\n{update.message.text}"
            )
        elif update.message.photo:
            photo = update.message.photo[-1]
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo.file_id,
                caption=f"✉️ Ответ от организаторов:\n\n{update.message.caption or ''}"
            )
        elif update.message.voice:
            await context.bot.send_voice(
                chat_id=chat_id,
                voice=update.message.voice.file_id
            )
        
    except Exception as e:
        logger.error(f"Ошибка отправки ответа: {e}")

async def add_game_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in get_admin_ids():
        await update.message.reply_text("У вас нет прав")
        return ConversationHandler.END
    await update.message.reply_text("Введите название новой игры (в формате 'Город дата'):")
    return ASKING_GAME_NAME

async def add_game_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_game = update.message.text.strip()
    data = load_data()
    data["games"].append(new_game)
    save_data(data)
    await update.message.reply_text(f"✅ Игра '{new_game}' добавлена!")
    return ConversationHandler.END

async def del_game_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in get_admin_ids():
        await update.message.reply_text("У вас нет прав")
        return ConversationHandler.END
    
    data = load_data()
    games = data.get("games", [])
    if not games:
        await update.message.reply_text("Нет игр для удаления")
        return ConversationHandler.END
    
    keyboard = []
    for i, game in enumerate(games):
        keyboard.append([InlineKeyboardButton(f"❌ {game}", callback_data=f"del_{i}")])
    keyboard.append([InlineKeyboardButton("🚫 Отмена", callback_data="del_cancel")])
    
    await update.message.reply_text(
        "Выберите игру для удаления:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ASKING_GAME_TO_DELETE

async def del_game_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "del_cancel":
        await query.edit_message_text("Удаление отменено")
        return ConversationHandler.END
    
    try:
        game_index = int(query.data.replace("del_", ""))
        data = load_data()
        games = data.get("games", [])
        
        if 0 <= game_index < len(games):
            deleted_game = games.pop(game_index)
            data["games"] = games
            save_data(data)
            await query.edit_message_text(f"✅ Игра '{deleted_game}' удалена!")
        else:
            await query.edit_message_text("Ошибка: игра не найдена")
    except Exception as e:
        await query.edit_message_text(f"Ошибка: {e}")
    
    return ConversationHandler.END

async def check_games(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in get_admin_ids():
        await update.message.reply_text("У вас нет прав")
        return
    
    data = load_data()
    games = data.get("games", [])
    message = "📋 Список игр:\n\n"
    for i, game in enumerate(games):
        message += f"{i}. {game}\n"
    await update.message.reply_text(message)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Действие отменено"
    )
    welcome_text = (
        "Привет! На связи футбольный квиз «Паненка» ✌🏻\n\n"
        "Этот бот поможет вашей команде попасть на ближайший квиз.\n\n"
        "Выберите город и дату 👇"
    )
    await send_main_menu(update, context, welcome_text)
    return SELECTING_GAME

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "❓ Помощь по боту:\n\n"
        "📋 Команды:\n"
        "/start - Показать главное меню\n"
        "/cancel - Отменить текущее действие\n\n"
        "📨 Связаться с нами - задать вопрос организаторам\n\n"
        "🎁 Акция от FONBET:\n"
        "Пари от 700₽ с 24.02.2026 по дату игры"
    )
    
    await update.message.reply_text(
        help_text,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 В главное меню", callback_data="back_to_main")
        ]])
    )

def main():
    Thread(target=run_web, daemon=True).start()
    logger.info("🌐 Веб-сервер запущен на порту 10000")

    try:
        application = Application.builder().token(BOT_TOKEN).build()

        reg_conv_handler = ConversationHandler(
            entry_points=[CommandHandler("start", start)],
            states={
                SELECTING_GAME: [
                    CallbackQueryHandler(game_selected),
                ],
                SHOWING_CITY_MENU: [
                    CallbackQueryHandler(game_selected),
                ],
                SHOWING_REGISTER_MENU: [
                    CallbackQueryHandler(game_selected),
                ],
                SHOWING_PROMO_MENU: [
                    CallbackQueryHandler(game_selected),
                ],
                SHOWING_TERMS_MENU: [
                    CallbackQueryHandler(game_selected),
                ],
                TYPING_TEAM_NAME: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, team_name_received)
                ],
                TYPING_PLAYER_COUNT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, player_count_received)
                ],
                ASKING_LEGIONER: [
                    CallbackQueryHandler(legioner_received)
                ],
                TYPING_CAPTAIN_INFO: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, captain_info_received)
                ],
                ASKING_PROMO_TEAM: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, promo_team_received),
                    CallbackQueryHandler(game_selected)
                ],
                ASKING_CLIENT_ID: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, client_id_received),
                    CallbackQueryHandler(game_selected)
                ],
                ASKING_BET_NUMBER: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, bet_number_received),
                    CallbackQueryHandler(game_selected)
                ],
                ASKING_PROMO_PHONE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, promo_phone_received),
                    CallbackQueryHandler(game_selected)
                ],
                ASKING_HELP_MESSAGE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, help_message_received),
                    CallbackQueryHandler(game_selected)
                ],
                ASKING_MESSAGE_TO_ADMIN: [
                    MessageHandler(filters.TEXT | filters.PHOTO | filters.VOICE, message_to_admin_received),
                    CallbackQueryHandler(game_selected)
                ],
                REPLYING_TO_USER: [
                    CallbackQueryHandler(game_selected)
                ],
            },
            fallbacks=[
                CommandHandler("cancel", cancel),
                CommandHandler("start", start),
                CommandHandler("help", help_command),
                CallbackQueryHandler(game_selected, pattern="^back_to_main$")
            ],
        )

        add_game_conv_handler = ConversationHandler(
            entry_points=[CommandHandler("addgame", add_game_start)],
            states={
                ASKING_GAME_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_game_received)],
            },
            fallbacks=[CommandHandler("cancel", cancel)],
        )
        
        del_game_conv_handler = ConversationHandler(
            entry_points=[CommandHandler("delgame", del_game_start)],
            states={
                ASKING_GAME_TO_DELETE: [CallbackQueryHandler(del_game_selected)],
            },
            fallbacks=[CommandHandler("cancel", cancel)],
        )

        application.add_handler(MessageHandler(
            filters.TEXT | filters.PHOTO | filters.VOICE, 
            admin_reply_from_private
        ), group=1)

        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("checkgames", check_games))
        application.add_handler(reg_conv_handler)
        application.add_handler(add_game_conv_handler)
        application.add_handler(del_game_conv_handler)

        print("✅ Бот запущен!")
        print(f"👑 Админы для регистраций: {get_registration_admin_ids()}")
        print(f"👑 Админ для вопросов: {get_help_admin_ids()}")
        print(f"🖼️ Фото Москвы: {PHOTO_MOSCOW}")
        print(f"🖼️ Фото Казани: {PHOTO_KAZAN}")
        print(f"🖼️ Фото Краснодара: {PHOTO_KRASNODAR}")
        print(f"📁 Файлы существуют: {os.path.exists(PHOTO_MOSCOW)} {os.path.exists(PHOTO_KAZAN)} {os.path.exists(PHOTO_KRASNODAR)}")
        print("📨 Сообщения будут приходить в ЛИЧКУ")
        print("🌐 Веб-сервер активен на / - бот не уснет!")
        print("📊 Данные акции будут сохраняться в Google Sheets")
        
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