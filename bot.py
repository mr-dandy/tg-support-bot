import logging
import os
import psycopg2
from telebot import TeleBot
from telebot.types import Message
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Загружаем переменные из .env (для локального запуска)
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Токен бота и другие переменные из окружения
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не установлен в переменных окружения")

# ID администраторов (список через запятую)
ADMIN_IDS_STR = os.getenv('ADMIN_IDS', '')
ADMIN_IDS = [int(admin_id.strip()) for admin_id in ADMIN_IDS_STR.split(
    ',') if admin_id.strip().isdigit()]
if not ADMIN_IDS:
    raise ValueError("ADMIN_IDS не установлен или пустой")

# Параметры подключения к PostgreSQL
DB_HOST = os.getenv('DB_HOST')
DB_PORT = os.getenv('DB_PORT')
DB_NAME = os.getenv('DB_NAME')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')

# Проверка наличия параметров БД
if not all([DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD]):
    raise ValueError(
        "Не все параметры PostgreSQL установлены в переменных окружения")

bot = TeleBot(BOT_TOKEN)

# Инициализация БД с ретраями


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type(psycopg2.OperationalError)
)
def init_db():
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            has_shown_suggestion BOOLEAN DEFAULT FALSE
        )
    ''')
    conn.commit()
    conn.close()


init_db()

# Функции для работы с БД


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=5),
    retry=retry_if_exception_type(psycopg2.OperationalError)
)
def has_shown_suggestion(user_id: int) -> bool:
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    cursor = conn.cursor()
    cursor.execute(
        'SELECT has_shown_suggestion FROM users WHERE user_id = %s', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else False


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=5),
    retry=retry_if_exception_type(psycopg2.OperationalError)
)
def set_has_shown_suggestion(user_id: int, value: bool):
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO users (user_id, has_shown_suggestion)
        VALUES (%s, %s)
        ON CONFLICT (user_id) DO UPDATE
        SET has_shown_suggestion = EXCLUDED.has_shown_suggestion
    ''', (user_id, value))
    conn.commit()
    conn.close()


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
        if not has_shown_suggestion(user_id):
            bot.reply_to(
                message, "Пожалуйста, используйте /start для начала взаимодействия.")
            set_has_shown_suggestion(user_id, True)
        # После первого сообщения вне поддержки игнорируем дальнейшие, не повторяя предложение


if __name__ == '__main__':
    logging.info("Бот запущен...")
    bot.infinity_polling(none_stop=True)
