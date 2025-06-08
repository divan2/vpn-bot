import os
import json
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)
import xui_api
from database import Database

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

def get_main_keyboard(user_id: int):
    keyboard = [
        [InlineKeyboardButton("🔄 Продлить подписку", callback_data="renew")],
        [InlineKeyboardButton("📊 Моя статистика", callback_data="stats")],
        [InlineKeyboardButton("🆘 Помощь", callback_data="help_menu")]
    ]
    if str(user_id) in config['ADMIN_IDS']:
        keyboard.append([InlineKeyboardButton("👑 Админ-панель", callback_data="admin_menu")])
    return InlineKeyboardMarkup(keyboard)

def append_back_button(keyboard):
    keyboard.append([InlineKeyboardButton("⬅️ Назад в меню", callback_data="back_menu")])
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    logger.info(f"Команда /start от пользователя {user_id}")

    if not db.user_exists(user_id):
        if not xui.check_connection():
            await update.message.reply_text("❌ Ошибка подключения к серверу VPN")
            return

        result = xui.create_user(
            remark=f"user_{user_id}",
            traffic_gb=config['TRIAL_TRAFFIC_GB'],
            expire_days=config['TRIAL_DAYS']
        )

        if not result:
            await update.message.reply_text("❌ Ошибка при создании VPN-профиля")
            return

        uuid, port = result
        db.create_user(
            user_id=user_id,
            username=user.username,
            uuid=uuid,
            traffic_limit=config['TRIAL_TRAFFIC_GB'] * 1024 ** 3,
            expire_date=(datetime.now() + timedelta(days=config['TRIAL_DAYS'])).strftime('%Y-%m-%d')
        )
        config_link = xui.generate_config(uuid, port)
        await update.message.reply_text(
            f"🎉 Ваш VPN-доступ активирован!

"
            f"🔑 Конфигурация:
<code>{config_link}</code>",
            parse_mode="HTML"
        )
    await show_main_menu(update, context)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)
    if not user_data:
        await update.message.reply_text("❌ Данные не найдены")
        return
    if not user_data['is_active']:
        await update.message.reply_text("❌ Аккаунт деактивирован")
        return

    expire_date = datetime.strptime(user_data['expire_date'], '%Y-%m-%d')
    remaining_days = max(0, (expire_date - datetime.now()).days)
    remaining_traffic_gb = max(0, (user_data['traffic_limit'] - user_data['traffic_used']) // (1024 ** 3))

    keyboard = get_main_keyboard(user_id)
    text = (
        f"👋 Привет, {update.effective_user.first_name}!

"
        f"• Осталось дней: {remaining_days}
"
        f"• Осталось трафика: {remaining_traffic_gb} ГБ

"
        "Выберите действие:"
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard)
    else:
        await update.message.reply_text(text, reply_markup=keyboard)

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await show_main_menu(update, context)

async def renew(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("+30 дней +40 ГБ", callback_data="renew_basic")]
    ]
    reply_markup = append_back_button(keyboard)
    await query.edit_message_text("🎁 Продление подписки:

Выберите вариант:", reply_markup=reply_markup)

async def renew_basic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_data = db.get_user(user_id)
    if not user_data:
        await query.edit_message_text("❌ Пользователь не найден")
        return

    expire_date = datetime.strptime(user_data['expire_date'], '%Y-%m-%d')
    new_expire = expire_date + timedelta(days=30)
    new_traffic = user_data['traffic_limit'] + 40 * 1024**3
    db.update_user(user_id, traffic_limit=new_traffic, expire_date=new_expire.strftime('%Y-%m-%d'))
    xui.update_user(uuid=user_data['uuid'], traffic_gb=new_traffic // (1024**3), expire_days=30)

    await query.edit_message_text(
        f"✅ Подписка продлена!

"
        f"📅 До: {new_expire.strftime('%d.%m.%Y')}
"
        f"📶 Трафик: {new_traffic // (1024**3)} ГБ"
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_data = db.get_user(user_id)
    if not user_data:
        await query.edit_message_text("❌ Пользователь не найден")
        return

    expire_date = datetime.strptime(user_data['expire_date'], '%Y-%m-%d')
    remaining_days = (expire_date - datetime.now()).days
    traffic_used = user_data['traffic_used'] // (1024 ** 3)
    traffic_limit = user_data['traffic_limit'] // (1024 ** 3)

    await query.edit_message_text(
        f"📊 Ваша статистика:

"
        f"🆔 @{user_data['username']}
"
        f"📅 До: {expire_date.strftime('%d.%m.%Y')} ({remaining_days} дн.)
"
        f"📶 Трафик: {traffic_used}/{traffic_limit} ГБ"
    )

def main():
    application = ApplicationBuilder().token(config['BOT_TOKEN']).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(back_to_menu, pattern="^back_menu$"))
    application.add_handler(CallbackQueryHandler(renew, pattern="^renew$"))
    application.add_handler(CallbackQueryHandler(renew_basic, pattern="^renew_basic$"))
    application.add_handler(CallbackQueryHandler(stats, pattern="^stats$"))
    logger.info("Бот запущен")
    application.run_polling()

if __name__ == '__main__':
    main()