# bot_complete.py
import logging
import os
import json
import random
import time
import datetime
import aiohttp
import asyncio
import copy
from io import BytesIO

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler,
    CallbackQueryHandler,
    PreCheckoutQueryHandler
)
from dotenv import load_dotenv
import atexit
from threading import Timer, Thread
from flask import Flask
import requests

# -------------- Load env ----------------
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
OWNER_IDS = list(map(int, os.getenv("OWNER_IDS", "").split(","))) if os.getenv("OWNER_IDS") else []
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
BOT_USERNAME = os.getenv("BOT_USERNAME", "@Tester894bot")
USER_DATA_FILE = "user_data.json"
BACKUP_FILE = "user_data_backup.json"
TELEGRAM_PAYMENT_PROVIDER_TOKEN = os.getenv("TELEGRAM_PAYMENT_PROVIDER_TOKEN")  # Optional
OCR_API_KEY = os.getenv("OCR_API_KEY")  # Optional: OCR.space key
OWNER_PAYMENT_DETAILS = os.getenv("OWNER_PAYMENT_DETAILS", "Свяжитесь с владельцем для оплаты.")  # For manual payments
FREE_DAILY_LIMIT = int(os.getenv("FREE_DAILY_LIMIT", "5"))

# -------------- Logging ------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# -------------- User data manager (improved) -------------
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
        for file_path in [USER_DATA_FILE, BACKUP_FILE]:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                continue
        return {}

    def save(self):
        if self.lock:
            return
        self.lock = True
        try:
            temp_file = f"{USER_DATA_FILE}.tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            if os.path.exists(USER_DATA_FILE):
                os.replace(USER_DATA_FILE, BACKUP_FILE)
            os.replace(temp_file, USER_DATA_FILE)
        except Exception as e:
            logger.error(f"Ошибка сохранения: {e}")
        finally:
            self.lock = False

    def get(self, user_id: str):
        return self.data.get(user_id, None)

    def ensure_user(self, user_id: str, full_name: str = None, username: str = None):
        if user_id not in self.data:
            self.data[user_id] = {
                "full_name": full_name or "Неизвестный",
                "username": username or "нет_username",
                "subject": None,
                "free_uses_today": 0,
                "last_free_date": "",
                "premium_until": 0,
                "referrer": None,
                "referrals": [],
            }
            self.save()
        else:
            changed = False
            if full_name and self.data[user_id].get("full_name") != full_name:
                self.data[user_id]["full_name"] = full_name
                changed = True
            if username and self.data[user_id].get("username") != username:
                self.data[user_id]["username"] = username
                changed = True
            if changed:
                self.save()

    def set_subject(self, user_id: str, subject: str):
        self.ensure_user(user_id)
        self.data[user_id]["subject"] = subject
        self.save()

    def reset_daily_if_needed(self, user_id: str):
        self.ensure_user(user_id)
        today = datetime.date.today().isoformat()
        if self.data[user_id].get("last_free_date") != today:
            self.data[user_id]["free_uses_today"] = 0
            self.data[user_id]["last_free_date"] = today
            self.save()

    def can_use_free(self, user_id: str) -> bool:
        self.ensure_user(user_id)
        self.reset_daily_if_needed(user_id)
        if self.is_premium(user_id):
            return True
        return self.data[user_id].get("free_uses_today", 0) < FREE_DAILY_LIMIT

    def use_free(self, user_id: str):
        self.ensure_user(user_id)
        self.reset_daily_if_needed(user_id)
        if not self.is_premium(user_id):
            self.data[user_id]["free_uses_today"] = self.data[user_id].get("free_uses_today", 0) + 1
            self.save()

    def add_premium_days(self, user_id: str, days: int):
        self.ensure_user(user_id)
        now = int(time.time())
        current_until = self.data[user_id].get("premium_until", 0)
        if current_until < now:
            new_until = now + days * 86400
        else:
            new_until = current_until + days * 86400
        self.data[user_id]["premium_until"] = new_until
        self.save()

    def is_premium(self, user_id: str) -> bool:
        self.ensure_user(user_id)
        return int(self.data[user_id].get("premium_until", 0)) > int(time.time())

    def get_premium_until_readable(self, user_id: str) -> str:
        ts = self.data.get(user_id, {}).get("premium_until", 0)
        if ts and int(ts) > int(time.time()):
            return datetime.datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M:%S")
        return "Нет"

    def add_referral(self, referrer_id: str, new_user_id: str):
        self.ensure_user(referrer_id)
        self.data[referrer_id].setdefault("referrals", [])
        self.data[referrer_id]["referrals"].append(new_user_id)
        self.save()

    def get_all(self):
        return copy.deepcopy(self.data)

