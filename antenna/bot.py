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
        "THE ENGINE — All Commands\n"
        "═════════════════════════════════════\n"
        "\n"
        "SCOUTING (competition day)\n"
        "─────────────────────────────────────\n"
        "!event <key>     Set active event for this channel\n"
        "!matchnow <key>  Set current match being played\n"
        "!scout <team> <tags>  Record scouting observation\n"
        "!scouted [team]  Show scout data (team or summary)\n"
        "!eyescores       Show EYE + stand scout scores\n"
        "!loadscout       Load scouting data into pick board\n"
        "\n"
        "DRAFT (alliance selection)\n"
        "─────────────────────────────────────\n"
        "!rec             Show pick recommendation\n"
        "!pick <a#> <t#>  Record a pick\n"
        "!board           Show full pick board\n"
        "!lookup <team>   Team EPA lookup\n"
        "\n"
        "STRATEGY\n"
        "─────────────────────────────────────\n"
        "!strategy        Strategy for next match\n"
        "!strategy <key>  Strategy for specific match\n"
        "!strategy opponent <teams>  Opponent report\n"
        "!strategy synergy <teams>   Alliance synergy\n"
        "\n"
        "INTELLIGENCE (Antenna)\n"
        "─────────────────────────────────────\n"
        "!scan [pages]    Scan Chief Delphi\n"
        "!digest          Post weekly digest\n"
        "!search <query>  Search CD topics\n"
        "!alerts          High-priority posts\n"
        "!top [n]         Top scored posts\n"
        "!pulled [days]   All pulled posts\n"
        "!watch <query>   Add to watchlist\n"
        "!watchlist       Show watches\n"
        "!unwatch <id>    Remove a watch\n"
        "!report          Robot report template\n"
        "!stats           Database stats\n"
        "!commands        This help message\n"
        "═════════════════════════════════════\n"
        "```"
    )
    await ctx.send(text)


@bot.command(name="report")
async def cmd_report(ctx):
    """Post a blank robot report template for the team to fill out."""
    template = (
        "**ROBOT REPORT** — Fill this out after every match/practice\n"
        "```\n"
        "Match/Session: _______________\n"
        "Reporter: _______________\n"
        "\n"
        "MECHANICAL\n"
        "  Drivetrain: OK / Issue: ___\n"
        "  Intake:     OK / Issue: ___\n"
        "  Elevator:   OK / Issue: ___\n"
        "  Climber:    OK / Issue: ___\n"
        "  Bumpers:    OK / Issue: ___\n"
        "\n"
        "ELECTRICAL\n"
        "  Battery post-match: ___ V\n"
        "  Brownout: Y / N\n"
        "  CAN errors: Y / N\n"
        "\n"
        "WHAT BROKE:\n"
        "\n"
        "WHAT WE FIXED:\n"
        "\n"
        "PRIORITY FOR NEXT MATCH:\n"
        "  1.\n"
        "  2.\n"
        "  3.\n"
        "```"
    )
    await ctx.send(template)


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
# SCOUTING COMMANDS — Stand Scout + EYE + Strategy
# ═══════════════════════════════════════════════════════════════════

# Add scout paths for imports
SCOUT_PATH = Path(__file__).parent.parent / "scout"
EYE_PATH = Path(__file__).parent.parent / "eye"
sys.path.insert(0, str(SCOUT_PATH))
sys.path.insert(0, str(EYE_PATH))

# Track active event per channel (set via !event)
_active_events = {}  # channel_id -> event_key
_active_match = {}   # channel_id -> match_key


def _get_event(ctx) -> str:
    """Get active event for this channel."""
    return _active_events.get(ctx.channel.id, "")


@bot.command(name="event")
async def cmd_event(ctx, event_key: str = ""):
    """Set the active event for this channel. All scouting commands use it."""
    if not event_key:
        current = _get_event(ctx)
        if current:
            await ctx.send(f"Active event: `{current}`\nChange with: `!event <event_key>`")
        else:
            await ctx.send("No active event set.\nUsage: `!event 2026txbel`")
        return

    _active_events[ctx.channel.id] = event_key
    await ctx.send(f"Active event set to `{event_key}` for this channel.")


