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

# --- Исправленные функции для broadcast ---
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
    """Проверка прав с логированием"""
    result = user_id in OWNER_IDS
    logger.info(f"Проверка прав для {user_id}: {'Доступ разрешен' if result else 'Доступ запрещен'}")
    return result

async def debug_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для отладки"""
    user_id = update.effective_user.id
    await update.message.reply_text(
        f"🔍 Ваш ID: {user_id}\n"
        f"OWNER_IDS: {OWNER_IDS}\n"
        f"Вы учитель: {'✅' if await is_owner(user_id) else '❌'}"
    )

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Новая версия команды /broadcast"""
    user_id = update.effective_user.id
    if not await is_owner(user_id):
        await update.message.reply_text(f"⛔ Доступ запрещен! Ваш ID: {user_id}")
        return
    
    logger.info(f"Учитель {user_id} начал рассылку")
    await update.message.reply_text(
        "📢 Введите сообщение для рассылки (текст или фото):\n"
        "Для отмены используйте /cancel"
    )
    return BROADCAST_MESSAGE

async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Улучшенная рассылка"""
    if not user_data:
        await update.message.reply_text("❌ Нет пользователей для рассылки")
        return ConversationHandler.END

    status_msg = await update.message.reply_text("🔄 Начинаю рассылку...")
    successful = 0
    failed = []

    try:
        # Для текста
        if update.message.text:
            for user_id_str, user_info in user_data.items():
                try:
                    await context.bot.send_message(
                        chat_id=int(user_id_str),
                        text=f"📢 Рассылка от учителя:\n\n{update.message.text}"
                    )
                    successful += 1
                except Exception as e:
                    failed.append(user_id_str)
                    logger.warning(f"Ошибка отправки для {user_id_str}: {e}")

        # Для фото
        elif update.message.photo:
            photo = update.message.photo[-1].file_id
            caption = update.message.caption or ""
            for user_id_str, user_info in user_data.items():
                try:
                    await context.bot.send_photo(
                        chat_id=int(user_id_str),
                        photo=photo,
                        caption=f"📢 {caption}" if caption else "📢 Сообщение от учителя"
                    )
                    successful += 1
                except Exception as e:
                    failed.append(user_id_str)
                    logger.warning(f"Ошибка отправки фото для {user_id_str}: {e}")

        # Отчет
        report = [
            f"📊 Результат:",
            f"• Отправлено: {successful}",
            f"• Ошибок: {len(failed)}"
        ]
        if failed:
            report.append(f"❌ Не удалось: {', '.join(failed[:5])}{'...' if len(failed) > 5 else ''}")
        
        await status_msg.edit_text("\n".join(report))

    except Exception as e:
        logger.error(f"КРИТИЧЕСКАЯ ОШИБКА: {e}")
        await status_msg.edit_text("⚠️ Рассылка прервана из-за ошибки")

    return ConversationHandler.END

# --- Все ИИ-команды остаются БЕЗ ИЗМЕНЕНИЙ ---
async def theorem_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (полностью без изменений) ...

async def formula_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (полностью без изменений) ...

async def task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (полностью без изменений) ...

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (полностью без изменений) ...

# ... (остальные функции тоже без изменений) ...

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # Важно: сначала регистрируем обычные команды
    app.add_handler(CommandHandler("debug_id", debug_id))  # Для отладки
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    
    # Затем ConversationHandler
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
    app.add_handler(conv_handler)

    # ИИ-команды
    app.add_handler(CommandHandler("theorem", theorem_command))
    app.add_handler(CommandHandler("formula", formula_command))
    app.add_handler(CommandHandler("task", task_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("list", list_command))

    app.add_error_handler(error_handler)
    logger.info("Бот запущен с исправленной рассылкой")
    app.run_polling()

if __name__ == "__main__":
    main()
