"""
Database Creation Script
-------------------------
Creates the 'village_pond' PostgreSQL database if it doesn't already exist.
Reads credentials from .env to avoid hardcoding passwords.
"""

import os
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from dotenv import load_dotenv

load_dotenv()

DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "village_pond")

try:
    # Connect to the default postgres database to create a new one
    conn = psycopg2.connect(
        dbname="postgres",
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()

    # Check if database exists
    cursor.execute(
        "SELECT 1 FROM pg_catalog.pg_database WHERE datname = %s", (DB_NAME,)
    )
    exists = cursor.fetchone()

    if not exists:
        cursor.execute(f'CREATE DATABASE "{DB_NAME}"')
        print(f"Database '{DB_NAME}' created successfully!")
    else:
        print(f"Database '{DB_NAME}' already exists.")

    cursor.close()
    conn.close()
except Exception as e:
    print(f"FAILED: {e}")
