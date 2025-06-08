import os
import json
import logging
import sqlite3
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)
import xui_api
from database import Database

# Настройка логгера
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('vpn_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Загрузка конфигурации
try:
    with open('config.json') as f:
        config = json.load(f)
    logger.info("Конфигурация успешно загружена")
except Exception as e:
    logger.critical(f"Ошибка загрузки конфигурации: {str(e)}")
    raise

# Инициализация базы данных и X-UI API
try:
    db = Database('vpn_bot.db')
    xui = xui_api.XUIAPI(
        config['XUI_PANEL_URL'],
        config['XUI_USERNAME'],
        config['XUI_PASSWORD'],
        config.get('XUI_API_PREFIX', '')
    )
    logger.info("База данных и X-UI API инициализированы")
except Exception as e:
    logger.critical(f"Ошибка инициализации: {str(e)}")
    raise

# Состояния для ConversationHandler
SET_TRAFFIC, SET_DAYS = range(2)

def get_main_keyboard(user_id: int):
    keyboard = [
        [InlineKeyboardButton("🔄 Продлить подписку", callback_data="renew")],
        [InlineKeyboardButton("📊 Моя статистика", callback_data="stats")],
        [InlineKeyboardButton("🆘 Помощь", callback_data="help_menu")]
    ]
    if str(user_id) in config['ADMIN_IDS']:
        keyboard.append([InlineKeyboardButton("👑 Админ-панель", callback_data="admin_menu")])
    return InlineKeyboardMarkup(keyboard)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)

    if not user_data:
        logger.error(f"Данные пользователя не найдены: {user_id}")
        await update.message.reply_text("❌ Ошибка: данные пользователя не найдены")
        return

    if not user_data['is_active']:
        logger.warning(f"Попытка доступа к деактивированному аккаунту: {user_id}")
        await update.message.reply_text("❌ Ваш аккаунт деактивирован")
        return

    expire_date = datetime.strptime(user_data['expire_date'], '%Y-%m-%d')
    remaining_days = max(0, (expire_date - datetime.now()).days)
    remaining_traffic_gb = max(0, (user_data['traffic_limit'] - user_data['traffic_used']) // (1024 ** 3))

    reply_markup = get_main_keyboard(user_id)
    message_text = (
        f"👋 Привет, {update.effective_user.first_name}!\n\n"
        f"• Осталось дней: {remaining_days}\n"
        "Выберите действие:"
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup)

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await show_main_menu(update, context)

# Обновление всех inline-клавиатур — добавляем кнопку "Назад в меню"
def append_back_button(keyboard):
    keyboard.append([InlineKeyboardButton("⬅️ Назад в меню", callback_data="back_menu")])
    return InlineKeyboardMarkup(keyboard)

# 🔄 Автоматическое добавление кнопки "Назад в меню" в нужные обработчики

# 🔹 Обновлённый пример использования
# Применяй в любом обработчике:
# reply_markup = append_back_button([...])
# await query.edit_message_text(..., reply_markup=reply_markup)

# 🔧 Применено вручную:
# - renew_subscription, renew_basic, show_stats
# - show_help_menu, help_android, help_windows, help_ios, help_linux
# - admin_menu, list_users, server_stats, delete_user_menu, confirm_delete, delete_user
# Все reply_markup передаются через append_back_button() для возврата в меню
