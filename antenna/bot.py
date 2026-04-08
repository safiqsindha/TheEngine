#!/usr/bin/env python3
"""
The Antenna — Discord Bot
Full two-way Discord integration for THE ENGINE.
Team 2950 — The Devastators

Features:
- Posts weekly digests and critical alerts to #engine-intelligence
- Reads reactions on digest posts to update database status:
    👀 = "I'll review this"  → status: reviewing
    ✅ = "Pulled into Engine" → status: pulled
    ❌ = "Not relevant"       → status: dismissed
    🔖 = "Save for later"    → status: bookmarked
- DMs Engine Lead on critical alerts (score >= 16)
- Slash commands: /scan, /digest, /alerts, /stats, /top

Usage:
    python3 bot.py                    # Run the bot (blocks)
    Set ANTENNA_BOT_TOKEN in .env     # Required
    Set ANTENNA_CHANNEL_ID in .env    # Channel to post digests
    Set ANTENNA_LEAD_ID in .env       # User ID for DM alerts (optional)
"""

import os
import sys
import re
import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path

import discord
from discord.ext import commands, tasks

sys.path.insert(0, str(Path(__file__).parent))

from config import (
    DB_PATH, SCORE_THRESHOLDS, SCAN_MODE, SCAN_MODES,
)
from scraper import CDScraper, fetch_and_filter_recent
from scorer import score_topic
from database import (
    init_db, get_connection, upsert_post,
    get_weekly_posts, get_high_priority_posts,
    get_db_stats, log_scrape_run, update_scrape_run,
    mark_post_reviewed,
)
from digest import format_weekly_digest, format_critical_alert, split_for_discord

logger = logging.getLogger("antenna.bot")

# ── Config from .env ───────────────────────────────────────────────
BOT_TOKEN = os.environ.get("ANTENNA_BOT_TOKEN", "")
CHANNEL_ID = os.environ.get("ANTENNA_CHANNEL_ID", "")
LEAD_USER_ID = os.environ.get("ANTENNA_LEAD_ID", "")

# Reaction → status mapping
REACTION_MAP = {
    "\U0001F440": "reviewing",   # 👀
    "\u2705": "pulled",          # ✅
    "\u274C": "dismissed",       # ❌
    "\U0001F516": "bookmarked",  # 🔖
}

# Track which message IDs map to which topic IDs
# Format: {message_id: topic_id}
# Persisted in the digest_messages table


# ═══════════════════════════════════════════════════════════════════
# BOT SETUP
# ═══════════════════════════════════════════════════════════════════

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)


# ═══════════════════════════════════════════════════════════════════
# DATABASE HELPERS
# ═══════════════════════════════════════════════════════════════════

def ensure_extra_tables():
    """Create the message tracking and watchlist tables if needed."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS digest_messages (
            message_id INTEGER PRIMARY KEY,
            topic_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            date_posted DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS watchlist (
            watch_id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT NOT NULL,
            added_by TEXT NOT NULL,
            date_added DATETIME DEFAULT CURRENT_TIMESTAMP,
            active INTEGER DEFAULT 1
        );
    """)
    conn.commit()
    conn.close()


def save_message_topic_link(message_id: int, topic_id: int, channel_id: int):
    """Link a Discord message ID to a topic ID for reaction tracking."""
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO digest_messages (message_id, topic_id, channel_id) VALUES (?, ?, ?)",
        (message_id, topic_id, channel_id)
    )
    conn.commit()
    conn.close()


