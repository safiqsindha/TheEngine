#!/usr/bin/env python3
"""
The Antenna — Main Orchestrator
Chief Delphi Intelligence Watcher for THE ENGINE
Team 2950 — The Devastators

Usage:
    python3 antenna.py scan [N]        # Scan CD, score topics (N pages, default 10)
    python3 antenna.py search <query>  # Search CD for a specific topic
    python3 antenna.py digest          # Generate and print weekly digest
    python3 antenna.py digest --send   # Generate and send digest to Discord
    python3 antenna.py stats           # Show database statistics
    python3 antenna.py alerts          # Show unreviewed high-priority posts
    python3 antenna.py top [N]         # Show top N scored posts
    python3 antenna.py review <id>     # Mark a topic as reviewed
    python3 antenna.py pull <id>       # Mark a topic as pulled into Engine
    python3 antenna.py scheduler       # Run the automated scheduler (blocks)
    python3 antenna.py mode [mode]     # Show or set scan mode (normal/kickoff/build/competition/postseason)
"""

import re
import sys
import logging
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import (
    DB_PATH, LOG_PATH, SCORE_THRESHOLDS, SCAN_MODE, SCAN_MODES,
    SCAN_HOUR, DIGEST_HOUR, MECHANISM_KEYWORDS,
)
from scraper import CDScraper, fetch_and_filter_recent
from scorer import score_topic
from database import (
    init_db, get_connection, upsert_post,
    get_weekly_posts, get_high_priority_posts,
    get_tracked_team_activity, get_db_stats,
    log_scrape_run, update_scrape_run,
    mark_post_reviewed,
)
from digest import format_weekly_digest, format_critical_alert
from discord_webhook import send_digest as discord_send_digest, send_critical_alert

# ── Logging setup ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(str(LOG_PATH)),
    ]
)
logger = logging.getLogger("antenna")


# ═══════════════════════════════════════════════════════════════════
# SCAN
# ═══════════════════════════════════════════════════════════════════