@bot.command(name="matchnow")
async def cmd_matchnow(ctx, match_key: str = ""):
    """Set the current match being played. Auto-fills match key for !scout."""
    if not match_key:
        current = _active_match.get(ctx.channel.id, "")
        if current:
            await ctx.send(f"Current match: `{current}`\nChange: `!matchnow <match_key>`")
        else:
            await ctx.send("No match set. Usage: `!matchnow 2026txbel_qm15`")
        return

    _active_match[ctx.channel.id] = match_key
    await ctx.send(f"Current match: `{match_key}`")


@bot.command(name="scout")
async def cmd_scout(ctx, team: str = "", *, tags_str: str = ""):
    """Record a stand scouting observation.

    Usage: !scout <team> <tags...> [note:"free text"]
    Tags: auto:scored, fast, fuel, climbed, elite, intake-jam, etc.
    """
    if not team:
        await ctx.send(
            "```\n"
            "STAND SCOUT — Quick-tap scouting\n"
            "────────────────────────────────\n"
            "!scout <team> <tags...> [note:\"text\"]\n\n"
            "Auto:      auto:scored  auto:moved  auto:none\n"
            "Speed:     fast  moderate  slow\n"
            "Zone:      fuel  tower  both\n"
            "Endgame:   climbed  barge  parked  no-endgame  fell\n"
            "Defense:   played-defense  received-defense\n"
            "Mechanism: intake-jam  drivetrain-issue  disabled  tipped\n"
            "Quality:   elite  solid  average  weak  carried\n\n"
            "Example:\n"
            "  !scout 2950 auto:scored fast fuel climbed elite\n"
            "  !scout 7521 moderate tower barge note:\"great driver\"\n"
            "```"
        )
        return

    try:
        team_num = int(team)
    except ValueError:
        await ctx.send(f"Invalid team number: `{team}`")
        return

    # Parse tags and note from the combined string
    tags = []
    note = ""
    parts = tags_str.split() if tags_str else []

    i = 0
    while i < len(parts):
        part = parts[i]
        if part.startswith("note:"):
            # Collect everything after note: as the note text
            note_text = part[5:].strip('"')
            i += 1
            while i < len(parts):
                if parts[i].endswith('"'):
                    note_text += " " + parts[i].strip('"')
                    i += 1
                    break
                note_text += " " + parts[i]
                i += 1
            note = note_text.strip('"')
        else:
            tags.append(part)
            i += 1

    event_key = _get_event(ctx)
    match_key = _active_match.get(ctx.channel.id, "")

    def _do_scout():
        from stand_scout import parse_scout_input, save_observation, format_observation_discord
        obs = parse_scout_input(
            team_num, tags, note=note,
            match_key=match_key, event_key=event_key,
            scout_name=str(ctx.author),
        )
        path = save_observation(obs, event_key=event_key)
        display = format_observation_discord(obs)
        return path.name, display

    try:
        filename, display = await asyncio.to_thread(_do_scout)
        match_tag = f" | `{match_key}`" if match_key else ""
        await ctx.send(f"Saved scouting data for **{team_num}**{match_tag}\n{display}")
    except Exception as e:
        await ctx.send(f"Error saving scout data: {e}")


@bot.command(name="scouted")
async def cmd_scouted(ctx, team: str = ""):
    """Show scouting data for a team, or coverage summary if no team specified."""
    event_key = _get_event(ctx)

    if team:
        try:
            team_num = int(team)
        except ValueError:
            await ctx.send(f"Invalid team number: `{team}`")
            return

        def _get_data():
            from stand_scout import get_team_observations, format_team_summary_discord
            observations = get_team_observations(team_num, event_key)
            return format_team_summary_discord(team_num, observations)

        try:
            text = await asyncio.to_thread(_get_data)
            for chunk in split_for_discord(text):
                await ctx.send(chunk)
        except Exception as e:
            await ctx.send(f"Error: {e}")
    else:
        def _get_summary():
            from stand_scout import get_observation_summary
            return get_observation_summary(event_key)

        try:
            summary = await asyncio.to_thread(_get_summary)
            text = (
                f"**STAND SCOUT — Coverage**\n"
                f"```\n"
                f"Observations: {summary['total_observations']}\n"
                f"Teams scouted: {summary['teams_scouted']}\n"
                f"Scouts: {', '.join(summary['scouts']) if summary['scouts'] else 'none'}\n"
                f"Teams: {', '.join(summary['team_list'][:20])}\n"
                f"```"
            )
            if event_key:
                text += f"\nEvent: `{event_key}`"
            else:
                text += "\nNo event set. Use `!event <key>` to filter."
            await ctx.send(text)
        except Exception as e:
            await ctx.send(f"Error: {e}")


