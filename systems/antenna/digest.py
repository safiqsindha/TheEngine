"""
The Antenna — Weekly Digest Formatter (AN.4) + Action Recommender (AN.6)
Formats scored posts into a Discord-ready weekly intelligence digest.
Team 2950 — The Devastators
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
) -> str:
    """
    Format the weekly digest from scored posts.
    Returns a string ready for Discord (may need splitting at 2000 chars).
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

    # Header
    lines = []
    lines.append("```")
    lines.append("=" * 55)
    lines.append("THE ANTENNA — Weekly Intelligence Digest")
    lines.append(f"Week of {week_start.strftime('%B %d')} - {week_end.strftime('%B %d, %Y')}")
    lines.append(
        f"Posts scanned: {total_scanned} | "
        f"Relevant: {len(posts)} | "
        f"High priority: {len(high_priority)}"
    )
    lines.append("=" * 55)
    lines.append("```")

    # High Priority section
    if high_priority:
        lines.append("")
        lines.append("**HIGH PRIORITY (action recommended)**")
        lines.append("")
        for i, post in enumerate(high_priority, 1):
            lines.append(f"**{i}. {post['title']}**")
            lines.append(f"   {post['url']}")
            lines.append(
                f"   Score: {post['relevance_score']} | "
                f"{post['like_count']} likes | "
                f"{post['reply_count']} replies"
            )
            if post.get("tracked_teams"):
                lines.append(f"   Teams: {post['tracked_teams']}")
            if post.get("keywords_matched"):
                lines.append(f"   Keywords: {post['keywords_matched']}")
            if post.get("engine_file_target"):
                lines.append(f"   **TARGET:** {post['engine_file_target']}")
            if post.get("action_recommendation"):
                lines.append(f"   **ACTION:** {post['action_recommendation']}")
            lines.append("")

    # Notable section
    if notable:
        lines.append("")
        lines.append("**NOTABLE (review when time allows)**")
        lines.append("")
        for i, post in enumerate(notable, len(high_priority) + 1):
            lines.append(f"{i}. **{post['title']}**")
            lines.append(f"   {post['url']}")
            score_info = f"Score: {post['relevance_score']}"
            if post["like_count"]:
                score_info += f" | {post['like_count']} likes"
            lines.append(f"   {score_info}")
            if post.get("keywords_matched"):
                lines.append(f"   Keywords: {post['keywords_matched']}")
            lines.append("")

    # Tracked team activity
    team_posts = _group_by_tracked_teams(posts)
    if team_posts:
        lines.append("")
        lines.append("**TRACKED TEAM ACTIVITY**")
        lines.append("")
        for team_num in sorted(team_posts.keys()):
            team_topics = team_posts[team_num]
            count = len(team_topics)
            titles = ", ".join(t["title"][:40] for t in team_topics[:3])
            lines.append(f"- **{team_num}**: {count} post(s) ({titles})")

        # Show tracked teams with no activity
        active_teams = set(team_posts.keys())
        silent_teams = TRACKED_TEAMS - active_teams
        if silent_teams:
            silent_str = ", ".join(str(t) for t in sorted(silent_teams))
            lines.append(f"- No activity: {silent_str}")
        lines.append("")

    # Footer
    lines.append("```")
    lines.append(f"Total posts in database: {db_total}")
    lines.append(
        f"Next digest: Sunday, "
        f"{(week_end + timedelta(days=7)).strftime('%B %d, %Y')}"
    )
    lines.append("```")

    return "\n".join(lines)


def format_critical_alert(post: dict) -> str:
    """Format an immediate alert for a critical post (score >= 16)."""
    lines = [
        "**ANTENNA CRITICAL ALERT**",
        "",
        f"**{post['title']}**",
        f"{post['url']}",
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


if __name__ == "__main__":
    # Test with sample data
    sample_posts = [
        {
            "title": "254 Technical Binder 2026 Released",
            "url": "https://www.chiefdelphi.com/t/254-binder/12345",
            "relevance_score": 18,
            "tier": "critical",
            "like_count": 234,
            "reply_count": 89,
            "tracked_teams": "254",
            "keywords_matched": "binder,elevator,swerve",
            "engine_file_target": "254_CROSS_SEASON_ANALYSIS.md",
            "action_recommendation": "Extract motor census and architecture.",
        },
        {
            "title": "1323 Build Thread — Mid-Season Redesign",
            "url": "https://www.chiefdelphi.com/t/1323-build/12346",
            "relevance_score": 14,
            "tier": "high",
            "like_count": 67,
            "reply_count": 34,
            "tracked_teams": "1323",
            "keywords_matched": "intake,build thread",
            "engine_file_target": "TEAM_DATABASE.md",
            "action_recommendation": "Update with redesign details.",
        },
        {
            "title": "AdvantageScope 4.0 Released",
            "url": "https://www.chiefdelphi.com/t/as-4/12347",
            "relevance_score": 9,
            "tier": "notable",
            "like_count": 112,
            "reply_count": 28,
            "tracked_teams": "",
            "keywords_matched": "advantagescope",
            "engine_file_target": "",
            "action_recommendation": "",
        },
    ]

    digest = format_weekly_digest(
        posts=sample_posts,
        total_scanned=847,
        db_total=1847,
    )
    print(digest)
    print(f"\n--- Digest length: {len(digest)} chars ---")
    chunks = split_for_discord(digest)
    print(f"--- Would split into {len(chunks)} Discord message(s) ---")
