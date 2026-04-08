#!/usr/bin/env python3
"""
The Antenna — Main Orchestrator
Chief Delphi Intelligence Watcher for THE ENGINE
Team 2950 — The Devastators

Usage:
    python3 antenna.py scan          # Scan CD and score new topics
    python3 antenna.py digest        # Generate and print weekly digest
    python3 antenna.py digest --send # Generate and send digest to Discord
    python3 antenna.py stats         # Show database statistics
    python3 antenna.py alerts        # Show unreviewed high-priority posts
    python3 antenna.py top [N]       # Show top N scored posts
"""

import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path

# Ensure we can import from the antenna package
sys.path.insert(0, str(Path(__file__).parent))

from config import DB_PATH, LOG_PATH, SCORE_THRESHOLDS
from scraper import CDScraper, fetch_and_filter_recent
from scorer import score_topic
from database import (
    init_db, get_connection, upsert_post,
    get_weekly_posts, get_high_priority_posts,
    get_tracked_team_activity, get_db_stats,
    log_scrape_run, update_scrape_run,
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


def cmd_scan(max_pages: int = 10):
    """
    Main scan routine: fetch topics from CD, score them, store in database.
    This is the daily automated task.
    """
    logger.info("=" * 60)
    logger.info("THE ANTENNA — Starting scan")
    logger.info("=" * 60)

    init_db()
    conn = get_connection()
    run_id = log_scrape_run(conn)

    try:
        # Fetch topics
        scraper = CDScraper()
        topics = fetch_and_filter_recent(scraper, max_pages=max_pages)
        logger.info(f"Fetched {len(topics)} topics from Chief Delphi")

        new_count = 0
        updated_count = 0
        scored_count = 0
        critical_alerts = []

        for topic in topics:
            # Score the topic
            score_result = score_topic(topic)
            scored_count += 1

            # Merge score results into topic dict
            topic.update(score_result)

            # Store in database
            is_new = upsert_post(conn, topic)
            if is_new:
                new_count += 1
            else:
                updated_count += 1

            # Check for critical alerts
            if score_result["tier"] == "critical" and is_new:
                critical_alerts.append(topic)

            # Log high-value finds
            if score_result["relevance_score"] >= SCORE_THRESHOLDS["ignore"] + 1:
                logger.info(
                    f"  [{score_result['tier'].upper()}] "
                    f"Score {score_result['relevance_score']}: "
                    f"{topic['title'][:60]}"
                )

        conn.commit()

        # Send critical alerts immediately
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

        # Summary
        stats = get_db_stats(conn)
        logger.info("")
        logger.info("=" * 60)
        logger.info("SCAN COMPLETE")
        logger.info(f"  Topics fetched:  {len(topics)}")
        logger.info(f"  New topics:      {new_count}")
        logger.info(f"  Updated topics:  {updated_count}")
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


def cmd_digest(send_to_discord: bool = False):
    """Generate the weekly digest."""
    init_db()
    conn = get_connection()

    posts = get_weekly_posts(conn, min_score=8)
    stats = get_db_stats(conn)

    if not posts:
        print("No relevant posts found in the last 7 days.")
        print("Run 'python3 antenna.py scan' first.")
        conn.close()
        return

    digest = format_weekly_digest(
        posts=posts,
        total_scanned=stats["total_posts"],
        db_total=stats["total_posts"],
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
        print(f"\n[{post['tier'].upper()}] Score: {post['relevance_score']}")
        print(f"  {post['title']}")
        print(f"  {post['url']}")
        print(f"  Likes: {post['like_count']} | Replies: {post['reply_count']}")
        if post.get("tracked_teams"):
            print(f"  Teams: {post['tracked_teams']}")
        if post.get("engine_file_target"):
            print(f"  Target: {post['engine_file_target']}")
        if post.get("action_recommendation"):
            print(f"  Action: {post['action_recommendation']}")

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

        print(f"\n  {tier_badge} Score: {post['relevance_score']:3d} | "
              f"Likes: {post['like_count']:4d} | "
              f"{post['title'][:55]}")
        if post.get("tracked_teams"):
            print(f"       Teams: {post['tracked_teams']}")
        if post.get("keywords_matched"):
            print(f"       Keywords: {post['keywords_matched'][:60]}")

    conn.close()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    command = sys.argv[1].lower()

    if command == "scan":
        pages = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        cmd_scan(max_pages=pages)
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
    else:
        print(f"Unknown command: {command}")
        print(__doc__)


if __name__ == "__main__":
    main()