@bot.command(name="eyescores")
async def cmd_eyescores(ctx):
    """Show EYE + stand scout scores for all scouted teams in the draft."""
    def _get_scores():
        sys.path.insert(0, str(EYE_PATH))
        from eye_bridge import load_all_reports, aggregate_blended, STATE_FILE
        if not STATE_FILE.exists():
            return None, "No active draft. Run `pick_board.py setup` first."

        state = json.loads(STATE_FILE.read_text())
        event_key = state.get("event_key", "")
        eye_reports, stand_reports = load_all_reports(event_key)
        scores = aggregate_blended(eye_reports, stand_reports)

        if not scores:
            return None, "No scouting data found."

        lines = ["**EYE + STAND SCOUT SCORES**", "```"]
        lines.append(f"{'Team':>6} {'Score':>6} {'Reliab':>7} {'Driver':>7} {'Src':>8} {'Conf':>5}")
        lines.append("─" * 45)

        sorted_teams = sorted(scores.items(),
                              key=lambda x: x[1].get("eye_composite", 0), reverse=True)
        for team_key, s in sorted_teams[:20]:
            sources = s.get("eye_sources", {})
            if sources:
                src_str = f"E{sources.get('eye', 0)}+S{sources.get('stand', 0)}"
            else:
                src_str = f"{s.get('eye_matches', 0)}m"
            lines.append(
                f"{int(team_key):6d} {s.get('eye_composite', 0):6.1f} "
                f"{s.get('eye_reliability', 0):7.1f} "
                f"{s.get('eye_driver', 0):7.1f} "
                f"{src_str:>8} {s.get('eye_confidence', 0):4d}%"
            )

        lines.append("```")
        lines.append(f"E=EYE vision, S=stand scout | {len(eye_reports)} EYE + {len(stand_reports)} stand reports")
        return "\n".join(lines), None

    try:
        text, err = await asyncio.to_thread(_get_scores)
        if err:
            await ctx.send(err)
        else:
            for chunk in split_for_discord(text):
                await ctx.send(chunk)
    except Exception as e:
        await ctx.send(f"Error: {e}")


@bot.command(name="loadscout")
async def cmd_loadscout(ctx):
    """Load all EYE + stand scout data into the pick board."""
    def _do_load():
        sys.path.insert(0, str(EYE_PATH))
        from eye_bridge import (load_all_reports, aggregate_blended,
                                inject_eye_data, STATE_FILE, STATE_DIR)
        if not STATE_FILE.exists():
            return "No active draft."

        state = json.loads(STATE_FILE.read_text())
        event_key = state.get("event_key", "")
        eye_reports, stand_reports = load_all_reports(event_key)

        if not eye_reports and not stand_reports:
            eye_reports, stand_reports = load_all_reports()
            if not eye_reports and not stand_reports:
                return "No scouting data found."

        scores = aggregate_blended(eye_reports, stand_reports)
        enriched = inject_eye_data(state, scores)

        STATE_DIR.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2))

        return (f"Loaded {len(eye_reports)} EYE + {len(stand_reports)} stand reports. "
                f"Enriched {enriched} teams. Pick board rec now uses scouting data.")

    try:
        result = await asyncio.to_thread(_do_load)
        await ctx.send(result)
    except Exception as e:
        await ctx.send(f"Error: {e}")


