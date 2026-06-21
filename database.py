import sqlite3
import os
import hashlib
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DEFAULT_DB_PATH = os.getenv("DATABASE_PATH", "memory.db")

def get_db(db_path: str = None) -> sqlite3.Connection:
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    
    # Establish connection with a 30-second timeout to handle concurrency
    conn = sqlite3.connect(db_path, timeout=30.0)
    
    # Configure production SQLite settings
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    
    return conn

def hash_api_key(api_key: str) -> str:
    """Return SHA-256 hash of the API key for secure verification."""
    return hashlib.sha256(api_key.encode('utf-8')).hexdigest()

def initialize_db(conn: sqlite3.Connection):
    """Create all schema tables if they do not exist, and enforce indices."""
    
    # Table 1: Namespaces isolation table
    conn.execute("""
    CREATE TABLE IF NOT EXISTS agent_namespaces (
        agent_id      TEXT PRIMARY KEY,
        owner_id      TEXT NOT NULL,
        api_key_hash  TEXT NOT NULL,
        created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    # Table 2: Raw memory events table (append-only)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS memory_events (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id      TEXT NOT NULL,
        memory_class  TEXT NOT NULL CHECK (memory_class IN ('library', 'episodic')),
        memory_type   TEXT NOT NULL,
        content       TEXT NOT NULL,
        embedding     BLOB,
        source        TEXT,
        confidence    REAL DEFAULT 1.0,
        created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        superseded_by INTEGER REFERENCES memory_events(id)
    );
    """)
    
    # Create required indices for event storage performance
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_agent_class ON memory_events(agent_id, memory_class);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_created ON memory_events(created_at);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_agent_type ON memory_events(agent_id, memory_type);")
    
    # Rollup Table 3: Day summaries
    conn.execute("""
    CREATE TABLE IF NOT EXISTS memory_days (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id    TEXT NOT NULL,
        day_date    DATE NOT NULL,
        summary     TEXT NOT NULL,
        embedding   BLOB,
        source_ids  TEXT,
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(agent_id, day_date)
    );
    """)
    
    # Rollup Table 4: Month summaries
    conn.execute("""
    CREATE TABLE IF NOT EXISTS memory_months (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id    TEXT NOT NULL,
        month_date  TEXT NOT NULL, -- 'YYYY-MM'
        summary     TEXT NOT NULL,
        embedding   BLOB,
        source_ids  TEXT,
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(agent_id, month_date)
    );
    """)
    
    # Rollup Table 5: Year summaries
    conn.execute("""
    CREATE TABLE IF NOT EXISTS memory_years (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id    TEXT NOT NULL,
        year        INTEGER NOT NULL,
        summary     TEXT NOT NULL,
        embedding   BLOB,
        source_ids  TEXT,
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(agent_id, year)
    );
    """)
    
    # Table 6: Table of Contents Index
    conn.execute("""
    CREATE TABLE IF NOT EXISTS memory_toc (
        agent_id      TEXT NOT NULL,
        period_type   TEXT NOT NULL CHECK (period_type IN ('day','month','year')),
        period_key    TEXT NOT NULL,
        record_id     INTEGER NOT NULL,
        PRIMARY KEY (agent_id, period_type, period_key)
    );
    """)
    
    # Table 7: Conflicts table
    conn.execute("""
    CREATE TABLE IF NOT EXISTS memory_conflicts (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        old_memory_id INTEGER NOT NULL,
        new_memory_id INTEGER NOT NULL,
        reason        TEXT,
        status        TEXT DEFAULT 'pending' CHECK (status IN ('pending','resolved')),
        created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    conn.commit()

# Core Database Insertion / Query Operations
def register_agent_namespace(conn: sqlite3.Connection, agent_id: str, owner_id: str, api_key: str):
    """Register an agent's namespace, locking it to a hashed API key and owner."""
    api_key_hash = hash_api_key(api_key)
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("""
            INSERT OR REPLACE INTO agent_namespaces (agent_id, owner_id, api_key_hash)
            VALUES (?, ?, ?)
        """, (agent_id, owner_id, api_key_hash))
        conn.commit()
    except Exception:
        conn.rollback()
        raise

def verify_namespace_access(conn: sqlite3.Connection, agent_id: str, api_key: str) -> bool:
    """Verify that the provided API key has access to write/read the specified agent namespace."""
    api_key_hash = hash_api_key(api_key)
    row = conn.execute(
        "SELECT owner_id FROM agent_namespaces WHERE agent_id = ? AND api_key_hash = ?",
        (agent_id, api_key_hash)
    ).fetchone()
    return row is not None

def get_namespace_owner(conn: sqlite3.Connection, agent_id: str) -> str:
    """Get owner_id of the agent namespace."""
    row = conn.execute(
        "SELECT owner_id FROM agent_namespaces WHERE agent_id = ?",
        (agent_id,)
    ).fetchone()
    return row["owner_id"] if row else None

def remember(conn: sqlite3.Connection, agent_id: str, memory_class: str, memory_type: str, 
             content: str, source: str = None, confidence: float = 1.0, embedding: bytes = None) -> int:
    """Write an append-only memory event into the database. Returns insertion ID."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        cursor = conn.execute(
            """INSERT INTO memory_events
               (agent_id, memory_class, memory_type, content, source, confidence, embedding)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (agent_id, memory_class, memory_type, content, source, confidence, embedding)
        )
        conn.commit()
        return cursor.lastrowid
    except Exception:
        conn.rollback()
        raise

def supersede(conn: sqlite3.Connection, old_id: int, new_id: int):
    """Mark a memory event as superseded by a newer memory event."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "UPDATE memory_events SET superseded_by = ? WHERE id = ?",
            (new_id, old_id)
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
