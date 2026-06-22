import logging
from .functions import Kafkaa

kafka_logger = logging.getLogger("kafka")
kafka_logger.setLevel(logging.ERROR) 