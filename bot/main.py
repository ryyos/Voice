import logging

from telegram.ext import ApplicationBuilder

from shared.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    app = ApplicationBuilder().token(settings.telegram_bot_token).build()
    # TODO: register handlers
    logger.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
