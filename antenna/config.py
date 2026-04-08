"""
The Antenna — Configuration
Chief Delphi Intelligence Watcher for THE ENGINE
Team 2950 — The Devastators
"""

import os
from pathlib import Path

# ── Load .env if present ───────────────────────────────────────────
BASE_DIR = Path(__file__).parent
_env_path = BASE_DIR / ".env"
if _env_path.exists():
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

# ── Paths ──────────────────────────────────────────────────────────
DB_PATH = BASE_DIR / "antenna.db"
LOG_PATH = BASE_DIR / "antenna.log"

# ── Chief Delphi API ───────────────────────────────────────────────
CD_BASE_URL = "https://www.chiefdelphi.com"
CD_USER_AGENT = "TheEngine/1.0 (FRC Team 2950; github.com/safiqsindha/TheEngine)"
CD_RATE_LIMIT_SECONDS = 1.0
CD_TOPICS_PER_PAGE = 30

# Discourse category IDs (from /categories.json)
# 9 = Technical, 5 = Competition, 7 = FIRST, 8 = Other
CD_PRIORITY_CATEGORIES = {9, 5}
CD_CATEGORY_SLUGS = {
    9: "technical",
    5: "competition",
    7: "first",
}

# ── Tracked Teams ──────────────────────────────────────────────────
_teams_env = os.environ.get("ANTENNA_TRACKED_TEAMS", "")
if _teams_env:
    TRACKED_TEAMS = {int(t.strip()) for t in _teams_env.split(",") if t.strip()}
else:
    TRACKED_TEAMS = {
        254, 118, 1678, 6328, 3847, 1323, 2056, 4414, 2910, 1690, 1114, 973, 2826
    }

# ── Known High-Value Authors ──────────────────────────────────────
# CD usernames of mentors/leads from tracked teams and respected CD regulars
KNOWN_AUTHORS = {
    # Team leads and mentors
    "Karthik",          # 1114 Simbotics legend, strategy guru
    "AdamHeard",        # 254 mentor
    "Travis_Covington", # 1678 Citrus Circuits
    "Nick_Lawrence",    # 1678
    "jaredhk",          # resource compiler, CD regular
    "Brandon_Holley",   # 6328 Mechanical Advantage
    "Nate_Laverdure",   # 2910 Jack in the Bot
    "AllenGregoryIV",   # 3847 Spectrum
    # CD regulars with consistently high-value posts
    "AriMB",            # strategy analysis
    "cadandcookies",    # CAD resources
    "Billfred",         # rules expert
    "Jon_Stratis",      # 1114
    "EricH",            # WPILib core
    "Peter_Johnson",    # WPILib lead
    "calcmogul",        # WPILib controls
    "Thad_House",       # WPILib
    "mjansen4857",      # PathPlanner creator
    "bovlb",            # rules and strategy
}

# ── Relevance Scoring Keywords ─────────────────────────────────────

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

COTS_PRODUCT_KEYWORDS = [
    "swerve module", "mk4i", "mk4n", "x2i", "thrifty swerve",
    "sds", "rev ion", "rev neo", "kraken", "falcon",
    "spark max", "spark flex", "talon fx", "talon srx",
    "rev max planetary", "versaplanetary", "ultraplanetary",
    "limelight 3", "limelight 4", "photonvision",
    "new product", "product release", "now available",
    "andymark", "rev robotics", "west coast products", "wcp",
    "thrifty bot", "the thrifty bot", "ttb",
    "cross the road electronics", "playing with fusion",
]

GAME_QA_KEYWORDS = [
    "team update", "game manual", "rule clarification",
    "q&a", "q and a", "head ref", "blue box",
    "inspection", "legal", "illegal", "rule change",
]

STATBOTICS_KEYWORDS = [
    "statbotics", "expected points added", "expected points", "opr",
    "ranking prediction", "match prediction",
    "win probability", "power ranking",
]

CAD_CODE_DOMAINS = [
    "github.com", "cad.onshape.com", "grabcad.com"
]

VIDEO_KEYWORDS = [
    "reveal", "robot reveal", "match video", "behind the scenes",
    "youtube.com", "youtu.be"
]

# ── Score thresholds ───────────────────────────────────────────────
SCORE_THRESHOLDS = {
    "ignore": 7,      # 0-7: not relevant
    "notable": 11,     # 8-11: store and include in digest
    "high": 15,        # 12-15: flag for immediate review
    "critical": 16,    # 16+: alert Engine Lead
}

# ── Discord ────────────────────────────────────────────────────────
DISCORD_WEBHOOK_URL = os.environ.get("ANTENNA_DISCORD_WEBHOOK", "")

# ── Scan Settings ─────────────────────────────────────────────────
MAX_PAGES_PER_RUN = int(os.environ.get("ANTENNA_MAX_PAGES", "10"))
BOOTSTRAP_DAYS = 7

# ── Seasonal Scan Modes ───────────────────────────────────────────
# Override with ANTENNA_SCAN_MODE env var
SCAN_MODE = os.environ.get("ANTENNA_SCAN_MODE", "normal")

SCAN_MODES = {
    "normal": {
        "scan_interval_hours": 24,
        "digest_day": "sunday",
        "digest_hour": 8,
        "max_pages": 10,
        "description": "Standard daily scan, weekly Sunday digest",
    },
    "kickoff": {
        "scan_interval_hours": 6,
        "digest_day": "daily",
        "digest_hour": 20,
        "max_pages": 20,
        "description": "Kickoff week: scan every 6h, daily digest at 8 PM",
    },
    "build": {
        "scan_interval_hours": 24,
        "digest_day": "sunday",
        "digest_hour": 8,
        "max_pages": 10,
        "description": "Build season: daily scan, focus on OA updates and reveals",
    },
    "competition": {
        "scan_interval_hours": 12,
        "digest_day": "sunday",
        "digest_hour": 8,
        "max_pages": 15,
        "description": "Competition season: twice daily, focus on match results and strategy",
    },
    "postseason": {
        "scan_interval_hours": 24,
        "digest_day": "sunday",
        "digest_hour": 8,
        "max_pages": 15,
        "description": "Post-season: daily, HIGH PRIORITY on binders and code releases",
    },
}

# ── Scheduler Settings ─────────────────────────────────────────────
SCAN_HOUR = 2    # Default daily scan at 2 AM
DIGEST_HOUR = 8  # Default weekly digest at 8 AM Sunday