user_manager = UserDataManager()

# -------------- Autosave --------------
def auto_save():
    user_manager.save()
    Timer(300, auto_save).start()

# -------------- Helper/permissions --------------
async def is_owner(user_id: int) -> bool:
    return user_id in OWNER_IDS

# -------------- Subjects & Task bank --------------
SUBJECTS = {
    "math": "Математика",
    "english": "Английский",
    "history": "История",
    "literature": "Литература"
}

# Пример банка задач — расширяй по желанию
TASK_BANK = {
    "math": {
        "algebra": [
            "Решите уравнение: 2x + 5 = 17",
            "Найдите корни квадратного уравнения: x^2 - 5x + 6 = 0"
        ],
        "geometry": [
            "В треугольнике ABC угол A=60°, B=70°. Найдите C.",
            "Найдите площадь круга радиуса 5."
        ]
    },
    "english": {
        "grammar": [
            "Сделайте предложение в Past Simple: I (to go) to the store yesterday.",
            "Употребите Present Perfect в предложении на тему 'travel'."
        ],
        "vocabulary": [
            "Дай 10 слов по теме 'school' с переводом.",
            "Составь 5 предложений с глаголом 'to improve'."
        ]
    },
    "history": {
        "middle_ages": [
            "Опишите причины начала Столетней войны.",
            "Кто такой Чингисхан? Кратко опишите."
        ]
    },
    "literature": {
        "poetry": [
            "Проанализируй стихотворение (пример): 'Стих' — какие образы в нём используются?",
        ]
    }
}

# -------------- AI (OpenRouter) --------------
async def ask_ai(prompt: str, context_text: str = "") -> str:
    if not OPENROUTER_API_KEY:
        return "⚠️ OpenRouter API key не настроен."
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "openai/gpt-3.5-turbo",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant, a teacher."},
            {"role": "user", "content": f"{context_text}\n\n{prompt}"}
        ]
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=30) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"].strip()
                else:
                    text = await resp.text()
                    logger.error(f"OpenRouter error {resp.status}: {text}")
                    return "⚠️ Ошибка при обращении к ИИ."
    except Exception as e:
        logger.error(f"ask_ai exception: {e}")
        return "⚠️ Не удалось связаться с ИИ."

# -------------- OCR (optional, OCR.space) --------------
async def ocr_from_bytes(file_bytes: bytes) -> str | None:
    if not OCR_API_KEY:
        return None
    url = "https://api.ocr.space/parse/image"
    data = {
        "apikey": OCR_API_KEY,
        "language": "rus",
        "isOverlayRequired": False
    }
    files = {
        'file': ('image.jpg', file_bytes)
    }
    try:
        # Using requests because OCR.space doesn't need async; it's okay here
        resp = requests.post(url, data=data, files=files, timeout=30)
        if resp.status_code == 200:
            result = resp.json()
            if result.get("IsErroredOnProcessing"):
                logger.error(f"OCR error: {result}")
                return None
            parsed = result.get("ParsedResults", [])
            text = "\n".join([p.get("ParsedText", "") for p in parsed])
            return text.strip()
        else:
            logger.error(f"OCR request failed {resp.status_code}")
            return None
    except Exception as e:
        logger.error(f"OCR exception: {e}")
        return None

