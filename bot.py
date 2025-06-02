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
    ContextTypes
)
import xui_api
from database import Database

# Настройка логгера
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Загрузка конфигурации
with open('config.json') as f:
    config = json.load(f)

# Инициализация базы данных и X-UI API
db = Database('vpn_bot.db')
xui = xui_api.XUIAPI(config['XUI_PANEL_URL'], config['XUI_USERNAME'], config['XUI_PASSWORD'])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    # Проверяем существование пользователя
    if not db.user_exists(user_id):
        # Создаем нового пользователя
        uuid = xui.create_user(
            remark=f"user_{user_id}",
            traffic_gb=config['TRIAL_TRAFFIC_GB'],
            expire_days=config['TRIAL_DAYS']
        )

        db.create_user(
            user_id=user_id,
            username=user.username,
            uuid=uuid,
            traffic_limit=config['TRIAL_TRAFFIC_GB'] * 1024 ** 3,
            expire_date=(datetime.now() + timedelta(days=config['TRIAL_DAYS'])).strftime('%Y-%m-%d')
        )

        await update.message.reply_text(
            "🎉 Добро пожаловать! Вы получили пробный период:\n"
            f"• {config['TRIAL_DAYS']} дней\n"
            f"• {config['TRIAL_TRAFFIC_GB']} ГБ трафика\n\n"
            "Ваша конфигурация генерируется..."
        )

        # Отправляем конфиг
        config_link = xui.generate_config(uuid)
        await update.message.reply_text(
            f"🔑 Ваш конфиг:\n`{config_link}`\n\n"
            "📚 Инструкции по установке: /help",
            parse_mode="Markdown"
        )
    else:
        # Пользователь уже существует
        await show_main_menu(update, context)


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)

    # Рассчитываем оставшиеся дни
    expire_date = datetime.strptime(user_data['expire_date'], '%Y-%m-%d')
    remaining_days = (expire_date - datetime.now()).days
    remaining_days = max(0, remaining_days)

    # Рассчитываем оставшийся трафик
    remaining_traffic_gb = max(0, (user_data['traffic_limit'] - user_data['traffic_used']) // (1024 ** 3))

    keyboard = [
        [InlineKeyboardButton("🔄 Продлить подписку", callback_data="renew")],
        [InlineKeyboardButton("📊 Моя статистика", callback_data="stats")],
        [InlineKeyboardButton("🆘 Помощь", callback_data="help")]
    ]

    # Кнопка администратора, если пользователь - админ
    if str(user_id) in config['ADMIN_IDS']:
        keyboard.append([InlineKeyboardButton("👑 Админ-панель", callback_data="admin_panel")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"👋 Привет, {update.effective_user.first_name}!\n\n"
        f"• Осталось дней: {remaining_days}\n"
        f"• Осталось трафика: {remaining_traffic_gb} ГБ\n\n"
        "Выберите действие:",
        reply_markup=reply_markup
    )


async def renew_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("+30 дней +40 ГБ", callback_data="renew_basic")],
        [InlineKeyboardButton("Назад", callback_data="back")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "🎁 Варианты продления:\n\n"
        "1. Базовый: +30 дней и +40 ГБ трафика\n\n"
        "Выберите опцию:",
        reply_markup=reply_markup
    )


async def renew_basic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_data = db.get_user(user_id)

    # Обновляем дату окончания
    expire_date = datetime.strptime(user_data['expire_date'], '%Y-%m-%d')
    new_expire_date = expire_date + timedelta(days=30)

    # Обновляем лимит трафика
    new_traffic_limit = user_data['traffic_limit'] + 40 * 1024 ** 3

    # Обновляем в базе
    db.update_user(
        user_id=user_id,
        traffic_limit=new_traffic_limit,
        expire_date=new_expire_date.strftime('%Y-%m-%d')
    )

    # Обновляем в X-UI
    xui.update_user(
        uuid=user_data['uuid'],
        traffic_gb=new_traffic_limit // (1024 ** 3),
        expire_days=(new_expire_date - datetime.now()).days
    )

    await query.edit_message_text(
        "✅ Подписка успешно продлена!\n\n"
        f"• Новый срок окончания: {new_expire_date.strftime('%d.%m.%Y')}\n"
        f"• Новый трафик: {new_traffic_limit // (1024 ** 3)} ГБ"
    )


async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_data = db.get_user(user_id)

    expire_date = datetime.strptime(user_data['expire_date'], '%Y-%m-%d')
    remaining_days = (expire_date - datetime.now()).days
    remaining_traffic_gb = (user_data['traffic_limit'] - user_data['traffic_used']) // (1024 ** 3)

    await query.edit_message_text(
        f"📊 Ваша статистика:\n\n"
        f"• Имя пользователя: @{user_data['username']}\n"
        f"• Дата регистрации: {user_data['created_at']}\n"
        f"• Окончание подписки: {expire_date.strftime('%d.%m.%Y')} ({remaining_days} дн.)\n"
        f"• Трафик: {user_data['traffic_used'] // (1024 ** 3)}/{user_data['traffic_limit'] // (1024 ** 3)} ГБ\n"
        f"• Статус: {'Активен' if user_data['is_active'] else 'Заблокирован'}"
    )


async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("📱 Android", callback_data="help_android")],
        [InlineKeyboardButton("💻 Windows", callback_data="help_windows")],
        [InlineKeyboardButton("🍎 iOS", callback_data="help_ios")],
        [InlineKeyboardButton("🐧 Linux/Mac", callback_data="help_linux")],
        [InlineKeyboardButton("Назад", callback_data="back")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "📚 Инструкции по подключению:\n\n"
        "Выберите ваше устройство:",
        reply_markup=reply_markup
    )


