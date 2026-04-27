import logging
from telegram.ext import Application
from config import TELEGRAM_TOKEN, logger
from database import Database
from handlers import register_handlers


def main():
    db = Database()
    db.init_db()

    application = Application.builder().token(TELEGRAM_TOKEN).build()
    register_handlers(application)

    logger.info("Бот запущен. Ожидание сообщений...")
    application.run_polling(
        drop_pending_updates=True,
        poll_interval=0.0,
        timeout=10,
    )


if __name__ == "__main__":
    main()