# -------------- Registration & start --------------
GET_NAME = range(1)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    args = context.args or []
    # Referral support: /start <referrer_id>
    if args:
        ref = args[0]
        try:
            ref_id = str(int(ref))
            if ref_id != user_id:
                user_manager.ensure_user(ref_id)
                user_manager.add_referral(ref_id, user_id)
                # set referrer for new user
                user_manager.ensure_user(user_id, user.full_name, user.username)
                user_manager.data[user_id]["referrer"] = ref_id
                user_manager.save()
        except Exception:
            pass

    user_manager.ensure_user(user_id, user.full_name, user.username)

    # If already registered, welcome back
    if user_manager.get(user_id):
        await update.message.reply_text(
            f"👋 С возвращением, {user.full_name}!\n"
            "Используйте /help для списка команд"
        )
        return ConversationHandler.END

    # else ask name (this branch rarely used because ensure_user created one)
    await update.message.reply_text(
        "👋 Добро пожаловать! Я - бот для помощи в учебе.\n"
        "Пожалуйста, введите ваше полное имя (как в школе):"
    )
    return ConversationHandler.END

# -------------- Help --------------
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    help_text = (
        "📚 Доступные команды:\n"
        "/start - Начать работу с ботом\n"
        "/subject - Выбрать предмет (Math, English, History, Literature)\n"
        "/gettask - Получить задание по теме (интерактивно)\n"
        "/task - Решить задачу (текстом)\n"
        "/formula - Объяснить формулу\n"
        "/theorem - Объяснить теорему\n"
        "/search - Поиск информации\n"
        "/status - Статус подписки/лимитов\n"
        "/buy - Купить премиум (если есть провайдер — оплата в Telegram, иначе ручная инструкция)\n"
    )
    if await is_owner(user.id):
        help_text += (
            "\n👨‍🏫 Команды учителя:\n"
            "/list - Список учеников\n"
            "/broadcast - Рассылка сообщений\n"
            "/grant <user_id> <days> - Выдать премиум пользователю вручную\n"
        )
    await update.message.reply_text(help_text)

# -------------- List / broadcast (kept) --------------
BROADCAST = range(1)

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Доступ только для учителей")
        return ConversationHandler.END
    await update.message.reply_text(
        "📢 Введите сообщение для рассылки (текст или фото с подписью):\n"
        "Для отмены используйте /cancel"
    )
    return BROADCAST

async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = user_manager.get_all()
    if not user_data:
        await update.message.reply_text("❌ Нет пользователей для рассылки")
        return ConversationHandler.END

    successful = 0
    failed = []
    try:
        if update.message.text:
            for user_id in user_data:
                try:
                    await context.bot.send_message(chat_id=int(user_id), text=f"📢 Сообщение от учителя:\n\n{update.message.text}")
                    successful += 1
                except Exception as e:
                    failed.append(user_id)
                    logger.error(f"Ошибка отправки для {user_id}: {e}")
        elif update.message.photo:
            photo = update.message.photo[-1].file_id
            caption = update.message.caption or ""
            for user_id in user_data:
                try:
                    await context.bot.send_photo(chat_id=int(user_id), photo=photo, caption=f"📢 {caption}" if caption else "📢 Сообщение от учителя")
                    successful += 1
                except Exception as e:
                    failed.append(user_id)
                    logger.error(f"Ошибка отправки фото для {user_id}: {e}")
        report = f"✅ Рассылка завершена:\nОтправлено: {successful}\nНе удалось: {len(failed)}"
        if failed:
            report += f"\n\nОшибки у ID: {', '.join(failed[:5])}{'...' if len(failed) > 5 else ''}"
        await update.message.reply_text(report)
    except Exception as e:
        logger.error(f"Ошибка рассылки: {e}")
        await update.message.reply_text("⚠️ Произошла ошибка при рассылке")
    return ConversationHandler.END

async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Рассылка отменена")
    return ConversationHandler.END

# -------------- List_command --------------
async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Доступ только для учителей")
        return
    user_data = user_manager.get_all()
    if not user_data:
        await update.message.reply_text("❌ Нет зарегистрированных пользователей")
        return
    message = ["📝 Список пользователей:"]
    for uid, d in user_data.items():
        message.append(f"👤 {d.get('full_name', 'Неизвестный')} (@{d.get('username','нет_username')}) ID: {uid}")
    full_message = "\n".join(message)
    for i in range(0, len(full_message), 4096):
        await update.message.reply_text(full_message[i:i+4096])