async def help_android(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "📱 Инструкция для Android:\n\n"
        "1. Установите приложение Nekobox из Play Market\n"
        "2. Откройте приложение и нажмите ➕ в верхнем правом углу\n"
        "3. Выберите 'Импортировать из буфера обмена'\n"
        "4. Вернитесь в бота и скопируйте ваш конфиг\n"
        "5. Приложение автоматически добавит конфигурацию\n"
        "6. Нажмите на переключатель для подключения\n\n"
        "Готово! Ваше соединение защищено."
    )


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    if str(user_id) not in config['ADMIN_IDS']:
        await query.edit_message_text("⛔ У вас нет прав доступа!")
        return

    keyboard = [
        [InlineKeyboardButton("👥 Список пользователей", callback_data="list_users")],
        [InlineKeyboardButton("📊 Статистика сервера", callback_data="server_stats")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "⚙️ Панель администратора:",
        reply_markup=reply_markup
    )


async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    users = db.get_all_users()
    if not users:
        await query.edit_message_text("❌ Пользователи не найдены")
        return

    message = "👥 Список пользователей:\n\n"
    for user in users[:10]:  # Первые 10 пользователей
        expire_date = datetime.strptime(user['expire_date'], '%Y-%m-%d')
        remaining_days = (expire_date - datetime.now()).days
        message += f"• @{user['username']} | 🕒 {remaining_days}д | 📊 {user['traffic_used'] // 1024 ** 3}/{user['traffic_limit'] // 1024 ** 3}ГБ\n"

    await query.edit_message_text(message)


async def server_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Получаем статистику сервера (заглушка)
    stats = xui.get_server_stats()

    await query.edit_message_text(
        f"📊 Статистика сервера:\n\n"
        f"• Пользователей: {len(db.get_all_users())}\n"
        f"• Загрузка CPU: {stats['cpu']}%\n"
        f"• Использовано RAM: {stats['ram']}%\n"
        f"• Трафик: ↑{stats['upload']}GB ↓{stats['download']}GB"
    )


async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await show_main_menu(update, context)


def main():
    # Создаем приложение
    application = ApplicationBuilder().token(config['BOT_TOKEN']).build()

    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", show_help))
    application.add_handler(CommandHandler("admin", admin_panel))

    # Обработчики callback-запросов
    application.add_handler(CallbackQueryHandler(renew_subscription, pattern="^renew$"))
    application.add_handler(CallbackQueryHandler(renew_basic, pattern="^renew_basic$"))
    application.add_handler(CallbackQueryHandler(show_stats, pattern="^stats$"))
    application.add_handler(CallbackQueryHandler(show_help, pattern="^help$"))
    application.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    application.add_handler(CallbackQueryHandler(list_users, pattern="^list_users$"))
    application.add_handler(CallbackQueryHandler(server_stats, pattern="^server_stats$"))
    application.add_handler(CallbackQueryHandler(help_android, pattern="^help_android$"))
    application.add_handler(CallbackQueryHandler(back_to_menu, pattern="^back$"))

    # Запускаем бота
    application.run_polling()


if __name__ == '__main__':
    main()