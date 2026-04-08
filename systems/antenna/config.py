"""
The Antenna — Configuration
Chief Delphi Intelligence Watcher for THE ENGINE
Team 2950 — The Devastators
"""

import os
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "antenna.db"
LOG_PATH = BASE_DIR / "antenna.log"

# ── Chief Delphi API ───────────────────────────────────────────────
CD_BASE_URL = "https://www.chiefdelphi.com"
CD_USER_AGENT = "TheEngine/1.0 (FRC Team 2950; github.com/safiqsindha/TheEngine)"
CD_RATE_LIMIT_SECONDS = 1.0  # Min seconds between requests
CD_TOPICS_PER_PAGE = 30

# Categories we care about (Discourse category IDs)
# 9 = Technical, 5 = Competition, 7 = FIRST, 8 = Other
# We scan all categories but weight Technical and Competition higher
CD_PRIORITY_CATEGORIES = {9, 5}

# ── Tracked Teams ──────────────────────────────────────────────────
# Elite teams whose posts are always high-value intelligence
TRACKED_TEAMS = {
    254, 118, 1678, 6328, 3847, 1323, 2056, 4414, 2910, 1690, 1114, 973, 2826
}

# ── Relevance Scoring ─────────────────────────────────────────────
# Points awarded when keywords are found in title or body

MECHANISM_KEYWORDS = [
    "elevator", "intake", "climber", "turret", "shooter", "flywheel",
    "wrist", "swerve", "drivetrain", "arm", "pivot", "linkage",
    "roller", "funnel", "hook", "winch", "telescope", "cascade",
    "bumper", "bellypan", "gearbox", "gusset"
]

DESIGN_DOC_KEYWORDS = [
    "binder", "technical document", "technical binder", "cad release",
    "build blog", "design review", "behind the bumpers", "btb",
    "robot in 3 days", "ri3d"
]

OPEN_ALLIANCE_KEYWORDS = [
    "open alliance", "build thread", "week 1 update", "week 2 update",
    "week 3 update", "week 4 update", "week 5 update", "week 6 update",
    "week 7 update", "week 8 update", "oa update"
]

STRATEGY_KEYWORDS = [
    "lessons learned", "what we changed", "redesign", "post-mortem",
    "post mortem", "what worked", "what didn't work", "retrospective",
    "what we would change", "iteration"
]

SOFTWARE_TOOL_KEYWORDS = [
    "advantagekit", "advantagescope", "pathplanner", "choreo",
    "yolo", "limelight", "photonvision", "wpilib", "rev hardware client",
    "phoenix", "ctre", "navx", "pigeon"
]

CAD_CODE_DOMAINS = [
    "github.com", "cad.onshape.com", "grabcad.com"
]

VIDEO_KEYWORDS = [
    "reveal", "robot reveal", "match video", "behind the scenes",
    "youtube.com", "youtu.be"
]

# Score thresholds
SCORE_THRESHOLDS = {
    "ignore": 7,      # 0-7: not relevant
    "notable": 11,     # 8-11: store and include in digest
    "high": 15,        # 12-15: flag for immediate review
    "critical": 16,    # 16+: alert Engine Lead
}

# ── Discord ────────────────────────────────────────────────────────
# Set via environment variable or .env file
DISCORD_WEBHOOK_URL = os.environ.get("ANTENNA_DISCORD_WEBHOOK", "")

# ── Scraper Settings ──────────────────────────────────────────────
# How many pages to scan on each run (30 topics per page)
# 10 pages = 300 topics, covers ~1-2 days of CD activity
MAX_PAGES_PER_RUN = 10

# How many days back to look on first run (bootstrap)
BOOTSTRAP_DAYS = 7
