"""Persistence: tickets + append-only audit trail.

SQLite by default (offline, zero-config). Postgres when DATABASE_URL starts
with postgres:// — requires psycopg (pip install psycopg[binary]).
Schema is created on first use; audit events are append-only.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import Settings, get_settings


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS tickets (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    customer_id TEXT DEFAULT '',
    label TEXT DEFAULT '',
    confidence REAL DEFAULT 0,
    runner_up TEXT DEFAULT '',
    status TEXT DEFAULT 'open',
    duplicate_of TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
    id TEXT PRIMARY KEY,
    ticket_id TEXT NOT NULL,
    event TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_ticket ON audit_events(ticket_id);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
"""

SCHEMA_POSTGRES = """
CREATE TABLE IF NOT EXISTS tickets (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    customer_id TEXT DEFAULT '',
    label TEXT DEFAULT '',
    confidence DOUBLE PRECISION DEFAULT 0,
    runner_up TEXT DEFAULT '',
    status TEXT DEFAULT 'open',
    duplicate_of TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
    id TEXT PRIMARY KEY,
    ticket_id TEXT NOT NULL,
    event TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_ticket ON audit_events(ticket_id);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
"""


class TicketStore:
    """Small sync store with a SQLite/Postgres switch."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._pg = None  # lazy psycopg connection
        if not self.settings.is_postgres:
            Path(self.settings.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    # -- connection helpers -------------------------------------------------
    def _pg_conn(self):  # type: ignore[no-untyped-def]
        if self._pg is None:
            import psycopg  # type: ignore

            self._pg = psycopg.connect(self.settings.database_url, autocommit=True)
        return self._pg

    def _sqlite_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.settings.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _execute(self, sql: str, params: tuple = (), fetch: str = "none") -> Any:
        if self.settings.is_postgres:
            conn = self._pg_conn()
            # translate ? placeholders to %s
            sql = sql.replace("?", "%s")
            with conn.cursor() as cur:
                cur.execute(sql, params)
                if fetch == "one":
                    row = cur.fetchone()
                    return dict(zip([d[0] for d in cur.description], row)) if row else None
                if fetch == "all":
                    cols = [d[0] for d in cur.description]
                    return [dict(zip(cols, r)) for r in cur.fetchall()]
            return None
        conn = self._sqlite_conn()
        try:
            cur = conn.execute(sql, params)
            if fetch == "one":
                row = cur.fetchone()
                return dict(row) if row else None
            if fetch == "all":
                return [dict(r) for r in cur.fetchall()]
            conn.commit()
            return None
        finally:
            conn.close()

    # -- schema --------------------------------------------------------------
    def init_db(self) -> None:
        schema = SCHEMA_POSTGRES if self.settings.is_postgres else SCHEMA_SQLITE
        if self.settings.is_postgres:
            conn = self._pg_conn()
            with conn.cursor() as cur:
                cur.execute(schema)
        else:
            conn = self._sqlite_conn()
            try:
                conn.executescript(schema)
                conn.commit()
            finally:
                conn.close()

    # -- tickets --------------------------------------------------------------
    def create_ticket(
        self,
        title: str,
        body: str,
        customer_id: str = "",
        label: str = "",
        confidence: float = 0.0,
        runner_up: str = "",
        status: str = "open",
        duplicate_of: str = "",
    ) -> dict[str, Any]:
        ticket_id = f"t_{uuid.uuid4().hex[:12]}"
        now = _now_iso()
        self._execute(
            """INSERT INTO tickets
               (id, title, body, customer_id, label, confidence, runner_up,
                status, duplicate_of, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (ticket_id, title, body, customer_id, label, confidence, runner_up,
             status, duplicate_of, now, now),
        )
        self.add_audit(ticket_id, "created", {"title": title, "status": status})
        row = self.get_ticket(ticket_id)
        assert row is not None
        return row

    def get_ticket(self, ticket_id: str) -> dict[str, Any] | None:
        return self._execute(
            "SELECT * FROM tickets WHERE id = ?", (ticket_id,), fetch="one"
        )

    def update_ticket(self, ticket_id: str, **fields: Any) -> dict[str, Any] | None:
        allowed = {"label", "confidence", "runner_up", "status", "duplicate_of"}
        sets = [f"{k} = ?" for k in fields if k in allowed]
        params = [fields[k] for k in fields if k in allowed]
        if sets:
            sets.append("updated_at = ?")
            params.append(_now_iso())
            self._execute(
                f"UPDATE tickets SET {', '.join(sets)} WHERE id = ?",
                (*params, ticket_id),
            )
        return self.get_ticket(ticket_id)

    def list_review_queue(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._execute(
            "SELECT * FROM tickets WHERE status IN ('needs_review', 'abstained')"
            " ORDER BY created_at DESC LIMIT ?",
            (limit,),
            fetch="all",
        ) or []

    def list_tickets(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._execute(
            "SELECT * FROM tickets ORDER BY created_at DESC LIMIT ?",
            (limit,),
            fetch="all",
        ) or []

    # -- audit (append-only) ---------------------------------------------------
    def add_audit(self, ticket_id: str, event: str, payload: dict[str, Any]) -> str:
        event_id = f"e_{uuid.uuid4().hex[:12]}"
        self._execute(
            "INSERT INTO audit_events (id, ticket_id, event, payload, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (event_id, ticket_id, event, json.dumps(payload), _now_iso()),
        )
        return event_id

    def list_audit(self, ticket_id: str) -> list[dict[str, Any]]:
        return self._execute(
            "SELECT * FROM audit_events WHERE ticket_id = ? ORDER BY created_at ASC",
            (ticket_id,),
            fetch="all",
        ) or []

    # -- misc ------------------------------------------------------------------
    def counts_by_status(self) -> dict[str, int]:
        rows = self._execute(
            "SELECT status, COUNT(*) AS n FROM tickets GROUP BY status", fetch="all"
        ) or []
        return {r["status"]: r["n"] for r in rows}

    def wait_ready(self, timeout_s: float = 5.0) -> bool:
        """Poll until the DB answers (useful for Postgres in CI)."""
        start = time.time()
        while time.time() - start < timeout_s:
            try:
                self._execute("SELECT 1", fetch="one")
                return True
            except Exception:
                time.sleep(0.2)
        return False
