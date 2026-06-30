import logging

from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

from shared.config import settings
from shared.kafka.functions import Kafkaa

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def handle_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyword = update.message.text.strip()
    if not keyword:
        return

    Kafkaa.send(
        data={
            "keyword": keyword,
            "interval": "30d",
            "platforms": "all",
            "news_sources": "all",
            "force": False
        },
        topic=settings.kafka_topic_keyword,
        bootstrap=settings.kafka_broker,
    )

    await update.message.reply_text(f"Keyword '{keyword}' sedang diproses.")


def main() -> None:
    app = ApplicationBuilder().token(settings.telegram_bot_token).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_keyword))
    logger.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
