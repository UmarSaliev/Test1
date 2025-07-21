import logging
import os
import json
from telegram import Update, InputFile
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

async def ask_ai(prompt: str) -> str:
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": f"https://t.me/{BOT_USERNAME[1:]}",
        "X-Title": "MathHelperBot"
    }
    payload = {
        "model": "openrouter/auto",
        "messages": [{"role": "user", "content": prompt}]
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=20)
            ) as response:
                if response.status != 200:
                    error = await response.text()
                    logger.error(f"API Error: {error}")
                    return None
                
                data = await response.json()
                return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"AI Error: {str(e)}")
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
        f"Дай подробное объяснение теоремы '{query}' на русском языке:\n"
        f"- Формулировка\n- Доказательство\n- Примеры применения\n- Историческая справка"
    )
    
    response = await ask_ai(prompt)
    if response:
        await update.message.reply_text(f"📚 Теорема {query}:\n\n{response}")
    else:
        await update.message.reply_text("⚠️ Не удалось получить ответ. Попробуйте позже.")

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
        f"Реши задачу: '{query}'. Дай пошаговое решение на русском языке с объяснением каждого шага."
    )
    
    response = await ask_ai(prompt)
    if response:
        await update.message.reply_text(f"📝 Решение задачи:\n\n{response}")
    else:
        await update.message.reply_text("⚠️ Не удалось решить задачу. Попробуйте позже.")

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        # Обработка поиска по фото
        await update.message.reply_text("🔍 Анализирую изображение...")
        # Здесь можно добавить обработку фото через API
        await update.message.reply_text("⚠️ Поиск по изображениям временно недоступен")
    elif context.args:
        # Обработка текстового поиска
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

# Команды для учителей
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Доступ запрещен")
        return
    
    await update.message.reply_text(
        "📢 Введите сообщение для рассылки (текст или фото с подписью):\n"
        "Используйте /cancel для отмены"
    )
    return BROADCAST_MESSAGE

async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    successful = 0
    failed = 0
    
    if update.message.text:
        # Текстовая рассылка
        for user_id, data in user_data.items():
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"📢 Сообщение от учителя:\n\n{update.message.text}"
                )
                successful += 1
            except Exception as e:
                logger.error(f"Broadcast error to {user_id}: {str(e)}")
                failed += 1
    elif update.message.photo:
        # Рассылка фото
        photo = update.message.photo[-1].file_id
        caption = update.message.caption or ""
        
        for user_id, data in user_data.items():
            try:
                await context.bot.send_photo(
                    chat_id=user_id,
                    photo=photo,
                    caption=f"📢 От учителя:\n\n{caption}" if caption else "📢 Сообщение от учителя"
                )
                successful += 1
            except Exception as e:
                logger.error(f"Broadcast photo error to {user_id}: {str(e)}")
                failed += 1
    
    await update.message.reply_text(
        f"✅ Рассылка завершена:\n"
        f"• Успешно: {successful}\n"
        f"• Не доставлено: {failed}"
    )
    return ConversationHandler.END

async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Доступ запрещен")
        return
    
    if not user_data:
        await update.message.reply_text("📋 Список пользователей пуст")
        return
    
    user_list = "\n".join(
        f"@{data['username']} - {data['full_name']} (ID: {user_id})"
        for user_id, data in user_data.items()
    )
    
    await update.message.reply_text(f"📋 Список пользователей:\n\n{user_list}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Действие отменено")
    return ConversationHandler.END

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error: {context.error}")
    if update.message:
        await update.message.reply_text("⚠️ Произошла внутренняя ошибка")

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

    # Команды
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("theorem", theorem_command))
    app.add_handler(CommandHandler("formula", formula_command))
    app.add_handler(CommandHandler("task", task_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))

    # Обработчик ошибок
    app.add_error_handler(error_handler)

    logger.info("Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
