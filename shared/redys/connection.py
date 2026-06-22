import os
import settings as s
from redis import Redis
from loguru import logger

class ConnectionRedys:
    def __init__(self, **kwargs) -> None:
        
        logger.info(f"START CREATE REDIS CONNECTIONS :: HOST [ {s.REDIS['host']} ] | PORT [ {s.REDIS['port']} ] | DB [ {s.REDIS['db']} ]")
        self.client: Redis = Redis(
            host=s.REDIS["host"],
            port=s.REDIS["port"],
            db=s.REDIS["db"],
            decode_responses=True,
            **kwargs
        )
        ...

