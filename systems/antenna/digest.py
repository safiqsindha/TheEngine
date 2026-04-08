"""
The Antenna — Weekly Digest Formatter (AN.4) + Action Recommender (AN.6)
Formats scored posts into a Discord-ready weekly intelligence digest.
Team 2950 — The Devastators

Design principle: NO bare URLs in digest body text.
URLs only appear on reaction-trackable messages, wrapped in <> to suppress embeds.
"""

from datetime import datetime, timedelta
from typing import Optional

from config import TRACKED_TEAMS, SCORE_THRESHOLDS


def format_weekly_digest(
    posts: list[dict],
    total_scanned: int = 0,
    week_start: Optional[datetime] = None,
    week_end: Optional[datetime] = None,
    db_total: int = 0,
    trends: Optional[list[dict]] = None,
) -> str:
    """
    Format the weekly digest from scored posts.
    Returns a single Discord message (kept under 1900 chars).
    NO URLs in this text — they go on separate reaction messages.
    """
    if not week_start:
        week_start = datetime.utcnow() - timedelta(days=7)
    if not week_end:
        week_end = datetime.utcnow()

    # Separate by tier
    critical = [p for p in posts if p.get("tier") == "critical"]
    high = [p for p in posts if p.get("tier") == "high"]
    notable = [p for p in posts if p.get("tier") == "notable"]
    high_priority = critical + high

    lines = []

    # Header in code block
    lines.append("```")
    lines.append("THE ANTENNA — Weekly Intelligence Digest")
    lines.append(f"Week of {week_start.strftime('%b %d')} – {week_end.strftime('%b %d, %Y')}")
    lines.append(
        f"Scanned: {total_scanned} | Relevant: {len(posts)} | High priority: {len(high_priority)}"
    )
    lines.append("```")

    # High Priority — titles only, no URLs
    if high_priority:
        lines.append("")
        lines.append("**HIGH PRIORITY** (react below to track)")
        for i, post in enumerate(high_priority, 1):
            target = f" → {post['engine_file_target']}" if post.get("engine_file_target") else ""
            teams = f" | Teams: {post['tracked_teams']}" if post.get("tracked_teams") else ""
            lines.append(
                f"**{i}.** {post['title'][:60]} "
                f"[{post['relevance_score']}]{teams}{target}"
            )

    # Notable — compact one-liners, no URLs
    if notable:
        lines.append("")
        shown = notable[:5]
        remaining = len(notable) - len(shown)
        lines.append(f"**NOTABLE** ({len(notable)} total)")
        for post in shown:
            likes = f" ({post['like_count']} likes)" if post.get("like_count") else ""
            lines.append(f"• [{post['relevance_score']}] {post['title'][:55]}{likes}")
        if remaining > 0:
            lines.append(f"*+{remaining} more — run `!top` for full list*")

    # Tracked team activity
    team_posts = _group_by_tracked_teams(posts)
    if team_posts:
        lines.append("")
        lines.append("**TRACKED TEAMS**")
        for team_num in sorted(team_posts.keys()):
            topics = team_posts[team_num]
            titles = ", ".join(t["title"][:30] for t in topics[:2])
            lines.append(f"• **{team_num}**: {len(topics)} post(s) — {titles}")
        active = set(team_posts.keys())
        silent = TRACKED_TEAMS - active
        if silent:
            lines.append(f"• No activity: {', '.join(str(t) for t in sorted(silent))}")

    # Community trends
    if trends:
        lines.append("")
        lines.append("**TRENDS**")
        for trend in trends[:5]:
            lines.append(f"• **{trend['keyword']}**: {trend['count']} threads")

    # Footer
    lines.append("")
    lines.append(f"```DB: {db_total} posts | Next digest: {(week_end + timedelta(days=7)).strftime('%b %d')}```")

    return "\n".join(lines)


def format_critical_alert(post: dict) -> str:
    """Format an immediate alert for a critical post (score >= 16)."""
    lines = [
        "**ANTENNA CRITICAL ALERT**",
        "",
        f"**{post['title']}**",
        f"<{post['url']}>",
        f"Score: {post['relevance_score']} | "
        f"{post['like_count']} likes | "
        f"{post['reply_count']} replies",
    ]
    if post.get("tracked_teams"):
        lines.append(f"Teams: {post['tracked_teams']}")
    if post.get("engine_file_target"):
        lines.append(f"**TARGET:** {post['engine_file_target']}")
    if post.get("action_recommendation"):
        lines.append(f"**ACTION:** {post['action_recommendation']}")
    return "\n".join(lines)


def split_for_discord(text: str, max_length: int = 1900) -> list[str]:
    """Split a message into Discord-safe chunks (under 2000 chars)."""
    if len(text) <= max_length:
        return [text]

    chunks = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > max_length:
            if current:
                chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line

    if current:
        chunks.append(current)

    return chunks


def _group_by_tracked_teams(posts: list[dict]) -> dict[int, list[dict]]:
    """Group posts by which tracked teams they mention."""
    team_posts = {}
    for post in posts:
        teams_str = post.get("tracked_teams", "")
        if not teams_str:
            continue
        for team_str in teams_str.split(","):
            try:
                team_num = int(team_str.strip())
                if team_num in TRACKED_TEAMS:
                    team_posts.setdefault(team_num, []).append(post)
            except ValueError:
                continue
    return team_posts
