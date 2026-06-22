import json
import logging

from shared.kafka import Kafkaa

from shared.config import settings
from sources.registry import get_all_sources
from icecream import ic

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def process_job(keyword: str) -> None:
    for name, SourceClass in get_all_sources().items():
        try:
            plugin = SourceClass()
            results = plugin.process(keyword)
            if results:
                # db["raw_documents"].insert_many(results)
                logger.info("Stored %d docs from '%s' for keyword '%s'", len(results), name, keyword)
        except Exception:
            logger.exception("Source '%s' failed for keyword '%s'", name, keyword)


def main() -> None:
    logger.info("Worker starting — broker: %s, topic: %s", settings.kafka_broker, settings.kafka_topic_keyword)
    
    for msg in Kafkaa.consume(
        topic=settings.kafka_topic_keyword,
        bootstrap=settings.kafka_broker,
        beginning=True,
        group_id="%s-v%s" % (
            settings.kafka_topic_keyword,
            settings.kafka_project_version
        )
    ):
        try:
            keyword = msg["keyword"]
        except (json.JSONDecodeError, KeyError):
            logger.warning("Skipping malformed job: %s", msg.value())
            continue

        logger.info("Processing job — keyword: '%s'", keyword)
        # process_job(keyword)



if __name__ == "__main__":
    main()
