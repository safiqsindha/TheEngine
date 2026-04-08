"""
The Antenna — Relevance Scoring Engine (AN.2)
Scores Chief Delphi topics by relevance to THE ENGINE's knowledge base.
Team 2950 — The Devastators
"""

import re
from typing import Optional

from config import (
    TRACKED_TEAMS,
    MECHANISM_KEYWORDS,
    DESIGN_DOC_KEYWORDS,
    OPEN_ALLIANCE_KEYWORDS,
    STRATEGY_KEYWORDS,
    SOFTWARE_TOOL_KEYWORDS,
    CAD_CODE_DOMAINS,
    VIDEO_KEYWORDS,
    SCORE_THRESHOLDS,
    CD_PRIORITY_CATEGORIES,
)


# ── Team number extraction ─────────────────────────────────────────
# Matches 3-4 digit numbers that look like FRC team numbers
# Avoids matching years (2024, 2025, 2026) and common non-team numbers
YEAR_PATTERN = re.compile(r'\b20[12]\d\b')
TEAM_NUMBER_PATTERN = re.compile(r'\b(\d{2,4})\b')


def extract_team_numbers(text: str) -> set[int]:
    """Extract FRC team numbers from text, filtering out years."""
    if not text:
        return set()
    years = set(YEAR_PATTERN.findall(text))
    candidates = TEAM_NUMBER_PATTERN.findall(text)
    teams = set()
    for num_str in candidates:
        if num_str in years:
            continue
        num = int(num_str)
        # FRC teams range from 1 to ~9999, skip very low numbers
        if 10 <= num <= 9999:
            teams.add(num)
    return teams


def find_keyword_matches(text: str, keywords: list[str]) -> list[str]:
    """Find which keywords appear in the text (case-insensitive)."""
    if not text:
        return []
    text_lower = text.lower()
    return [kw for kw in keywords if kw.lower() in text_lower]


def check_link_types(text: str) -> dict:
    """Check for CAD, code, and video links in text."""
    if not text:
        return {"cad": False, "code": False, "video": False}
    text_lower = text.lower()
    return {
        "cad": any(d in text_lower for d in ["cad.onshape.com", "grabcad.com", ".step", ".stp"]),
        "code": "github.com" in text_lower,
        "video": any(v in text_lower for v in ["youtube.com", "youtu.be"]),
    }


# ── Engine file targeting ──────────────────────────────────────────

def recommend_engine_target(topic: dict, score_breakdown: dict) -> tuple[str, str]:
    """
    Based on what triggered the score, recommend which Engine file
    to update and what action to take.

    Returns (engine_file_target, action_recommendation).
    """
    title = (topic.get("title") or "").lower()
    teams_found = score_breakdown.get("tracked_teams_found", set())
    keywords = score_breakdown.get("all_keywords", [])

    # Priority 1: Team 254 binder
    if 254 in teams_found and any(k in title for k in ["binder", "technical"]):
        return (
            "254_CROSS_SEASON_ANALYSIS.md",
            "Extract motor census, architecture decisions, rejected designs, "
            "software stack, weight breakdown. Update CROSS_SEASON_PATTERNS if "
            "any new rules emerge."
        )

    # Priority 2: Any tracked team binder/reveal
    if teams_found and any(k in title for k in ["binder", "technical", "reveal", "behind the bumpers"]):
        teams_str = ", ".join(str(t) for t in sorted(teams_found))
        return (
            "TEAM_DATABASE.md + MULTI_TEAM_ANALYSIS.md",
            f"Update tracked team(s) {teams_str}: key specs, design rationale, "
            "architecture decisions. Check against pattern rules."
        )

    # Priority 3: Open Alliance update
    if any(kw in keywords for kw in OPEN_ALLIANCE_KEYWORDS):
        return (
            "OPEN_ALLIANCE_TRACKER.md",
            "Update OA directory with mechanism choices and build progress."
        )

    # Priority 4: Mechanism innovation
    mech_kw = [k for k in keywords if k in MECHANISM_KEYWORDS]
    if mech_kw:
        return (
            "CROSS_SEASON_PATTERNS.md",
            f"Check if mechanism discussion ({', '.join(mech_kw)}) introduces "
            "a new pattern rule candidate or modifies existing rules."
        )

    # Priority 5: Software tool release
    sw_kw = [k for k in keywords if k in SOFTWARE_TOOL_KEYWORDS]
    if sw_kw:
        return (
            "OPEN_ALLIANCE_TRACKER.md (community tools)",
            f"New version or feature for {', '.join(sw_kw)}. "
            "Check relevance to Cockpit, Pit Crew, or Eye."
        )

    # Priority 6: CAD/code resource
    if score_breakdown.get("has_cad_link") or score_breakdown.get("has_code_link"):
        return (
            "OPEN_ALLIANCE_TRACKER.md (community resources)",
            "New CAD/code resource. Check if useful for Blueprint templates "
            "or other Engine systems."
        )

    # Priority 7: Strategy discussion
    if any(kw in keywords for kw in STRATEGY_KEYWORDS):
        return (
            "CROSS_SEASON_PATTERNS.md (meta-rules)",
            "Community strategy discussion. Check for consensus shifts "
            "that affect prediction engine rules."
        )

    return ("", "")


