import asyncio
import threading

from shared.kafka import Kafkaa
from shared.config import settings
from shared.utils import log
from shared.utils.monitor import ProcessMonitor
from sources.registry import get_all_sources


async def run_source(name: str, SourceClass, msg: dict, monitor: ProcessMonitor) -> None:
    try:
        plugin = SourceClass()
        saved = await plugin.process(msg, monitor)
        log.info("Done — source '%s', keyword '%s', saved %d docs", name, msg.get("keyword"), saved)
    except Exception:
        log.exception("Source '%s' failed for keyword '%s'", name, msg.get("keyword"))


async def process_job(msg: dict) -> None:
    with ProcessMonitor(split=settings.log_split) as monitor:
        await asyncio.gather(*[
            run_source(name, SourceClass, msg, monitor)
            for name, SourceClass in get_all_sources().items()
        ])


async def main() -> None:
    log.info("Worker starting — broker: %s, topic: %s", settings.kafka_broker, settings.kafka_topic_keyword)

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def kafka_thread() -> None:
        for msg in Kafkaa.consume(
            topic=settings.kafka_topic_keyword,
            bootstrap=settings.kafka_broker,
            beginning=True,
            group_id="%s-v%s" % (settings.kafka_topic_keyword, settings.kafka_project_version),
        ):
            asyncio.run_coroutine_threadsafe(queue.put(msg), loop)

    threading.Thread(target=kafka_thread, daemon=True).start()

    while True:
        msg = await queue.get()

        try:
            keyword = msg["keyword"]
        except (KeyError, TypeError):
            log.warning("Skipping malformed job: %s", msg)
            continue

        log.info("Processing job — keyword: '%s'", keyword)
        asyncio.create_task(process_job(msg))


if __name__ == "__main__":
    asyncio.run(main())
