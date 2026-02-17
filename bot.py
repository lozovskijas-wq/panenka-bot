import json
import logging
import os
import sys
import time
from typing import Dict, Any, List
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

if sys.version_info >= (3, 12):
    print("Ошибка: Python 3.12+ не поддерживается. Используйте Python 3.11")
    sys.exit(1)

BOT_TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_IDS_STR = os.environ.get('ADMIN_ID', '')
SPECIFIC_ADMIN_ID = 286355827

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
) = range(7)
ASKING_GAME_NAME = range(7, 8)
ASKING_GAME_TO_DELETE = range(8, 9)

PHOTO_FILE = "logo.jpg"

GAME_INFO = {
    "Москва 28.02": {
        "full_date": "28 февраля (суббота)",
        "venue": "COiN HALL - ул. Пятницкая, 71/5с2 (м. Добрынинская)",
        "time": "Двери открыты с 15:00, игра начнется в 15:30"
    },
    "Казань 11.03": {
        "full_date": "11 марта (среда)",
        "venue": "MAXIMILIAN'S - ул. Спартаковская, 6",
        "time": "Двери открыты с 19:00, игра начнется в 19:30"
    },
    "Краснодар 14.03": {
        "full_date": "14 марта (суббота)",
        "venue": "NAMESTi - ул. Красноармейская 55/2",
        "time": "Двери открыты с 16:30, игра начнется в 17:00"
    }
}

def get_admin_ids() -> List[int]:
    admin_ids = [SPECIFIC_ADMIN_ID]
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

DATA_FILE = "data.json"