def cmd_scan(max_pages: int = 10):
    """
    Main scan routine: fetch topics from CD, score them, store in DB.
    For high-priority posts, fetches full topic detail for deeper analysis.
    """
    logger.info("=" * 60)
    logger.info("THE ANTENNA — Starting scan")
    logger.info(f"  Mode: {SCAN_MODE} | Max pages: {max_pages}")
    logger.info("=" * 60)

    init_db()
    conn = get_connection()
    run_id = log_scrape_run(conn)

    try:
        scraper = CDScraper()
        topics = fetch_and_filter_recent(scraper, max_pages=max_pages)
        logger.info(f"Fetched {len(topics)} topics from Chief Delphi")

        new_count = 0
        updated_count = 0
        scored_count = 0
        critical_alerts = []
        high_priority_ids = []

        for topic in topics:
            score_result = score_topic(topic)
            scored_count += 1
            topic.update(score_result)

            is_new = upsert_post(conn, topic)
            if is_new:
                new_count += 1
            else:
                updated_count += 1

            if score_result["tier"] == "critical" and is_new:
                critical_alerts.append(topic)

            # Track high-priority posts for detail fetching
            if score_result["relevance_score"] >= 12 and is_new:
                high_priority_ids.append(topic["topic_id"])

            if score_result["relevance_score"] >= SCORE_THRESHOLDS["ignore"] + 1:
                logger.info(
                    f"  [{score_result['tier'].upper()}] "
                    f"Score {score_result['relevance_score']}: "
                    f"{topic['title'][:60]}"
                )

        conn.commit()

        # Fetch full detail for high-priority posts (deeper keyword analysis)
        if high_priority_ids:
            logger.info(f"Fetching detail for {len(high_priority_ids)} high-priority posts...")
            for topic_id in high_priority_ids[:10]:  # Cap at 10 to be respectful
                detail = scraper.fetch_topic_detail(topic_id)
                if detail and detail.get("op_cooked"):
                    # Re-score with full body content
                    # Strip HTML tags for keyword matching
                    body_text = re.sub(r'<[^>]+>', ' ', detail["op_cooked"])
                    # Find the topic in our list
                    for topic in topics:
                        if topic["topic_id"] == topic_id:
                            topic["excerpt"] = f"{topic['title']} {body_text[:2000]}"
                            topic["author"] = detail.get("op_username", topic.get("author", ""))
                            rescore = score_topic(topic)
                            if rescore["relevance_score"] > topic.get("relevance_score", 0):
                                logger.info(
                                    f"  Re-scored {topic['title'][:40]}: "
                                    f"{topic.get('relevance_score')} → {rescore['relevance_score']}"
                                )
                                topic.update(rescore)
                                upsert_post(conn, topic)
                            break

            conn.commit()

        # Send critical alerts
        for alert_topic in critical_alerts:
            alert_text = format_critical_alert(alert_topic)
            logger.info(f"CRITICAL ALERT: {alert_topic['title']}")
            send_critical_alert(alert_text)

        # Update run log
        update_scrape_run(conn, run_id,
            end_time=datetime.utcnow().isoformat(),
            topics_fetched=len(topics),
            topics_new=new_count,
            topics_updated=updated_count,
            topics_scored=scored_count,
            status="complete",
        )

        stats = get_db_stats(conn)
        logger.info("")
        logger.info("=" * 60)
        logger.info("SCAN COMPLETE")
        logger.info(f"  Topics fetched:  {len(topics)}")
        logger.info(f"  New topics:      {new_count}")
        logger.info(f"  Updated topics:  {updated_count}")
        logger.info(f"  Detail fetched:  {min(len(high_priority_ids), 10)}")
        logger.info(f"  Critical alerts: {len(critical_alerts)}")
        logger.info(f"  Total in DB:     {stats['total_posts']}")
        logger.info(f"  Relevant in DB:  {stats['relevant_posts']}")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Scan failed: {e}", exc_info=True)
        update_scrape_run(conn, run_id,
            end_time=datetime.utcnow().isoformat(),
            status="error",
            error_message=str(e),
        )
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════
# SEARCH
# ═══════════════════════════════════════════════════════════════════

def cmd_search(query: str):
    """Search Chief Delphi for a specific topic, score and display results."""
    scraper = CDScraper()
    results = scraper.search_topics(query, max_results=15)

    if not results:
        print(f"No results found for: {query}")
        return

    # Score each result
    for topic in results:
        score_result = score_topic(topic)
        topic.update(score_result)

    results.sort(key=lambda t: t["relevance_score"], reverse=True)

    print("=" * 60)
    print(f"SEARCH RESULTS: {query}")
    print(f"Found {len(results)} topics")
    print("=" * 60)

    for i, r in enumerate(results, 1):
        tier_badge = {
            "critical": "!!!",
            "high": "!! ",
            "notable": "!  ",
            "ignore": "   ",
        }.get(r["tier"], "   ")

        print(f"\n  {tier_badge} {i}. {r['title'][:55]}")
        print(f"       {r['url']}")
        print(f"       Score: {r['relevance_score']} | "
              f"Likes: {r['like_count']} | Replies: {r['reply_count']}")
        if r.get("keywords_matched"):
            print(f"       Keywords: {r['keywords_matched'][:60]}")
        if r.get("engine_file_target"):
            print(f"       Target: {r['engine_file_target']}")
        if r.get("action_recommendation"):
            print(f"       Action: {r['action_recommendation']}")


# ═══════════════════════════════════════════════════════════════════
# COMMUNITY TRENDS
# ═══════════════════════════════════════════════════════════════════

