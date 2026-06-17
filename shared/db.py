from pymongo import MongoClient
from pymongo.database import Database
import psycopg2
from psycopg2.extensions import connection as PgConnection

from shared.config import settings


def get_mongo_db() -> Database:
    client: MongoClient = MongoClient(settings.mongo_uri)
    return client[settings.mongo_db]


def get_postgres_conn() -> PgConnection:
    return psycopg2.connect(settings.postgres_dsn)