def load_data() -> Dict[str, Any]:
    if not os.path.exists(DATA_FILE):
        default_data = {
            "games": [
                "Москва 28.02",
                "Казань 11.03",
                "Краснодар 14.03"
            ], 
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

async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    data = load_data()
    games = data.get("games", [])
    
    games_keyboard = []
    if games:
        for i, game in enumerate(games):
            callback_data = f"game_{i}"
            games_keyboard.append([InlineKeyboardButton(game, callback_data=callback_data)])
    
    games_keyboard.append([InlineKeyboardButton("📨 Связаться с нами", callback_data="contact_admin")])
    
    info_keyboard = [
        [
            InlineKeyboardButton("❓ Помощь", callback_data="show_help"),
            InlineKeyboardButton("❌ Отмена", callback_data="cancel_action")
        ]
    ]
    
    full_keyboard = games_keyboard + info_keyboard
    reply_markup = InlineKeyboardMarkup(full_keyboard)
    clean_text = text.replace('*', '')
    
    try:
        if os.path.exists(PHOTO_FILE):
            with open(PHOTO_FILE, 'rb') as photo:
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
            logger.info("Новое сообщение с фото отправлено")
        else:
            logger.error(f"Файл {PHOTO_FILE} не найден!")
            if update.callback_query:
                await update.callback_query.message.reply_text(
                    text=f"{clean_text}\n\n(⚠️ Фото не загружено)",
                    reply_markup=reply_markup
                )
            else:
                await update.message.reply_text(
                    text=f"{clean_text}\n\n(⚠️ Фото не загружено)",
                    reply_markup=reply_markup
                )
    except Exception as e:
        logger.error(f"Ошибка отправки фото: {e}")
        if update.callback_query:
            await update.callback_query.message.reply_text(
                text=f"{clean_text}\n\n(⚠️ Ошибка загрузки фото)",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                text=f"{clean_text}\n\n(⚠️ Ошибка загрузки фото)",
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
        "Привет! На связи футбольный квиз «Паненка»✌🏻\n\n"
        "В каком городе регистрируем команду?"
    )
    
    await send_main_menu(update, context, welcome_text)
    return SELECTING_GAME

async def game_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    callback_data = query.data
    logger.info(f"Нажата кнопка: {callback_data}")
    
    if callback_data == "contact_admin":
        await query.message.reply_text(
            "📝 Напишите ваше сообщение для нас:\n\n(Отправьте текст, фото или голосовое сообщение)"
        )
        return ASKING_MESSAGE_TO_ADMIN
    
    elif callback_data == "show_help":
        help_text = (
            "❓ Помощь по боту:\n\n"
            "📋 Команды:\n"
            "/start - Показать главное меню\n"
            "/cancel - Отменить текущее действие\n\n"
            "📨 Связаться с нами - задать вопрос организаторам\n\n"
            "⚽ Регистрация на игру:\n"
            "1. Выбери город из списка\n"
            "2. Введи название команды\n"
            "3. Укажи количество игроков\n"
            "4. Ответь про легионера\n"
            "5. Оставь контакты капитана\n\n"
            "После регистрации админ получит уведомление"
        )
        await query.message.reply_text(
            text=help_text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_menu")
            ]])
        )
        return SELECTING_GAME
    
    elif callback_data == "back_to_menu":
        context.user_data.clear()
        welcome_text = (
            "Привет! На связи футбольный квиз «Паненка»✌🏻\n\n"
            "В каком городе регистрируем команду?"
        )
        await send_main_menu(update, context, welcome_text)
        return SELECTING_GAME
    
    elif callback_data == "cancel_action":
        await query.message.reply_text(
            "❌ Действие отменено. Выберите город или свяжитесь с нами.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 В меню", callback_data="back_to_menu")
            ]])
        )
        return SELECTING_GAME
    
    elif callback_data.startswith("game_"):
        try:
            game_index = int(callback_data.replace("game_", ""))
            data = load_data()
            games = data.get("games", [])
            
            if 0 <= game_index < len(games):
                selected_game = games[game_index]
                context.user_data["selected_game"] = selected_game
                
                game_info = GAME_INFO.get(selected_game, {})
                
                info_lines = [
                    f"{selected_game} - {game_info.get('full_date', '')}",
                    game_info.get('venue', ''),
                    "",
                    game_info.get('time', ''),
                    "",
                    "Стоимость участия - 800₽ с игрока в джерси любого клуба или сборной 🎽, 1000₽ — с игрока в обычной одежде",
                    "",
                    "Напишите название своей команды 👇"
                ]
                
                info_text = "\n".join(info_lines)
                
                await query.message.reply_text(info_text)
                return TYPING_TEAM_NAME
            else:
                await query.message.reply_text("Ошибка: игра не найдена")
                return SELECTING_GAME
        except Exception as e:
            logger.error(f"Ошибка выбора игры: {e}")
            await query.message.reply_text("Ошибка при выборе игры")
            return SELECTING_GAME

async def team_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.startswith('/'):
        await update.message.reply_text("Пожалуйста, введите название команды, а не команду.")
        return TYPING_TEAM_NAME
    
    team_name = update.message.text.strip()
    if not team_name:
        await update.message.reply_text("Название команды не может быть пустым. Введите название:")
        return TYPING_TEAM_NAME
        
    context.user_data["team_name"] = team_name
    logger.info(f"Название команды: {team_name}")
    
    await update.message.reply_text("Сколько будет игроков? (от 3 до 10)")
    return TYPING_PLAYER_COUNT

