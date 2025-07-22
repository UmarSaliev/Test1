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
import atexit
from threading import Timer
import copy

# Загрузка переменных окружения
load_dotenv()

# Конфигурация
TOKEN = os.getenv("BOT_TOKEN")
OWNER_IDS = list(map(int, os.getenv("OWNER_IDS", "").split(","))) if os.getenv("OWNER_IDS") else []
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
BOT_USERNAME = "@Tester894bot"
USER_DATA_FILE = "user_data.json"
BACKUP_FILE = "user_data_backup.json"

# Состояния для ConversationHandler
GET_NAME, BROADCAST = range(2)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Улучшенная система хранения данных ---
class UserDataManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.data = cls._load_data()
            cls._instance.lock = False
        return cls._instance
    
    @staticmethod
    def _load_data():
        """Пытаемся загрузить данные из основного или резервного файла"""
        for file_path in [USER_DATA_FILE, BACKUP_FILE]:
            try:
                with open(file_path, 'r') as f:
                    return json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                continue
        return {}
    
    def save(self):
        """Безопасное сохранение с резервной копией"""
        if self.lock or not self.data:
            return
            
        self.lock = True
        try:
            temp_file = f"{USER_DATA_FILE}.tmp"
            with open(temp_file, 'w') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            
            if os.path.exists(USER_DATA_FILE):
                os.replace(USER_DATA_FILE, BACKUP_FILE)
            
            os.replace(temp_file, USER_DATA_FILE)
            
        except Exception as e:
            logger.error(f"Ошибка сохранения данных: {e}")
        finally:
            self.lock = False
    
    def get(self, user_id: str):
        return self.data.get(user_id, {})
    
    def set(self, user_id: str, full_name: str, username: str):
        self.data[user_id] = {
            "full_name": full_name,
            "username": username or "нет_username"
        }
        self.save()
    
    def get_all(self):
        return copy.deepcopy(self.data)

# Инициализация менеджера данных
user_manager = UserDataManager()

# --- Автосохранение каждые 5 минут ---
def auto_save():
    user_manager.save()
    Timer(300, auto_save).start()

# --- Проверка прав ---
async def is_owner(user_id: int) -> bool:
    return user_id in OWNER_IDS

# --- Рассылка сообщений ---
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало рассылки (только для учителей)"""
    if not await is_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Доступ только для учителей")
        return
    
    await update.message.reply_text(
        "📢 Введите сообщение для рассылки (текст или фото с подписью):\n"
        "Для отмены используйте /cancel"
    )
    return BROADCAST

async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка рассылки"""
    user_data = user_manager.get_all()
    if not user_data:
        await update.message.reply_text("❌ Нет пользователей для рассылки")
        return ConversationHandler.END
    
    successful = 0
    failed = []
    
    try:
        # Рассылка текста
        if update.message.text:
            for user_id in user_data:
                try:
                    await context.bot.send_message(
                        chat_id=int(user_id),
                        text=f"📢 Сообщение от учителя:\n\n{update.message.text}"
                    )
                    successful += 1
                except Exception as e:
                    failed.append(user_id)
                    logger.error(f"Ошибка отправки для {user_id}: {e}")
        
        # Рассылка фото
        elif update.message.photo:
            photo = update.message.photo[-1].file_id
            caption = update.message.caption or ""
            for user_id in user_data:
                try:
                    await context.bot.send_photo(
                        chat_id=int(user_id),
                        photo=photo,
                        caption=f"📢 {caption}" if caption else "📢 Сообщение от учителя"
                    )
                    successful += 1
                except Exception as e:
                    failed.append(user_id)
                    logger.error(f"Ошибка отправки фото для {user_id}: {e}")
        
        # Отчет
        report = f"✅ Рассылка завершена:\nОтправлено: {successful}\nНе удалось: {len(failed)}"
        if failed:
            report += f"\n\nОшибки у ID: {', '.join(failed[:5])}{'...' if len(failed) > 5 else ''}"
        
        await update.message.reply_text(report)
    
    except Exception as e:
        logger.error(f"Ошибка рассылки: {e}")
        await update.message.reply_text("⚠️ Произошла ошибка при рассылке")
    
    return ConversationHandler.END

async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена рассылки"""
    await update.message.reply_text("❌ Рассылка отменена")
    return ConversationHandler.END

# --- Обработка медиа от учеников ---
async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo and update.message.caption:
        user_id = str(update.effective_user.id)
        user_info = user_manager.get(user_id)
        
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

# [Остальные функции (list_command, ask_ai, task_command и т.д.) остаются БЕЗ ИЗМЕНЕНИЙ]
# ... (вставьте сюда все функции из вашего исходного кода, кроме handle_media) ...

# --- Обновленная help-команда ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📚 Доступные команды:\n"
        "/task - Решить задачу\n"
        "/formula - Объяснить формулу\n"
        "/theorem - Объяснить теорему\n"
        "/search - Найти информацию\n"
    )
    
    if await is_owner(update.effective_user.id):
        help_text += (
            "\n👨‍🏫 Команды учителя:\n"
            "/list - Список учеников\n"
            "/broadcast - Рассылка сообщений"
        )
    
    await update.message.reply_text(help_text)

# --- Запуск бота ---
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # Обработчики
    app.add_handler(MessageHandler(filters.PHOTO & filters.CAPTION, handle_media))
    
    # ConversationHandler для рассылки
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("broadcast", broadcast_command)],
        states={
            BROADCAST: [
                MessageHandler(filters.TEXT | filters.PHOTO, handle_broadcast),
                CommandHandler("cancel", cancel_broadcast)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_broadcast)]
    ))
    
    # ConversationHandler для регистрации
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

    # Обработка ошибок
    app.add_error_handler(lambda u, c: logger.error(c.error))
    
    # Система автосохранения
    auto_save()
    atexit.register(user_manager.save)
    
    logger.info("Бот запущен с функцией рассылки")
    app.run_polling()

if __name__ == "__main__":
    main()
