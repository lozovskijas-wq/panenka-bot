import json
import logging
import os
import sys
from typing import Dict, Any

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

# Простой способ получить токен - сначала из переменных окружения, потом из config
BOT_TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_IDS_STR = os.environ.get('ADMIN_ID', '')

# Если нет в окружении, пробуем из config.py
if not BOT_TOKEN:
    try:
        import config
        BOT_TOKEN = config.BOT_TOKEN
        ADMIN_IDS_STR = config.ADMIN_ID
    except ImportError:
        print("ERROR: No BOT_TOKEN found in environment or config.py")
        sys.exit(1)

if not BOT_TOKEN:
    print("ERROR: BOT_TOKEN is not set")
    sys.exit(1)

# Включаем логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Состояния для разговоров ---
(
    SELECTING_GAME,
    TYPING_TEAM_NAME,
    TYPING_PLAYER_COUNT,
    ASKING_LEGIONER,
    TYPING_CAPTAIN_INFO,
) = range(5)
ASKING_GAME_NAME = range(5, 6)

# --- URL картинки (замени на свою ссылку) ---
PHOTO_URL = "https://example.com/your-image.jpg"  # ЗАМЕНИ НА РЕАЛЬНУЮ ССЫЛКУ!

# --- Функция для получения списка админов ---
def get_admin_ids():
    """Преобразует строку с ID админов в список чисел."""
    if not ADMIN_IDS_STR:
        return []
    
    # Если это строка, разделяем по запятой
    if isinstance(ADMIN_IDS_STR, str):
        try:
            # Убираем пробелы и превращаем в числа
            admin_ids = [int(id_str.strip()) for id_str in ADMIN_IDS_STR.split(',') if id_str.strip()]
            return admin_ids
        except ValueError:
            logger.error(f"Ошибка преобразования ADMIN_ID: {ADMIN_IDS_STR}")
            return []
    else:
        # Если это просто число (один админ)
        return [ADMIN_IDS_STR]

# --- Работа с файлом data.json ---
DATA_FILE = "data.json"

def load_data() -> Dict[str, Any]:
    """Загружает данные из JSON файла."""
    if not os.path.exists(DATA_FILE):
        default_data = {"games": [], "registrations": []}
        save_data(default_data)
        return default_data
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"games": [], "registrations": []}

def save_data(data: Dict[str, Any]):
    """Сохраняет данные в JSON файл."""
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Ошибка сохранения данных: {e}")