async def player_count_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    
    keyboard = [
        [
            InlineKeyboardButton("Да", callback_data="legioner_yes"),
            InlineKeyboardButton("Нет", callback_data="legioner_no")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Готовы ли взять в команду легионера (игрока без команды)?",
        reply_markup=reply_markup
    )
    return ASKING_LEGIONER

async def legioner_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    legioner_answer = "Да" if query.data == "legioner_yes" else "Нет"
    context.user_data["legioner"] = legioner_answer
    
    await query.message.reply_text(
        text="Имя и номер телефона капитана 👇"
    )
    return TYPING_CAPTAIN_INFO

async def captain_info_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.startswith('/'):
        await update.message.reply_text("Пожалуйста, введите данные капитана, а не команду.")
        return TYPING_CAPTAIN_INFO
    
    captain_info = update.message.text.strip()
    if not captain_info:
        await update.message.reply_text("Данные капитана не могут быть пустыми. Введите ФИО и телефон:")
        return TYPING_CAPTAIN_INFO
    
    user = update.effective_user
    selected_game = context.user_data.get("selected_game", "")
    team_name = context.user_data.get("team_name", "")

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
    data["registrations"].append(registration)
    save_data(data)
    logger.info(f"Новая регистрация: {registration}")

    game_info = GAME_INFO.get(selected_game, {})
    game_date = game_info.get('full_date', selected_game)

    await update.message.reply_text(
        f"Команда {team_name} зарегистрирована на квиз {game_date}\n\n"
        f"Просим приходить заранее и подготовить наличные для оплаты\n\n"
        f"До встречи на игре ⚽️",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 В главное меню", callback_data="back_to_menu")
        ]])
    )

    admin_ids = get_admin_ids()
    admin_message = (
        f"🔔 Новая регистрация!\n"
        f"Игра: {selected_game}\n"
        f"Команда: {team_name}\n"
        f"Игроков: {context.user_data.get('player_count')}\n"
        f"Легионер: {context.user_data.get('legioner', 'Не указано')}\n"
        f"Капитан: {captain_info}\n"
        f"От: {user.full_name} (@{user.username})"
    )
    
    for admin_id in admin_ids:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=admin_message
            )
        except Exception as e:
            logger.error(f"Ошибка отправки админу {admin_id}: {e}")

    return SELECTING_GAME

async def message_to_admin_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    admin_ids = get_admin_ids()
    
    await update.message.reply_text(
        "✅ Ваше сообщение отправлено нам!\n\nОжидайте ответа, мы свяжемся с вами в ближайшее время."
    )
    
    welcome_text = (
        "Привет! На связи футбольный квиз «Паненка»✌🏻\n\n"
        "В каком городе регистрируем команду?"
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
    if admin_id not in get_admin_ids():
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
        "Привет! На связи футбольный квиз «Паненка»✌🏻\n\n"
        "В каком городе регистрируем команду?"
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
        "⚽ Регистрация на игру:\n"
        "1. Выбери город из списка\n"
        "2. Введи название команды\n"
        "3. Укажи количество игроков\n"
        "4. Ответь про легионера\n"
        "5. Оставь контакты капитана\n\n"
        "После регистрации админ получит уведомление"
    )
    
    await update.message.reply_text(
        help_text,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 В главное меню", callback_data="back_to_menu")
        ]])
    )

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    reg_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECTING_GAME: [
                CallbackQueryHandler(game_selected),
            ],
            TYPING_TEAM_NAME: [
                MessageHandler(filters.TEXT, team_name_received)
            ],
            TYPING_PLAYER_COUNT: [
                MessageHandler(filters.TEXT, player_count_received)
            ],
            ASKING_LEGIONER: [
                CallbackQueryHandler(legioner_received)
            ],
            TYPING_CAPTAIN_INFO: [
                MessageHandler(filters.TEXT, captain_info_received)
            ],
            ASKING_MESSAGE_TO_ADMIN: [
                MessageHandler(filters.TEXT | filters.PHOTO | filters.VOICE, message_to_admin_received)
            ],
            REPLYING_TO_USER: [],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start),
            CommandHandler("help", help_command),
            CallbackQueryHandler(game_selected, pattern="^back_to_menu$")
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
    print(f"👑 Админы: {get_admin_ids()}")
    print(f"🖼️ Файл фото: {PHOTO_FILE}")
    print(f"📁 Файл существует: {os.path.exists(PHOTO_FILE)}")
    print("📨 Сообщения будут приходить в ЛИЧКУ")
    print("⏱️ Polling настроен для стабильной работы на Render")
    
    # Оптимизированный polling для Render
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        timeout=30,
        drop_pending_updates=True,
        poll_interval=1.0
    )

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        time.sleep(5)
        os.execl(sys.executable, sys.executable, *sys.argv)