# -------------- Status & Grant (premium) --------------
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    user_manager.ensure_user(uid, user.full_name, user.username)
    premium = user_manager.is_premium(uid)
    until = user_manager.get_premium_until_readable(uid)
    user_manager.reset_daily_if_needed(uid)
    free_left = max(0, FREE_DAILY_LIMIT - user_manager.data[uid].get("free_uses_today", 0))
    await update.message.reply_text(
        f"👤 {user.full_name}\n"
        f"Премиум: {'Да' if premium else 'Нет'}\n"
        f"Премиум до: {until}\n"
        f"Бесплатных решений сегодня осталось: {free_left}/{FREE_DAILY_LIMIT}\n"
    )

async def grant_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Только владелец может выдать премиум")
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Использование: /grant <user_id> <days>")
        return
    user_id = args[0]
    try:
        days = int(args[1])
    except:
        await update.message.reply_text("Некорректное число дней")
        return
    user_manager.add_premium_days(user_id, days)
    await update.message.reply_text(f"✅ Выдал премиум пользователю {user_id} на {days} дней")

# -------------- Payments: /buy (telegram or manual) --------------
async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    price_rub = int(os.getenv("PREMIUM_PRICE_RUB", "199"))  # пример: 199 руб
    if TELEGRAM_PAYMENT_PROVIDER_TOKEN:
        # Use Telegram Payments
        title = "Premium подписка"
        description = f"Премиум на 30 дней. Цена {price_rub} RUB"
        payload = f"premium_30_{uid}"
        provider_token = TELEGRAM_PAYMENT_PROVIDER_TOKEN
        currency = os.getenv("PAYMENT_CURRENCY", "RUB")
        # price must be integer of smallest currency unit? For telegram LabeledPrice expects amount in the smallest unit.
        # LabeledPrice(amount) where amount is integer in **cents**? For RUB - kopecks. For safety, using integer *100
        amount = price_rub * 100
        prices = [LabeledPrice("Premium 30 дней", amount)]
        try:
            await context.bot.send_invoice(
                chat_id=user.id,
                title=title,
                description=description,
                payload=payload,
                provider_token=provider_token,
                currency=currency,
                prices=prices,
                start_parameter="buy_premium"
            )
        except Exception as e:
            logger.error(f"send_invoice error: {e}")
            await update.message.reply_text("⚠️ Не удалось отправить счет. Проверьте настройки платежного провайдера.")
    else:
        # Manual flow
        await update.message.reply_text(
            "⚠️ Telegram Payments не настроены.\n\n"
            "Инструкция для ручной оплаты:\n"
            f"{OWNER_PAYMENT_DETAILS}\n\n"
            "Отправьте скриншот оплаты в этот чат, и администратор проверит и выдаст вам премиум.\n\n"
            "После отправки скриншота используйте /confirm_payment чтобы уведомить администратора."
        )
        # set flag in context.user_data so that next photo will be handled as payment screenshot
        context.user_data["awaiting_payment_screenshot"] = True

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Payment via Telegram succeeded
    user = update.effective_user
    uid = str(user.id)
    # Example: we give 30 days premium by default
    PREMIUM_DAYS = int(os.getenv("PREMIUM_DAYS_DEFAULT", "30"))
    user_manager.add_premium_days(uid, PREMIUM_DAYS)
    await update.message.reply_text(f"✅ Оплата получена. Вам выдан премиум на {PREMIUM_DAYS} дней. Спасибо!")

# -------------- Confirm manual payment (for manual flow) --------------
async def confirm_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    # This command not strictly necessary; mainly informs admins to check incoming photo
    await update.message.reply_text("Спасибо — ваш запрос отправлен администраторам. Как только админ подтвердит оплату, вам будет выдан премиум.")
    # Forward to owners a notification
    for owner in OWNER_IDS:
        try:
            await context.bot.send_message(owner, f"Пользователь @{user.username} ({uid}) сообщает о платеже. Проверьте скриншот в чате.")
        except Exception as e:
            logger.error(f"notify owner error: {e}")