# --- Команда /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает приветствие с картинкой и список игр."""
    data = load_data()
    games = data.get("games", [])
    
    # Текст приветствия
    caption = "Привет! На связи футбольный квиз «Паненка»! На какую игру регистрируемся? 🤔"
    
    # Создаем кнопки с играми
    if games:
        keyboard = []
        for game in games:
            callback_data = game[:50]
            keyboard.append([InlineKeyboardButton(game, callback_data=callback_data)])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Отправляем фото с подписью и кнопками
        try:
            # Пробуем отправить фото
            await update.message.reply_photo(
                photo=PHOTO_URL,
                caption=caption,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Ошибка отправки фото: {e}")
            # Если фото не отправилось, шлем просто текст
            await update.message.reply_text(
                caption,
                reply_markup=reply_markup
            )
    else:
        # Если игр нет
        await update.message.reply_text("Пока нет доступных игр. Загляните позже!")
    
    return SELECTING_GAME

# --- Обработчик выбора игры ---
async def game_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запоминает выбранную игру и спрашивает название команды."""
    query = update.callback_query
    await query.answer()

    selected_game = query.data
    context.user_data["selected_game"] = selected_game

    await query.edit_message_text(
        text="Как называется ваша команда?"
    )
    return TYPING_TEAM_NAME

# --- Обработчик названия команды ---
async def team_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохраняет название команды и спрашивает количество игроков."""
    team_name = update.message.text
    context.user_data["team_name"] = team_name

    await update.message.reply_text("Сколько человек в вашей команде?")
    return TYPING_PLAYER_COUNT

# --- Обработчик количества игроков ---
async def player_count_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохраняет количество игроков и спрашивает про легионера."""
    player_count = update.message.text
    context.user_data["player_count"] = player_count

    # Создаем кнопки Да/Нет
    keyboard = [
        [
            InlineKeyboardButton("Да", callback_data="legioner_yes"),
            InlineKeyboardButton("Нет", callback_data="legioner_no")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Готовы ли вы взять в команду легионера (человека без команды)?",
        reply_markup=reply_markup
    )
    return ASKING_LEGIONER

# --- Обработчик ответа про легионера ---
async def legioner_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохраняет ответ про легионера и спрашивает данные капитана."""
    query = update.callback_query
    await query.answer()
    
    legioner_answer = "Да" if query.data == "legioner_yes" else "Нет"
    context.user_data["legioner"] = legioner_answer
    
    await query.edit_message_text(
        text="Супер! Напишите ФИО и номер телефона капитана (в свободной форме):"
    )
    return TYPING_CAPTAIN_INFO

# --- Обработчик данных капитана ---
async def captain_info_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохраняет данные капитана, завершает регистрацию и шлет уведомление админу."""
    captain_info = update.message.text
    user = update.effective_user

    # Собираем все данные
    registration = {
        "user_id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "selected_game": context.user_data.get("selected_game"),
        "team_name": context.user_data.get("team_name"),
        "player_count": context.user_data.get("player_count"),
        "legioner": context.user_data.get("legioner", "Не указано"),
        "captain_info": captain_info,
        "date": str(update.message.date)
    }

    # Сохраняем в JSON
    data = load_data()
    data["registrations"].append(registration)
    save_data(data)
    logger.info(f"Новая регистрация: {registration}")

    # Отправляем подтверждение пользователю
    await update.message.reply_text(
        "Спасибо за регистрацию, увидимся на игре ♥️😉"
    )

    # Отправляем уведомление ВСЕМ админам
    admin_ids = get_admin_ids()
    admin_message = (
        f"🔔 *Новая регистрация!*\n"
        f"*Игра:* {registration['selected_game']}\n"
        f"*Команда:* {registration['team_name']}\n"
        f"*Игроков:* {registration['player_count']}\n"
        f"*Легионер:* {registration['legioner']}\n"
        f"*Капитан:* {registration['captain_info']}\n"
        f"*От:* {registration['full_name']} (@{registration['username']})"
    )
    
    for admin_id in admin_ids:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=admin_message,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение админу {admin_id}: {e}")

    context.user_data.clear()
    return ConversationHandler.END

# --- Команда /addgame (для админов) ---
async def add_game_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начинает диалог добавления игры."""
    user_id = update.effective_user.id
    admin_ids = get_admin_ids()
    
    if user_id not in admin_ids:
        await update.message.reply_text("У вас нет прав на выполнение этой команды.")
        return ConversationHandler.END

    await update.message.reply_text("Введите название новой игры:")
    return ASKING_GAME_NAME

async def add_game_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получает название новой игры от админа и сохраняет."""
    new_game = update.message.text

    data = load_data()
    if "games" not in data:
        data["games"] = []
    data["games"].append(new_game)
    save_data(data)

    await update.message.reply_text(f"Игра '{new_game}' успешно добавлена!")
    return ConversationHandler.END

# --- Команда /cancel ---
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменяет текущий диалог."""
    await update.message.reply_text("Действие отменено.")
    return ConversationHandler.END

# --- Команда /help ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает справку."""
    help_text = (
        "Доступные команды:\n"
        "/start - Начать регистрацию на игру\n"
        "/cancel - Отменить текущее действие\n"
        "/help - Показать эту справку"
    )
    
    # Добавляем инфо про /addgame только для админов
    user_id = update.effective_user.id
    if user_id in get_admin_ids():
        help_text += "\n/addgame - Добавить новую игру (только для админов)"
    
    await update.message.reply_text(help_text)

# --- Главная функция ---
def main():
    """Запускает бота."""
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()

    # Диалог регистрации
    reg_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECTING_GAME: [CallbackQueryHandler(game_selected)],
            TYPING_TEAM_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, team_name_received)],
            TYPING_PLAYER_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, player_count_received)],
            ASKING_LEGIONER: [CallbackQueryHandler(legioner_received)],
            TYPING_CAPTAIN_INFO: [MessageHandler(filters.TEXT & ~filters.COMMAND, captain_info_received)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start),
            CommandHandler("help", help_command)
        ],
    )

    # Диалог добавления игры
    add_game_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("addgame", add_game_start)],
        states={
            ASKING_GAME_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_game_received)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start),
            CommandHandler("help", help_command)
        ],
    )

    # Обработчик команды help вне диалогов
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(reg_conv_handler)
    application.add_handler(add_game_conv_handler)

    print("Бот запущен...")
    # Запускаем polling
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()