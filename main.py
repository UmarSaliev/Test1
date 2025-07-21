import logging
import os
import json
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler
)
import aiohttp
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Конфигурация
TOKEN = os.getenv("BOT_TOKEN")
OWNER_IDS = list(map(int, os.getenv("OWNER_IDS", "").split(","))) if os.getenv("OWNER_IDS") else []
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
BOT_USERNAME = "@Tester894bot"
USER_DATA_FILE = "user_data.json"

# Состояния для ConversationHandler
GET_NAME = 0

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Функции для работы с данными ---
def load_user_data():
    try:
        with open(USER_DATA_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_user_data(data):
    with open(USER_DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

user_data = load_user_data()

async def is_owner(user_id: int) -> bool:
    """Проверка, является ли пользователь учителем"""
    return user_id in OWNER_IDS

# --- Обработка медиа ---
async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo and update.message.caption:
        user_id = update.effective_user.id
        user_info = user_data.get(str(user_id), {})
        
        caption = (
            f"📩 От ученика {user_info.get('full_name', 'Неизвестный')}\n"
            f"@{user_info.get('username', 'нет_username')}\n\n"
            f"{update.message.caption}"
        )
        
        # Отправка всем учителям
        for teacher_id in OWNER_IDS:
            try:
                await context.bot.send_photo(
                    chat_id=teacher_id,
                    photo=update.message.photo[-1].file_id,
                    caption=caption
                )
            except Exception as e:
                logger.error(f"Ошибка отправки учителю {teacher_id}: {e}")
        
        await update.message.reply_text("✅ Ваше фото отправлено учителям")

# --- Команды для учителей ---
async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Доступ только для учителей")
        return
    
    if not user_data:
        await update.message.reply_text("📋 Список учеников пуст")
        return
    
    user_list = "\n".join(
        f"@{data['username']} - {data['full_name']} (ID: {user_id})"
        for user_id, data in user_data.items()
    )
    await update.message.reply_text(f"📋 Список учеников:\n\n{user_list}")

# --- ИИ-команды ---
async def ask_ai(prompt: str) -> str:
    """Универсальная функция запроса к ИИ"""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": f"https://t.me/{BOT_USERNAME[1:]}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "meta-llama/llama-3-70b-instruct",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data["choices"][0]["message"]["content"]
                logger.error(f"API Error: {await response.text()}")
    except Exception as e:
        logger.error(f"AI request failed: {str(e)}")
    return None

async def task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Решение математических задач (/task)"""
    if not context.args:
        await update.message.reply_text("ℹ️ Пример: /task 2+2")
        return
    
    query = " ".join(context.args)
    await update.message.reply_chat_action("typing")
    
    response = await ask_ai(
        f"Реши задачу: '{query}'. Объясни шаги решения на русском языке. "
        f"Ответ должен быть точным и понятным школьнику."
    )
    
    await update.message.reply_text(response or "⚠️ Не удалось решить задачу")

async def formula_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Объяснение формул (/formula)"""
    if not context.args:
        await update.message.reply_text("ℹ️ Пример: /formula площадь круга")
        return
    
    query = " ".join(context.args)
    await update.message.reply_chat_action("typing")
    
    response = await ask_ai(
        f"Объясни формулу: '{query}'. Приведи математическую запись, "
        f"пояснение переменных и пример использования на русском языке."
    )
    
    await update.message.reply_text(response or "⚠️ Не удалось обработать запрос")

async def theorem_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Объяснение теорем (/theorem)"""
    if not context.args:
        await update.message.reply_text("ℹ️ Пример: /theorem Пифагора")
        return
    
    query = " ".join(context.args)
    await update.message.reply_chat_action("typing")
    
    response = await ask_ai(
        f"Объясни теорему {query} на русском языке. Приведи формулировку, "
        f"доказательство и примеры применения."
    )
    
    await update.message.reply_text(response or "⚠️ Не удалось обработать запрос")

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Поиск информации (/search)"""
    if not context.args:
        await update.message.reply_text("ℹ️ Пример: /search интегралы")
        return
    
    query = " ".join(context.args)
    await update.message.reply_chat_action("typing")
    
    response = await ask_ai(
        f"Дай краткий и точный ответ на русском языке по запросу: '{query}'. "
        f"Используй только проверенные научные источники."
    )
    
    await update.message.reply_text(response or "⚠️ Не удалось найти информацию")

# --- Системные команды ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /start"""
    user_id = update.effective_user.id
    if str(user_id) not in user_data:
        await update.message.reply_text("👋 Введите ваше имя и фамилию:")
        return GET_NAME
    await update.message.reply_text("🤖 Используйте /help для списка команд")
    return ConversationHandler.END

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка имени пользователя"""
    user_id = update.effective_user.id
    user_data[str(user_id)] = {
        "full_name": update.message.text,
        "username": update.effective_user.username or "нет_username"
    }
    save_user_data(user_data)
    await update.message.reply_text("✅ Регистрация завершена! Используйте /help")
    return ConversationHandler.END

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Справка по командам (/help)"""
    help_text = (
        "📚 Доступные команды:\n"
        "/task - Решить задачу\n"
        "/formula - Объяснить формулу\n"
        "/theorem - Объяснить теорему\n"
        "/search - Найти информацию\n"
    )
    if await is_owner(update.effective_user.id):
        help_text += "\n👨‍🏫 Команды учителя:\n/list - Список учеников"
    await update.message.reply_text(help_text)

# --- Запуск бота ---
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # Обработчики
    app.add_handler(MessageHandler(filters.PHOTO & filters.CAPTION, handle_media))
    
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={GET_NAME: [MessageHandler(filters.TEXT, get_name)]},
        fallbacks=[]
    ))

    # Регистрация команд
    commands = [
        ("help", help_command),
        ("task", task_command),
        ("formula", formula_command),
        ("theorem", theorem_command),
        ("search", search_command),
        ("list", list_command)
    ]
    for cmd, handler in commands:
        app.add_handler(CommandHandler(cmd, handler))

    app.add_error_handler(lambda u, c: logger.error(c.error))
    logger.info("Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
