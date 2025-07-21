import logging
import os
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
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

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def is_owner(user_id: int) -> bool:
    """Проверяет, является ли пользователь владельцем"""
    return user_id in OWNER_IDS

async def ask_ai(prompt: str) -> str:
    """Запрос к OpenRouter API"""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": f"https://t.me/{BOT_USERNAME[1:]}",
        "X-Title": "MathHelperBot"
    }
    payload = {
        "model": "openrouter/meta-llama/llama-3-8b-instruct:free",
        "messages": [{"role": "user", "content": prompt}]
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                data = await response.json()
                return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"OpenRouter error: {e}")
        return "⚠️ Произошла ошибка при обработке запроса"

# Добавленная функция для обработки текстовых сообщений
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    try:
        prompt = update.message.text
        response = await ask_ai(prompt)
        await update.message.reply_text(response)
    except Exception as e:
        logger.error(f"Error in handle_text_message: {e}")
        await update.message.reply_text("⚠️ Произошла ошибка при обработке сообщения")

# Команды бота
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот-помощник по математике.\n"
        "Отправьте мне задачу, формулу или теорему.\n"
        "Фото с подписью будут отправлены учителю."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📚 Доступные команды:\n"
        "/task <текст> - Решить задачу\n"
        "/formula <текст> - Найти формулу\n"
        "/theorem <текст> - Информация о теореме\n"
        "/search <текст/фото> - Поиск информации"
    )
    
    if await is_owner(update.effective_user.id):
        help_text += "\n\n👨‍🏫 Команды для учителя:\n/broadcast - Рассылка\n/list - Список учеников"
    
    await update.message.reply_text(help_text)

async def theorem_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /theorem (например: /theorem Теорема Виетта)"""
    if not context.args:
        await update.message.reply_text("ℹ️ Укажите название теоремы, например: /theorem Пифагора")
        return
    
    theorem_name = " ".join(context.args)
    prompt = (
        f"Дай подробное объяснение теоремы {theorem_name}:\n"
        f"- Формулировка\n"
        f"- Доказательство\n"
        f"- Примеры применения\n"
        f"- Историческая справка"
    )
    
    try:
        await update.message.reply_chat_action(action="typing")
        response = await ask_ai(prompt)
        await update.message.reply_text(f"📚 Теорема {theorem_name}:\n\n{response}")
    except Exception as e:
        logger.error(f"Theorem error: {e}")
        await update.message.reply_text("⚠️ Не удалось найти информацию о теореме")

async def formula_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /formula"""
    if not context.args:
        await update.message.reply_text("ℹ️ Укажите название формулы, например: /formula квадратное уравнение")
        return
    
    formula_name = " ".join(context.args)
    prompt = (
        f"Объясни формулу {formula_name}:\n"
        f"- Математическая запись\n"
        f"- Пояснение каждого элемента\n"
        f"- Примеры использования\n"
        f"- Типичные задачи"
    )
    
    try:
        await update.message.reply_chat_action(action="typing")
        response = await ask_ai(prompt)
        await update.message.reply_text(f"🧮 Формула {formula_name}:\n\n{response}")
    except Exception as e:
        logger.error(f"Formula error: {e}")
        await update.message.reply_text("⚠️ Не удалось найти информацию о формуле")

async def task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /task"""
    if not context.args:
        await update.message.reply_text("ℹ️ Укажите задачу, например: /task Найти площадь круга радиусом 5 см")
        return
    
    task_text = " ".join(context.args)
    prompt = (
        f"Реши задачу: {task_text}\n"
        f"- Подробное пошаговое решение\n"
        f"- Объяснение каждого шага\n"
        f"- Итоговый ответ"
    )
    
    try:
        await update.message.reply_chat_action(action="typing")
        response = await ask_ai(prompt)
        await update.message.reply_text(f"📝 Решение задачи:\n\n{response}")
    except Exception as e:
        logger.error(f"Task error: {e}")
        await update.message.reply_text("⚠️ Не удалось решить задачу")

async def handle_photo_with_caption(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка фото с подписью (ФИО и др.)"""
    photo = update.message.photo[-1].file_id
    caption = update.message.caption or "Без подписи"
    
    user_info = (
        f"👤 От: {update.message.from_user.full_name}\n"
        f"🆔 ID: {update.message.from_user.id}\n"
        f"📝 Подпись: {caption}"
    )
    
    if OWNER_IDS:
        try:
            for owner_id in OWNER_IDS:
                await context.bot.send_photo(
                    chat_id=owner_id,
                    photo=photo,
                    caption=user_info
                )
            await update.message.reply_text("📤 Фото с подписью отправлено учителю!")
        except Exception as e:
            logger.error(f"Photo forwarding error: {e}")
            await update.message.reply_text("⚠️ Не удалось отправить фото")
    else:
        await update.message.reply_text("✅ Фото получено")

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда рассылки (/broadcast)"""
    if not await is_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Доступ запрещен")
        return
    
    if not context.args:
        await update.message.reply_text("ℹ️ Укажите сообщение для рассылки")
        return
    
    await update.message.reply_text("📢 Рассылка начата")

async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда списка (/list)"""
    if not await is_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Доступ запрещен")
        return
    
    await update.message.reply_text("📋 Список учеников")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Глобальный обработчик ошибок"""
    logger.error(f"Update {update} caused error: {context.error}")
    if update.message:
        await update.message.reply_text("⚠️ Произошла внутренняя ошибка")

def main():
    """Запуск бота"""
    app = ApplicationBuilder().token(TOKEN).build()

    # Регистрация команд
    command_handlers = [
        ('start', start),
        ('help', help_command),
        ('theorem', theorem_command),
        ('formula', formula_command),
        ('task', task_command),
        ('broadcast', broadcast_command),
        ('list', list_command)
    ]
    
    for command, handler in command_handlers:
        app.add_handler(CommandHandler(command, handler))

    # Обработка сообщений
    app.add_handler(MessageHandler(filters.PHOTO & filters.CAPTION, handle_photo_with_caption))
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.CAPTION, handle_photo_with_caption))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    # Обработчик ошибок
    app.add_error_handler(error_handler)

    logger.info("Бот запущен и готов к работе")
    app.run_polling()

if __name__ == "__main__":
    main()
