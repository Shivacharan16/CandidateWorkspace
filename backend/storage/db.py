import sqlite3
import threading
from pathlib import Path
from contextlib import contextmanager
from backend.config import DATABASE_PATH, SCHEMA_PATH

_tls = threading.local()

def get_connection(db_path: Path = None) -> sqlite3.Connection:
    """Returns a SQLite connection with WAL mode and foreign keys enabled."""
    target_path = db_path or DATABASE_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(
        str(target_path),
        timeout=30.0,
        check_same_thread=False,
        isolation_level=None # Manage transactions explicitly
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection):
    """Context manager for explicit atomic transaction control."""
    conn.execute("BEGIN IMMEDIATE;")
    try:
        yield conn
        conn.execute("COMMIT;")
    except Exception:
        conn.execute("ROLLBACK;")
        raise


def init_db(db_path: Path = None, schema_file: Path = None) -> None:
    """Initializes the database schema from DDL script."""
    target_db = db_path or DATABASE_PATH
    target_schema = schema_file or SCHEMA_PATH
    
    if not target_schema.exists():
        raise FileNotFoundError(f"Schema file not found at: {target_schema}")
        
    with open(target_schema, "r", encoding="utf-8") as f:
        ddl = f.read()

    conn = get_connection(target_db)
    try:
        conn.executescript(ddl)
    finally:
        conn.close()
