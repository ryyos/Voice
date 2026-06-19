
import json
import settings
import os

from loguru import logger
from time import sleep
from icecream import ic

from typing import Generator
from valkyt.utils import Stream, File
from .connection import ConnectionKafkaProducer, ConnectionKafkaConsumer

class Kafkaa:
    _instance = None
    _connection = {}

    def __new__(cls, bootstrap: str, mode: str, *args):
        if not cls._instance or not cls._connection.get(bootstrap+mode):
            cls._instance = super().__new__(cls)
            logger.debug(f"[ KAFKA ] create new connections")
            match mode:
                case "send":
                    cls._connection[bootstrap+mode] = ConnectionKafkaProducer(bootstrap)
                case "get":
                    cls._connection[bootstrap+mode] = ConnectionKafkaConsumer(
                        bootstrap, group_id=args[0], topic=args[1]
                    )
            
        return cls._instance
    
    @classmethod
    def send(cls, data: dict, topic: str, bootstrap: str, log: bool = True) -> None:
        cls(bootstrap, (mode:="send"))
        logs = cls._connection[bootstrap+mode].kafka_produser.send(topic=topic, value=str.encode(json.dumps(data))).get(timeout=10)
        if log:
            logger.info(f'SEND KAFKA :: MESSAGE [ {logs} ]')
            Stream.shareKafka(topic)
            
    @classmethod
    def consume(cls, topic: str, group_id: str, bootstrap: str, beginning: bool = False) -> Generator:
        cls(bootstrap, (mode := "get"), group_id, topic)
        consumer = cls._connection[bootstrap + mode].kafka_consumer

        while not consumer.assignment():
            consumer.poll(timeout_ms=1000)

        logger.debug(f"assignment = {consumer.assignment()}")
        logger.debug(f"subscription = {consumer.subscription()}")

        if beginning:
            consumer.seek_to_beginning()

        while True:
            records = consumer.poll(timeout_ms=5000)
            if not records:
                continue

            for tp, messages in records.items():
                end_offset = consumer.end_offsets([tp])[tp]
                
                for message in messages:
                    current_offset = message.offset
                    lag = end_offset - current_offset

                    logger.info(
                        f"RECEIVE KAFKA :: topic={message.topic} "
                        f"partition={message.partition} "
                        f"offset={current_offset}/{end_offset} "
                        f"lag={lag}"
                    )

                    yield message.value
                    consumer.commit()


    @staticmethod
    def local2kafka(source: str, topic: str, bootstrap: str) -> None:
        for root, _, files in os.walk(source.replace('\\', '/')):
            for file in files:
                if file.endswith('json'):
                    file_path = os.path.join(root, file).replace('\\', '/')
                    Stream.shareKafka(topic)
                    data: dict = File.read_json(file_path)
                    Kafkaa.send(data, topic, bootstrap)
                    
    @classmethod
    def reset(cls):
        logger.warning("[ KAFKA ] reset singleton & connections")
        for conn in cls._connection.values():
            if hasattr(conn, "kafka_consumer"):
                try:
                    conn.kafka_consumer.close()
                except Exception:
                    pass

            if hasattr(conn, "kafka_produser"):
                try:
                    conn.kafka_produser.close()
                except Exception:
                    pass

        cls._connection.clear()
        cls._instance = None