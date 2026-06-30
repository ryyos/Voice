from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # MongoDB
    mongo_uri: str
    mongo_db: str
    mongo_collection: str

    # PostgreSQL
    postgres_dsn: str

    # Message broker — "redpanda" atau "kafka" (set di .env)
    broker_type: str
    redpanda_broker: str
    kafka_broker: str
    kafka_topic_keyword: str
    kafka_project_version: str

    @property
    def broker_address(self) -> str:
        return self.redpanda_broker if self.broker_type == "redpanda" else self.kafka_broker

    # Piped (YouTube data source via local Docker)
    piped_base_url: str

    # Gemini
    gemini_api_key: str

    # Telegram
    telegram_bot_token: str

    # Valkey
    valkey_url: str
    valkey_key: str

    # Monitoring
    log_split: bool


settings = Settings()