# -------------- Command handlers: task / formula / theorem / search (preserve) --------------
async def task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Пожалуйста, укажите задачу после команды /task")
        return
    user = update.effective_user
    uid = str(user.id)
    user_manager.ensure_user(uid, user.full_name, user.username)
    if not user_manager.can_use_free(uid):
        await update.message.reply_text("💳 Вы использовали все бесплатные запросы. Купите премиум через /buy или подождите до завтра.")
        return
    task = " ".join(context.args)
    await update.message.reply_text("🔍 Решаю задачу...")
    prompt = f"Реши эту задачу по шагам: {task}"
    response = await ask_ai(prompt, "Ты опытный преподаватель. Реши задачу подробно с объяснением каждого шага.")
    user_manager.use_free(uid)
    await update.message.reply_text(f"📚 Решение задачи:\n\n{response}")

async def formula_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Пожалуйста, укажите формулу после команды /formula")
        return
    user = update.effective_user
    uid = str(user.id)
    user_manager.ensure_user(uid, user.full_name, user.username)
    if not user_manager.can_use_free(uid):
        await update.message.reply_text("💳 Вы использовали все бесплатные запросы. Купите премиум через /buy или подождите до завтра.")
        return
    formula = " ".join(context.args)
    await update.message.reply_text("🔍 Объясняю формулу...")
    response = await ask_ai(f"Объясни эту формулу: {formula}", "Ты опытный преподаватель. Объясни формулу простым языком с примерами.")
    user_manager.use_free(uid)
    await update.message.reply_text(f"📖 Объяснение формулы:\n\n{response}")

async def theorem_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Пожалуйста, укажите теорему после команды /theorem")
        return
    user = update.effective_user
    uid = str(user.id)
    user_manager.ensure_user(uid, user.full_name, user.username)
    if not user_manager.can_use_free(uid):
        await update.message.reply_text("💳 Вы использовали все бесплатные запросы. Купите премиум через /buy или подождите до завтра.")
        return
    theorem = " ".join(context.args)
    await update.message.reply_text("🔍 Объясняю теорему...")
    response = await ask_ai(f"Объясни эту теорему: {theorem}", "Ты опытный преподаватель. Объясни теорему с доказательством и примерами.")
    user_manager.use_free(uid)
    await update.message.reply_text(f"📖 Объяснение теоремы:\n\n{response}")

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Пожалуйста, укажите запрос после команды /search")
        return
    user = update.effective_user
    uid = str(user.id)
    user_manager.ensure_user(uid, user.full_name, user.username)
    if not user_manager.can_use_free(uid):
        await update.message.reply_text("💳 Вы использовали все бесплатные запросы. Купите премиум через /buy или подождите до завтра.")
        return
    query = " ".join(context.args)
    await update.message.reply_text("🔍 Ищу информацию...")
    response = await ask_ai(f"Найди информацию по запросу: {query}", "Ты опытный преподаватель. Дай развернутый ответ на запрос с примерами.")
    user_manager.use_free(uid)
    await update.message.reply_text(f"🔎 Результаты поиска:\n\n{response}")

# -------------- Subject selection (/subject) --------------
async def subject_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    user_manager.ensure_user(uid, user.full_name, user.username)
    buttons = []
    for key, name in SUBJECTS.items():
        buttons.append([InlineKeyboardButton(name, callback_data=f"subject_{key}")])
    markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("Выберите предмет:", reply_markup=markup)

async def subject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data  # "subject_math"
    if not data.startswith("subject_"):
        return
    key = data.split("_", 1)[1]
    uid = str(query.from_user.id)
    user_manager.set_subject(uid, key)
    await query.edit_message_text(f"✅ Предмет установлен: {SUBJECTS.get(key,'Неизвестно')}\nИспользуйте /gettask чтобы получить задания по теме.")

# -------------- Gettask flow (interactive) --------------
# We'll use callback data "tasksub_<subject>" and "tasktopic_<subject>_<topic>"
async def gettask_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # If user provided args like /gettask math algebra, handle quickly
    args = context.args
    if args and args[0].lower() in SUBJECTS:
        subj = args[0].lower()
        # if topic provided
        if len(args) > 1:
            topic = args[1].lower()
            await send_task_by_subject_topic(update, context, subj, topic)
            return
    # else interactive list subjects
    buttons = []
    for key, name in SUBJECTS.items():
        buttons.append([InlineKeyboardButton(name, callback_data=f"tasksub_{key}")])
    await update.message.reply_text("Выберите предмет для задания:", reply_markup=InlineKeyboardMarkup(buttons))

