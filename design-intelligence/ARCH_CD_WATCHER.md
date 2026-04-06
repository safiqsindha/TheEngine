# THE ENGINE — Chief Delphi Intelligence Watcher
# Codename: "The Antenna"
# Target: Running by Summer 2026 (feeds into 2027 season prep)
# Team 2950 — The Devastators
# ═══════════════════════════════════════════════════════════════════

## Vision

Chief Delphi is where FRC's collective intelligence lives. Every day,
teams publish build threads, technical binders, mechanism reveals,
strategy discussions, and lessons learned. The problem: there are
hundreds of posts per day and no student has time to read them all.

The Antenna scans Chief Delphi once daily, identifies posts relevant
to The Engine's knowledge base, scores them by value, and stores the
best ones. Once per week, it sends a Discord summary with the top
finds and specific recommendations on what to pull into The Engine.

Over time, The Engine's pattern rules, tracked teams, and design
intelligence update themselves — driven by what the community is
actually building and discussing.

---

## How It Works

```
DAILY (automated, runs at 2 AM)
┌─────────────────────────────────────────────────────┐
│  Chief Delphi RSS / Discourse API                    │
│  └── Pull all new posts from last 24 hours           │
│      └── Categories: Technical Discussion, Build     │
│          Season, Open Alliance, Robot Showcase,      │
│          Programming, Controls, Strategy             │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│  RELEVANCE FILTER                                    │
│                                                      │
│  Score each post on:                                 │
│  - Contains tracked team number (254, 118, etc.) +5  │
│  - Contains mechanism keyword (elevator, intake,     │
│    swerve, turret, climber, shooter, YOLO, etc.) +3  │
│  - Is a build thread / technical binder release   +5 │
│  - Is an Open Alliance update                     +4 │
│  - Has >50 likes or >20 replies (high engagement) +3 │
│  - Contains CAD link (OnShape, GrabCAD, STEP)     +4 │
│  - Contains code link (GitHub)                    +3  │
│  - Contains video (YouTube reveal, match video)   +2  │
│  - Is from a known high-value poster              +3  │
│  - Contains keywords: "binder", "technical",          │
│    "lessons learned", "what we changed", "redesign",  │
│    "open alliance update", "week X", "reveal"     +2  │
│                                                      │
│  Threshold: posts scoring ≥8 are stored              │
│  Posts scoring ≥12 are flagged HIGH PRIORITY          │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│  LOCAL DATABASE (SQLite)                             │
│                                                      │
│  Per post:                                           │
│  - post_id, url, title, author                       │
│  - category, date, score                             │
│  - tracked_team (if applicable)                      │
│  - keywords matched                                  │
│  - summary (first 200 chars or LLM-generated)        │
│  - status: new / reviewed / pulled_into_engine       │
│  - action_taken (if any)                             │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼ (weekly, Sunday 8 AM)
┌─────────────────────────────────────────────────────┐
│  WEEKLY DISCORD DIGEST                               │
│                                                      │
│  Auto-posted to #engine-intelligence channel         │
│  Contains: top posts from the week, organized by     │
│  category, with specific action recommendations      │
└─────────────────────────────────────────────────────┘
```

---

## Weekly Discord Digest Format

