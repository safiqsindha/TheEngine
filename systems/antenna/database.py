"""
The Antenna — Database Layer (AN.3)
SQLite storage for Chief Delphi posts, digests, and engine updates.
Team 2950 — The Devastators
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from config import DB_PATH


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Get a database connection with row factory enabled."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Path = DB_PATH) -> None:
    """Create all tables if they don't exist."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS posts (
            post_id INTEGER PRIMARY KEY,
            topic_id INTEGER NOT NULL,
            url TEXT NOT NULL,
            title TEXT NOT NULL,
            author TEXT,
            category_id INTEGER,
            category_name TEXT,
            date_posted DATETIME,
            last_activity DATETIME,
            relevance_score INTEGER DEFAULT 0,
            tier TEXT DEFAULT 'ignore',
            tracked_teams TEXT,
            keywords_matched TEXT,
            tags TEXT,
            like_count INTEGER DEFAULT 0,
            reply_count INTEGER DEFAULT 0,
            views INTEGER DEFAULT 0,
            has_cad_link INTEGER DEFAULT 0,
            has_code_link INTEGER DEFAULT 0,
            has_video_link INTEGER DEFAULT 0,
            summary TEXT,
            raw_excerpt TEXT,
            engine_file_target TEXT,
            action_recommendation TEXT,
            status TEXT DEFAULT 'new',
            reviewed_by TEXT,
            date_reviewed DATETIME,
            date_scraped DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_posts_score ON posts(relevance_score DESC);
        CREATE INDEX IF NOT EXISTS idx_posts_tier ON posts(tier);
        CREATE INDEX IF NOT EXISTS idx_posts_date ON posts(date_posted DESC);
        CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status);
        CREATE INDEX IF NOT EXISTS idx_posts_topic ON posts(topic_id);

        CREATE TABLE IF NOT EXISTS weekly_digests (
            digest_id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_start DATE NOT NULL,
            week_end DATE NOT NULL,
            posts_scanned INTEGER DEFAULT 0,
            posts_relevant INTEGER DEFAULT 0,
            posts_high_priority INTEGER DEFAULT 0,
            digest_text TEXT,
            discord_message_id TEXT,
            date_sent DATETIME
        );

        CREATE TABLE IF NOT EXISTS engine_updates (
            update_id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER REFERENCES posts(post_id),
            engine_file TEXT NOT NULL,
            change_description TEXT,
            date_applied DATETIME DEFAULT CURRENT_TIMESTAMP,
            applied_by TEXT
        );

        CREATE TABLE IF NOT EXISTS scrape_runs (
            run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_time DATETIME NOT NULL,
            end_time DATETIME,
            topics_fetched INTEGER DEFAULT 0,
            topics_new INTEGER DEFAULT 0,
            topics_updated INTEGER DEFAULT 0,
            topics_scored INTEGER DEFAULT 0,
            status TEXT DEFAULT 'running',
            error_message TEXT
        );
    """)

    conn.commit()
    conn.close()


def upsert_post(conn: sqlite3.Connection, post: dict) -> bool:
    """
    Insert or update a post. Returns True if this was a new insert.
    Uses topic_id as the unique key (one row per CD topic).
    """
    cursor = conn.cursor()

    # Check if topic already exists
    existing = cursor.execute(
        "SELECT topic_id, relevance_score FROM posts WHERE topic_id = ?",
        (post["topic_id"],)
    ).fetchone()

    if existing:
        # Update engagement metrics and score if it changed
        cursor.execute("""
            UPDATE posts SET
                like_count = ?,
                reply_count = ?,
                views = ?,
                last_activity = ?,
                relevance_score = ?,
                tier = ?,
                keywords_matched = ?,
                tracked_teams = ?,
                has_cad_link = ?,
                has_code_link = ?,
                has_video_link = ?,
                engine_file_target = ?,
                action_recommendation = ?
            WHERE topic_id = ?
        """, (
            post.get("like_count", 0),
            post.get("reply_count", 0),
            post.get("views", 0),
            post.get("last_activity"),
            post.get("relevance_score", 0),
            post.get("tier", "ignore"),
            post.get("keywords_matched", ""),
            post.get("tracked_teams", ""),
            post.get("has_cad_link", 0),
            post.get("has_code_link", 0),
            post.get("has_video_link", 0),
            post.get("engine_file_target", ""),
            post.get("action_recommendation", ""),
            post["topic_id"],
        ))
        return False
    else:
        cursor.execute("""
            INSERT INTO posts (
                topic_id, url, title, author, category_id, category_name,
                date_posted, last_activity, relevance_score, tier,
                tracked_teams, keywords_matched, tags,
                like_count, reply_count, views,
                has_cad_link, has_code_link, has_video_link,
                summary, raw_excerpt,
                engine_file_target, action_recommendation
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            post["topic_id"],
            post.get("url", ""),
            post.get("title", ""),
            post.get("author", ""),
            post.get("category_id"),
            post.get("category_name", ""),
            post.get("date_posted"),
            post.get("last_activity"),
            post.get("relevance_score", 0),
            post.get("tier", "ignore"),
            post.get("tracked_teams", ""),
            post.get("keywords_matched", ""),
            post.get("tags", ""),
            post.get("like_count", 0),
            post.get("reply_count", 0),
            post.get("views", 0),
            post.get("has_cad_link", 0),
            post.get("has_code_link", 0),
            post.get("has_video_link", 0),
            post.get("summary", ""),
            post.get("raw_excerpt", ""),
            post.get("engine_file_target", ""),
            post.get("action_recommendation", ""),
        ))
        return True


