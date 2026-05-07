from contextlib import contextmanager

import pyodbc
import pymssql

from config import Config


class DbRow:
    def __init__(self, columns, values):
        self._columns = columns
        self._values = tuple(values)
        self._index = {name.lower(): index for index, name in enumerate(columns)}

    def __getitem__(self, key):
        if isinstance(key, str):
            return self._values[self._index[key.lower()]]
        return self._values[key]

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __iter__(self):
        return iter(self._values)


class PymssqlCursorAdapter:
    def __init__(self, cursor):
        self.cursor = cursor

    @property
    def rowcount(self):
        return self.cursor.rowcount

    def execute(self, query, params=None):
        query = query.replace('?', '%s')
        self.cursor.execute(query, params or ())
        return self

    def fetchone(self):
        row = self.cursor.fetchone()
        return self._wrap(row) if row is not None else None

    def fetchall(self):
        return [self._wrap(row) for row in self.cursor.fetchall()]

    def close(self):
        self.cursor.close()

    def _wrap(self, row):
        columns = [column[0] for column in self.cursor.description or []]
        return DbRow(columns, row)


def get_db_connection():
    if Config.DB_BACKEND == 'pymssql':
        return pymssql.connect(
            server=Config.DB_SERVER,
            user=Config.DB_USERNAME,
            password=Config.DB_PASSWORD,
            database=Config.DB_DATABASE,
            login_timeout=10,
            timeout=30,
        )

    conn_str = (
        f"DRIVER={Config.DB_DRIVER};"
        f"SERVER={Config.DB_SERVER};"
        f"DATABASE={Config.DB_DATABASE};"
        f"UID={Config.DB_USERNAME};"
        f"PWD={Config.DB_PASSWORD};"
        f"Encrypt={Config.DB_ENCRYPT};"
        f"TrustServerCertificate={Config.DB_TRUST_SERVER_CERTIFICATE};"
    )
    return pyodbc.connect(conn_str)


@contextmanager
def get_db_cursor():
    """Gerencia abertura, commit/rollback e fechamento da conexão."""
    conn = get_db_connection()
    raw_cursor = conn.cursor()
    cursor = PymssqlCursorAdapter(raw_cursor) if Config.DB_BACKEND == 'pymssql' else raw_cursor
    try:
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()
