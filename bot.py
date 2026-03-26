import json
import logging
import os
import sys
import time
import base64
import gspread
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
    filters,
    ContextTypes,
)
from flask import Flask

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

# Flask для Render
app = Flask('')

@app.route('/')
def home():
    return "OK"

def run_web():
    app.run(host='0.0.0.0', port=10000)

# Восстановление credentials.json
if os.environ.get('GOOGLE_CREDENTIALS_BASE64'):
    try:
        creds_base64 = os.environ.get('GOOGLE_CREDENTIALS_BASE64')
        creds_json = base64.b64decode(creds_base64).decode('utf-8')
        with open('credentials.json', 'w') as f:
            f.write(creds_json)
        print("✅ credentials.json восстановлен")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

# Данные об играх
GAME_INFO = {
    "Москва 11.04": {
        "active": True,
        "text": "📍 Москва – 11 апреля (суббота)\n\n🏟️ Бар «Золотая Вобла»\n📫 Протоповоский пер, 3\n\n🕖 Двери открыты с 16:00\n⚽️ Старт игры – 16:20\n\n💰 Стоимость участия:\n800₽ – в джерси любого клуба или сборной\n1 000₽ – в обычной одежде"
    }
}

DATA_FILE = "data.json"

def load_data():
    if not os.path.exists(DATA_FILE):
        default_data = {
            "registrations": [],
            "users": {}
        }
        save_data(default_data)
        return default_data
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"registrations": [], "users": {}}

