import psycopg2
import psycopg2.pool

from shared.config import settings
from shared.utils.logger import log


class PGConnection:
    def __init__(self, dsn: str) -> None:
        self._pool = psycopg2.pool.ThreadedConnectionPool(1, 10, dsn)
        log.debug("[ POSTGRESQL ] connection pool created")

    def get(self):
        return self._pool.getconn()

    def put(self, conn) -> None:
        self._pool.putconn(conn)

    def close(self) -> None:
        self._pool.closeall()
        log.debug("[ POSTGRESQL ] connection pool closed")
