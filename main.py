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
GET_NAME, BROADCAST_MESSAGE = range(2)

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
        json.dump(data, f)

user_data = load_user_data()

async def is_owner(user_id: int) -> bool:
    return user_id in OWNER_IDS

async def check_api_available():
    """Проверяет доступность OpenRouter API"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
                timeout=10
            ) as resp:
                return resp.status == 200
    except:
        return False

async def ask_ai(prompt: str) -> str:
    """Улучшенная функция запроса к ИИ"""
    if not await check_api_available():
        return None

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": f"https://t.me/{BOT_USERNAME[1:]}",
        "X-Title": "MathHelperBot",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "meta-llama/llama-3-70b-instruct",  # Более мощная модель
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

# Команды ИИ
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

# Остальные функции (formula_command, search_command и т.д.) остаются без изменений

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📚 Доступные команды:\n"
        "/start - Начать работу\n"
        "/task <текст> - Решить задачу\n"
        "/theorem <текст> - Объяснить теорему\n"
        "/formula <текст> - Найти формулу\n"
        "/search <текст> - Поиск информации\n"
    )
    
    if await is_owner(update.effective_user.id):
        help_text += (
            "\n👨‍🏫 Команды для учителя:\n"
            "/broadcast - Рассылка сообщений\n"
            "/list - Список учеников"
        )
    
    await update.message.reply_text(help_text)

# Команды для учителей
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Доступ запрещен")
        return
    
    await update.message.reply_text(
        "📢 Введите сообщение для рассылки (текст или фото с подписью):\n"
        "Для отмены используйте /cancel"
    )
    return BROADCAST_MESSAGE

async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not user_data:
        await update.message.reply_text("❌ Нет пользователей для рассылки")
        return ConversationHandler.END
    
    successful = 0
    failed = []
    
    try:
        if update.message.text:
            # Текстовая рассылка
            for user_id in user_data:
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"📢 Сообщение от учителя:\n\n{update.message.text}"
                    )
                    successful += 1
                except Exception as e:
                    failed.append(user_id)
                    logger.error(f"Failed to send to {user_id}: {e}")
        
        elif update.message.photo:
            # Рассылка фото
            photo = update.message.photo[-1].file_id
            caption = update.message.caption or ""
            
            for user_id in user_data:
                try:
                    await context.bot.send_photo(
                        chat_id=user_id,
                        photo=photo,
                        caption=f"📢 От учителя:\n\n{caption}" if caption else "📢 Сообщение от учителя"
                    )
                    successful += 1
                except Exception as e:
                    failed.append(user_id)
                    logger.error(f"Failed to send photo to {user_id}: {e}")
        
        # Формируем отчет
        report = f"✅ Рассылка завершена:\nОтправлено: {successful}\nНе удалось: {len(failed)}"
        if failed:
            report += "\n\nНе удалось отправить следующим пользователям:\n" + "\n".join(failed[:10])  # Показываем первые 10 ошибок
        await update.message.reply_text(report)
    
    except Exception as e:
        logger.error(f"Broadcast failed: {e}")
        await update.message.reply_text("⚠️ Произошла ошибка при рассылке")
    
    return ConversationHandler.END

# Остальные функции (list_command, cancel, error_handler) остаются без изменений

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # Обработчик регистрации
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            GET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            BROADCAST_MESSAGE: [
                MessageHandler(filters.TEXT | filters.PHOTO, broadcast_message),
                CommandHandler("cancel", cancel)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    # Регистрация обработчиков команд
    command_handlers = [
        ('help', help_command),
        ('theorem', theorem_command),
        ('task', task_command),
        ('formula', formula_command),
        ('search', search_command),
        ('list', list_command),
        ('broadcast', broadcast_command)
    ]
    
    for command, handler in command_handlers:
        app.add_handler(CommandHandler(command, handler))

    app.add_handler(conv_handler)
    app.add_error_handler(error_handler)

    logger.info("Бот запущен и готов к работе")
    app.run_polling()

if __name__ == "__main__":
    main()