def save_data(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Ошибка сохранения: {e}")

async def save_to_google_sheets(registration):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_file = "credentials.json"
        if os.path.exists(creds_file):
            creds = ServiceAccountCredentials.from_json_keyfile_name(creds_file, scope)
            client = gspread.authorize(creds)
            sheet = client.open_by_key(SPREADSHEET_ID).sheet1
            now = datetime.now()
            row = [
                now.strftime("%Y-%m-%d %H:%M:%S"),
                registration.get('team_name', ''),
                registration.get('player_count', ''),
                registration.get('legioner', ''),
                registration.get('captain_info', ''),
                registration.get('user_name', '')
            ]
            sheet.append_row(row)
            logger.info("✅ Сохранено в Google Sheets")
    except Exception as e:
        logger.error(f"Ошибка Google Sheets: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name
    
    # Сохраняем пользователя
    data = load_data()
    data["users"][str(user_id)] = user_name
    save_data(data)
    
    welcome_text = (
        "Привет! На связи футбольный квиз «Паненка» ✌🏻\n\n"
        "Этот бот поможет вашей команде попасть на ближайший квиз.\n\n"
        "Выберите город и дату 👇"
    )
    
    keyboard = [[InlineKeyboardButton("Москва 11.04", callback_data="city_moscow")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if os.path.exists('logo.jpg'):
        with open('logo.jpg', 'rb') as photo:
            await update.message.reply_photo(photo, caption=welcome_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(welcome_text, reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик всех кнопок"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    logger.info(f"Нажата кнопка: {data}")
    
    # Кнопка города Москва
    if data == "city_moscow":
        game_text = GAME_INFO["Москва 11.04"]["text"]
        keyboard = [
            [InlineKeyboardButton("📄 Заявить команду", callback_data="register_start")],
            [
                InlineKeyboardButton("❓ Помощь", callback_data="help_start"),
                InlineKeyboardButton("🔙 Назад", callback_data="back_main")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if os.path.exists('photo1.jpg'):
            with open('photo1.jpg', 'rb') as photo:
                await query.message.reply_photo(photo, caption=game_text, reply_markup=reply_markup)
        else:
            await query.message.reply_text(game_text, reply_markup=reply_markup)
    
    # Начать регистрацию
    elif data == "register_start":
        context.user_data["registration"] = {}
        await query.message.reply_text(
            "Отлично! ✌🏻\n\nДавайте зарегистрируем команду.\n\nВведите название команды 👇"
        )
    
    # Помощь
    elif data == "help_start":
        await query.message.reply_text(
            "❓ Есть вопрос?\n\nНапишите ваш вопрос одним сообщением, и мы ответим в ближайшее время."
        )
        context.user_data["waiting_for_question"] = True
    
    # Назад в главное меню
    elif data == "back_main":
        welcome_text = (
            "Привет! На связи футбольный квиз «Паненка» ✌🏻\n\n"
            "Выберите город и дату 👇"
        )
        keyboard = [[InlineKeyboardButton("Москва 11.04", callback_data="city_moscow")]]
        await query.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard))
    
    # Обработка кнопок легионера
    elif data == "legioner_yes":
        context.user_data["registration"]["legioner"] = "Да"
        await query.message.reply_text(
            "Напишите имя и номер телефона капитана 👇\n\nПример: Иван Иванов, +7 999 123-45-67"
        )
    
    elif data == "legioner_no":
        context.user_data["registration"]["legioner"] = "Нет"
        await query.message.reply_text(
            "Напишите имя и номер телефона капитана 👇\n\nПример: Иван Иванов, +7 999 123-45-67"
        )

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name
    text = update.message.text.strip()
    
    # Проверяем, ждем ли вопрос
    if context.user_data.get("waiting_for_question"):
        # Отправляем вопрос админу
        admin_message = (
            f"❓ Вопрос от пользователя\n\n"
            f"👤 Имя: {user_name}\n"
            f"🆔 ID: {user_id}\n"
            f"------------------------\n"
            f"{text}"
        )
        
        try:
            await context.bot.send_message(chat_id=HELP_ADMIN_ID, text=admin_message)
            await update.message.reply_text(
                "✅ Ваш вопрос отправлен! Мы ответим в ближайшее время.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 В главное меню", callback_data="back_main")
                ]])
            )
        except Exception as e:
            logger.error(f"Ошибка отправки вопроса: {e}")
            await update.message.reply_text("❌ Ошибка отправки вопроса. Попробуйте позже.")
        
        context.user_data["waiting_for_question"] = False
        return
    
    # Проверяем, идет ли регистрация
    if "registration" in context.user_data:
        reg = context.user_data["registration"]
        
        # Шаг 1: название команды
        if "team_name" not in reg:
            if len(text) > 50:
                await update.message.reply_text("Название слишком длинное (макс 50 символов). Введите название 👇")
                return
            reg["team_name"] = text
            await update.message.reply_text("Сколько игроков будет в команде? (от 3 до 10 человек)")
        
        # Шаг 2: количество игроков
        elif "player_count" not in reg:
            if not text.isdigit():
                await update.message.reply_text("Пожалуйста, введите число (от 3 до 10):")
                return
            count = int(text)
            if count < 3 or count > 10:
                await update.message.reply_text("Количество игроков должно быть от 3 до 10. Введите число:")
                return
            reg["player_count"] = text
            
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
        
        # Шаг 3: данные капитана
        elif "captain_info" not in reg:
            if len(text) > 100:
                await update.message.reply_text("Данные слишком длинные. Введите короче 👇")
                return
            
            reg["captain_info"] = text
            reg["user_id"] = user_id
            reg["user_name"] = user_name
            reg["date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Сохраняем регистрацию
            data = load_data()
            data["registrations"].append(reg.copy())
            save_data(data)
            
            # Сохраняем в Google Sheets
            await save_to_google_sheets(reg)
            
            # Отправляем подтверждение пользователю
            final_message = (
                f"✅ Команда зарегистрирована!\n\n"
                f"🏆 {reg['team_name']}\n"
                f"👥 {reg['player_count']} игроков\n"
                f"🌟 Легионер: {reg['legioner']}\n"
                f"👨‍💼 Капитан: {reg['captain_info']}\n\n"
                f"Ждем вас в субботу в баре «Золотая Вобла»!"
            )
            
            keyboard = [[InlineKeyboardButton("🔙 В главное меню", callback_data="back_main")]]
            await update.message.reply_text(final_message, reply_markup=InlineKeyboardMarkup(keyboard))
            
            # Отправляем уведомление админам
            admin_message = (
                f"🔔 НОВАЯ РЕГИСТРАЦИЯ!\n\n"
                f"🎮 Игра: Москва 11.04\n"
                f"🏆 Команда: {reg['team_name']}\n"
                f"👥 Игроков: {reg['player_count']}\n"
                f"🌟 Легионер: {reg['legioner']}\n"
                f"👨‍💼 Капитан: {reg['captain_info']}\n"
                f"👤 От: {user_name}\n"
                f"🆔 ID: {user_id}"
            )
            
            for admin_id in [SPECIFIC_ADMIN_ID, SECOND_ADMIN_ID]:
                try:
                    await context.bot.send_message(chat_id=admin_id, text=admin_message)
                except Exception as e:
                    logger.error(f"Ошибка отправки админу {admin_id}: {e}")
            
            # Очищаем данные регистрации
            del context.user_data["registration"]
    
    else:
        # Если ничего не ожидаем, отправляем в главное меню
        welcome_text = "Выберите город и дату 👇"
        keyboard = [[InlineKeyboardButton("Москва 11.04", callback_data="city_moscow")]]
        await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard))

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика для админов"""
    user_id = update.effective_user.id
    
    # Проверяем, админ ли это
    if user_id not in [SPECIFIC_ADMIN_ID, SECOND_ADMIN_ID]:
        await update.message.reply_text("⛔️ У вас нет доступа к этой команде")
        return
    
    data = load_data()
    registrations = data.get("registrations", [])
    
    stats_text = "📊 СТАТИСТИКА РЕГИСТРАЦИЙ\n\n"
    stats_text += f"Всего команд: {len(registrations)}\n\n"
    
    if registrations:
        stats_text += "Последние 5 регистраций:\n"
        for reg in registrations[-5:]:
            stats_text += f"• {reg.get('team_name', '?')} - {reg.get('player_count', '?')} чел.\n"
    
    await update.message.reply_text(stats_text)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена действия"""
    context.user_data.clear()
    await update.message.reply_text("❌ Действие отменено")
    
    welcome_text = "Выберите город и дату 👇"
    keyboard = [[InlineKeyboardButton("Москва 11.04", callback_data="city_moscow")]]
    await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard))

def main():
    # Запускаем веб-сервер
    Thread(target=run_web, daemon=True).start()
    
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    print("=" * 50)
    print("✅ БОТ ЗАПУЩЕН!")
    print(f"👑 Админы: {SPECIFIC_ADMIN_ID}, {SECOND_ADMIN_ID}")
    print(f"❓ Вопросы: {HELP_ADMIN_ID}")
    print("=" * 50)
    
    # Запускаем бота
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()