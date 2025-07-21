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
GET_NAME = 0

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
            
            # Сначала сохраняем резервную копию
            if os.path.exists(USER_DATA_FILE):
                os.replace(USER_DATA_FILE, BACKUP_FILE)
            
            # Затем основной файл
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

# --- Обработка медиа ---
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

# --- Команды для учителей ---
async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Доступ только для учителей")
        return
    
    user_data = user_manager.get_all()
    if not user_data:
        await update.message.reply_text("📋 Список учеников пуст")
        return
    
    user_list = "\n".join(
        f"@{data['username']} - {data['full_name']} (ID: {user_id})"
        for user_id, data in user_data.items()
    )
    await update.message.reply_text(f"📋 Список учеников:\n\n{user_list}")

# --- ИИ-команды (без изменений, полная безопасность) ---
async def ask_ai(prompt: str) -> str:
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
    if not context.args:
        await update.message.reply_text("ℹ️ Пример: /task 2+2")
        return
    
    query = " ".join(context.args)
    await update.message.reply_chat_action("typing")
    response = await ask_ai(f"Реши задачу: '{query}'. Объясни шаги решения на русском языке.")
    await update.message.reply_text(response or "⚠️ Не удалось решить задачу")

async def formula_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("ℹ️ Пример: /formula площадь круга")
        return
    
    query = " ".join(context.args)
    await update.message.reply_chat_action("typing")
    response = await ask_ai(f"Объясни формулу: '{query}'. Приведи математическую запись и примеры.")
    await update.message.reply_text(response or "⚠️ Не удалось обработать запрос")

async def theorem_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("ℹ️ Пример: /theorem Пифагора")
        return
    
    query = " ".join(context.args)
    await update.message.reply_chat_action("typing")
    response = await ask_ai(f"Объясни теорему {query} на русском языке.")
    await update.message.reply_text(response or "⚠️ Не удалось обработать запрос")

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("ℹ️ Пример: /search интегралы")
        return
    
    query = " ".join(context.args)
    await update.message.reply_chat_action("typing")
    response = await ask_ai(f"Дай ответ по запросу: '{query}' на русском языке.")
    await update.message.reply_text(response or "⚠️ Не удалось найти информацию")

# --- Системные команды ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not user_manager.get(user_id):
        await update.message.reply_text("👋 Введите ваше имя и фамилию:")
        return GET_NAME
    await update.message.reply_text("🤖 Используйте /help для списка команд")
    return ConversationHandler.END

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_manager.set(
        user_id,
        update.message.text,
        update.effective_user.username
    )
    await update.message.reply_text("✅ Регистрация завершена! Используйте /help")
    return ConversationHandler.END

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    # Обработка ошибок
    app.add_error_handler(lambda u, c: logger.error(c.error))
    
    # Система автосохранения
    auto_save()
    atexit.register(user_manager.save)
    
    logger.info("Бот запущен с улучшенной системой хранения данных")
    app.run_polling()

if __name__ == "__main__":
    main()
