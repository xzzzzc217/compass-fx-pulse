from contextlib import contextmanager
import mysql.connector
from mysql.connector import pooling
from .config import settings

_pool: pooling.MySQLConnectionPool | None = None


def _build_pool() -> pooling.MySQLConnectionPool:
    """Build the global MySQL connection pool.

    Phase 4.1: bumped pool_size from 5 → 20 to support concurrent Agent
    runs without queueing on the connection layer. mysql-connector caps
    pool_size at 32 by default; 20 is comfortable for a 4-worker gunicorn
    setup (5 conns/worker).
    """
    import os
    pool_size = int(os.environ.get("MYSQL_POOL_SIZE", "20"))
    return pooling.MySQLConnectionPool(
        pool_name="compass_fx_pool",
        pool_size=pool_size,
        host=settings.MYSQL_HOST,
        port=settings.MYSQL_PORT,
        user=settings.MYSQL_USER,
        password=settings.MYSQL_PASSWORD,
        database=settings.MYSQL_DB,
        autocommit=False,
        charset="utf8mb4",
    )


def get_pool() -> pooling.MySQLConnectionPool:
    global _pool
    if _pool is None:
        _pool = _build_pool()
    return _pool


@contextmanager
def get_cursor(commit: bool = False):
    conn = get_pool().get_connection()
    cur = conn.cursor()
    try:
        yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
