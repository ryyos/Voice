import os
import json

from json import dumps

from typing import Any, Dict, Generator
from loguru import logger
from botocore.exceptions import ClientError
from .connection import ConnectionRedys

class Redys:
    _instance: dict = dict()
    
    def __new__(cls, **kwargs):
        if not cls._instance.get("c"):
            cls._instance["i"] = super().__new__(cls)
            cls._instance["c"] = ConnectionRedys(**kwargs)
        
    @classmethod
    def check(cls, key: str, id: str, **kwargs) -> Dict:
        cls(**kwargs)
        """
        Examples:
            >>> check(key="xxxx:xxxx:xxxx", id="xxxxxx")
            {
                "data": xxxxx
            }
            
            >>> check(key="xxxx:xxxx:xxxx", id="xxxxxx")
            None
        """
        __key: str = "{}:{}".format(
            key,
            id
        )
        __key = cls._instance["c"].client.get(__key)
        if __key:
            logger.info(f'DATA ALREDY IN REDIS :: ID [ {id} ]')
            return json.loads(__key)
        return None
        ...
        
    @classmethod
    def push(cls, data: str, key: str, id: str, **kwargs):
        cls(**kwargs)
        """
        Examples:
            >>> push(
                data={
                    "data": xxxxx
                },
                key="xxxx:xxxx:xxxx",
                id="xxxxxx"
            )
        """
        cls._instance["c"].client.set(
            "{}:{}".format(
                key,
                id
            ),
            json.dumps(
                data,
                ensure_ascii=False
            ),
            **kwargs
        )
        logger.info(f"NEW DATA ADD IN REDIS :: ID [ {id} ]")
        
        
    @classmethod
    def get(cls, key: str, id: str, **kwargs) -> Dict | None:
        cls(**kwargs)
        """
        Get data from redis by key without deleting it

        Examples:
            >>> get(key="xxxx:xxxx:xxxx", id="xxxxxx")
            {
                "data": xxxxx
            }
        """
        __key: str = f"{key}:{id}"
        data = cls._instance["c"].client.get(__key)

        if not data:
            return None

        logger.info(f"GET DATA FROM REDIS :: ID [ {id} ]")
        return json.loads(data)


    @classmethod
    def consume(
        cls,
        key: str,
        delete: bool = True,
        count: int = 100,
        **kwargs
    ) -> Generator[Dict, None, None]:
        """
        Consume all redis keys by prefix and return id + data

        Examples:
            >>> consume_by_prefix(key="order:process")
        """
        cls(**kwargs)
        
        pattern = f"{key}:*"
        cursor = 0

        while True:
            cursor, keys = cls._instance["c"].client.scan(
                cursor=cursor,
                match=pattern,
                count=count
            )

            for full_key in keys:
                raw = cls._instance["c"].client.get(full_key)
                if not raw:
                    continue

                yield (res:={
                    "id": full_key.split(":")[-1],
                    "data": json.loads(raw)
                })
                logger.info(
                    f"CONSUME REDIS BY PREFIX :: KEY [ {key} ] | TOTAL [ {len(res)} ]"
                )

                if delete:
                    cls._instance["c"].client.delete(full_key)

            if cursor == 0:
                break
