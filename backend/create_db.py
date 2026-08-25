"""Create the configured PostgreSQL database; schema changes belong to Alembic."""

import os
import sys

import psycopg2
from dotenv import load_dotenv
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


def main() -> int:
    load_dotenv()
    database_name = os.getenv("DB_NAME", "village_pond")
    try:
        with psycopg2.connect(
            dbname="postgres",
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "postgres"),
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5432"),
        ) as connection:
            connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM pg_catalog.pg_database WHERE datname = %s", (database_name,))
                if cursor.fetchone() is None:
                    cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
                    print(f"Database '{database_name}' created. Run: alembic upgrade head")
                else:
                    print(f"Database '{database_name}' already exists. Run: alembic upgrade head")
        return 0
    except Exception as exc:
        print(f"Database creation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