@bot.command(name="strategy")
async def cmd_strategy(ctx, match_key: str = "", *, extra: str = ""):
    """Generate a match strategy brief.

    Usage:
      !strategy                          — next unplayed match
      !strategy 2026txbel_qm15           — specific match
      !strategy opponent 4364,9311,10032  — quick opponent report
      !strategy synergy 2950,7521,3035   — alliance synergy
    """
    event_key = _get_event(ctx)
    if not event_key:
        await ctx.send("Set active event first: `!event <event_key>`")
        return

    # Determine our team from draft state or default
    def _get_our_team():
        if STATE_FILE.exists():
            state = json.loads(STATE_FILE.read_text())
            return state.get("our_team", 2950)
        return 2950

    our_team = await asyncio.to_thread(_get_our_team)

    # Route to the right strategy sub-command
    if match_key == "opponent" and extra:
        teams_str = extra.split()[0]
        def _opponent():
            from match_strategy import load_teams_db, analyze_alliance
            teams_db = load_teams_db(event_key)
            opp_teams = [int(t) for t in teams_str.split(",")]
            opp = analyze_alliance(teams_db, opp_teams)

            lines = [f"**OPPONENT REPORT**"]
            for detail in opp["team_details"]:
                td = teams_db.get(str(detail["team"]), {})
                lines.append(
                    f"**{detail['team']}** {detail.get('name', '?')[:20]} — "
                    f"EPA {td.get('epa', 0):.1f} | {detail['role']}"
                )
            lines.append(f"\nCombined EPA: {opp['total_epa']:.0f}")
            if opp["strengths"]:
                lines.append(f"Strengths: {', '.join(opp['strengths'])}")
            if opp["weaknesses"]:
                lines.append(f"Weaknesses: {', '.join(opp['weaknesses'])}")
            return "\n".join(lines)

        try:
            text = await asyncio.to_thread(_opponent)
            await ctx.send(text)
        except Exception as e:
            await ctx.send(f"Error: {e}")
        return

    if match_key == "synergy" and extra:
        teams_str = extra.split()[0]
        def _synergy():
            from match_strategy import load_teams_db, analyze_alliance
            teams_db = load_teams_db(event_key)
            alliance_teams = [int(t) for t in teams_str.split(",")]
            profile = analyze_alliance(teams_db, alliance_teams)

            lines = [f"**ALLIANCE SYNERGY** — {', '.join(str(t) for t in alliance_teams)}"]
            lines.append(f"Combined EPA: {profile['total_epa']:.0f} "
                        f"(floor {profile['total_floor']:.0f}, ceiling {profile['total_ceiling']:.0f})")
            lines.append("")
            for detail in profile["team_details"]:
                td = teams_db.get(str(detail["team"]), {})
                lines.append(f"**{detail['team']}** — {detail['role']}")
            if profile["strengths"]:
                lines.append(f"\nStrengths: {', '.join(profile['strengths'])}")
            if profile["weaknesses"]:
                lines.append(f"Weaknesses: {', '.join(profile['weaknesses'])}")
            return "\n".join(lines)

        try:
            text = await asyncio.to_thread(_synergy)
            await ctx.send(text)
        except Exception as e:
            await ctx.send(f"Error: {e}")
        return

    # Default: generate full match strategy brief
    def _strategy():
        from match_strategy import (load_teams_db, get_match_teams,
                                     find_next_match, generate_strategy)
        teams_db = load_teams_db(event_key)
        if not teams_db:
            return f"No team data for `{event_key}`"

        # Find the match
        if match_key:
            mk = match_key if event_key in match_key else f"{event_key}_{match_key}"
        else:
            # Find next unplayed match
            next_m = find_next_match(event_key, our_team)
            if not next_m:
                return f"No upcoming match found for {our_team} at `{event_key}`"
            mk = next_m["match_key"]

        match_teams = get_match_teams(event_key, mk)
        if not match_teams:
            return f"Match `{mk}` not found"

        # Determine our alliance
        if our_team in match_teams.get("red", []):
            our_alliance = match_teams["red"]
            opp_alliance = match_teams["blue"]
        elif our_team in match_teams.get("blue", []):
            our_alliance = match_teams["blue"]
            opp_alliance = match_teams["red"]
        else:
            return f"Team {our_team} not in match `{mk}`"

        match_info = {
            "match_key": mk,
            "comp_level": match_teams.get("comp_level", "qm"),
            "match_number": match_teams.get("match_number", 0),
            "red": match_teams.get("red", []),
            "blue": match_teams.get("blue", []),
        }

        strat = generate_strategy(our_team, our_alliance, opp_alliance,
                                   teams_db, match_info)

        # Format for Discord
        pred = strat.get("prediction", {})
        plan = strat.get("game_plan", {})
        us = strat.get("our_alliance", {})
        them = strat.get("opponent", {})

        win_pct = pred.get("win_pct", 0) * 100
        bar_len = int(win_pct / 5)
        bar = "█" * bar_len + "░" * (20 - bar_len)

        lines = [
            f"**MATCH STRATEGY — {match_info.get('comp_level', 'qm').upper()} "
            f"{match_info.get('match_number', '?')}**",
            f"Win: **{win_pct:.0f}%** `[{bar}]`",
            f"Score: {pred.get('us_avg', 0):.0f} — {pred.get('them_avg', 0):.0f} "
            f"(margin {pred.get('avg_margin', 0):+.0f})",
            "",
        ]

        if strat.get("key_insight"):
            lines.append(f"**{strat['key_insight']}**")
            lines.append("")

        # Our alliance
        lines.append("**OUR ALLIANCE:**")
        for detail in us.get("team_details", []):
            me = " ← US" if detail["team"] == our_team else ""
            lines.append(f"  {detail['team']} — EPA {detail.get('epa', 0):.1f} | {detail.get('role', '?')}{me}")

        # Opponent
        lines.append("\n**OPPONENT:**")
        for detail in them.get("team_details", []):
            lines.append(f"  {detail['team']} — EPA {detail.get('epa', 0):.1f} | {detail.get('role', '?')}")

        # Game plan highlights
        lines.append("")
        defense = plan.get("defense", {})
        if defense.get("play_defense"):
            lines.append(f"**DEFENSE:** Send {defense['defender']} → defend {defense['target']}")
        else:
            lines.append("**DEFENSE:** All-out scoring")

        for note in defense.get("notes", [])[:2]:
            lines.append(f"  _{note}_")

        endgame = plan.get("endgame", {})
        if endgame.get("sequence"):
            lines.append(f"\n**ENDGAME:** {' → '.join(str(t) for t in endgame['sequence'])}")

        # Risk flags
        risks = strat.get("risk_flags", [])
        if risks:
            lines.append("\n**RISKS:**")
            for r in risks[:3]:
                lines.append(f"  ⚠ {r}")

        return "\n".join(lines)

    try:
        text = await asyncio.to_thread(_strategy)
        for chunk in split_for_discord(text):
            await ctx.send(chunk)
    except Exception as e:
        await ctx.send(f"Error: {e}")