def get_posts_since(conn: sqlite3.Connection, since: datetime,
                    min_score: int = 0) -> list[dict]:
    """Get posts created since a given date with minimum score."""
    cursor = conn.cursor()
    rows = cursor.execute("""
        SELECT * FROM posts
        WHERE date_posted >= ? AND relevance_score >= ?
        ORDER BY relevance_score DESC, like_count DESC
    """, (since.isoformat(), min_score)).fetchall()
    return [dict(row) for row in rows]


def get_weekly_posts(conn: sqlite3.Connection, min_score: int = 8) -> list[dict]:
    """Get all relevant posts from the last 7 days for the weekly digest."""
    since = datetime.utcnow() - timedelta(days=7)
    return get_posts_since(conn, since, min_score)


def get_high_priority_posts(conn: sqlite3.Connection,
                            status: str = "new") -> list[dict]:
    """Get unreviewed high-priority and critical posts."""
    cursor = conn.cursor()
    rows = cursor.execute("""
        SELECT * FROM posts
        WHERE tier IN ('high', 'critical') AND status = ?
        ORDER BY relevance_score DESC
    """, (status,)).fetchall()
    return [dict(row) for row in rows]


def get_tracked_team_activity(conn: sqlite3.Connection,
                              days: int = 7) -> list[dict]:
    """Get posts mentioning tracked teams from the last N days."""
    since = datetime.utcnow() - timedelta(days=days)
    cursor = conn.cursor()
    rows = cursor.execute("""
        SELECT * FROM posts
        WHERE tracked_teams != '' AND date_scraped >= ?
        ORDER BY relevance_score DESC
    """, (since.isoformat(),)).fetchall()
    return [dict(row) for row in rows]


def mark_post_reviewed(conn: sqlite3.Connection, topic_id: int,
                       reviewed_by: str, status: str = "reviewed") -> None:
    """Mark a post as reviewed."""
    conn.execute("""
        UPDATE posts SET status = ?, reviewed_by = ?, date_reviewed = ?
        WHERE topic_id = ?
    """, (status, reviewed_by, datetime.utcnow().isoformat(), topic_id))
    conn.commit()


def log_scrape_run(conn: sqlite3.Connection, **kwargs) -> int:
    """Log the start of a scrape run, return run_id."""
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO scrape_runs (start_time, status)
        VALUES (?, 'running')
    """, (datetime.utcnow().isoformat(),))
    conn.commit()
    return cursor.lastrowid


def update_scrape_run(conn: sqlite3.Connection, run_id: int, **kwargs) -> None:
    """Update a scrape run with results."""
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [run_id]
    conn.execute(f"UPDATE scrape_runs SET {sets} WHERE run_id = ?", values)
    conn.commit()


def get_db_stats(conn: sqlite3.Connection) -> dict:
    """Get overall database statistics."""
    cursor = conn.cursor()
    stats = {}
    stats["total_posts"] = cursor.execute(
        "SELECT COUNT(*) FROM posts").fetchone()[0]
    stats["relevant_posts"] = cursor.execute(
        "SELECT COUNT(*) FROM posts WHERE relevance_score >= 8").fetchone()[0]
    stats["high_priority"] = cursor.execute(
        "SELECT COUNT(*) FROM posts WHERE tier IN ('high', 'critical')").fetchone()[0]
    stats["unreviewed"] = cursor.execute(
        "SELECT COUNT(*) FROM posts WHERE status = 'new' AND relevance_score >= 8").fetchone()[0]
    stats["total_digests"] = cursor.execute(
        "SELECT COUNT(*) FROM weekly_digests").fetchone()[0]
    stats["total_scrape_runs"] = cursor.execute(
        "SELECT COUNT(*) FROM scrape_runs").fetchone()[0]
    return stats


if __name__ == "__main__":
    print(f"Initializing database at {DB_PATH}")
    init_db()
    conn = get_connection()
    stats = get_db_stats(conn)
    print(f"Database ready. Stats: {stats}")
    conn.close()
