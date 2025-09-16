import os
import logging
from telebot import TeleBot
from telebot.types import Message

# Настройка логирования
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Токен бота из переменной окружения
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не установлен в переменных окружения")

bot = TeleBot(BOT_TOKEN)

# ID администраторов (список через запятую в переменной окружения)
ADMIN_IDS_STR = os.getenv('ADMIN_IDS', '')
ADMIN_IDS = [int(admin_id.strip()) for admin_id in ADMIN_IDS_STR.split(
    ',') if admin_id.strip().isdigit()]
if not ADMIN_IDS:
    raise ValueError("ADMIN_IDS не установлен или пустой")

# Словарь для отслеживания режима поддержки: {user_id: bool}
support_mode = {}


@bot.message_handler(commands=['start'])
def handle_start(message: Message):
    user_id = message.from_user.id
    support_mode[user_id] = True
    welcome_text = "Здравствуйте. Напишите, пожалуйста, подробно одним сообщением какой у вас вопрос. Оператор ответит в течение 10 минут."
    bot.reply_to(message, welcome_text)

# Обработчик текстовых сообщений


@bot.message_handler(content_types=['text'])
def handle_text(message: Message):
    user_id = message.from_user.id
    if user_id in support_mode and support_mode[user_id]:
        # Пользователь в режиме поддержки, пересылаем сообщение администраторам
        for admin_id in ADMIN_IDS:
            bot.forward_message(admin_id, message.chat.id, message.message_id)
        bot.reply_to(
            message, "Ваше сообщение отправлено в поддержку. Ожидайте ответа.")
        support_mode[user_id] = False  # Выходим из режима после отправки
    elif user_id in ADMIN_IDS:
        # Если сообщение от админа и это ответ на сообщение
        if message.reply_to_message and message.reply_to_message.forward_from:
            forwarded_user_id = message.reply_to_message.forward_from.id
            bot.send_message(forwarded_user_id, message.text)
            bot.reply_to(
                message, f"Ответ отправлен пользователю {forwarded_user_id}.")
    else:
        # Обычное сообщение, если не в поддержке и не от админа
        bot.reply_to(
            message, "Пожалуйста, используйте /start для начала взаимодействия.")


if __name__ == '__main__':
    logging.info("Бот запущен...")
    bot.infinity_polling(none_stop=True)
