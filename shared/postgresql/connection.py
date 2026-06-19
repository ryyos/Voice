from sqlalchemy import create_engine
from sqlalchemy.engine.url import URL
import settings

class PostgresConnections:

    def __init__(self, config: dict | None = None):
        self._engine = create_engine(
            URL.create(**(config or settings.POSTGRESQL)),
            connect_args={"options": "-c default_transaction_read_only=off"},
        )
