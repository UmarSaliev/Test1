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

# ... (остальные импорты и настройки остаются БЕЗ ИЗМЕНЕНИЙ до функции broadcast_message) ...

async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Улучшенная версия рассылки с защитой от конфликтов"""
    if not user_data:
        await update.message.reply_text("❌ Нет пользователей для рассылки")
        return ConversationHandler.END

    # Уведомление о начале рассылки
    status_msg = await update.message.reply_text("🔄 Начинаю рассылку...")

    successful = 0
    failed_users = []
    total = len(user_data)

    try:
        # Для текстовых сообщений
        if update.message.text:
            for user_id_str, user_info in user_data.items():
                try:
                    await context.bot.send_message(
                        chat_id=int(user_id_str),
                        text=f"📢 Сообщение от учителя:\n\n{update.message.text}"
                    )
                    successful += 1
                except Exception as e:
                    failed_users.append(user_id_str)
                    logger.warning(f"Не удалось отправить {user_id_str}: {str(e)}")

        # Для фото с подписью
        elif update.message.photo:
            photo = update.message.photo[-1].file_id
            caption = update.message.caption or ""
            for user_id_str, user_info in user_data.items():
                try:
                    await context.bot.send_photo(
                        chat_id=int(user_id_str),
                        photo=photo,
                        caption=f"📢 От учителя:\n\n{caption}" if caption else "📢 Сообщение"
                    )
                    successful += 1
                except Exception as e:
                    failed_users.append(user_id_str)
                    logger.warning(f"Не удалось отправить фото {user_id_str}: {str(e)}")

        # Формируем отчет
        report = [
            f"📊 Результат рассылки:",
            f"• Всего получателей: {total}",
            f"• Успешно: {successful}",
            f"• Не удалось: {len(failed_users)}"
        ]
        
        if failed_users:
            report.append("\n❌ Ошибки у ID: " + ", ".join(failed_users[:10]) + ("..." if len(failed_users) > 10 else ""))
        
        await status_msg.edit_text("\n".join(report))

    except Exception as e:
        logger.error(f"FATAL BROADCAST ERROR: {str(e)}")
        await status_msg.edit_text("⚠️ Критическая ошибка при рассылке")

    return ConversationHandler.END

# ... (ВСЕ остальные функции и main() остаются БЕЗ ИЗМЕНЕНИЙ!) ...
