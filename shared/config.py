from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # MongoDB
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "voice_raw"

    # PostgreSQL
    postgres_dsn: str = "postgresql://voice:voice@localhost:5432/voice"

    # Kafka / Redpanda
    kafka_broker: str = "localhost:9092"
    kafka_topic_jobs: str = "search_jobs"

    # Gemini
    gemini_api_key: str

    # Telegram
    telegram_bot_token: str


settings = Settings()