# ── Main scoring function ──────────────────────────────────────────

def score_topic(topic: dict) -> dict:
    """
    Score a Chief Delphi topic for relevance to The Engine.

    Input: dict with keys from CD API (title, excerpt, like_count,
           posts_count, category_id, tags, etc.)

    Returns: dict with score, tier, matched keywords, tracked teams,
             engine file target, and action recommendation.
    """
    title = topic.get("title", "")
    excerpt = topic.get("excerpt", "") or topic.get("raw_excerpt", "")
    tags_list = topic.get("tags", [])
    if isinstance(tags_list, list) and tags_list and isinstance(tags_list[0], dict):
        tags_text = " ".join(t.get("name", "") for t in tags_list)
    elif isinstance(tags_list, list):
        tags_text = " ".join(str(t) for t in tags_list)
    else:
        tags_text = str(tags_list)

    # Combine all searchable text
    search_text = f"{title} {excerpt} {tags_text}"

    score = 0
    breakdown = {
        "tracked_teams_found": set(),
        "all_keywords": [],
        "has_cad_link": False,
        "has_code_link": False,
        "has_video_link": False,
    }

    # ── 1. Tracked teams (+5 per team found) ──
    teams_in_text = extract_team_numbers(search_text)
    tracked_found = teams_in_text & TRACKED_TEAMS
    if tracked_found:
        score += 5 * len(tracked_found)
        breakdown["tracked_teams_found"] = tracked_found

    # ── 2. Mechanism keywords (+3) ──
    mech_matches = find_keyword_matches(search_text, MECHANISM_KEYWORDS)
    if mech_matches:
        score += 3
        breakdown["all_keywords"].extend(mech_matches)

    # ── 3. Design document keywords (+5) ──
    design_matches = find_keyword_matches(search_text, DESIGN_DOC_KEYWORDS)
    if design_matches:
        score += 5
        breakdown["all_keywords"].extend(design_matches)

    # ── 4. Open Alliance keywords (+4) ──
    oa_matches = find_keyword_matches(search_text, OPEN_ALLIANCE_KEYWORDS)
    if oa_matches:
        score += 4
        breakdown["all_keywords"].extend(oa_matches)

    # ── 5. Strategy keywords (+3) ──
    strategy_matches = find_keyword_matches(search_text, STRATEGY_KEYWORDS)
    if strategy_matches:
        score += 3
        breakdown["all_keywords"].extend(strategy_matches)

    # ── 6. Software tool keywords (+3) ──
    sw_matches = find_keyword_matches(search_text, SOFTWARE_TOOL_KEYWORDS)
    if sw_matches:
        score += 3
        breakdown["all_keywords"].extend(sw_matches)

    # ── 7. CAD/code/video links (+4 / +3 / +2) ──
    link_types = check_link_types(search_text)
    if link_types["cad"]:
        score += 4
        breakdown["has_cad_link"] = True
    if link_types["code"]:
        score += 3
        breakdown["has_code_link"] = True
    if link_types["video"]:
        score += 2
        breakdown["has_video_link"] = True

    # ── 8. Engagement scoring ──
    like_count = topic.get("like_count", 0) or 0
    reply_count = topic.get("posts_count", 0) or 0
    # Likes
    if like_count >= 100:
        score += 5
    elif like_count >= 50:
        score += 3
    # Replies
    if reply_count >= 50:
        score += 4
    elif reply_count >= 20:
        score += 2

    # ── 9. Determine tier ──
    if score >= SCORE_THRESHOLDS["critical"]:
        tier = "critical"
    elif score >= SCORE_THRESHOLDS["notable"] + 1:  # 12+
        tier = "high"
    elif score >= SCORE_THRESHOLDS["ignore"] + 1:  # 8+
        tier = "notable"
    else:
        tier = "ignore"

    # ── 10. Engine file targeting ──
    engine_file, action_rec = recommend_engine_target(topic, breakdown)

    return {
        "relevance_score": score,
        "tier": tier,
        "tracked_teams": ",".join(str(t) for t in sorted(breakdown["tracked_teams_found"])),
        "keywords_matched": ",".join(sorted(set(breakdown["all_keywords"]))),
        "has_cad_link": int(breakdown["has_cad_link"]),
        "has_code_link": int(breakdown["has_code_link"]),
        "has_video_link": int(breakdown["has_video_link"]),
        "engine_file_target": engine_file,
        "action_recommendation": action_rec,
    }