def detect_trends(posts: list[dict], top_n: int = 5) -> list[dict]:
    """
    Detect community trends from this week's posts.
    Groups by keyword clusters and counts thread frequency.
    """
    keyword_counter = Counter()
    keyword_posts = {}

    for post in posts:
        kw_str = post.get("keywords_matched", "")
        if not kw_str:
            continue
        keywords = [k.strip() for k in kw_str.split(",")]
        for kw in keywords:
            keyword_counter[kw] += 1
            keyword_posts.setdefault(kw, []).append(post["title"][:50])

    trends = []
    for kw, count in keyword_counter.most_common(top_n):
        if count >= 2:  # Only show trends with 2+ posts
            sample_titles = keyword_posts[kw][:3]
            trends.append({
                "keyword": kw,
                "count": count,
                "sample_titles": sample_titles,
            })

    return trends


# ═══════════════════════════════════════════════════════════════════
# DIGEST
# ═══════════════════════════════════════════════════════════════════

def cmd_digest(send_to_discord: bool = False):
    """Generate the weekly digest with community trends."""
    init_db()
    conn = get_connection()

    posts = get_weekly_posts(conn, min_score=8)
    stats = get_db_stats(conn)

    if not posts:
        print("No relevant posts found in the last 7 days.")
        print("Run 'python3 antenna.py scan' first.")
        conn.close()
        return

    # Detect trends
    trends = detect_trends(posts)

    digest = format_weekly_digest(
        posts=posts,
        total_scanned=stats["total_posts"],
        db_total=stats["total_posts"],
        trends=trends,
    )

    print(digest)

    if send_to_discord:
        print("\nSending to Discord...")
        success = discord_send_digest(digest)
        if success:
            print("Digest sent to Discord!")
        else:
            print("Failed to send to Discord. Check webhook URL.")

    conn.close()


# ═══════════════════════════════════════════════════════════════════
# STATS / ALERTS / TOP
# ═══════════════════════════════════════════════════════════════════

def cmd_stats():
    """Show database statistics."""
    init_db()
    conn = get_connection()
    stats = get_db_stats(conn)

    print("=" * 40)
    print("THE ANTENNA — Database Stats")
    print("=" * 40)
    for key, value in stats.items():
        label = key.replace("_", " ").title()
        print(f"  {label}: {value}")
    print(f"\n  Scan mode: {SCAN_MODE}")
    print(f"  Mode info: {SCAN_MODES.get(SCAN_MODE, {}).get('description', 'unknown')}")

    conn.close()


def cmd_alerts():
    """Show unreviewed high-priority posts."""
    init_db()
    conn = get_connection()
    posts = get_high_priority_posts(conn)

    if not posts:
        print("No unreviewed high-priority posts.")
        conn.close()
        return

    print("=" * 60)
    print(f"UNREVIEWED HIGH PRIORITY POSTS ({len(posts)})")
    print("=" * 60)

    for post in posts:
        print(f"\n[{post['tier'].upper()}] Score: {post['relevance_score']} | ID: {post['topic_id']}")
        print(f"  {post['title']}")
        print(f"  {post['url']}")
        print(f"  Likes: {post['like_count']} | Replies: {post['reply_count']}")
        if post.get("tracked_teams"):
            print(f"  Teams: {post['tracked_teams']}")
        if post.get("engine_file_target"):
            print(f"  Target: {post['engine_file_target']}")
        if post.get("action_recommendation"):
            print(f"  Action: {post['action_recommendation']}")

    print(f"\nMark as reviewed: python3 antenna.py review <topic_id>")
    print(f"Mark as pulled:   python3 antenna.py pull <topic_id>")

    conn.close()


