import os
from contextlib import contextmanager
from typing import Any, Dict, Generator, Optional

import psycopg2
from psycopg2.extras import RealDictCursor


DATABASE_URL_ENV_NAME = "DATABASE_URL"


def get_database_url() -> str:
    database_url = os.getenv(DATABASE_URL_ENV_NAME, "").strip()

    if not database_url:
        raise ValueError(
            "Missing DATABASE_URL. Add the Render PostgreSQL Internal Database URL "
            "to your backend environment variables as DATABASE_URL."
        )

    return database_url


@contextmanager
def get_db_connection() -> Generator[Any, None, None]:
    connection = None

    try:
        connection = psycopg2.connect(
            get_database_url(),
            cursor_factory=RealDictCursor,
        )
        yield connection
        connection.commit()

    except Exception:
        if connection:
            connection.rollback()
        raise

    finally:
        if connection:
            connection.close()


def postgres_status() -> Dict[str, Any]:
    try:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT NOW() AS server_time;")
                row = cursor.fetchone()

        return {
            "success": True,
            "database": "connected",
            "provider": "PostgreSQL",
            "server_time": str(row.get("server_time")) if row else None,
        }

    except Exception as error:
        return {
            "success": False,
            "database": "not_connected",
            "provider": "PostgreSQL",
            "error": str(error),
        }


def execute_sql(sql: str, params: Optional[tuple] = None) -> None:
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)


def fetch_one(sql: str, params: Optional[tuple] = None) -> Optional[Dict[str, Any]]:
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            row = cursor.fetchone()
            return dict(row) if row else None


def fetch_all(sql: str, params: Optional[tuple] = None) -> list:
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
