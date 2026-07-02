"""SQLite storage for the surveillance pipeline: cycles, items, seen_ids."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS cycles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT NOT NULL,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    disease_groups TEXT NOT NULL,   -- JSON list of group keys
    queries_json TEXT NOT NULL,     -- JSON: exact queries/filters used, for reproducibility
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id INTEGER NOT NULL REFERENCES cycles(id),
    disease_group TEXT NOT NULL,
    source_type TEXT NOT NULL,      -- 'pubmed' | 'ctgov'
    pmid TEXT,
    doi TEXT,
    nct TEXT,
    title TEXT,
    journal TEXT,
    pub_date TEXT,
    record_type TEXT,
    raw_payload TEXT NOT NULL,      -- JSON, verbatim source record
    status TEXT NOT NULL,           -- 'included' | 'needs_review' | 'excluded' | 'flagged_retraction'
    llm_output TEXT,                -- JSON: parsed model response
    retrieved_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS seen_ids (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    id_type TEXT NOT NULL,          -- 'pmid' | 'doi' | 'nct'
    id_value TEXT NOT NULL,
    disease_group TEXT NOT NULL,
    first_seen_cycle_id INTEGER NOT NULL REFERENCES cycles(id),
    last_checked_at TEXT,
    retracted INTEGER NOT NULL DEFAULT 0,
    retraction_note TEXT,
    UNIQUE(id_type, id_value)
);

CREATE INDEX IF NOT EXISTS idx_items_cycle ON items(cycle_id);
CREATE INDEX IF NOT EXISTS idx_seen_type_value ON seen_ids(id_type, id_value);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


@contextmanager
def connect(path: str):
    conn = get_connection(path)
    try:
        init_db(conn)
        yield conn
    finally:
        conn.close()


def start_cycle(conn, run_date: str, window_start: str, window_end: str,
                 disease_groups: list[str], queries: dict) -> int:
    cur = conn.execute(
        "INSERT INTO cycles (run_date, window_start, window_end, disease_groups, queries_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (run_date, window_start, window_end, json.dumps(disease_groups), json.dumps(queries), now_iso()),
    )
    conn.commit()
    return cur.lastrowid


def is_seen(conn, id_type: str, id_value: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM seen_ids WHERE id_type = ? AND id_value = ?", (id_type, id_value)
    ).fetchone()
    return row is not None


def mark_seen(conn, id_type: str, id_value: str, disease_group: str, cycle_id: int) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO seen_ids (id_type, id_value, disease_group, first_seen_cycle_id, last_checked_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (id_type, id_value, disease_group, cycle_id, now_iso()),
    )
    conn.commit()


def get_all_seen_pmids(conn) -> list[str]:
    rows = conn.execute("SELECT id_value FROM seen_ids WHERE id_type = 'pmid'").fetchall()
    return [r["id_value"] for r in rows]


def update_retraction_status(conn, pmid: str, retracted: bool, note: str = "") -> None:
    conn.execute(
        "UPDATE seen_ids SET retracted = ?, retraction_note = ?, last_checked_at = ? "
        "WHERE id_type = 'pmid' AND id_value = ?",
        (1 if retracted else 0, note, now_iso(), pmid),
    )
    conn.commit()


def insert_item(conn, cycle_id: int, disease_group: str, source_type: str,
                 pmid: str | None, doi: str | None, nct: str | None,
                 title: str, journal: str | None, pub_date: str | None,
                 record_type: str | None, raw_payload: dict, status: str,
                 llm_output: dict | None) -> int:
    cur = conn.execute(
        "INSERT INTO items (cycle_id, disease_group, source_type, pmid, doi, nct, title, journal, "
        "pub_date, record_type, raw_payload, status, llm_output, retrieved_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (cycle_id, disease_group, source_type, pmid, doi, nct, title, journal, pub_date,
         record_type, json.dumps(raw_payload), status,
         json.dumps(llm_output) if llm_output is not None else None, now_iso()),
    )
    conn.commit()
    return cur.lastrowid


def get_items_for_cycle(conn, cycle_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM items WHERE cycle_id = ? ORDER BY disease_group, record_type", (cycle_id,)
    ).fetchall()
