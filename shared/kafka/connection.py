import os
import json

from shared.config import settings
from icecream import ic
from loguru import logger
from kafka import KafkaProducer, KafkaConsumer

class ConnectionKafkaProducer:
    def __init__(self, bootstrap: str) -> KafkaProducer:
        for i in range(10):
            try:
                _bootstrap: str = settings.kafka_broker
                self.kafka_produser = KafkaProducer(bootstrap_servers=_bootstrap)
                
                if self.kafka_produser:
                    break
            except Exception as err:
                logger.warning(f"[ {i} ] - [ create connection kafka failed, try again ] [ {str(err)} ]")
                ...
        ...

class ConnectionKafkaConsumer:
    def __init__(
        self,
        bootstrap: str,
        topic: str,
        group_id: str,
        auto_offset_reset: str = "earliest"
    ) -> KafkaConsumer:

        for i in range(10):
            try:
                _bootstrap: str = settings.kafka_broker

                self.kafka_consumer = KafkaConsumer(
                    topic,
                    bootstrap_servers=_bootstrap,
                    group_id=group_id,
                    auto_offset_reset=auto_offset_reset,
                    enable_auto_commit=False,
                    value_deserializer=lambda v: json.loads(v.decode("utf-8")),
                    max_poll_records=100,
                    max_poll_interval_ms=900000
                )
                
                logger.debug(f"[ KAFKA CONSUMER ] create connections success")

                if self.kafka_consumer:
                    break

            except Exception as err:
                logger.warning(f"[ {i} ] - [ create connection kafka failed, try again ] [ {str(err)} ]")