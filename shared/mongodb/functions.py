from datetime import datetime, timezone
from typing import Any, Generator, Optional

from loguru import logger
from pymongo import IndexModel, ASCENDING, DESCENDING
from pymongo.errors import PyMongoError, DuplicateKeyError

from shared.config import settings
from .connection import MongoConnection


class _MongoProxy:
    """Proxy that routes all methods to a specific database connection."""

    def __init__(self, name: str, conn: MongoConnection, db_name: str):
        self._name = name
        self._conn = conn
        self._db = conn.client[db_name]

    @property
    def db(self):
        return self._db

    # ── delegates ──────────────────────────────────────────────
    def insert_one(self, collection: str, data: dict, **kw) -> str | None:
        return Mongo._insert_one(self._conn, self._db, collection, data, **kw)

    def insert_many(self, collection: str, data: list[dict], **kw) -> int:
        return Mongo._insert_many(self._conn, self._db, collection, data, **kw)

    def find(
        self, collection: str, query: dict | None = None, **kw
    ) -> list[dict]:
        return Mongo._find(self._db, collection, query, **kw)

    def find_one(
        self, collection: str, query: dict | None = None, **kw
    ) -> dict | None:
        return Mongo._find_one(self._db, collection, query, **kw)

    def find_iter(
        self, collection: str, query: dict | None = None, **kw
    ) -> Generator[dict, None, None]:
        return Mongo._find_iter(self._db, collection, query, **kw)

    def update_one(
        self, collection: str, query: dict, update: dict, upsert: bool = False, **kw
    ) -> int:
        return Mongo._update_one(self._db, collection, query, update, upsert, **kw)

    def update_many(
        self, collection: str, query: dict, update: dict, **kw
    ) -> int:
        return Mongo._update_many(self._db, collection, query, update, **kw)

    def delete_one(self, collection: str, query: dict, **kw) -> int:
        return Mongo._delete_one(self._db, collection, query, **kw)

    def delete_many(self, collection: str, query: dict, **kw) -> int:
        return Mongo._delete_many(self._db, collection, query, **kw)

    def count(self, collection: str, query: dict | None = None) -> int:
        return Mongo._count(self._db, collection, query)

    def aggregate(self, collection: str, pipeline: list[dict]) -> list[dict]:
        return Mongo._aggregate(self._db, collection, pipeline)

    def ensure_index(self, collection: str, keys: list[tuple], **kw) -> str:
        return Mongo._ensure_index(self._db, collection, keys, **kw)

    def close(self) -> None:
        self._conn.close()
        logger.success(f"[ MONGODB:{self._name} ] CONNECTION CLOSED")


