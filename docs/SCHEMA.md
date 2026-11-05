# Database schema

SQLite by default (`DATABASE_URL`, offline-friendly); Postgres supported via
`DATABASE_URL=postgresql://...` (`src/db.py` holds both DDL variants).

```sql
CREATE TABLE tickets (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    customer_id TEXT DEFAULT '',
    label TEXT DEFAULT '',
    confidence REAL DEFAULT 0,
    runner_up TEXT DEFAULT '',
    status TEXT DEFAULT 'open',          -- open | needs_review | abstained | reviewed
    duplicate_of TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE audit_events (
    id TEXT PRIMARY KEY,
    ticket_id TEXT NOT NULL,
    event TEXT NOT NULL,                 -- submitted | routed | reviewed | ...
    payload TEXT NOT NULL,               -- JSON rationale snapshot
    created_at TEXT NOT NULL
);
CREATE INDEX idx_audit_ticket ON audit_events(ticket_id);
CREATE INDEX idx_tickets_status ON tickets(status);
```

The audit table is append-only: every routing/review decision keeps its
rationale for later inspection and evals.
