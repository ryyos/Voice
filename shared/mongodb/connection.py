from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from loguru import logger


class MongoConnection:
    """Thin wrapper around pymongo.MongoClient with retry on connect."""

    def __init__(self, uri: str, max_retries: int = 5) -> None:
        for attempt in range(1, max_retries + 1):
            try:
                self.client: MongoClient = MongoClient(
                    uri,
                    serverSelectionTimeoutMS=5000,
                    connectTimeoutMS=5000,
                )
                # Trigger actual connection
                self.client.admin.command("ping")
                logger.success(
                    f"[ MONGODB ] connected  |  attempt {attempt}/{max_retries}"
                )
                return
            except (ConnectionFailure, ServerSelectionTimeoutError) as e:
                logger.warning(
                    f"[ MONGODB ] connection attempt {attempt}/{max_retries} failed: {e}"
                )
                if attempt == max_retries:
                    raise
        ...

    def close(self) -> None:
        self.client.close()
        logger.info("[ MONGODB ] connection closed")