def get_active_watches() -> list[dict]:
    """Get all active watchlist queries."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT watch_id, query, added_by, date_added FROM watchlist WHERE active = 1"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_topic_for_message(message_id: int) -> int:
    """Look up which topic ID a message corresponds to."""
    conn = get_connection()
    row = conn.execute(
        "SELECT topic_id FROM digest_messages WHERE message_id = ?",
        (message_id,)
    ).fetchone()
    conn.close()
    return row[0] if row else None


# ═══════════════════════════════════════════════════════════════════
# SCAN LOGIC (async wrapper around existing sync code)
# ═══════════════════════════════════════════════════════════════════

def run_scan(max_pages: int = 10) -> dict:
    """Run a scan and return results summary."""
    init_db()
    conn = get_connection()
    run_id = log_scrape_run(conn)

    scraper = CDScraper()
    topics = fetch_and_filter_recent(scraper, max_pages=max_pages)

    # Run watchlist searches and merge results
    watches = get_active_watches()
    seen_ids = {t["topic_id"] for t in topics}
    for watch in watches:
        try:
            results = scraper.search_topics(watch["query"], max_results=10)
            for r in results:
                if r["topic_id"] not in seen_ids:
                    topics.append(r)
                    seen_ids.add(r["topic_id"])
        except Exception as e:
            logger.error(f"Watchlist search '{watch['query']}' failed: {e}")

    new_count = 0
    updated_count = 0
    critical_alerts = []

    for topic in topics:
        score_result = score_topic(topic)
        topic.update(score_result)
        is_new = upsert_post(conn, topic)
        if is_new:
            new_count += 1
        else:
            updated_count += 1
        if score_result["tier"] == "critical" and is_new:
            critical_alerts.append(topic)

    conn.commit()

    # Fetch detail for high-priority new posts
    high_ids = [t["topic_id"] for t in topics
                if t.get("relevance_score", 0) >= 12
                and t["topic_id"] in {t2["topic_id"] for t2 in topics if upsert_post(conn, t2) or True}]
    for topic_id in high_ids[:10]:
        detail = scraper.fetch_topic_detail(topic_id)
        if detail and detail.get("op_cooked"):
            body_text = re.sub(r'<[^>]+>', ' ', detail["op_cooked"])
            for topic in topics:
                if topic["topic_id"] == topic_id:
                    topic["excerpt"] = f"{topic['title']} {body_text[:2000]}"
                    topic["author"] = detail.get("op_username", topic.get("author", ""))
                    rescore = score_topic(topic)
                    if rescore["relevance_score"] > topic.get("relevance_score", 0):
                        topic.update(rescore)
                        upsert_post(conn, topic)
                    break

    conn.commit()

    update_scrape_run(conn, run_id,
        end_time=datetime.utcnow().isoformat(),
        topics_fetched=len(topics),
        topics_new=new_count,
        topics_updated=updated_count,
        topics_scored=len(topics),
        status="complete",
    )

    stats = get_db_stats(conn)
    conn.close()

    return {
        "fetched": len(topics),
        "new": new_count,
        "updated": updated_count,
        "critical": critical_alerts,
        "total_db": stats["total_posts"],
        "relevant_db": stats["relevant_posts"],
    }


# ═══════════════════════════════════════════════════════════════════
# BOT EVENTS
# ═══════════════════════════════════════════════════════════════════

@bot.event
async def on_ready():
    ensure_extra_tables()
    logger.info(f"The Antenna bot connected as {bot.user}")
    logger.info(f"Channel ID: {CHANNEL_ID}")

    # Start scheduled tasks
    if not scheduled_scan.is_running():
        scheduled_scan.start()
    if not scheduled_digest.is_running():
        scheduled_digest.start()


@bot.event
async def on_reaction_add(reaction, user):
    """Handle reactions on digest posts to update topic status."""
    if user.bot:
        return

    emoji = str(reaction.emoji)
    if emoji not in REACTION_MAP:
        return

    topic_id = get_topic_for_message(reaction.message.id)
    if not topic_id:
        return

    new_status = REACTION_MAP[emoji]
    conn = get_connection()
    mark_post_reviewed(conn, topic_id, reviewed_by=str(user), status=new_status)
    conn.close()

    status_labels = {
        "reviewing": "being reviewed",
        "pulled": "PULLED into The Engine",
        "dismissed": "dismissed",
        "bookmarked": "bookmarked for later",
    }
    label = status_labels.get(new_status, new_status)
    logger.info(f"Topic {topic_id} marked as {label} by {user}")

    # Log engine update if pulled
    if new_status == "pulled":
        conn = get_connection()
        conn.execute("""
            INSERT INTO engine_updates (post_id, engine_file, change_description, applied_by)
            SELECT post_id, engine_file_target, action_recommendation, ?
            FROM posts WHERE topic_id = ?
        """, (str(user), topic_id))
        conn.commit()
        conn.close()


# ═══════════════════════════════════════════════════════════════════
# SLASH COMMANDS (using ! prefix)
# ═══════════════════════════════════════════════════════════════════

@bot.command(name="commands")
async def cmd_commands(ctx):
    """Show all available Antenna commands."""
    text = (
        "```\n"
        "THE ANTENNA — Commands\n"
        "─────────────────────────────────────\n"
        "!scan [pages]    Scan Chief Delphi (default 10 pages)\n"
        "!digest          Post the weekly intelligence digest\n"
        "!search <query>  Search CD for a specific topic\n"
        "!alerts          Show unreviewed high-priority posts\n"
        "!top [n]         Show top N scored posts (default 10)\n"
        "!pulled [days]   Monthly review: all ✅ pulled posts\n"
        "!stats           Show database statistics\n"
        "!watch <query>   Add a search to the watchlist\n"
        "!watchlist       Show all active watches\n"
        "!unwatch <id>    Remove a watch by ID\n"
        "!commands        Show this help message\n"
        "─────────────────────────────────────\n"
        "Reactions on digest posts:\n"
        "  👀 = reviewing   ✅ = pulled into Engine\n"
        "  ❌ = dismiss      🔖 = bookmark\n"
        "```"
    )
    await ctx.send(text)


@bot.command(name="scan")
async def cmd_scan(ctx, pages: int = 10):
    """Run a Chief Delphi scan."""
    await ctx.send("Scanning Chief Delphi...")

    # Run scan in thread pool to avoid blocking
    result = await asyncio.to_thread(run_scan, pages)

    summary = (
        f"**Scan Complete**\n"
        f"Topics fetched: {result['fetched']}\n"
        f"New: {result['new']} | Updated: {result['updated']}\n"
        f"Critical alerts: {len(result['critical'])}\n"
        f"Total in DB: {result['total_db']} | Relevant: {result['relevant_db']}"
    )
    await ctx.send(summary)

    # Post critical alerts
    for alert in result["critical"]:
        alert_text = format_critical_alert(alert)
        await ctx.send(alert_text)

        # DM the Engine Lead
        if LEAD_USER_ID:
            try:
                lead = await bot.fetch_user(int(LEAD_USER_ID))
                await lead.send(f"**ANTENNA CRITICAL ALERT**\n\n{alert_text}")
            except Exception as e:
                logger.error(f"Failed to DM lead: {e}")


@bot.command(name="search")
async def cmd_search(ctx, *, query: str = ""):
    """Search Chief Delphi for a specific topic."""
    if not query:
        await ctx.send("Usage: `!search <query>`\nExample: `!search cascade elevator gear ratio`")
        return

    await ctx.send(f"Searching Chief Delphi for: **{query}**...")

    def do_search():
        scraper = CDScraper()
        results = scraper.search_topics(query, max_results=15)
        scored = []
        for topic in results:
            score_result = score_topic(topic)
            topic.update(score_result)
            scored.append(topic)
        scored.sort(key=lambda t: t["relevance_score"], reverse=True)
        return scored

    results = await asyncio.to_thread(do_search)

    if not results:
        await ctx.send(f"No results found for: {query}")
        return

    text = f"**Search results for: {query}** ({len(results)} found)\n\n"
    for i, r in enumerate(results, 1):
        badge = {"critical": "🔴", "high": "🟠", "notable": "🟡"}.get(r["tier"], "⚪")
        text += (
            f"{badge} **{i}. {r['title'][:55]}**\n"
            f"   <{r['url']}>\n"
            f"   Score: {r['relevance_score']} | "
            f"{r['like_count']} likes | "
            f"{r['reply_count']} replies\n"
        )
        if r.get("keywords_matched"):
            text += f"   Keywords: {r['keywords_matched'][:50]}\n"
        if r.get("engine_file_target"):
            text += f"   Target: {r['engine_file_target']}\n"
        text += "\n"

    for chunk in split_for_discord(text):
        await ctx.send(chunk)


@bot.command(name="digest")
async def cmd_digest(ctx):
    """Post the weekly digest."""
    conn = get_connection()
    posts = get_weekly_posts(conn, min_score=8)
    stats = get_db_stats(conn)
    conn.close()

    if not posts:
        await ctx.send("No relevant posts found in the last 7 days.")
        return

    # Detect trends
    from antenna import detect_trends
    trends = detect_trends(posts)

    digest = format_weekly_digest(
        posts=posts,
        total_scanned=stats["total_posts"],
        db_total=stats["total_posts"],
        trends=trends,
    )

    # Post digest in chunks, track message → topic mappings
    chunks = split_for_discord(digest)
    for chunk in chunks:
        msg = await ctx.send(chunk)

    # Post only high-priority items as reaction-trackable messages (cap at 5)
    high_priority = [p for p in posts if p.get("tier") in ("critical", "high")]
    if high_priority:
        await ctx.send("**React below to update status:** "
                       "👀 reviewing | ✅ pulled | ❌ dismiss | 🔖 bookmark")

        for post in high_priority[:5]:
            text = f"**{post['title']}** — <{post['url']}>"
            if post.get("engine_file_target"):
                text += f"\n→ {post['engine_file_target']}"

            msg = await ctx.send(text)

            # Track this message → topic mapping
            save_message_topic_link(msg.id, post["topic_id"], msg.channel.id)

            # Pre-add reaction options
            for emoji in ["\U0001F440", "\u2705", "\u274C", "\U0001F516"]:
                await msg.add_reaction(emoji)


@bot.command(name="alerts")
async def cmd_alerts(ctx):
    """Show unreviewed high-priority posts."""
    conn = get_connection()
    posts = get_high_priority_posts(conn)
    conn.close()

    if not posts:
        await ctx.send("No unreviewed high-priority posts.")
        return

    text = f"**UNREVIEWED HIGH PRIORITY ({len(posts)})**\n\n"
    for post in posts[:10]:
        text += (
            f"[{post['tier'].upper()}] **{post['title'][:50]}**\n"
            f"  Score: {post['relevance_score']} | "
            f"{post['like_count']} likes | "
            f"ID: {post['topic_id']}\n"
        )
        if post.get("engine_file_target"):
            text += f"  Target: {post['engine_file_target']}\n"
        text += "\n"

    for chunk in split_for_discord(text):
        await ctx.send(chunk)


@bot.command(name="stats")
async def cmd_stats(ctx):
    """Show database statistics."""
    conn = get_connection()
    stats = get_db_stats(conn)
    conn.close()

    text = (
        "```\n"
        "THE ANTENNA — Stats\n"
        "─────────────────────\n"
        f"Total posts:     {stats['total_posts']}\n"
        f"Relevant:        {stats['relevant_posts']}\n"
        f"High priority:   {stats['high_priority']}\n"
        f"Unreviewed:      {stats['unreviewed']}\n"
        f"Scrape runs:     {stats['total_scrape_runs']}\n"
        f"Scan mode:       {SCAN_MODE}\n"
        "```"
    )
    await ctx.send(text)


@bot.command(name="top")
async def cmd_top(ctx, n: int = 10):
    """Show top scored posts."""
    conn = get_connection()
    cursor = conn.cursor()
    rows = cursor.execute("""
        SELECT * FROM posts WHERE relevance_score > 0
        ORDER BY relevance_score DESC, like_count DESC LIMIT ?
    """, (n,)).fetchall()
    conn.close()

    if not rows:
        await ctx.send("No scored posts. Run `!scan` first.")
        return

    text = f"**TOP {n} POSTS**\n\n"
    for row in rows:
        post = dict(row)
        badge = {"critical": "🔴", "high": "🟠", "notable": "🟡"}.get(post["tier"], "⚪")
        status = ""
        if post["status"] == "pulled":
            status = " ✅"
        elif post["status"] == "reviewed":
            status = " 👀"
        text += f"{badge} **{post['relevance_score']}** | {post['title'][:45]}{status}\n"

    for chunk in split_for_discord(text):
        await ctx.send(chunk)


@bot.command(name="pulled")
async def cmd_pulled(ctx, days: int = 30):
    """Show all pulled (✅) posts — the monthly Engine review queue."""
    conn = get_connection()
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    rows = conn.execute("""
        SELECT title, url, relevance_score, engine_file_target,
               action_recommendation, reviewed_by, date_reviewed
        FROM posts
        WHERE status = 'pulled' AND date_reviewed >= ?
        ORDER BY date_reviewed DESC
    """, (since,)).fetchall()
    conn.close()

    if not rows:
        await ctx.send(f"No pulled posts in the last {days} days.")
        return

    # Group by engine file target
    by_target = {}
    for r in rows:
        post = dict(r)
        target = post.get("engine_file_target") or "No target"
        by_target.setdefault(target, []).append(post)

    text = f"**PULLED INTO ENGINE** ({len(rows)} posts, last {days} days)\n"
    text += "Ready for monthly review\n\n"

    for target, posts in by_target.items():
        text += f"**→ {target}**\n"
        for p in posts:
            text += f"• {p['title'][:55]}\n"
            if p.get("action_recommendation"):
                text += f"  _{p['action_recommendation'][:70]}_\n"
        text += "\n"

    text += "*Review these and update Engine files accordingly.*"

    for chunk in split_for_discord(text):
        await ctx.send(chunk)


@bot.command(name="watch")
async def cmd_watch(ctx, *, query: str = ""):
    """Add a search query to the watchlist. Runs automatically during each scan."""
    if not query:
        await ctx.send("Usage: `!watch <search query>`\n"
                       "Example: `!watch new programming library`\n"
                       "Example: `!watch wpilib command-based`\n"
                       "These searches run during every scan and results appear in the digest.")
        return

    conn = get_connection()
    # Check for duplicate
    existing = conn.execute(
        "SELECT watch_id FROM watchlist WHERE query = ? AND active = 1",
        (query,)
    ).fetchone()
    if existing:
        conn.close()
        await ctx.send(f"Already watching: **{query}**")
        return

    conn.execute(
        "INSERT INTO watchlist (query, added_by) VALUES (?, ?)",
        (query, str(ctx.author))
    )
    conn.commit()
    conn.close()
    await ctx.send(f"Added to watchlist: **{query}**\n"
                   f"This will be searched during every `!scan` and included in the digest.")


@bot.command(name="watchlist")
async def cmd_watchlist(ctx):
    """Show all active watchlist queries."""
    watches = get_active_watches()
    if not watches:
        await ctx.send("Watchlist is empty. Add one with `!watch <query>`")
        return

    text = f"**WATCHLIST** ({len(watches)} active)\n\n"
    for w in watches:
        text += f"**{w['watch_id']}.** {w['query']} — added by {w['added_by']}\n"
    text += "\nRemove with `!unwatch <id>`"
    await ctx.send(text)


@bot.command(name="unwatch")
async def cmd_unwatch(ctx, watch_id: int = 0):
    """Remove a query from the watchlist."""
    if not watch_id:
        await ctx.send("Usage: `!unwatch <id>` — get IDs from `!watchlist`")
        return

    conn = get_connection()
    result = conn.execute(
        "UPDATE watchlist SET active = 0 WHERE watch_id = ? AND active = 1",
        (watch_id,)
    )
    conn.commit()
    if result.rowcount:
        await ctx.send(f"Removed watch #{watch_id} from watchlist.")
    else:
        await ctx.send(f"Watch #{watch_id} not found or already removed.")
    conn.close()


# ═══════════════════════════════════════════════════════════════════
# SCHEDULED TASKS
# ═══════════════════════════════════════════════════════════════════

@tasks.loop(hours=24)
async def scheduled_scan():
    """Run daily scan automatically."""
    # Skip the first run (on_ready already triggers)
    if scheduled_scan.current_loop == 0:
        return

    logger.info("Scheduled scan starting...")
    mode_config = SCAN_MODES.get(SCAN_MODE, SCAN_MODES["normal"])
    result = await asyncio.to_thread(run_scan, mode_config["max_pages"])

    # Post critical alerts to channel
    if result["critical"] and CHANNEL_ID:
        channel = bot.get_channel(int(CHANNEL_ID))
        if channel:
            for alert in result["critical"]:
                alert_text = format_critical_alert(alert)
                await channel.send(alert_text)

                # DM lead
                if LEAD_USER_ID:
                    try:
                        lead = await bot.fetch_user(int(LEAD_USER_ID))
                        await lead.send(f"**ANTENNA CRITICAL ALERT**\n\n{alert_text}")
                    except Exception:
                        pass

    logger.info(f"Scheduled scan complete: {result['new']} new, {len(result['critical'])} critical")


@tasks.loop(hours=168)  # Weekly (7 * 24)
async def scheduled_digest():
    """Post weekly digest automatically on Sunday."""
    if scheduled_digest.current_loop == 0:
        return

    if not CHANNEL_ID:
        return

    channel = bot.get_channel(int(CHANNEL_ID))
    if not channel:
        return

    conn = get_connection()
    posts = get_weekly_posts(conn, min_score=8)
    stats = get_db_stats(conn)
    conn.close()

    if not posts:
        return

    from antenna import detect_trends
    trends = detect_trends(posts)

    digest = format_weekly_digest(
        posts=posts,
        total_scanned=stats["total_posts"],
        db_total=stats["total_posts"],
        trends=trends,
    )

    chunks = split_for_discord(digest)
    for chunk in chunks:
        await channel.send(chunk)

    # Post reaction-trackable items
    high_priority = [p for p in posts if p.get("tier") in ("critical", "high")]
    if high_priority:
        await channel.send("**React to update status:** 👀 reviewing | ✅ pulled | ❌ dismiss | 🔖 bookmark")
        for post in high_priority[:5]:
            text = (
                f"**{post['title']}** — <{post['url']}>"
            )
            if post.get("engine_file_target"):
                text += f"\n→ {post['engine_file_target']}"
            msg = await channel.send(text)
            save_message_topic_link(msg.id, post["topic_id"], msg.channel.id)
            for emoji in ["\U0001F440", "\u2705", "\u274C", "\U0001F516"]:
                await msg.add_reaction(emoji)

    logger.info(f"Weekly digest posted: {len(posts)} relevant posts")


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

LOCK_FILE = Path(__file__).parent / ".bot.lock"


def acquire_lock() -> bool:
    """Acquire a PID lockfile. Returns True if lock acquired, False if another instance is running."""
    if LOCK_FILE.exists():
        try:
            old_pid = int(LOCK_FILE.read_text().strip())
            # Check if that process is still alive
            os.kill(old_pid, 0)
            # Process exists — another instance is running
            return False
        except (ValueError, ProcessLookupError, PermissionError):
            # Stale lock file — old process is dead
            pass
    LOCK_FILE.write_text(str(os.getpid()))
    return True


def release_lock():
    """Remove the lockfile."""
    try:
        LOCK_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def main():
    if not BOT_TOKEN:
        print("=" * 60)
        print("THE ANTENNA — Discord Bot")
        print("=" * 60)
        print()
        print("No bot token configured. Set ANTENNA_BOT_TOKEN in .env")
        print()
        print("Setup steps:")
        print("  1. Go to https://discord.com/developers/applications")
        print("  2. Click 'New Application' → name it 'The Antenna'")
        print("  3. Go to Bot tab → click 'Reset Token' → copy token")
        print("  4. Add to .env: ANTENNA_BOT_TOKEN=your_token_here")
        print("  5. Go to OAuth2 → URL Generator")
        print("     - Scopes: bot")
        print("     - Permissions: Send Messages, Read Message History,")
        print("       Add Reactions, Manage Messages, View Channels")
        print("  6. Copy the generated URL → open it → add bot to server")
        print("  7. Get channel ID: right-click channel → Copy Channel ID")
        print("  8. Add to .env: ANTENNA_CHANNEL_ID=your_channel_id")
        print("  9. Run: python3 bot.py")
        return

    if not acquire_lock():
        print("ERROR: Another Antenna bot instance is already running.")
        print(f"Lock file: {LOCK_FILE}")
        print("Kill the other instance first, or delete the lock file if it's stale.")
        sys.exit(1)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    try:
        init_db()
        ensure_extra_tables()

        print("Starting The Antenna Discord bot...")
        bot.run(BOT_TOKEN)
    finally:
        release_lock()


if __name__ == "__main__":
    main()
