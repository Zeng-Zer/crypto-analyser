"""PostgreSQL schema initialization for historical news."""

from pathlib import Path

import psycopg2

from crypto_analyser._paths import asset_path


def initialize_database(database_url: str, schema_path: Path | None = None) -> None:
    """Apply the idempotent news schema to PostgreSQL."""
    sql = (schema_path or asset_path("schema.sql")).read_text(encoding="utf-8")
    connection = psycopg2.connect(database_url)
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(sql)
    finally:
        connection.close()
