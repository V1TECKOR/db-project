import os
from dotenv import load_dotenv
from mysql.connector import pooling

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_DATABASE"),
}

_pool = pooling.MySQLConnectionPool(pool_name="interclub_pool", pool_size=2, **DB_CONFIG)

def _conn():
    return _pool.get_connection()

def db_read(sql, params=None, single=False):
    conn = _conn()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(sql, params or ())
        return cur.fetchone() if single else cur.fetchall()
    finally:
        cur.close()
        conn.close()

def db_write(sql, params=None):
    conn = _conn()
    cur = conn.cursor()
    try:
        cur.execute(sql, params or ())
        conn.commit()
    finally:
        cur.close()
        conn.close()