class Mongo:
    """
    MongoDB client — mirrors the PG / Redys / Kafkaa pattern.

    Usage (default connection from settings)
    ----------------------------------------
    >>> Mongo.insert_one("raw_documents", {...})
    >>> docs = Mongo.find("raw_documents", {"keyword": "pilpres"})
    >>> Mongo.update_one("raw_documents", {"_id": ...}, {"$set": {...}})
    >>> total = Mongo.count("raw_documents")

    Multiple connections
    --------------------
    >>> logs_db = Mongo["logs"]
    >>> logs_db.insert_one("events", {...})
    """

    _registry: dict[str, MongoConnection] = {}

    # ── singleton-ish constructor ───────────────────────────────
    def __new__(cls):
        if "default" not in cls._registry:
            logger.debug("[ MONGODB:default ] CREATE NEW CONNECTION")
            cls._registry["default"] = MongoConnection(settings.mongo_uri)
        return super().__new__(cls)

    @classmethod
    def __class_getitem__(cls, name: str) -> _MongoProxy:
        """Support Mongo["connection_name"] syntax."""
        if name not in cls._registry:
            # If you have multiple mongo URIs in settings, resolve here.
            # For now we reuse the default URI.
            logger.debug(f"[ MONGODB:{name} ] CREATE NEW CONNECTION")
            cls._registry[name] = MongoConnection(settings.mongo_uri)
        db_name = settings.mongo_db
        return _MongoProxy(name, cls._registry[name], db_name)

    # ── public classmethods (default connection) ────────────────

    @classmethod
    def insert_one(
        cls, collection: str, data: dict, *, add_timestamps: bool = True, **kw
    ) -> str | None:
        cls()
        return cls._insert_one(
            cls._registry["default"],
            cls._registry["default"].client[settings.mongo_db],
            collection,
            data,
            add_timestamps=add_timestamps,
            **kw,
        )

    @classmethod
    def insert_many(
        cls,
        collection: str,
        data: list[dict],
        *,
        add_timestamps: bool = True,
        ordered: bool = False,
        **kw,
    ) -> int:
        cls()
        return cls._insert_many(
            cls._registry["default"],
            cls._registry["default"].client[settings.mongo_db],
            collection,
            data,
            add_timestamps=add_timestamps,
            ordered=ordered,
            **kw,
        )

    @classmethod
    def find(
        cls,
        collection: str,
        query: dict | None = None,
        *,
        projection: dict | None = None,
        sort: list[tuple] | None = None,
        skip: int = 0,
        limit: int = 0,
        **kw,
    ) -> list[dict]:
        cls()
        return cls._find(
            cls._registry["default"].client[settings.mongo_db],
            collection,
            query,
            projection=projection,
            sort=sort,
            skip=skip,
            limit=limit,
            **kw,
        )

    @classmethod
    def find_one(
        cls,
        collection: str,
        query: dict | None = None,
        *,
        projection: dict | None = None,
        sort: list[tuple] | None = None,
        **kw,
    ) -> dict | None:
        cls()
        return cls._find_one(
            cls._registry["default"].client[settings.mongo_db],
            collection,
            query,
            projection=projection,
            sort=sort,
            **kw,
        )

    @classmethod
    def find_iter(
        cls,
        collection: str,
        query: dict | None = None,
        *,
        projection: dict | None = None,
        sort: list[tuple] | None = None,
        batch_size: int = 100,
        **kw,
    ) -> Generator[dict, None, None]:
        cls()
        yield from cls._find_iter(
            cls._registry["default"].client[settings.mongo_db],
            collection,
            query,
            projection=projection,
            sort=sort,
            batch_size=batch_size,
            **kw,
        )

    @classmethod
    def update_one(
        cls,
        collection: str,
        query: dict,
        update: dict,
        *,
        upsert: bool = False,
        **kw,
    ) -> int:
        cls()
        return cls._update_one(
            cls._registry["default"].client[settings.mongo_db],
            collection,
            query,
            update,
            upsert,
            **kw,
        )

    @classmethod
    def update_many(
        cls, collection: str, query: dict, update: dict, **kw
    ) -> int:
        cls()
        return cls._update_many(
            cls._registry["default"].client[settings.mongo_db],
            collection,
            query,
            update,
            **kw,
        )

    @classmethod
    def delete_one(cls, collection: str, query: dict, **kw) -> int:
        cls()
        return cls._delete_one(
            cls._registry["default"].client[settings.mongo_db],
            collection,
            query,
            **kw,
        )

    @classmethod
    def delete_many(cls, collection: str, query: dict, **kw) -> int:
        cls()
        return cls._delete_many(
            cls._registry["default"].client[settings.mongo_db],
            collection,
            query,
            **kw,
        )

    @classmethod
    def count(cls, collection: str, query: dict | None = None) -> int:
        cls()
        return cls._count(
            cls._registry["default"].client[settings.mongo_db],
            collection,
            query,
        )

    @classmethod
    def aggregate(cls, collection: str, pipeline: list[dict]) -> list[dict]:
        cls()
        return cls._aggregate(
            cls._registry["default"].client[settings.mongo_db],
            collection,
            pipeline,
        )

    @classmethod
    def ensure_index(
        cls, collection: str, keys: list[tuple], *, unique: bool = False, **kw
    ) -> str:
        cls()
        return cls._ensure_index(
            cls._registry["default"].client[settings.mongo_db],
            collection,
            keys,
            unique=unique,
            **kw,
        )

    @classmethod
    def close(cls, name: str = "default") -> None:
        if conn := cls._registry.pop(name, None):
            conn.close()
            logger.success(f"[ MONGODB:{name} ] CONNECTION CLOSED")

    # ── internal implementations ─────────────────────────────────

    @staticmethod
    def _insert_one(
        conn: MongoConnection,
        db,
        collection: str,
        data: dict,
        *,
        add_timestamps: bool = True,
        **kw,
    ) -> str | None:
        if add_timestamps:
            now = datetime.now(timezone.utc).isoformat()
            data.setdefault("created_at", now)
            data.setdefault("updated_at", now)
        try:
            result = db[collection].insert_one(data, **kw)
            logger.debug(
                f"[ MONGODB ] insert_one → {collection}  id={result.inserted_id}"
            )
            return str(result.inserted_id)
        except DuplicateKeyError:
            logger.warning(f"[ MONGODB ] duplicate key in {collection}")
            return None
        except PyMongoError as e:
            logger.error(f"[ MONGODB ] insert_one failed → {e}")
            return None

    @staticmethod
    def _insert_many(
        conn: MongoConnection,
        db,
        collection: str,
        data: list[dict],
        *,
        add_timestamps: bool = True,
        ordered: bool = False,
        **kw,
    ) -> int:
        if not data:
            return 0
        if add_timestamps:
            now = datetime.now(timezone.utc).isoformat()
            for doc in data:
                doc.setdefault("created_at", now)
                doc.setdefault("updated_at", now)
        try:
            result = db[collection].insert_many(data, ordered=ordered)
            n = len(result.inserted_ids)
            logger.info(f"[ MONGODB ] insert_many → {collection}  count={n}")
            return n
        except PyMongoError as e:
            logger.error(f"[ MONGODB ] insert_many failed → {e}")
            return 0

    @staticmethod
    def _find(
        db,
        collection: str,
        query: dict | None,
        *,
        projection: dict | None = None,
        sort: list[tuple] | None = None,
        skip: int = 0,
        limit: int = 0,
        **kw,
    ) -> list[dict]:
        cursor = db[collection].find(query or {}, projection=projection, **kw)
        if sort:
            cursor = cursor.sort(sort)
        if skip:
            cursor = cursor.skip(skip)
        if limit:
            cursor = cursor.limit(limit)
        results = list(cursor)
        logger.debug(f"[ MONGODB ] find → {collection}  count={len(results)}")
        return results

    @staticmethod
    def _find_one(
        db,
        collection: str,
        query: dict | None,
        *,
        projection: dict | None = None,
        sort: list[tuple] | None = None,
        **kw,
    ) -> dict | None:
        cursor = db[collection].find(query or {}, projection=projection, **kw)
        if sort:
            cursor = cursor.sort(sort)
        result = cursor[0] if cursor else None
        logger.debug(
            f"[ MONGODB ] find_one → {collection}  "
            f"{'found' if result else 'not found'}"
        )
        return result

    @staticmethod
    def _find_iter(
        db,
        collection: str,
        query: dict | None,
        *,
        projection: dict | None = None,
        sort: list[tuple] | None = None,
        batch_size: int = 100,
        **kw,
    ) -> Generator[dict, None, None]:
        cursor = db[collection].find(query or {}, projection=projection, **kw)
        if sort:
            cursor = cursor.sort(sort)
        cursor = cursor.batch_size(batch_size)
        total = 0
        for doc in cursor:
            total += 1
            yield doc
        logger.info(f"[ MONGODB ] find_iter complete → {collection}  total={total}")

    @staticmethod
    def _update_one(
        db,
        collection: str,
        query: dict,
        update: dict,
        upsert: bool = False,
        **kw,
    ) -> int:
        if "$set" in update:
            update.setdefault("$set", {})
            update["$set"]["updated_at"] = datetime.now(timezone.utc).isoformat()
        try:
            result = db[collection].update_one(query, update, upsert=upsert, **kw)
            logger.debug(
                f"[ MONGODB ] update_one → {collection}  "
                f"matched={result.matched_count}  modified={result.modified_count}"
            )
            return result.modified_count
        except PyMongoError as e:
            logger.error(f"[ MONGODB ] update_one failed → {e}")
            return 0

    @staticmethod
    def _update_many(
        db, collection: str, query: dict, update: dict, **kw
    ) -> int:
        try:
            result = db[collection].update_many(query, update, **kw)
            logger.info(
                f"[ MONGODB ] update_many → {collection}  "
                f"matched={result.matched_count}  modified={result.modified_count}"
            )
            return result.modified_count
        except PyMongoError as e:
            logger.error(f"[ MONGODB ] update_many failed → {e}")
            return 0

    @staticmethod
    def _delete_one(db, collection: str, query: dict, **kw) -> int:
        try:
            result = db[collection].delete_one(query, **kw)
            logger.debug(f"[ MONGODB ] delete_one → {collection}  deleted={result.deleted_count}")
            return result.deleted_count
        except PyMongoError as e:
            logger.error(f"[ MONGODB ] delete_one failed → {e}")
            return 0

    @staticmethod
    def _delete_many(db, collection: str, query: dict, **kw) -> int:
        try:
            result = db[collection].delete_many(query, **kw)
            logger.info(f"[ MONGODB ] delete_many → {collection}  deleted={result.deleted_count}")
            return result.deleted_count
        except PyMongoError as e:
            logger.error(f"[ MONGODB ] delete_many failed → {e}")
            return 0

    @staticmethod
    def _count(db, collection: str, query: dict | None) -> int:
        n = db[collection].count_documents(query or {})
        logger.debug(f"[ MONGODB ] count → {collection}  total={n}")
        return n

    @staticmethod
    def _aggregate(db, collection: str, pipeline: list[dict]) -> list[dict]:
        try:
            results = list(db[collection].aggregate(pipeline))
            logger.debug(f"[ MONGODB ] aggregate → {collection}  count={len(results)}")
            return results
        except PyMongoError as e:
            logger.error(f"[ MONGODB ] aggregate failed → {e}")
            return []

    @staticmethod
    def _ensure_index(
        db,
        collection: str,
        keys: list[tuple],
        *,
        unique: bool = False,
        **kw,
    ) -> str:
        index_models = [
            IndexModel([(field, direction)], **{**kw, "unique": unique})
            if i == 0
            else IndexModel([(field, direction)])
            for i, (field, direction) in enumerate(keys)
        ]
        # Simplify — just build the tuple list
        result = db[collection].create_index(keys, unique=unique, **kw)
        logger.info(f"[ MONGODB ] index created → {collection}  name={result}")
        return result
