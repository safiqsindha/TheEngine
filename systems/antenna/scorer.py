"""
The Antenna — Relevance Scoring Engine (AN.2)
Scores Chief Delphi topics by relevance to THE ENGINE's knowledge base.
Team 2950 — The Devastators
"""

import re
from typing import Optional

from config import (
    TRACKED_TEAMS,
    KNOWN_AUTHORS,
    MECHANISM_KEYWORDS,
    DESIGN_DOC_KEYWORDS,
    OPEN_ALLIANCE_KEYWORDS,
    STRATEGY_KEYWORDS,
    SOFTWARE_TOOL_KEYWORDS,
    COTS_PRODUCT_KEYWORDS,
    GAME_QA_KEYWORDS,
    STATBOTICS_KEYWORDS,
    CAD_CODE_DOMAINS,
    VIDEO_KEYWORDS,
    SCORE_THRESHOLDS,
    CD_PRIORITY_CATEGORIES,
    SCAN_MODE,
)


# ── Team number extraction ─────────────────────────────────────────
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

    # Priority 3: Game Q&A / rule clarification
    qa_kw = [k for k in keywords if k in GAME_QA_KEYWORDS]
    if qa_kw:
        return (
            "REBUILT_VALIDATION.md (or current game)",
            f"Rule clarification detected ({', '.join(qa_kw)}). Check if it "
            "affects prediction engine assumptions or mechanism legality."
        )

    # Priority 4: Open Alliance update
    if any(kw in keywords for kw in OPEN_ALLIANCE_KEYWORDS):
        return (
            "OPEN_ALLIANCE_TRACKER.md",
            "Update OA directory with mechanism choices and build progress."
        )

    # Priority 5: Statbotics / EPA discussion
    stats_kw = [k for k in keywords if k in STATBOTICS_KEYWORDS]
    if stats_kw:
        return (
            "STATBOTICS_EPA_2026.md",
            f"Statbotics/EPA discussion ({', '.join(stats_kw)}). Check for "
            "new analysis methods or data insights for The Scout."
        )

    # Priority 6: COTS product release
    cots_kw = [k for k in keywords if k in COTS_PRODUCT_KEYWORDS]
    if cots_kw:
        return (
            "OPEN_ALLIANCE_TRACKER.md (vendor products)",
            f"New COTS product or release ({', '.join(cots_kw[:3])}). "
            "Check relevance to Blueprint templates or team purchasing."
        )

    # Priority 7: Mechanism innovation
    mech_kw = [k for k in keywords if k in MECHANISM_KEYWORDS]
    if mech_kw:
        return (
            "CROSS_SEASON_PATTERNS.md",
            f"Check if mechanism discussion ({', '.join(mech_kw)}) introduces "
            "a new pattern rule candidate or modifies existing rules."
        )

    # Priority 8: Software tool release
    sw_kw = [k for k in keywords if k in SOFTWARE_TOOL_KEYWORDS]
    if sw_kw:
        return (
            "OPEN_ALLIANCE_TRACKER.md (community tools)",
            f"New version or feature for {', '.join(sw_kw)}. "
            "Check relevance to Cockpit, Pit Crew, or Eye."
        )

    # Priority 9: CAD/code resource
    if score_breakdown.get("has_cad_link") or score_breakdown.get("has_code_link"):
        return (
            "OPEN_ALLIANCE_TRACKER.md (community resources)",
            "New CAD/code resource. Check if useful for Blueprint templates "
            "or other Engine systems."
        )

    # Priority 10: Strategy discussion
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
           posts_count, category_id, tags, author, etc.)

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
    author = topic.get("author", "") or ""

    score = 0
    breakdown = {
        "tracked_teams_found": set(),
        "all_keywords": [],
        "has_cad_link": False,
        "has_code_link": False,
        "has_video_link": False,
        "is_known_author": False,
    }

    # ── 1. Tracked teams (+5 per team found) ──
    teams_in_text = extract_team_numbers(search_text)
    tracked_found = teams_in_text & TRACKED_TEAMS
    if tracked_found:
        score += 5 * len(tracked_found)
        breakdown["tracked_teams_found"] = tracked_found

    # ── 2. Known high-value author (+3) ──
    if author in KNOWN_AUTHORS:
        score += 3
        breakdown["is_known_author"] = True

    # ── 3. Mechanism keywords (+3) ──
    mech_matches = find_keyword_matches(search_text, MECHANISM_KEYWORDS)
    if mech_matches:
        score += 3
        breakdown["all_keywords"].extend(mech_matches)

    # ── 4. Design document keywords (+5) ──
    design_matches = find_keyword_matches(search_text, DESIGN_DOC_KEYWORDS)
    if design_matches:
        score += 5
        breakdown["all_keywords"].extend(design_matches)

    # ── 5. Open Alliance keywords (+4) ──
    oa_matches = find_keyword_matches(search_text, OPEN_ALLIANCE_KEYWORDS)
    if oa_matches:
        score += 4
        breakdown["all_keywords"].extend(oa_matches)

    # ── 6. Strategy keywords (+3) ──
    strategy_matches = find_keyword_matches(search_text, STRATEGY_KEYWORDS)
    if strategy_matches:
        score += 3
        breakdown["all_keywords"].extend(strategy_matches)

    # ── 7. Software tool keywords (+3) ──
    sw_matches = find_keyword_matches(search_text, SOFTWARE_TOOL_KEYWORDS)
    if sw_matches:
        score += 3
        breakdown["all_keywords"].extend(sw_matches)

    # ── 8. COTS product keywords (+3) ──
    cots_matches = find_keyword_matches(search_text, COTS_PRODUCT_KEYWORDS)
    if cots_matches:
        score += 3
        breakdown["all_keywords"].extend(cots_matches)

    # ── 9. Game Q&A / rule keywords (+3) ──
    qa_matches = find_keyword_matches(search_text, GAME_QA_KEYWORDS)
    if qa_matches:
        score += 3
        breakdown["all_keywords"].extend(qa_matches)

    # ── 10. Statbotics / EPA keywords (+3) ──
    stats_matches = find_keyword_matches(search_text, STATBOTICS_KEYWORDS)
    if stats_matches:
        score += 3
        breakdown["all_keywords"].extend(stats_matches)

    # ── 11. CAD/code/video links (+4 / +3 / +2) ──
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

    # ── 12. Engagement scoring ──
    like_count = topic.get("like_count", 0) or 0
    reply_count = topic.get("posts_count", 0) or 0
    if like_count >= 100:
        score += 5
    elif like_count >= 50:
        score += 3
    if reply_count >= 50:
        score += 4
    elif reply_count >= 20:
        score += 2

    # ── 13. Postseason bonus ──
    # In postseason mode, binder/code releases get extra weight
    if SCAN_MODE == "postseason":
        if design_matches:
            score += 3  # Extra weight on binders
        if link_types["code"]:
            score += 2  # Extra weight on code releases

    # ── 14. Determine tier ──
    if score >= SCORE_THRESHOLDS["critical"]:
        tier = "critical"
    elif score >= SCORE_THRESHOLDS["notable"] + 1:  # 12+
        tier = "high"
    elif score >= SCORE_THRESHOLDS["ignore"] + 1:  # 8+
        tier = "notable"
    else:
        tier = "ignore"

    # ── 15. Engine file targeting ──
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
    test_topics = [
        {
            "title": "254 Technical Binder 2026 Released",
            "excerpt": "The Cheesy Poofs have released their technical binder for REBUILT. Elevator design, swerve drivetrain, GitHub code release.",
            "like_count": 234, "posts_count": 89,
            "tags": [{"name": "resources"}], "author": "AdamHeard",
        },
        {
            "title": "Best 3D printer for FRC?",
            "excerpt": "Looking for recommendations on a 3D printer for our team shop.",
            "like_count": 5, "posts_count": 12, "tags": [], "author": "newuser123",
        },
        {
            "title": "1323 Open Alliance Build Thread Week 4",
            "excerpt": "This week we finished our intake prototype. Full-width roller intake with under-bumper geometry. OnShape CAD link: cad.onshape.com/...",
            "like_count": 67, "posts_count": 34,
            "tags": [{"name": "open-alliance"}], "author": "someone",
        },
        {
            "title": "AdvantageScope 4.0 Released",
            "excerpt": "Major update to AdvantageScope with new 3D visualization, PathPlanner integration.",
            "like_count": 112, "posts_count": 28, "tags": [], "author": "someone",
        },
        {
            "title": "2026 Team Update 19",
            "excerpt": "Rule clarification on game manual G205. Swerve modules must be fully contained.",
            "like_count": 89, "posts_count": 45,
            "tags": [{"name": "game"}], "author": "Billfred",
        },
        {
            "title": "REV ION System — Now Available",
            "excerpt": "REV Robotics announces the new ION motor controller system. REV Neo compatible.",
            "like_count": 156, "posts_count": 67,
            "tags": [], "author": "REV_Engineering",
        },
        {
            "title": "Statbotics EPA Analysis — Week 5 Rankings",
            "excerpt": "Updated EPA rankings with week 5 data. Top teams shifting. Win probability model updated.",
            "like_count": 45, "posts_count": 18,
            "tags": [], "author": "AriMB",
        },
    ]

    print("=" * 60)
    print("ANTENNA SCORING ENGINE — TEST (v2)")
    print("=" * 60)
    for topic in test_topics:
        result = score_topic(topic)
        print(f"\n{'─' * 60}")
        print(f"Title: {topic['title']}")
        print(f"Author: {topic.get('author', '?')} {'[KNOWN]' if topic.get('author') in KNOWN_AUTHORS else ''}")
        print(f"Score: {result['relevance_score']} | Tier: {result['tier']}")
        print(f"Teams: {result['tracked_teams'] or 'none'}")
        print(f"Keywords: {result['keywords_matched'] or 'none'}")
        print(f"Links: CAD={result['has_cad_link']} Code={result['has_code_link']} Video={result['has_video_link']}")
        if result['engine_file_target']:
            print(f"Target: {result['engine_file_target']}")
            print(f"Action: {result['action_recommendation']}")
