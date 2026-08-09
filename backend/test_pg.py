import psycopg2
try:
    conn = psycopg2.connect(
        dbname="postgres",
        user="postgres",
        password="password",
        host="localhost",
        port="5432"
    )
    print("SUCCESS")
except Exception as e:
    print(f"FAILED: {e}")
