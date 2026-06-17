import logging

from shared.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("Worker starting — broker: %s, topic: %s", settings.kafka_broker, settings.kafka_topic_jobs)
    # TODO: consume search_jobs from Kafka, dispatch to registered source plugins,
    #       store raw documents in MongoDB
    raise NotImplementedError


if __name__ == "__main__":
    main()