@bot.command(name="rec")
async def cmd_rec(ctx):
    """Show current pick recommendation from the pick board."""
    def _get_rec():
        import subprocess
        result = subprocess.run(
            ["python3", str(SCOUT_PATH / "pick_board.py"), "rec"],
            capture_output=True, text=True, timeout=30,
        )
        return result.stdout or result.stderr

    try:
        text = await asyncio.to_thread(_get_rec)
        for chunk in split_for_discord(f"```\n{text}\n```"):
            await ctx.send(chunk)
    except Exception as e:
        await ctx.send(f"Error: {e}")


@bot.command(name="pick")
async def cmd_pick_draft(ctx, alliance: str = "", team: str = ""):
    """Record a pick in the live draft. Usage: !pick <alliance#> <team#>"""
    if not alliance or not team:
        await ctx.send("Usage: `!pick <alliance#> <team#>`\nExample: `!pick 1 148`")
        return

    def _record_pick():
        import subprocess
        result = subprocess.run(
            ["python3", str(SCOUT_PATH / "pick_board.py"), "pick", alliance, team],
            capture_output=True, text=True, timeout=15,
        )
        return result.stdout or result.stderr

    try:
        text = await asyncio.to_thread(_record_pick)
        await ctx.send(f"```\n{text}\n```")
    except Exception as e:
        await ctx.send(f"Error: {e}")


@bot.command(name="board")
async def cmd_board(ctx):
    """Show the current pick board."""
    def _get_board():
        import subprocess
        result = subprocess.run(
            ["python3", str(SCOUT_PATH / "pick_board.py"), "board"],
            capture_output=True, text=True, timeout=15,
        )
        return result.stdout or result.stderr

    try:
        text = await asyncio.to_thread(_get_board)
        for chunk in split_for_discord(f"```\n{text}\n```"):
            await ctx.send(chunk)
    except Exception as e:
        await ctx.send(f"Error: {e}")


@bot.command(name="lookup")
async def cmd_lookup(ctx, team: str = ""):
    """Look up a team's EPA and stats."""
    if not team:
        await ctx.send("Usage: `!lookup <team_number>`")
        return

    def _lookup():
        import subprocess
        result = subprocess.run(
            ["python3", str(SCOUT_PATH / "the_scout.py"), "lookup", team],
            capture_output=True, text=True, timeout=15,
        )
        return result.stdout or result.stderr

    try:
        text = await asyncio.to_thread(_lookup)
        for chunk in split_for_discord(f"```\n{text}\n```"):
            await ctx.send(chunk)
    except Exception as e:
        await ctx.send(f"Error: {e}")


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
