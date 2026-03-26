import json
import logging
import os
import sys
import base64
import gspread
import signal
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
from http.server import HTTPServer, BaseHTTPRequestHandler

# Простой HTTP сервер для health check
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    
    def log_message(self, format, *args):
        pass

def run_health_server():
    try:
        server = HTTPServer(('0.0.0.0', 10000), HealthHandler)
        server.serve_forever()
    except:
        pass

def signal_handler(sig, frame):
    print('Остановка бота...')
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

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

(
    MAIN_MENU,
    CITY_SELECTED,
    REGISTER_TEAM,
    REGISTER_PLAYERS,
    REGISTER_LEGIONER,
    REGISTER_CAPTAIN,
    HELP_MESSAGE,
) = range(7)

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
            "games": ["Москва 11.04", "Казань 11.03", "Краснодар 14.03"], 
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
                registration.get('captain_info', ''),
                registration.get('player_count', ''),
                registration.get('legioner', ''),
                str(registration.get('user_id', ''))
            ]
            sheet.append_row(row)
            logger.info(f"✅ Сохранено в Google Sheets")
    except Exception as e:
        logger.error(f"Ошибка Google Sheets: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    data = load_data()
    if "users" not in data:
        data["users"] = {}
    data["users"][str(user_id)] = chat_id
    save_data(data)
    
    context.user_data.clear()
    
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
            await update.message.reply_photo(photo, caption=welcome_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text=welcome_text, reply_markup=reply_markup)
    
    return MAIN_MENU

async def game_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    callback_data = query.data
    logger.info(f"Нажата кнопка: {callback_data}")
    
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
                await show_city_menu(update, context)
                return CITY_SELECTED
            else:
                await query.edit_message_text("Ошибка: игра не найдена")
                return MAIN_MENU
        except Exception as e:
            logger.error(f"Ошибка: {e}")
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
        help_text = "❓ Есть вопрос?\n\nНапишите его сюда @Panenka_Registration — поможем разобраться."
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_city")]]
        await query.edit_message_text(help_text, reply_markup=InlineKeyboardMarkup(keyboard))
        return HELP_MESSAGE
    
    elif callback_data == "start_registration":
        await query.edit_message_text("Отлично! ✌🏻\n\nДавайте зарегистрируем команду на игру в Москве — 11 апреля.\n\nВведите название команды 👇")
        return REGISTER_TEAM
    
    elif callback_data in ["legioner_yes", "legioner_no"]:
        context.user_data["legioner"] = "Да" if callback_data == "legioner_yes" else "Нет"
        await query.edit_message_text("Напишите имя и номер телефона капитана 👇")
        return REGISTER_CAPTAIN
    
    else:
        await start(update, context)
        return MAIN_MENU

async def show_city_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    selected_game = context.user_data.get("selected_game")
    
    if not selected_game:
        await query.edit_message_text("Ошибка: город не выбран")
        return MAIN_MENU
    
    game_info = GAME_INFO.get(selected_game, {})
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
        [InlineKeyboardButton("❓ Помощь", callback_data="help"), InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if os.path.exists(photo_file):
        with open(photo_file, 'rb') as photo:
            await query.edit_message_media(media=InputMediaPhoto(media=photo, caption=menu_text), reply_markup=reply_markup)
    else:
        await query.edit_message_text(text=menu_text, reply_markup=reply_markup)

async def team_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.startswith('/'):
        await update.message.reply_text("Пожалуйста, введите название команды.")
        return REGISTER_TEAM
    
    team_name = update.message.text.strip()
    if not team_name:
        await update.message.reply_text("Название команды не может быть пустым. Введите название 👇")
        return REGISTER_TEAM
    
    context.user_data["team_name"] = team_name
    await update.message.reply_text("Сколько игроков будет в команде? (от 3 до 10 человек)")
    return REGISTER_PLAYERS

async def player_count_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await update.message.reply_text("Количество игроков должно быть от 3 до 10. Введите число:")
        return REGISTER_PLAYERS
    
    context.user_data["player_count"] = player_count
    
    keyboard = [[InlineKeyboardButton("✅ Да", callback_data="legioner_yes"), InlineKeyboardButton("❌ Нет", callback_data="legioner_no")]]
    await update.message.reply_text("Готовы ли взять в команду «легионера» (человека без команды)?", reply_markup=InlineKeyboardMarkup(keyboard))
    return REGISTER_LEGIONER

async def legioner_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["legioner"] = "Да" if query.data == "legioner_yes" else "Нет"
    await query.edit_message_text("Напишите имя и номер телефона капитана 👇")
    return REGISTER_CAPTAIN

async def captain_info_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.startswith('/'):
        await update.message.reply_text("Пожалуйста, введите данные капитана.")
        return REGISTER_CAPTAIN
    
    captain_info = update.message.text.strip()
    if not captain_info:
        await update.message.reply_text("Данные капитана не могут быть пустыми. Введите имя и телефон 👇")
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
    save_to_google_sheets(registration)

    final_message = f"Команда зарегистрирована ✅ Ждем вас в субботу в баре «Золотая Вобла»\n\nМы свяжемся с капитаном при необходимости."
    keyboard = [[InlineKeyboardButton("🔙 В главное меню", callback_data="back_to_main")]]
    await update.message.reply_text(final_message, reply_markup=InlineKeyboardMarkup(keyboard))

    admin_message = f"🔔 Новая регистрация!\nИгра: {selected_game}\nКоманда: {team_name}\nИгроков: {context.user_data.get('player_count')}\nЛегионер: {context.user_data.get('legioner', 'Не указано')}\nКапитан: {captain_info}\nОт: {user.full_name} (@{user.username})"
    for admin_id in get_registration_admin_ids():
        try:
            await context.bot.send_message(chat_id=admin_id, text=admin_message)
        except Exception as e:
            logger.error(f"Ошибка: {e}")

    return MAIN_MENU

async def help_message_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.startswith('/'):
        await update.message.reply_text("Пожалуйста, напишите ваш вопрос.")
        return HELP_MESSAGE
    
    help_text = update.message.text.strip()
    user = update.effective_user
    
    await update.message.reply_text("✅ Ваш вопрос отправлен! Мы ответим в ближайшее время.", 
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="back_to_city")]]))

    for admin_id in get_help_admin_ids():
        try:
            await context.bot.send_message(chat_id=admin_id, 
                text=f"❓ Вопрос от пользователя\nID: {user.id}\nИмя: {user.full_name}\nUsername: @{user.username}\n------------------------\n{help_text}")
        except Exception as e:
            logger.error(f"Ошибка: {e}")
    
    return MAIN_MENU

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Действие отменено")
    return await start(update, context)

def main():
    # Запускаем простой HTTP сервер
    import threading
    server_thread = threading.Thread(target=run_health_server, daemon=True)
    server_thread.start()
    
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Очищаем вебхук
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(application.bot.delete_webhook(drop_pending_updates=True))
        print("✅ Вебхук очищен")
    except Exception as e:
        print(f"Ошибка очистки: {e}")
    loop.close()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [CallbackQueryHandler(game_selected)],
            CITY_SELECTED: [CallbackQueryHandler(game_selected)],
            REGISTER_TEAM: [MessageHandler(filters.TEXT & ~filters.COMMAND, team_name_received)],
            REGISTER_PLAYERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, player_count_received)],
            REGISTER_LEGIONER: [CallbackQueryHandler(legioner_received)],
            REGISTER_CAPTAIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, captain_info_received)],
            HELP_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, help_message_received), CallbackQueryHandler(game_selected)],
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start)],
    )
    
    application.add_handler(conv_handler)
    
    print("=" * 50)
    print("✅ БОТ ЗАПУЩЕН!")
    print(f"👑 Админы: {get_registration_admin_ids()}")
    print("=" * 50)
    
    # Запускаем бота
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
    
