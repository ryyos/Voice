import pandas as pd
import settings
import json

from sqlalchemy import text, inspect
from typing import Union
from valkyt.utils import File, Time
from .connection import PostgresConnections
from sqlalchemy.dialects.postgresql import insert
from loguru import logger
from icecream import ic

class _PGProxy:
    """Proxy yang mengarahkan semua method PG ke engine koneksi tertentu."""

    def __init__(self, name: str, engine: PostgresConnections):
        self._name    = name
        self._engine  = engine

    def write(self, data, table_name, **kwargs):
        return PG._write(self._engine, data, table_name, **kwargs)

    def read(self, table_name, fields=None, filters=None, schema=None):
        return PG._read(self._engine, table_name, fields, filters, schema)

    def iterate(self, table_name, fields=None, filters=None, schema=None, chunk_size=1000):
        return PG._iterate(self._engine, table_name, fields, filters, schema, chunk_size)

    def update(self, table_name, set_data, where, schema=None):
        return PG._update(self._engine, table_name, set_data, where, schema)

    def get_columns(self, table_name, schema=None):
        return PG._get_columns(self._engine, table_name, schema)

    def close(self):
        self._engine._engine.dispose()
        logger.success(f"[ POSTGRESQL:{self._name} ] CONNECTION CLOSED")


