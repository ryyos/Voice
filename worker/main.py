import asyncio
import logging
import threading

from shared.kafka import Kafkaa
from shared.config import settings
from sources.registry import get_all_sources

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def run_source(name: str, SourceClass, msg: dict) -> None:
    try:
        plugin = SourceClass()
        results = await plugin.process(msg)
        if results:
            logger.info("Stored docs from '%s' for keyword '%s'", name, msg.get("keyword"))
    except Exception:
        logger.exception("Source '%s' failed for keyword '%s'", name, msg.get("keyword"))


async def process_job(msg: dict) -> None:
    await asyncio.gather(*[
        run_source(name, SourceClass, msg)
        for name, SourceClass in get_all_sources().items()
    ])


async def main() -> None:
    logger.info("Worker starting — broker: %s, topic: %s", settings.kafka_broker, settings.kafka_topic_keyword)

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def kafka_thread() -> None:
        for msg in Kafkaa.consume(
            topic=settings.kafka_topic_keyword,
            bootstrap=settings.kafka_broker,
            beginning=True,
            group_id="%s-v%s" % (settings.kafka_topic_keyword, settings.kafka_project_version)
        ):
            asyncio.run_coroutine_threadsafe(queue.put(msg), loop)

    threading.Thread(target=kafka_thread, daemon=True).start()

    while True:
        msg = await queue.get()

        try:
            keyword = msg["keyword"]
        except (KeyError, TypeError):
            logger.warning("Skipping malformed job: %s", msg)
            continue

        logger.info("Processing job — keyword: '%s'", keyword)
        asyncio.create_task(process_job(msg))


if __name__ == "__main__":
    asyncio.run(main())