async def tasksub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data  # tasksub_math
    subj = data.split("_", 1)[1]
    topics = TASK_BANK.get(subj, {}).keys()
    if not topics:
        await q.edit_message_text("К сожалению, для этого предмета нет заданий.")
        return
    buttons = []
    for t in topics:
        buttons.append([InlineKeyboardButton(t, callback_data=f"tasktopic_{subj}_{t}")])
    await q.edit_message_text(f"Выбран предмет: {SUBJECTS.get(subj)}\nВыберите тему:", reply_markup=InlineKeyboardMarkup(buttons))

async def tasktopic_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data  # tasktopic_math_algebra
    _, subj, topic = data.split("_", 2)
    await send_task_by_subject_topic(q, context, subj, topic)

async def send_task_by_subject_topic(trigger, context, subj, topic):
    # trigger can be Update or CallbackQuery; unify
    if isinstance(trigger, Update):
        send_to = trigger.message
        uid = str(trigger.effective_user.id)
    else:
        # CallbackQuery
        send_to = trigger
        uid = str(trigger.from_user.id)

    tasks = TASK_BANK.get(subj, {}).get(topic, [])
    if not tasks:
        await send_to.edit_message_text("Заданий по этой теме не найдено.")
        return

    task = random.choice(tasks)
    # Provide a button to solve task
    buttons = [
        [InlineKeyboardButton("Решить (бот)", callback_data=f"solve_now_{subj}_{topic}")],
        [InlineKeyboardButton("Получить другое задание", callback_data=f"tasktopic_{subj}_{topic}")]
    ]
    text = f"📘 Предмет: {SUBJECTS.get(subj)}\n📚 Тема: {topic}\n\nЗадание:\n{task}"
    if isinstance(send_to, type(trigger)):  # shouldn't happen
        pass
    # If called from callback query:
    try:
        await send_to.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    except Exception:
        # fallback: send new message
        await context.bot.send_message(chat_id=int(uid), text=text, reply_markup=InlineKeyboardMarkup(buttons))

async def solve_now_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, subj, topic = q.data.split("_", 2)
    tasks = TASK_BANK.get(subj, {}).get(topic, [])
    if not tasks:
        await q.edit_message_text("Нет доступных заданий для решения.")
        return
    task = random.choice(tasks)
    await q.edit_message_text(f"🔎 Решаю задание:\n\n{task}")
    uid = str(q.from_user.id)
    if not user_manager.can_use_free(uid):
        await q.edit_message_text("💳 Вы использовали все бесплатные запросы. Купите премиум через /buy.")
        return
    response = await ask_ai(f"Реши по шагам: {task}", f"Предмет: {SUBJECTS.get(subj)}")
    user_manager.use_free(uid)
    await q.message.reply_text(f"✅ Решение:\n\n{response}")

