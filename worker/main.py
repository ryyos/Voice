import json
import logging

from confluent_kafka import Consumer, KafkaException

from shared.config import settings
from shared.db import get_mongo_db
from sources.registry import get_all_sources

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def process_job(keyword: str) -> None:
    db = get_mongo_db()

    for name, SourceClass in get_all_sources().items():
        try:
            plugin = SourceClass()
            results = plugin.fetch(keyword)
            if results:
                db["raw_documents"].insert_many(results)
                logger.info("Stored %d docs from '%s' for keyword '%s'", len(results), name, keyword)
        except Exception:
            logger.exception("Source '%s' failed for keyword '%s'", name, keyword)


def main() -> None:
    logger.info("Worker starting — broker: %s, topic: %s", settings.kafka_broker, settings.kafka_topic_jobs)

    consumer = Consumer({
        "bootstrap.servers": settings.kafka_broker,
        "group.id": "voice-worker",
        "auto.offset.reset": "earliest",
    })
    consumer.subscribe([settings.kafka_topic_jobs])

    try:
        while True:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                raise KafkaException(msg.error())

            try:
                job = json.loads(msg.value().decode("utf-8"))
                keyword = job["keyword"]
            except (json.JSONDecodeError, KeyError):
                logger.warning("Skipping malformed job: %s", msg.value())
                continue

            logger.info("Processing job — keyword: '%s'", keyword)
            process_job(keyword)
    finally:
        consumer.close()


if __name__ == "__main__":
    main()
