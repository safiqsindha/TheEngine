"""SQLite-backed spend tracker for the Engine Anthropic proxy.

One row per API request. Daily and total spend are computed by summing
cost_usd for the user. SQLite is plenty fast for the volumes a high-school
team will generate (a few thousand rows per month).
"""

import sqlite3
from datetime import date
from pathlib import Path
from threading import Lock
from typing import Optional


SCHEMA = """
CREATE TABLE IF NOT EXISTS spend (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user ON spend(user);
CREATE INDEX IF NOT EXISTS idx_user_date ON spend(user, created_at);
"""


class Storage:
    def __init__(self, db_path: str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self.lock = Lock()
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        # isolation_level=None gives autocommit; safe for our small writes.
        return sqlite3.connect(self.db_path, isolation_level=None)

    def record(
        self,
        user: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_creation_tokens: int,
        cache_read_tokens: int,
        cost_usd: float,
    ) -> None:
        with self.lock, self._conn() as conn:
            conn.execute(
                """
                INSERT INTO spend (
                    user, model,
                    input_tokens, output_tokens,
                    cache_creation_tokens, cache_read_tokens,
                    cost_usd
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user,
                    model,
                    input_tokens,
                    output_tokens,
                    cache_creation_tokens,
                    cache_read_tokens,
                    cost_usd,
                ),
            )

    def get_daily_spend(self, user: str, on_date: Optional[date] = None) -> float:
        on_date = on_date or date.today()
        with self.lock, self._conn() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(cost_usd), 0)
                FROM spend
                WHERE user = ? AND DATE(created_at) = ?
                """,
                (user, on_date.isoformat()),
            ).fetchone()
            return float(row[0])

    def get_total_spend(self, user: str) -> float:
        with self.lock, self._conn() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) FROM spend WHERE user = ?",
                (user,),
            ).fetchone()
            return float(row[0])

    def get_request_count(self, user: str) -> int:
        with self.lock, self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM spend WHERE user = ?", (user,)
            ).fetchone()
            return int(row[0])