# -------------- Media handler (improved) --------------
async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not update.message.photo:
            return

        user = update.effective_user
        uid = str(user.id)
        user_manager.ensure_user(uid, user.full_name, user.username)

        # If user was in manual payment flow and expects to send payment screenshot
        if context.user_data.get("awaiting_payment_screenshot"):
            # forward to owners and notify
            photo = update.message.photo[-1].file_id
            caption = update.message.caption or ""
            msg = f"💳 Скриншот оплаты от @{user.username} ({uid})\n{caption}"
            for owner in OWNER_IDS:
                try:
                    await context.bot.send_photo(chat_id=owner, photo=photo, caption=msg)
                except Exception as e:
                    logger.error(f"Error forwarding payment screenshot: {e}")
            context.user_data["awaiting_payment_screenshot"] = False
            await update.message.reply_text("✅ Скриншот отправлен администраторам. После проверки вам вручат премиум (через /grant).")
            return

        # Workflow: try OCR if possible -> if recognized text -> ask AI to solve -> else forward to teachers
        photo_file = await update.message.photo[-1].get_file()
        b = BytesIO()
        await photo_file.download_to_memory(out=b)
        file_bytes = b.getvalue()

        ocr_text = None
        if OCR_API_KEY:
            await update.message.reply_text("🔎 Пытаюсь распознать текст на фото...")
            loop = asyncio.get_event_loop()
            # OCR uses blocking requests internally, run in executor
            ocr_text = await loop.run_in_executor(None, ocr_from_bytes, file_bytes)
        if ocr_text:
            await update.message.reply_text("🧾 Текст распознан. Отправляю на решение...")
            # send to AI with subject context if present
            subj_key = user_manager.get(uid).get("subject")
            subj_name = SUBJECTS.get(subj_key, "Не указан") if subj_key else "Не указан"
            prompt = f"Реши задачу по шагам. Предмет: {subj_name}. Задача:\n{ocr_text}"
            if not user_manager.can_use_free(uid):
                await update.message.reply_text("💳 Вы использовали все бесплатные запросы. Купите премиум через /buy.")
                return
            response = await ask_ai(prompt, "Ты опытный преподаватель. Реши подробно с объяснениями.")
            user_manager.use_free(uid)
            await update.message.reply_text(f"📚 Решение:\n\n{response}")
            return
        else:
            # fallback: forward photo to teachers (old behavior)
            user_info = user_manager.get(uid)
            base_caption = f"📩 От ученика {user_info.get('full_name','Неизвестный')}\n@{user_info.get('username','нет_username')}"
            full_caption = base_caption
            if update.message.caption:
                full_caption += f"\n\n{update.message.caption}"
            for teacher_id in OWNER_IDS:
                try:
                    await context.bot.send_photo(chat_id=teacher_id, photo=update.message.photo[-1].file_id, caption=full_caption if full_caption else None)
                except Exception as e:
                    logger.error(f"Ошибка отправки учителю {teacher_id}: {e}")
            await update.message.reply_text("✅ Ваше фото отправлено учителям (распознавание не сработало).")
    except Exception as e:
        logger.error(f"Ошибка handle_media: {e}")
        await update.message.reply_text("⚠️ Произошла ошибка при обработке фото.")

# -------------- Error handler --------------
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")

# -------------- App start (Flask ping kept) --------------
app_flask = Flask(__name__)

@app_flask.route('/')
def flask_home():
    return "Telegram Bot is running!"

def run_flask():
    # Optional auto-ping for Replit; keep original behavior but safe
    if os.environ.get('REPL_SLUG'):
        def safe_ping():
            try:
                delay = random.randint(600, 900)
                time.sleep(delay)
                url = f"https://{os.environ['REPL_SLUG']}.{os.environ['REPL_OWNER']}.repl.co"
                requests.get(url, timeout=5)
            except Exception as e:
                logger.error(f"Ping failed: {e}")
            finally:
                Timer(1, safe_ping).start()
        Timer(60, safe_ping).start()
    app_flask.run(host='0.0.0.0', port=int(os.getenv("PORT", "8080")))

# -------------- Main --------------
def main():
    Thread(target=run_flask, daemon=True).start()

    app = ApplicationBuilder().token(TOKEN).build()

    # Existing handlers
    app.add_handler(MessageHandler(filters.PHOTO, handle_media))

    # Broadcast
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

    # Basic commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("task", task_command))
    app.add_handler(CommandHandler("formula", formula_command))
    app.add_handler(CommandHandler("theorem", theorem_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("grant", grant_command))
    app.add_handler(CommandHandler("buy", buy_command))
    app.add_handler(CommandHandler("confirm_payment", confirm_payment))
    app.add_handler(CommandHandler("subject", subject_command))
    app.add_handler(CommandHandler("gettask", gettask_command))

    # Payment handlers (if using Telegram payments)
    if TELEGRAM_PAYMENT_PROVIDER_TOKEN:
        app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
        app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

    # CallbackQuery handlers for subject selection and tasks
    app.add_handler(CallbackQueryHandler(subject_callback, pattern=r"^subject_"))
    app.add_handler(CallbackQueryHandler(tasksub_callback, pattern=r"^tasksub_"))
    app.add_handler(CallbackQueryHandler(tasktopic_callback, pattern=r"^tasktopic_"))
    app.add_handler(CallbackQueryHandler(solve_now_callback, pattern=r"^solve_now_"))

    # Error handler
    app.add_error_handler(error_handler)

    # Auto-save
    auto_save()
    atexit.register(user_manager.save)

    logger.info("Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
