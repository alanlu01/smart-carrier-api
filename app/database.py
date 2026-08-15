from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

import oracledb

from app.config import get_settings


@lru_cache
def get_pool() -> oracledb.ConnectionPool:
    settings = get_settings()
    if not settings.database_configured:
        raise RuntimeError("Oracle Database credentials and wallet settings are required")
    wallet_dir = str(settings.oracle_wallet_dir)
    return oracledb.create_pool(
        user=settings.oracle_user,
        password=settings.oracle_password.get_secret_value(),
        dsn=settings.oracle_dsn,
        config_dir=wallet_dir,
        wallet_location=wallet_dir,
        wallet_password=settings.oracle_wallet_password.get_secret_value(),
        min=0,
        max=settings.oracle_pool_max,
        increment=1,
        timeout=60,
    )


@contextmanager
def get_connection() -> Iterator[oracledb.Connection]:
    with get_pool().acquire() as connection:
        yield connection


def close_pool() -> None:
    if get_pool.cache_info().currsize:
        get_pool().close(force=True)
        get_pool.cache_clear()


def ping_database() -> None:
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM dual")
        cursor.fetchone()