def cmd_top(n: int = 20):
    """Show top N scored posts in the database."""
    init_db()
    conn = get_connection()

    cursor = conn.cursor()
    rows = cursor.execute("""
        SELECT * FROM posts
        WHERE relevance_score > 0
        ORDER BY relevance_score DESC, like_count DESC
        LIMIT ?
    """, (n,)).fetchall()

    if not rows:
        print("No scored posts in database. Run 'python3 antenna.py scan' first.")
        conn.close()
        return

    print("=" * 60)
    print(f"TOP {n} SCORED POSTS")
    print("=" * 60)

    for row in rows:
        post = dict(row)
        tier_badge = {
            "critical": "!!!",
            "high": "!! ",
            "notable": "!  ",
            "ignore": "   ",
        }.get(post["tier"], "   ")

        status_badge = ""
        if post["status"] == "reviewed":
            status_badge = " [REVIEWED]"
        elif post["status"] == "pulled":
            status_badge = " [PULLED]"

        print(f"\n  {tier_badge} Score: {post['relevance_score']:3d} | "
              f"Likes: {post['like_count']:4d} | "
              f"{post['title'][:50]}{status_badge}")
        if post.get("tracked_teams"):
            print(f"       Teams: {post['tracked_teams']}")
        if post.get("keywords_matched"):
            print(f"       Keywords: {post['keywords_matched'][:60]}")

    conn.close()


# ═══════════════════════════════════════════════════════════════════
# REVIEW / PULL WORKFLOW
# ═══════════════════════════════════════════════════════════════════

def cmd_review(topic_id: int):
    """Mark a post as reviewed."""
    init_db()
    conn = get_connection()

    # Verify the topic exists
    row = conn.execute(
        "SELECT title, relevance_score, status FROM posts WHERE topic_id = ?",
        (topic_id,)
    ).fetchone()

    if not row:
        print(f"Topic {topic_id} not found in database.")
        conn.close()
        return

    if row["status"] == "reviewed":
        print(f"Already reviewed: {row['title']}")
        conn.close()
        return

    mark_post_reviewed(conn, topic_id, reviewed_by="mentor", status="reviewed")
    print(f"Marked as REVIEWED: {row['title']}")
    print(f"  Score: {row['relevance_score']}")
    conn.close()


def cmd_pull(topic_id: int):
    """Mark a post as pulled into The Engine."""
    init_db()
    conn = get_connection()

    row = conn.execute(
        "SELECT title, relevance_score, engine_file_target, action_recommendation FROM posts WHERE topic_id = ?",
        (topic_id,)
    ).fetchone()

    if not row:
        print(f"Topic {topic_id} not found in database.")
        conn.close()
        return

    mark_post_reviewed(conn, topic_id, reviewed_by="mentor", status="pulled")

    # Log the engine update
    conn.execute("""
        INSERT INTO engine_updates (post_id, engine_file, change_description)
        SELECT post_id, engine_file_target, action_recommendation
        FROM posts WHERE topic_id = ?
    """, (topic_id,))
    conn.commit()

    print(f"Marked as PULLED INTO ENGINE: {row['title']}")
    if row["engine_file_target"]:
        print(f"  Target: {row['engine_file_target']}")
    if row["action_recommendation"]:
        print(f"  Action: {row['action_recommendation']}")
    conn.close()


# ═══════════════════════════════════════════════════════════════════
# SCAN MODE
# ═══════════════════════════════════════════════════════════════════

def cmd_mode(new_mode: str = None):
    """Show or set scan mode."""
    if not new_mode:
        print(f"Current mode: {SCAN_MODE}")
        print(f"Description:  {SCAN_MODES.get(SCAN_MODE, {}).get('description', 'unknown')}")
        print(f"\nAvailable modes:")
        for mode, info in SCAN_MODES.items():
            marker = " ←" if mode == SCAN_MODE else ""
            print(f"  {mode:14s} {info['description']}{marker}")
        print(f"\nTo change: set ANTENNA_SCAN_MODE in .env file")
        return

    if new_mode not in SCAN_MODES:
        print(f"Unknown mode: {new_mode}")
        print(f"Available: {', '.join(SCAN_MODES.keys())}")
        return

    # Update .env file
    env_path = Path(__file__).parent / ".env"
    lines = []
    found = False
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                if line.strip().startswith("ANTENNA_SCAN_MODE="):
                    lines.append(f"ANTENNA_SCAN_MODE={new_mode}\n")
                    found = True
                else:
                    lines.append(line)
    if not found:
        lines.append(f"ANTENNA_SCAN_MODE={new_mode}\n")

    with open(env_path, "w") as f:
        f.writelines(lines)

    print(f"Scan mode set to: {new_mode}")
    print(f"Description: {SCAN_MODES[new_mode]['description']}")
    print("Restart the scheduler for changes to take effect.")