class PG:
    _registry: dict[str, PostgresConnections] = {}

    @classmethod
    def _get_default_engine(cls) -> PostgresConnections:
        if "default" not in cls._registry:
            logger.debug("[ POSTGRESQL:default ] CREATE NEW POOL")
            cls._registry["default"] = PostgresConnections()
        return cls._registry["default"]

    @classmethod
    def __class_getitem__(cls, name: str) -> _PGProxy:
        if name not in cls._registry:
            config = settings.POSTGRESQL_CONNECTIONS.get(name)
            if not config:
                raise KeyError(f"[ POSTGRESQL ] no connection named '{name}' found in settings.POSTGRESQL_CONNECTIONS")
            logger.debug(f"[ POSTGRESQL:{name} ] CREATE NEW POOL")
            cls._registry[name] = PostgresConnections(config)
        return _PGProxy(name, cls._registry[name])

    def __new__(cls):
        cls._get_default_engine()
        ...
    
    # ── public classmethods (default connection) ─────────────────────────────

    @classmethod
    def write(cls, data: Union[dict, list], table_name: str, **kwargs) -> None:
        cls._write(cls._get_default_engine(), data, table_name, **kwargs)

    @classmethod
    def get_columns(cls, table_name: str, schema: str = None) -> dict:
        return cls._get_columns(cls._get_default_engine(), table_name, schema)

    @classmethod
    def read(cls, table_name: str, fields=None, filters=None, schema=None) -> list[dict]:
        return cls._read(cls._get_default_engine(), table_name, fields, filters, schema)

    @classmethod
    def iterate(cls, table_name: str, fields=None, filters=None, schema=None, chunk_size=1000):
        return cls._iterate(cls._get_default_engine(), table_name, fields, filters, schema, chunk_size)

    @classmethod
    def update(cls, table_name: str, set_data: dict, where: dict, schema=None) -> int:
        return cls._update(cls._get_default_engine(), table_name, set_data, where, schema)

    @classmethod
    def close(cls, name: str = "default"):
        if engine := cls._registry.pop(name, None):
            engine._engine.dispose()
            logger.success(f"[ POSTGRESQL:{name} ] CONNECTION CLOSED")

    # ── internal implementations (menerima engine eksplisit) ─────────────────

    @staticmethod
    def _write(engine: PostgresConnections, data: Union[dict, list], table_name: str, **kwargs) -> None:
        if not isinstance(data, list):
            data = [data]

        df = pd.DataFrame(data).drop_duplicates(subset=["id"], keep="last")
        with engine._engine.begin() as conn:
            if (_c := df.to_sql(
                table_name,
                con=conn,
                schema=sc if (sc := kwargs.get("schema")) else settings.SCHEMA["default"],
                if_exists="append",
                index=False,
                method=PG._conflict_do_update,
            )):
                logger.success(f"[ {str(data)[:50]} ] SUCCESS SEND TO POSTGRESQL :: [ {str(_c)} ]")
            else:
                logger.success(f"[ {str(data)[:50]} ] ALREDY EXISTS")

    @staticmethod
    def _get_columns(engine: PostgresConnections, table_name: str, schema: str = None) -> dict:
        def _normalize_type(col_type: str) -> str:
            t = col_type.lower()
            if "int" in t:                                          return "integer"
            elif "char" in t or "text" in t:                       return "string"
            elif "bool" in t:                                       return "boolean"
            elif "double" in t or "float" in t or "numeric" in t or "real" in t: return "float"
            elif "date" in t or "time" in t:                       return "datetime"
            elif "array" in t:                                      return "array"
            elif "json" in t:                                       return "json"
            return "string"

        schema = schema or settings.SCHEMA["default"]
        columns = inspect(engine._engine).get_columns(table_name, schema=schema)
        return {col["name"]: _normalize_type(str(col["type"])) for col in columns}

    @staticmethod
    def _read(engine: PostgresConnections, table_name: str, fields=None, filters=None, schema=None) -> list[dict]:
        schema        = schema or settings.SCHEMA["default"]
        select_fields = ", ".join(fields) if fields else "*"
        where_clause, params = "", {}

        if filters:
            where_clause = " WHERE " + " AND ".join(f"{k} = :{k}" for k in filters)
            params = filters

        query = f"SELECT {select_fields} FROM {schema}.{table_name} {where_clause}"
        with engine._engine.begin() as conn:
            return [dict(row) for row in conn.execute(text(query), params).mappings().all()]

    @staticmethod
    def _iterate(engine: PostgresConnections, table_name: str, fields=None, filters=None, schema=None, chunk_size=1000):
        schema = schema or settings.SCHEMA["default"]

        with engine._engine.connect().execution_options(stream_results=True) as conn:
            columns = conn.execute(text("""
                SELECT column_name, udt_name
                FROM information_schema.columns
                WHERE table_schema = :schema AND table_name = :table_name
                ORDER BY ordinal_position
            """), {"schema": schema, "table_name": table_name}).mappings().all()

            geometry_columns = {col["column_name"] for col in columns if col["udt_name"] in ("geometry", "geography")}
            selected_columns = [col for col in columns if col["column_name"] in fields] if fields else columns

            select_fields = ", ".join(
                f"ST_AsGeoJSON({col['column_name']}) AS {col['column_name']}"
                if col["column_name"] in geometry_columns else col["column_name"]
                for col in selected_columns
            )

            where_clause, params = "", {}
            if filters:
                where_clause = " WHERE " + " AND ".join(f"{k} = :{k}" for k in filters)
                params = filters

            logger.debug(f"[ POSTGRESQL ] STREAM START | table={schema}.{table_name} | filters={filters} | chunk_size={chunk_size}")

            count = 0
            for row in conn.execute(text(f"SELECT {select_fields} FROM {schema}.{table_name} {where_clause}"), params).mappings().yield_per(chunk_size):
                count += 1
                data = dict(row)
                for col in geometry_columns:
                    if col in data and data[col]:
                        data[col] = json.loads(data[col])
                logger.debug(f"[ POSTGRESQL ] STREAM COUNT | [ {count} ]")
                yield data

            logger.success(f"[ POSTGRESQL ] STREAM COMPLETE | table={schema}.{table_name} | total_rows={count}")

    @staticmethod
    def _update(engine: PostgresConnections, table_name: str, set_data: dict, where: dict, schema=None) -> int:
        if not where:
            raise ValueError("updates without a WHERE clause are not permitted.")

        schema, set_clause, params = schema or settings.SCHEMA["default"], [], {}

        for k, v in set_data.items():
            if "coordinate" in k:
                set_clause.append(f"{k} = ST_SetSRID(ST_MakePoint({v['lon']}, {v['lat']}), 4326)")
            else:
                set_clause.append(f"{k} = :set_{k}")
                params[f"set_{k}"] = v

        where_clause = [f"{k} = :where_{k}" for k in where]
        params.update({f"where_{k}": v for k, v in where.items()})

        query = f"UPDATE {schema}.{table_name} SET {', '.join(set_clause)} WHERE {' AND '.join(where_clause)}"
        with engine._engine.begin() as conn:
            result = conn.execute(text(query), params)
            logger.success(f"item succes updated :: [ {where['id']} ]")
            return result.rowcount
            
    @staticmethod
    def _conflict_do_update(table, conn, keys, data_iter):
        data = [dict(zip(keys, row)) for row in data_iter]
        
        insert_statement = insert(table.table).values(data)
        conflict_update = insert_statement.on_conflict_do_update(
            constraint=f"{table.table.name}_pkey",
            set_={column.key: column for column in insert_statement.excluded},
        )
        result = conn.execute(conflict_update)
        if result.rowcount < len(data):            
            File.write_json(f"duplicate/{data[0]['id']}_{Time.epoch_ms()}.json", data)
            logger.debug(f"DATA IS DUPLICATE :: [ {data[0]['id']} ]")
        return result.rowcount