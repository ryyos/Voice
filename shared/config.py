from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # MongoDB
    mongo_uri: str
    mongo_db: str

    # PostgreSQL
    postgres_dsn: str

    # Kafka / Redpanda
    kafka_broker: str
    kafka_topic_keyword: str
    kafka_project_version: str

    # Gemini
    gemini_api_key: str

    # Telegram
    telegram_bot_token: str

    # Monitoring
    log_split: bool = False


settings = Settings()
