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

# Загрузка/сохранение данных пользователей
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

# Обработка имени пользователя
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if str(user_id) not in user_data:
        await update.message.reply_text(
            "👋 Добро пожаловать! Пожалуйста, введите ваше имя и фамилию:"
        )
        return GET_NAME
    else:
        await update.message.reply_text(
            "🤖 Я ваш математический помощник. Используйте /help для списка команд."
        )
        return ConversationHandler.END

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    full_name = update.message.text
    username = update.effective_user.username or "нет_username"
    
    user_data[str(user_id)] = {
        "full_name": full_name,
        "username": username
    }
    save_user_data(user_data)
    
    await update.message.reply_text(
        f"✅ Спасибо, {full_name}! Теперь вы можете использовать все функции бота.\n"
        "Напишите /help для списка команд."
    )
    return ConversationHandler.END

# ИИ-команды
async def theorem_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("ℹ️ Пример: /theorem Теорема Пифагора")
        return
    
    query = " ".join(context.args)
    await update.message.reply_chat_action(action="typing")
    
    prompt = (
        f"Объясни теорему '{query}' на русском языке. Дайте:\n"
        f"1. Четкую формулировку\n"
        f"2. Подробное доказательство\n"
        f"3. Примеры применения\n"
        f"4. Исторический контекст\n\n"
        f"Ответ должен быть строго на русском языке, точным и понятным."
    )
    
    response = await ask_ai(prompt)
    if response:
        await update.message.reply_text(f"📚 Теорема {query}:\n\n{response}")
    else:
        await update.message.reply_text(
            "⚠️ Не удалось обработать запрос. Возможные причины:\n"
            "1. Проблемы с API\n"
            "2. Недостаточно токенов\n"
            "3. Слишком сложный запрос\n\n"
            "Попробуйте позже или упростите запрос."
        )

async def formula_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("ℹ️ Пример: /formula Квадратное уравнение")
        return
    
    query = " ".join(context.args)
    await update.message.reply_chat_action(action="typing")
    
    prompt = (
        f"Объясни формулу '{query}' на русском языке:\n"
        f"- Математическая запись\n- Пояснение элементов\n- Примеры использования\n- Типичные задачи"
    )
    
    response = await ask_ai(prompt)
    if response:
        await update.message.reply_text(f"🧮 Формула {query}:\n\n{response}")
    else:
        await update.message.reply_text("⚠️ Не удалось получить ответ. Попробуйте позже.")

async def task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("ℹ️ Пример: /task Найти площадь круга радиусом 5 см")
        return
    
    query = " ".join(context.args)
    await update.message.reply_chat_action(action="typing")
    
    prompt = (
        f"Реши задачу: '{query}'. Дайте:\n"
        f"1. Пошаговое решение с объяснением каждого шага\n"
        f"2. Итоговый ответ с единицами измерения\n"
        f"3. Альтернативные методы решения (если есть)\n\n"
        f"Ответ должен быть строго на русском языке, точным и понятным."
    )
    
    response = await ask_ai(prompt)
    if response:
        await update.message.reply_text(f"📝 Решение задачи:\n\n{response}")
    else:
        await update.message.reply_text(
            "⚠️ Не удалось решить задачу. Возможные причины:\n"
            "1. Некорректная формулировка задачи\n"
            "2. Проблемы с API\n"
            "3. Слишком сложная задача\n\n"
            "Попробуйте переформулировать запрос или обратиться позже."
        )

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        await update.message.reply_text("🔍 Анализирую изображение...")
        await update.message.reply_text("⚠️ Поиск по изображениям временно недоступен")
    elif context.args:
        query = " ".join(context.args)
        await update.message.reply_chat_action(action="typing")
        
        prompt = f"Найди информацию по запросу: '{query}'. Дай краткий и точный ответ на русском языке."
        
        response = await ask_ai(prompt)
        if response:
            await update.message.reply_text(f"🔎 Результаты по запросу '{query}':\n\n{response}")
        else:
            await update.message.reply_text("⚠️ Не удалось выполнить поиск. Попробуйте позже.")
    else:
        await update.message.reply_text("ℹ️ Отправьте текст или фото для поиска")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📚 Доступные команды:\n"
        "/start - Начать работу\n"
        "/task <текст> - Решить задачу\n"
        "/theorem <текст> - Объяснить теорему\n"
        "/formula <текст> - Найти формулу\n"
        "/search <текст> - Поиск информации\n"
    )
    
    await update.message.reply_text(help_text)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Текущее действие отменено")
    return ConversationHandler.END

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error: {context.error}")
    if update.message:
        await update.message.reply_text("⚠️ Произошла внутренняя ошибка")

async def ask_ai(prompt: str) -> str:
    """Функция запроса к ИИ"""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": f"https://t.me/{BOT_USERNAME[1:]}",
        "X-Title": "MathHelperBot",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "meta-llama/llama-3-70b-instruct",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 1000
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            ) as response:
                if response.status != 200:
                    error = await response.text()
                    logger.error(f"API Error: {error}")
                    return None
                
                data = await response.json()
                return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"AI request failed: {str(e)}", exc_info=True)
        return None

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # Обработчик регистрации
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            GET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    # Регистрация обработчиков команд
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("theorem", theorem_command))
    app.add_handler(CommandHandler("formula", formula_command))
    app.add_handler(CommandHandler("task", task_command))
    app.add_handler(CommandHandler("search", search_command))

    app.add_error_handler(error_handler)
    logger.info("Бот запущен (без функции рассылки)")
    app.run_polling()

if __name__ == "__main__":
    main()