# ═══════════════════════════════════════════════════════════════════
# SCHEDULER
# ═══════════════════════════════════════════════════════════════════

def cmd_scheduler():
    """
    Run the automated scheduler. Blocks forever.
    Runs scan at SCAN_HOUR daily and digest on Sundays at DIGEST_HOUR.
    Uses SCAN_MODE to determine frequency.
    """
    import schedule as sched_lib

    mode_config = SCAN_MODES.get(SCAN_MODE, SCAN_MODES["normal"])
    interval_hours = mode_config["scan_interval_hours"]
    digest_day = mode_config["digest_day"]
    max_pages = mode_config["max_pages"]

    print("=" * 60)
    print("THE ANTENNA — Scheduler Starting")
    print(f"  Mode: {SCAN_MODE}")
    print(f"  Scan interval: every {interval_hours} hours")
    print(f"  Digest: {digest_day} at {DIGEST_HOUR}:00")
    print(f"  Max pages per scan: {max_pages}")
    print("=" * 60)

    def run_scan():
        logger.info("Scheduler triggered: scan")
        cmd_scan(max_pages=max_pages)

    def run_digest():
        logger.info("Scheduler triggered: digest")
        cmd_digest(send_to_discord=True)

    # Schedule scans
    if interval_hours >= 24:
        sched_lib.every().day.at(f"{SCAN_HOUR:02d}:00").do(run_scan)
    elif interval_hours == 12:
        sched_lib.every(12).hours.do(run_scan)
    elif interval_hours == 6:
        sched_lib.every(6).hours.do(run_scan)
    else:
        sched_lib.every(interval_hours).hours.do(run_scan)

    # Schedule digest
    if digest_day == "daily":
        sched_lib.every().day.at(f"{DIGEST_HOUR:02d}:00").do(run_digest)
    else:
        sched_lib.every().sunday.at(f"{DIGEST_HOUR:02d}:00").do(run_digest)

    # Run initial scan immediately
    logger.info("Running initial scan...")
    run_scan()

    logger.info("Scheduler running. Press Ctrl+C to stop.")
    while True:
        sched_lib.run_pending()
        time.sleep(60)


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    command = sys.argv[1].lower()

    if command == "scan":
        pages = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        cmd_scan(max_pages=pages)
    elif command == "search":
        if len(sys.argv) < 3:
            print("Usage: python3 antenna.py search <query>")
            print("Example: python3 antenna.py search 'cascade elevator gear ratio'")
            return
        query = " ".join(sys.argv[2:])
        cmd_search(query)
    elif command == "digest":
        send = "--send" in sys.argv
        cmd_digest(send_to_discord=send)
    elif command == "stats":
        cmd_stats()
    elif command == "alerts":
        cmd_alerts()
    elif command == "top":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        cmd_top(n)
    elif command == "review":
        if len(sys.argv) < 3:
            print("Usage: python3 antenna.py review <topic_id>")
            return
        cmd_review(int(sys.argv[2]))
    elif command == "pull":
        if len(sys.argv) < 3:
            print("Usage: python3 antenna.py pull <topic_id>")
            return
        cmd_pull(int(sys.argv[2]))
    elif command == "mode":
        new_mode = sys.argv[2] if len(sys.argv) > 2 else None
        cmd_mode(new_mode)
    elif command == "scheduler":
        cmd_scheduler()
    else:
        print(f"Unknown command: {command}")
        print(__doc__)


if __name__ == "__main__":
    main()