```
═══════════════════════════════════════════════════════
🔭 THE ANTENNA — Weekly Intelligence Digest
Week of April 7-13, 2026
Posts scanned: 847 | Relevant: 23 | High priority: 4
═══════════════════════════════════════════════════════

🔴 HIGH PRIORITY (action recommended)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. 254 Technical Binder 2026 Released
   📎 https://chiefdelphi.com/t/...
   Score: 18 | 234 likes | 89 replies
   🎯 ACTION: Pull into 254_CROSS_SEASON_ANALYSIS.md
   Extract: motor census, architecture decisions, rejected designs,
   software stack, weight breakdown. Update CROSS_SEASON_PATTERNS
   if any new rules emerge.

2. 1323 Build Thread — Mid-Season Redesign of Intake
   📎 https://chiefdelphi.com/t/...
   Score: 14 | 67 likes | 34 replies
   🎯 ACTION: Update TEAM_DATABASE.md with redesign details.
   Check if redesign contradicts or confirms Rule 2 (full-width
   intake). Add to MULTI_TEAM_ANALYSIS.md.

🟡 NOTABLE (review when time allows)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

3. New OnShape FeatureScript: Auto Tube Notching v3.0
   📎 https://chiefdelphi.com/t/...
   Score: 10 | 45 likes
   📝 NOTE: Update OPEN_ALLIANCE_TRACKER.md community tools
   section. May improve CAD Pipeline template creation speed.

4. 6328 AdvantageScope 4.0 Released
   📎 https://chiefdelphi.com/t/...
   Score: 9 | 112 likes
   📝 NOTE: Check for new features relevant to The Cockpit
   dashboard or The Pit Crew diagnostic display.

5. Open Alliance Update — Team 525 Swartdogs Week 8
   📎 https://chiefdelphi.com/t/...
   Score: 9 | 28 replies
   📝 NOTE: Swartdogs in our OA tracking list. Check for
   mechanism choices that validate or challenge pattern rules.

🟢 TRACKED TEAM ACTIVITY (informational)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- 118 Robonauts: 2 posts (robot reveal discussion, Everybot update)
- 3847 Spectrum: 1 post (build blog update)
- 2056 OP Robotics: 0 posts
- 1678 Citrus Circuits: 1 post (code release)

📊 COMMUNITY TRENDS THIS WEEK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Hot topic: [telescope climbers vs hook climbers] (14 threads)
- New tool: [OnShape tube notcher v3.0] (widely adopted)
- Controversy: [swerve module comparison — MK4i vs X2i vs Thrifty]
- Game meta shift: [teams moving from turret to fixed shooter]

═══════════════════════════════════════════════════════
Next digest: Sunday, April 20, 2026
Total posts in database: 1,847
Engine updates triggered this week: 2
═══════════════════════════════════════════════════════
```

---

## Relevance Scoring System

### Keyword Categories

| Category | Keywords | Base Score |
|----------|----------|-----------|
| Tracked teams | 254, 118, 1678, 6328, 3847, 1323, 2056, 4414, 2910, 1690, 1114, 973, 2826 | +5 per team |
| Mechanism types | elevator, intake, climber, turret, shooter, flywheel, wrist, swerve, drivetrain | +3 |
| Design documents | binder, technical document, CAD release, build blog, design review | +5 |
| Open Alliance | "open alliance", "build thread", "week X update", "OA update" | +4 |
| Code/CAD links | github.com, cad.onshape.com, grabcad.com | +4 |
| Software tools | AdvantageKit, AdvantageScope, PathPlanner, Choreo, YOLO, Limelight, PhotonVision | +3 |
| Strategy | "lessons learned", "what we changed", "redesign", "post-mortem", "what worked" | +3 |
| High engagement | >50 likes | +3 |
| High engagement | >100 likes | +5 (replaces +3) |
| High discussion | >20 replies | +2 |
| High discussion | >50 replies | +4 (replaces +2) |
| Known authors | Mentors/leads from tracked teams, CD regulars with high rep | +3 |
| Video content | YouTube link with "reveal", "match", "behind the scenes" | +2 |

### Scoring Tiers

| Score | Tier | Action |
|-------|------|--------|
| 0-7 | Ignore | Not relevant to The Engine |
| 8-11 | Notable | Store in database, include in weekly digest |
| 12-15 | High Priority | Flag for immediate review, include action recommendation |
| 16+ | Critical | Alert via Discord DM to Engine Lead + include in digest |

---

## How The Antenna Improves The Engine

### Automatic Update Triggers

When specific post types are detected, The Antenna generates specific
recommendations for which Engine file to update:

| Post Type | Engine File to Update | What to Extract |
|-----------|----------------------|-----------------|
| Team 254 binder release | 254_CROSS_SEASON_ANALYSIS.md | Motor census, architecture, software |
| Any tracked team binder | TEAM_DATABASE.md + MULTI_TEAM_ANALYSIS.md | Key specs, design rationale |
| Mechanism innovation post | CROSS_SEASON_PATTERNS.md | New rule candidate or rule modification |
| New COTS product release | OPEN_ALLIANCE_TRACKER.md (community tools) | Product name, capabilities, vendor |
| Open Alliance update | OPEN_ALLIANCE_TRACKER.md (OA directory) | Mechanism choices, build progress |
| Software tool release | OPEN_ALLIANCE_TRACKER.md or ARCH docs | Version, new features, impact |
| Strategy discussion (>50 likes) | CROSS_SEASON_PATTERNS.md meta-rules | Community consensus on strategy |
| Game manual Q&A post | REBUILT_VALIDATION.md (or next game) | Rule clarifications affecting predictions |
| Statbotics EPA discussion | STATBOTICS_EPA_2026.md | New analysis methods, data insights |

### Seasonal Rhythm

| Period | Antenna Behavior |
|--------|-----------------|
| **Kickoff week** (January) | Scan every 6 hours. Flag ALL mechanism discussions. Track which teams announce what they're building. |
| **Build season** (Jan-Mar) | Daily scan. Focus on Open Alliance updates, mechanism reveals, mid-season redesigns. |
| **Competition season** (Mar-Apr) | Daily scan. Focus on match results, robot reveals, strategy shifts, meta changes. |
| **Post-season** (May-Jun) | Daily scan. HIGH PRIORITY period — binder releases, code releases, technical post-mortems. This is when 90% of learning content drops. |
| **Summer offseason** (Jul-Sep) | Daily scan. Focus on offseason event results, new tools/libraries, training resources. |
| **Pre-kickoff** (Oct-Dec) | Daily scan. Focus on rule rumors, evergreen rule changes, new products, training content. |

---

## Technical Implementation

### Data Source: Chief Delphi Discourse API

Chief Delphi runs on Discourse, which has a public JSON API:

```
# Get latest posts
GET https://www.chiefdelphi.com/latest.json

# Get posts in a category
GET https://www.chiefdelphi.com/c/technical-discussion/l/latest.json

# Get a specific topic
GET https://www.chiefdelphi.com/t/{topic_id}.json

# Search
GET https://www.chiefdelphi.com/search.json?q={query}
```

No authentication required for public content. Rate limit: be
reasonable (1 request per second, cache results).

### Software Stack

```
Python 3.11
├── requests (CD API calls)
├── sqlite3 (local database)
├── schedule (daily/weekly cron)
├── discord.py (webhook or bot for digest posting)
└── Optional: ollama (local LLM for post summarization)
```

### Database Schema

```sql
CREATE TABLE posts (
    post_id INTEGER PRIMARY KEY,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    author TEXT,
    category TEXT,
    date_posted DATETIME,
    relevance_score INTEGER,
    tier TEXT,  -- 'ignore', 'notable', 'high', 'critical'
    tracked_teams TEXT,  -- comma-separated team numbers
    keywords_matched TEXT,  -- comma-separated keywords
    summary TEXT,
    engine_file_target TEXT,  -- which Engine file to update
    action_recommendation TEXT,
    status TEXT DEFAULT 'new',  -- 'new', 'reviewed', 'pulled'
    reviewed_by TEXT,
    date_reviewed DATETIME
);

CREATE TABLE weekly_digests (
    digest_id INTEGER PRIMARY KEY,
    week_start DATE,
    week_end DATE,
    posts_scanned INTEGER,
    posts_relevant INTEGER,
    posts_high_priority INTEGER,
    discord_message_id TEXT,
    date_sent DATETIME
);

CREATE TABLE engine_updates (
    update_id INTEGER PRIMARY KEY,
    post_id INTEGER REFERENCES posts(post_id),
    engine_file TEXT,
    change_description TEXT,
    date_applied DATETIME,
    applied_by TEXT
);
```

### LLM-Enhanced Summarization (Optional)

If Ollama is running locally (or on the Jetson during offseason),
The Antenna can use the LLM to generate smarter summaries:

```python
def summarize_post(post_text, tracked_teams, engine_context):
    prompt = f"""You are an FRC design intelligence analyst for Team 2950.
    Summarize this Chief Delphi post in 2-3 sentences.
    Focus on: mechanism design decisions, lessons learned,
    software/controls innovations, and anything that confirms
    or challenges our pattern rules.

    Our tracked teams: {tracked_teams}
    Our pattern rules cover: swerve, intake, elevator, turret,
    climber, shooter, weight, cycle speed, autonomous, vision.

    Post:
    {post_text[:2000]}

    Summary:"""

    response = ollama.generate(model="llama3.2:3b", prompt=prompt)
    return response
```

Without the LLM, The Antenna uses the first 200 characters of the
post as the summary. The LLM version is better but not required.

---

## Discord Integration

### Channel Setup

Create a channel: `#engine-intelligence`
- Weekly digest posts here (Sunday 8 AM)
- Critical alerts post immediately (score ≥16)
- Only The Antenna bot posts — keeps it clean and scannable

### Webhook Setup (simplest)

```python
import requests

DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/..."

def send_digest(digest_markdown):
    # Discord has 2000 char limit per message
    # Split into multiple messages if needed
    chunks = split_into_chunks(digest_markdown, 1900)
    for chunk in chunks:
        requests.post(DISCORD_WEBHOOK_URL, json={
            "content": chunk,
            "username": "The Antenna 🔭",
        })
```

### Reaction-Based Workflow

After the digest posts, team members react:
- 👀 = "I'll review this post"
- ✅ = "I pulled this into The Engine"
- ❌ = "Not relevant, skip"
- 🔖 = "Save for later"

The Antenna bot tracks reactions and updates the database status
accordingly. This closes the loop — the team knows which posts
have been acted on and which are still pending.

---

## Development Roadmap

| Block | Task | Hours | Target |
|-------|------|-------|--------|
| AN.1 | CD API integration + post scraper | 6 | Summer 2026 |
| AN.2 | Relevance scoring engine + keyword system | 6 | Summer 2026 |
| AN.3 | SQLite database + post storage | 4 | Summer 2026 |
| AN.4 | Weekly digest formatter | 4 | Summer 2026 |
| AN.5 | Discord webhook integration | 3 | Summer 2026 |
| AN.6 | Action recommendation generator | 4 | Summer 2026 |
| AN.7 | LLM summarization (optional, if Ollama available) | 5 | Fall 2026 |
| **Total** | | **32** | |

---

## Integration with Other Engine Systems

```
The Antenna ──→ CROSS_SEASON_PATTERNS.md (new rules from binder analysis)
The Antenna ──→ OPEN_ALLIANCE_TRACKER.md (new teams, resources, tools)
The Antenna ──→ TEAM_DATABASE.md (tracked team updates)
The Antenna ──→ 254_CROSS_SEASON_ANALYSIS.md (when 254 publishes)
The Antenna ──→ MULTI_TEAM_ANALYSIS.md (cross-team mechanism comparisons)
The Antenna ──→ ARCH_CAD_PIPELINE.md (new OnShape tools, FeatureScripts)
The Antenna ──→ The Whisper (new LLM models, quantization techniques)
The Antenna ──→ The Eye (new computer vision tools, tracking algorithms)
The Antenna ──→ The Scout (Statbotics updates, new scouting methods)
The Antenna ──→ Senior Projects (flags posts that could be project topics)
```

The Antenna is the input funnel for the entire Engine ecosystem.
Without it, The Engine only gets smarter when a human manually
searches for new information. With it, The Engine surfaces relevant
information automatically and tells the team exactly where to put it.

---

## The Self-Improving Loop

```
Chief Delphi ──→ The Antenna ──→ Weekly Digest ──→ Human Review
                                                        │
     ┌──────────────────────────────────────────────────┘
     │
     ▼
Pattern Rules Updated ──→ Prediction Engine More Accurate
Team Database Updated ──→ Better CAD Templates
New Tools Discovered ──→ Faster Build Process
Strategy Shifts Detected ──→ Better Match Preparation
                                    │
                                    ▼
                        THE ENGINE GETS SMARTER
                        EVERY SINGLE WEEK
```

This is what makes The Engine a compound advantage. It's not a
static set of documents — it's a living system that absorbs the
FRC community's collective intelligence automatically and tells
the team exactly how to use it.

---

*Architecture document — The Antenna | THE ENGINE | Team 2950 The Devastators*