if __name__ == "__main__":
    # Quick test with sample topics
    test_topics = [
        {
            "title": "254 Technical Binder 2026 Released",
            "excerpt": "The Cheesy Poofs have released their technical binder for REBUILT. Elevator design, swerve drivetrain, GitHub code release.",
            "like_count": 234,
            "posts_count": 89,
            "tags": [{"name": "resources"}],
        },
        {
            "title": "Best 3D printer for FRC?",
            "excerpt": "Looking for recommendations on a 3D printer for our team shop.",
            "like_count": 5,
            "posts_count": 12,
            "tags": [],
        },
        {
            "title": "1323 Open Alliance Build Thread Week 4",
            "excerpt": "This week we finished our intake prototype. Full-width roller intake with under-bumper geometry. OnShape CAD link: cad.onshape.com/...",
            "like_count": 67,
            "posts_count": 34,
            "tags": [{"name": "open-alliance"}],
        },
        {
            "title": "AdvantageScope 4.0 Released",
            "excerpt": "Major update to AdvantageScope with new 3D visualization, PathPlanner integration, and mechanism state viewer.",
            "like_count": 112,
            "posts_count": 28,
            "tags": [],
        },
    ]

    print("=" * 60)
    print("ANTENNA SCORING ENGINE — TEST")
    print("=" * 60)
    for topic in test_topics:
        result = score_topic(topic)
        print(f"\n{'─' * 60}")
        print(f"Title: {topic['title']}")
        print(f"Score: {result['relevance_score']} | Tier: {result['tier']}")
        print(f"Teams: {result['tracked_teams'] or 'none'}")
        print(f"Keywords: {result['keywords_matched'] or 'none'}")
        print(f"Links: CAD={result['has_cad_link']} Code={result['has_code_link']} Video={result['has_video_link']}")
        if result['engine_file_target']:
            print(f"Target: {result['engine_file_target']}")
            print(f"Action: {result['action_recommendation']}")
