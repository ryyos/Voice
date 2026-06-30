from redis import Redis
from shared.config import settings
from shared.utils.logger import log


class RedysConnection:
    def __init__(self) -> None:
        self.client: Redis = Redis.from_url(
            settings.valkey_url,
            decode_responses=True,
        )
        log.debug("[ VALKEY ] connection created → {}", settings.valkey_url)
