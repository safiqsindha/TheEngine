#!/usr/bin/env python3
"""
The Engine — Wiki Update Script (Karpathy LLM Wiki Pattern)
Team 2950 — The Devastators

Automated incremental update loop for the design-intelligence wiki.
Takes a new source (URL, file path, raw text, or Antenna DB posts),
reads the existing wiki, identifies which pages are affected, generates
precise diffs via Claude API, and optionally applies them.

Modes:
  Single source:  url / file / text — one-shot analysis + diff
  Antenna feed:   antenna — pulls unprocessed high-priority CD posts
  Watch mode:     --watch — continuous loop polling Antenna every N minutes

Usage:
  python3 wiki_update.py url "https://www.chiefdelphi.com/t/..."
  python3 wiki_update.py file "/path/to/team_binder.pdf"
  python3 wiki_update.py text "Team 254 released their 2026 CAD..."
  python3 wiki_update.py antenna                          # Process new Antenna posts
  python3 wiki_update.py antenna --apply                  # Apply changes directly
  python3 wiki_update.py antenna --watch --interval 30    # Poll every 30 min
  python3 wiki_update.py --dry-run url "https://..."      # Show affected pages only
  python3 wiki_update.py --use-api url "https://..."      # Use Claude API for diffs

Requires: ANTHROPIC_API_KEY environment variable for --use-api / --apply modes.
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import textwrap
import time
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
WIKI_DIR = PROJECT_DIR / "design-intelligence"
WIKI_INDEX = WIKI_DIR / "WIKI_INDEX.md"
ANTENNA_DIR = PROJECT_DIR / "antenna"
ANTENNA_DB = ANTENNA_DIR / "antenna.db"

# ═══════════════════════════════════════════════════════════════════
# WIKI FILE CATALOG
# Maps each file to its purpose and what kind of updates affect it.
# This is the machine-readable companion to WIKI_INDEX.md.
# ═══════════════════════════════════════════════════════════════════

WIKI_FILES = {
    # Core Intelligence
    "CROSS_SEASON_PATTERNS.md": {
        "purpose": "18 prediction rules + 12 meta-rules",
        "triggers": ["new mechanism data", "rule contradiction", "new game validation",
                      "new elite team pattern"],
        "entities": ["rules R1-R19", "confidence scores", "game conditions"],
    },
    "254_CROSS_SEASON_ANALYSIS.md": {
        "purpose": "Deep patterns from Team 254 across seasons",
        "triggers": ["254 CAD release", "254 binder", "254 match data", "254 design change"],
        "entities": ["team 254"],
    },
    "MULTI_TEAM_ANALYSIS.md": {
        "purpose": "Cross-team comparison: 1678, 6328, 4414, 1323, 2910",
        "triggers": ["new data for tracked teams", "mechanism pattern change"],
        "entities": ["team 1678", "team 6328", "team 4414", "team 1323", "team 2910"],
    },
    "TEAM_DATABASE.md": {
        "purpose": "Historical inventory of elite teams with resource types",
        "triggers": ["new CAD release", "new code repo", "new binder", "new team discovered"],
        "entities": ["team resources", "CAD releases", "code repos"],
    },
    "OPEN_ALLIANCE_TRACKER.md": {
        "purpose": "Living index of teams whose public resources feed The Engine",
        "triggers": ["new Open Alliance post", "new team joins OA", "EPA update",
                      "new resource published"],
        "entities": ["Open Alliance teams", "EPA rankings", "GitHub repos"],
    },

    # Validation & Benchmarks
    "PREDICTION_ENGINE_VALIDATION_14GAME.md": {
        "purpose": "v2 engine tested against 14 historical games",
        "triggers": ["rule accuracy change", "new game validated"],
        "entities": ["rule accuracy", "game predictions"],
    },
    "REBUILT_VALIDATION.md": {
        "purpose": "2026 REBUILT game live validation",
        "triggers": ["new 2026 EPA data", "new 2026 mechanism data"],
        "entities": ["2026 REBUILT", "team EPA"],
    },
    "COMPETITIVE_BENCHMARKS.md": {
        "purpose": "Winning alliance score targets across games",
        "triggers": ["new competition results", "new season data"],
        "entities": ["winning scores", "EPA targets"],
    },
    "STATBOTICS_EPA_2026.md": {
        "purpose": "Real-time EPA data from 2026 REBUILT season",
        "triggers": ["new EPA data", "new competition results"],
        "entities": ["EPA rankings", "2026 data"],
    },

    # Architecture
    "ARCH_CAD_PIPELINE.md": {
        "purpose": "Autonomous CAD generation pipeline spec",
        "triggers": ["CAD pipeline improvement", "new COTS part source", "OnShape API change"],
        "entities": ["Blueprint pipeline", "OnShape", "COTS parts"],
    },
    "ARCH_CD_WATCHER.md": {
        "purpose": "Chief Delphi scraper spec",
        "triggers": ["Antenna improvement", "new scrape target", "CD API change"],
        "entities": ["Chief Delphi", "Antenna"],
    },

    # Training
    "TRAINING_MODULE_1_PATTERN_RULES.md": {
        "purpose": "Student education on team pattern analysis",
        "triggers": ["new team added to analysis", "rule change"],
        "entities": ["training", "pattern rules"],
    },
}

# Teams we track — maps team number to which files reference them
TRACKED_TEAMS = {
    "254": ["254_CROSS_SEASON_ANALYSIS.md", "CROSS_SEASON_PATTERNS.md",
            "TEAM_DATABASE.md", "OPEN_ALLIANCE_TRACKER.md", "MULTI_TEAM_ANALYSIS.md"],
    "1678": ["MULTI_TEAM_ANALYSIS.md", "TEAM_DATABASE.md", "OPEN_ALLIANCE_TRACKER.md"],
    "6328": ["MULTI_TEAM_ANALYSIS.md", "TEAM_DATABASE.md", "OPEN_ALLIANCE_TRACKER.md"],
    "4414": ["MULTI_TEAM_ANALYSIS.md", "TEAM_DATABASE.md"],
    "1323": ["MULTI_TEAM_ANALYSIS.md", "TEAM_DATABASE.md", "REBUILT_VALIDATION.md"],
    "2910": ["MULTI_TEAM_ANALYSIS.md", "TEAM_DATABASE.md", "OPEN_ALLIANCE_TRACKER.md"],
    "118": ["TEAM_DATABASE.md", "OPEN_ALLIANCE_TRACKER.md", "REBUILT_VALIDATION.md"],
    "3847": ["TEAM_DATABASE.md", "OPEN_ALLIANCE_TRACKER.md"],
    "1690": ["OPEN_ALLIANCE_TRACKER.md"],
    "1114": ["TEAM_DATABASE.md", "OPEN_ALLIANCE_TRACKER.md"],
    "973": ["TEAM_DATABASE.md", "OPEN_ALLIANCE_TRACKER.md"],
    "2056": ["TEAM_DATABASE.md", "OPEN_ALLIANCE_TRACKER.md"],
    "2826": ["TEAM_DATABASE.md"],
    "900": ["TEAM_DATABASE.md", "OPEN_ALLIANCE_TRACKER.md"],
}

# Mechanism keywords → files they affect
MECHANISM_KEYWORDS = {
    "swerve": ["CROSS_SEASON_PATTERNS.md", "ARCH_CAD_PIPELINE.md"],
    "intake": ["CROSS_SEASON_PATTERNS.md", "ARCH_CAD_PIPELINE.md"],
    "shooter": ["CROSS_SEASON_PATTERNS.md", "ARCH_CAD_PIPELINE.md"],
    "flywheel": ["CROSS_SEASON_PATTERNS.md", "ARCH_CAD_PIPELINE.md"],
    "elevator": ["CROSS_SEASON_PATTERNS.md", "ARCH_CAD_PIPELINE.md"],
    "climber": ["CROSS_SEASON_PATTERNS.md", "ARCH_CAD_PIPELINE.md"],
    "turret": ["CROSS_SEASON_PATTERNS.md"],
    "arm": ["CROSS_SEASON_PATTERNS.md", "ARCH_CAD_PIPELINE.md"],
    "drivetrain": ["CROSS_SEASON_PATTERNS.md"],
    "epa": ["COMPETITIVE_BENCHMARKS.md", "STATBOTICS_EPA_2026.md", "REBUILT_VALIDATION.md"],
}


# ═══════════════════════════════════════════════════════════════════
# SOURCE INGESTION
# ═══════════════════════════════════════════════════════════════════

def ingest_source(source_type: str, source_value: str) -> dict:
    """
    Ingest a new source and return structured content.
    Returns: {"type": str, "content": str, "metadata": dict}
    """
    if source_type == "text":
        return {
            "type": "text",
            "content": source_value,
            "metadata": {"length": len(source_value)},
        }

    elif source_type == "file":
        path = Path(source_value).expanduser()
        if not path.exists():
            print(f"  ERROR: File not found: {path}")
            sys.exit(1)

        if path.suffix == ".pdf":
            try:
                import subprocess
                result = subprocess.run(
                    ["python3", "-c", f"""
import sys
try:
    import fitz
    doc = fitz.open("{path}")
    for page in doc:
        print(page.get_text())
except ImportError:
    print(f"[PDF file: {path.name}, unable to extract - install PyMuPDF]")
"""],
                    capture_output=True, text=True, timeout=30
                )
                content = result.stdout or f"[PDF file: {path.name}]"
            except Exception:
                content = f"[PDF file: {path.name}]"
        else:
            content = path.read_text(errors="replace")

        return {
            "type": "file",
            "content": content,
            "metadata": {"path": str(path), "name": path.name, "size": path.stat().st_size},
        }

    elif source_type == "url":
        try:
            import requests
            resp = requests.get(source_value, timeout=30,
                                headers={"User-Agent": "TheEngine/1.0"})
            resp.raise_for_status()
            content = resp.text

            content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL)
            content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL)
            content = re.sub(r'<[^>]+>', ' ', content)
            content = re.sub(r'\s+', ' ', content).strip()

            if len(content) > 50000:
                content = content[:50000] + "\n\n[TRUNCATED — source exceeds 50k chars]"

        except ImportError:
            content = f"[URL: {source_value} — install 'requests' to fetch]"
        except Exception as e:
            content = f"[URL: {source_value} — fetch failed: {e}]"

        return {
            "type": "url",
            "content": content,
            "metadata": {"url": source_value},
        }

    else:
        print(f"  ERROR: Unknown source type: {source_type}")
        sys.exit(1)


# ═══════════════════════════════════════════════════════════════════
# ANTENNA INTEGRATION
# ═══════════════════════════════════════════════════════════════════

def get_antenna_connection() -> sqlite3.Connection:
    """Connect to the Antenna SQLite database."""
    if not ANTENNA_DB.exists():
        print(f"  ERROR: Antenna database not found at {ANTENNA_DB}")
        print(f"         Run the Antenna bot first to create it.")
        sys.exit(1)
    conn = sqlite3.connect(str(ANTENNA_DB))
    conn.row_factory = sqlite3.Row
    return conn


def get_unprocessed_posts(conn: sqlite3.Connection,
                          min_score: int = 12) -> list[dict]:
    """
    Get high-priority Antenna posts that haven't been wiki-processed yet.
    Joins against engine_updates to exclude already-processed posts.
    """
    rows = conn.execute("""
        SELECT p.* FROM posts p
        WHERE p.tier IN ('high', 'critical')
          AND p.relevance_score >= ?
          AND p.engine_file_target IS NOT NULL
          AND p.engine_file_target != ''
          AND p.topic_id NOT IN (
              SELECT DISTINCT eu.post_id FROM engine_updates eu
              WHERE eu.applied_by = 'wiki_update'
          )
        ORDER BY p.relevance_score DESC
        LIMIT 20
    """, (min_score,)).fetchall()
    return [dict(row) for row in rows]


def mark_post_wiki_processed(conn: sqlite3.Connection, topic_id: int,
                              files_updated: list[str]):
    """Record that a post has been processed by the wiki updater."""
    for wiki_file in files_updated:
        conn.execute("""
            INSERT INTO engine_updates (post_id, engine_file, change_description, applied_by)
            SELECT post_id, ?, ?, 'wiki_update'
            FROM posts WHERE topic_id = ?
        """, (wiki_file, f"Wiki auto-update from topic {topic_id}", topic_id))
    conn.commit()


def ingest_antenna_posts() -> list[dict]:
    """
    Pull unprocessed high-priority posts from the Antenna DB.
    Returns a list of source dicts (one per post).
    """
    conn = get_antenna_connection()
    posts = get_unprocessed_posts(conn)
    conn.close()

    sources = []
    for post in posts:
        content_parts = [
            f"Title: {post.get('title', '')}",
            f"Author: {post.get('author', '')}",
            f"URL: {post.get('url', '')}",
            f"Category: {post.get('category_name', '')}",
            f"Score: {post.get('relevance_score', 0)} | Tier: {post.get('tier', '')}",
            f"Teams: {post.get('tracked_teams', '')}",
            f"Keywords: {post.get('keywords_matched', '')}",
            f"Engine Target: {post.get('engine_file_target', '')}",
            f"Action: {post.get('action_recommendation', '')}",
        ]
        if post.get("raw_excerpt"):
            content_parts.append(f"\nExcerpt:\n{post['raw_excerpt']}")
        if post.get("summary"):
            content_parts.append(f"\nSummary:\n{post['summary']}")

        sources.append({
            "type": "antenna",
            "content": "\n".join(content_parts),
            "metadata": {
                "topic_id": post["topic_id"],
                "title": post.get("title", ""),
                "url": post.get("url", ""),
                "relevance_score": post.get("relevance_score", 0),
                "tier": post.get("tier", ""),
                "engine_file_target": post.get("engine_file_target", ""),
            },
        })

    return sources


# ═══════════════════════════════════════════════════════════════════
# ANALYSIS — Identify affected wiki pages
# ═══════════════════════════════════════════════════════════════════

def analyze_source(source: dict) -> dict:
    """
    Analyze ingested source content and identify which wiki pages are affected.
    Uses keyword matching and entity detection.
    """
    content = source["content"].lower()
    result = {
        "affected_files": {},
        "detected_teams": [],
        "detected_mechanisms": [],
        "detected_keywords": [],
        "contradictions": [],
        "summary": "",
    }

    def add_affected(filename, reason):
        if filename not in result["affected_files"]:
            result["affected_files"][filename] = []
        if reason not in result["affected_files"][filename]:
            result["affected_files"][filename].append(reason)

    # For Antenna sources, use the pre-computed engine_file_target
    if source["type"] == "antenna":
        target = source["metadata"].get("engine_file_target", "")
        if target:
            for f in target.split(","):
                f = f.strip()
                if f in WIKI_FILES:
                    add_affected(f, f"Antenna target: {source['metadata'].get('title', '')[:60]}")

    # Detect team numbers
    team_patterns = re.findall(
        r'(?:team\s*|frc\s*|#)(\d{1,5})\b|\b(\d{3,5})(?:\'s|\s+(?:robot|design|cad|code|binder))',
        content
    )
    found_teams = set()
    for groups in team_patterns:
        for g in groups:
            if g and g in TRACKED_TEAMS:
                found_teams.add(g)

    for team_num in found_teams:
        result["detected_teams"].append(team_num)
        for filename in TRACKED_TEAMS[team_num]:
            add_affected(filename, f"References tracked team {team_num}")

    # Detect mechanism keywords
    for keyword, files in MECHANISM_KEYWORDS.items():
        if keyword in content:
            result["detected_mechanisms"].append(keyword)
            for filename in files:
                add_affected(filename, f"Contains mechanism keyword: {keyword}")

    # Detect specific update triggers
    trigger_patterns = {
        "cad release": ("TEAM_DATABASE.md", "New CAD release mentioned"),
        "cad model": ("TEAM_DATABASE.md", "CAD model referenced"),
        "open alliance": ("OPEN_ALLIANCE_TRACKER.md", "Open Alliance mentioned"),
        "technical binder": ("TEAM_DATABASE.md", "Technical binder referenced"),
        "github": ("TEAM_DATABASE.md", "GitHub resource mentioned"),
        "onshape": ("ARCH_CAD_PIPELINE.md", "OnShape referenced"),
        "chief delphi": ("ARCH_CD_WATCHER.md", "Chief Delphi content"),
        "statbotics": ("STATBOTICS_EPA_2026.md", "Statbotics data referenced"),
        "kickoff": ("CROSS_SEASON_PATTERNS.md", "Game kickoff content"),
        "game manual": ("CROSS_SEASON_PATTERNS.md", "Game manual content"),
    }

    for pattern, (filename, reason) in trigger_patterns.items():
        if pattern in content:
            result["detected_keywords"].append(pattern)
            add_affected(filename, reason)

    # Detect potential rule contradictions
    rule_patterns = {
        "R1": r'(?:tank|west\s*coast|differential)\s*(?:drive|drivetrain)',
        "R2": r'(?:narrow|partial|half)\s*(?:width)?\s*intake',
        "R6": r'(?:turret|no\s*turret|fixed\s*shooter)',
    }

    for rule_id, pattern in rule_patterns.items():
        if re.search(pattern, content):
            result["contradictions"].append(
                f"{rule_id} may need review — source contains contrary pattern"
            )
            add_affected("CROSS_SEASON_PATTERNS.md",
                         f"Potential contradiction with {rule_id}")

    # Generate summary
    teams_str = ", ".join(result["detected_teams"]) if result["detected_teams"] else "none"
    mechs_str = ", ".join(result["detected_mechanisms"]) if result["detected_mechanisms"] else "none"
    n_affected = len(result["affected_files"])

    result["summary"] = (
        f"Source affects {n_affected} wiki pages. "
        f"Teams detected: {teams_str}. "
        f"Mechanisms: {mechs_str}."
    )

    return result


# ═══════════════════════════════════════════════════════════════════
# DIFF GENERATION — Propose updates for affected pages
# ═══════════════════════════════════════════════════════════════════

def generate_update_prompt(source: dict, analysis: dict, wiki_file: str) -> str:
    """
    Generate a prompt for Claude to produce the actual wiki page update.
    """
    wiki_path = WIKI_DIR / wiki_file
    if not wiki_path.exists():
        return ""

    current_content = wiki_path.read_text()
    reasons = analysis["affected_files"].get(wiki_file, [])

    prompt = f"""You are The Engine's wiki maintenance agent for FRC Team 2950.

CURRENT WIKI PAGE: {wiki_file}
---
{current_content[:8000]}
---

NEW SOURCE CONTENT:
---
{source['content'][:8000]}
---

REASONS THIS PAGE IS AFFECTED:
{chr(10).join(f'- {r}' for r in reasons)}

CONTRADICTIONS DETECTED:
{chr(10).join(f'- {c}' for c in analysis.get('contradictions', [])) or 'None'}

TASK: Generate the specific lines that need to change in {wiki_file}.
Output ONLY the diff in this exact format (one or more blocks):

```diff
SECTION: <section heading where change goes>
OLD: <exact text to replace (or "NEW ADDITION" if adding new content)>
NEW: <replacement text>
REASON: <why this change is needed>
```

Rules:
- Only propose changes supported by the new source content
- Preserve existing formatting and structure
- Flag contradictions with existing rules — don't silently override them
- If no changes are needed for this page, output exactly: NO_CHANGES_NEEDED
- Keep changes minimal and precise
- Each block must have all four fields: SECTION, OLD, NEW, REASON
"""
    return prompt


def parse_diff_blocks(diff_text: str) -> list[dict]:
    """Parse structured diff blocks from Claude API response."""
    if "NO_CHANGES_NEEDED" in diff_text:
        return []

    blocks = []
    current = {}

    for line in diff_text.split("\n"):
        line = line.strip()
        if line.startswith("SECTION:"):
            if current.get("section"):
                blocks.append(current)
            current = {"section": line[8:].strip()}
        elif line.startswith("OLD:"):
            current["old"] = line[4:].strip()
        elif line.startswith("NEW:"):
            current["new"] = line[4:].strip()
        elif line.startswith("REASON:"):
            current["reason"] = line[7:].strip()
            blocks.append(current)
            current = {}

    if current.get("section"):
        blocks.append(current)

    return blocks


def generate_diffs_local(source: dict, analysis: dict) -> list[dict]:
    """
    Generate proposed diffs using local heuristic analysis (no API needed).
    """
    diffs = []

    for wiki_file, reasons in analysis["affected_files"].items():
        wiki_path = WIKI_DIR / wiki_file
        if not wiki_path.exists():
            diffs.append({
                "file": wiki_file,
                "status": "FILE_NOT_FOUND",
                "reasons": reasons,
                "changes": [],
                "diff_blocks": [],
            })
            continue

        current = wiki_path.read_text()
        diffs.append({
            "file": wiki_file,
            "status": "NEEDS_UPDATE",
            "reasons": reasons,
            "current_size": len(current),
            "changes": [f"[Requires --use-api for specific changes] Reason: {r}"
                        for r in reasons],
            "diff_blocks": [],
        })

    return diffs


def generate_diffs_api(source: dict, analysis: dict) -> list[dict]:
    """
    Generate proposed diffs using Claude API for precise content updates.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("  WARNING: ANTHROPIC_API_KEY not set — falling back to local analysis")
        return generate_diffs_local(source, analysis)

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
    except ImportError:
        print("  WARNING: anthropic package not installed — falling back to local analysis")
        return generate_diffs_local(source, analysis)

    diffs = []
    for wiki_file, reasons in analysis["affected_files"].items():
        prompt = generate_update_prompt(source, analysis, wiki_file)
        if not prompt:
            continue

        try:
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            diff_text = response.content[0].text
            diff_blocks = parse_diff_blocks(diff_text)

            status = "NO_CHANGES" if not diff_blocks else "DIFF_GENERATED"
            diffs.append({
                "file": wiki_file,
                "status": status,
                "reasons": reasons,
                "diff": diff_text,
                "diff_blocks": diff_blocks,
            })
        except Exception as e:
            diffs.append({
                "file": wiki_file,
                "status": "API_ERROR",
                "reasons": reasons,
                "error": str(e),
                "diff_blocks": [],
            })

    return diffs


# ═══════════════════════════════════════════════════════════════════
# APPLY — Write diffs to wiki files
# ═══════════════════════════════════════════════════════════════════

def apply_diffs(diffs: list[dict]) -> list[str]:
    """
    Apply parsed diff blocks to wiki files.
    Returns list of files that were modified.
    """
    modified = []

    for diff in diffs:
        if diff["status"] != "DIFF_GENERATED" or not diff.get("diff_blocks"):
            continue

        wiki_path = WIKI_DIR / diff["file"]
        if not wiki_path.exists():
            continue

        content = wiki_path.read_text()
        original = content
        applied_count = 0

        for block in diff["diff_blocks"]:
            old = block.get("old", "")
            new = block.get("new", "")
            section = block.get("section", "")

            if not new:
                continue

            if old == "NEW ADDITION" or not old:
                # Insert new content after section heading
                if section:
                    marker = f"## {section}"
                    if marker not in content:
                        marker = f"# {section}"
                    if marker in content:
                        idx = content.index(marker) + len(marker)
                        next_newline = content.index("\n", idx) if "\n" in content[idx:] else len(content)
                        content = content[:next_newline] + "\n" + new + "\n" + content[next_newline:]
                        applied_count += 1
                    else:
                        content += f"\n\n## {section}\n{new}\n"
                        applied_count += 1
                else:
                    content += f"\n{new}\n"
                    applied_count += 1
            elif old in content:
                content = content.replace(old, new, 1)
                applied_count += 1

        if content != original:
            wiki_path.write_text(content)
            modified.append(diff["file"])
            print(f"    [APPLIED] {diff['file']} — {applied_count} change(s)")
        else:
            print(f"    [SKIPPED] {diff['file']} — no text matches found")

    return modified


# ═══════════════════════════════════════════════════════════════════
# OUTPUT
# ═══════════════════════════════════════════════════════════════════

def print_analysis(source: dict, analysis: dict):
    """Print the analysis results."""
    print(f"\n{'=' * 65}")
    print(f"  THE ENGINE — WIKI UPDATE ANALYSIS")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'=' * 65}")

    meta = source.get("metadata", {})
    if source["type"] == "url":
        print(f"\n  Source: {meta.get('url', 'unknown')}")
    elif source["type"] == "file":
        print(f"\n  Source: {meta.get('name', 'unknown')} ({meta.get('size', 0)} bytes)")
    elif source["type"] == "antenna":
        print(f"\n  Source: Antenna post — {meta.get('title', 'unknown')[:60]}")
        print(f"          Score: {meta.get('relevance_score', 0)} | Tier: {meta.get('tier', '')}")
    else:
        print(f"\n  Source: inline text ({meta.get('length', 0)} chars)")

    print(f"  {analysis['summary']}")

    if analysis["detected_teams"]:
        print(f"\n  Teams detected: {', '.join(analysis['detected_teams'])}")
    if analysis["detected_mechanisms"]:
        print(f"  Mechanisms: {', '.join(analysis['detected_mechanisms'])}")
    if analysis["detected_keywords"]:
        print(f"  Keywords: {', '.join(analysis['detected_keywords'])}")

    if analysis["affected_files"]:
        print(f"\n  AFFECTED WIKI PAGES ({len(analysis['affected_files'])}):")
        for filename, reasons in sorted(analysis["affected_files"].items()):
            print(f"    {filename}")
            for reason in reasons:
                print(f"      - {reason}")
    else:
        print(f"\n  No wiki pages affected by this source.")

    if analysis["contradictions"]:
        print(f"\n  CONTRADICTIONS DETECTED:")
        for c in analysis["contradictions"]:
            print(f"    - {c}")

    print(f"\n{'=' * 65}\n")


def print_diffs(diffs: list[dict]):
    """Print proposed diffs."""
    if not diffs:
        print("  No diffs generated.")
        return

    print(f"\n{'-' * 65}")
    print(f"  PROPOSED CHANGES")
    print(f"{'-' * 65}")

    for diff in diffs:
        print(f"\n  [{diff['status']}] {diff['file']}")
        for reason in diff.get("reasons", []):
            print(f"    Reason: {reason}")

        if diff.get("diff_blocks"):
            for block in diff["diff_blocks"]:
                print(f"\n    Section: {block.get('section', '?')}")
                if block.get("old") and block["old"] != "NEW ADDITION":
                    print(f"    - {block['old'][:120]}")
                print(f"    + {block.get('new', '')[:120]}")
                print(f"    Why: {block.get('reason', '?')}")
        elif diff.get("diff"):
            print(f"\n{textwrap.indent(diff['diff'], '    ')}")
        elif diff.get("changes"):
            for change in diff["changes"]:
                print(f"    {change}")
        elif diff.get("error"):
            print(f"    Error: {diff['error']}")

    print(f"\n{'-' * 65}\n")


def save_report(source: dict, analysis: dict, diffs: list[dict]):
    """Save a JSON report of the analysis."""
    report = {
        "timestamp": datetime.now().isoformat(),
        "source_type": source["type"],
        "source_metadata": source.get("metadata", {}),
        "analysis": {
            "affected_files": analysis["affected_files"],
            "detected_teams": analysis["detected_teams"],
            "detected_mechanisms": analysis["detected_mechanisms"],
            "detected_keywords": analysis["detected_keywords"],
            "contradictions": analysis["contradictions"],
            "summary": analysis["summary"],
        },
        "diffs": [{k: v for k, v in d.items() if k != "current_size"}
                  for d in diffs],
    }

    report_dir = WIKI_DIR / "_updates"
    report_dir.mkdir(exist_ok=True)
    report_path = report_dir / f"update_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"  Report saved: {report_path.relative_to(PROJECT_DIR)}")
    return report_path


# ═══════════════════════════════════════════════════════════════════
# PIPELINE — Process a single source end-to-end
# ═══════════════════════════════════════════════════════════════════

def process_source(source: dict, use_api: bool = False, apply: bool = False,
                   dry_run: bool = False, save: bool = True,
                   quiet: bool = False) -> dict:
    """
    Full pipeline for a single source: analyze → diff → optionally apply.
    Returns: {"analysis": dict, "diffs": list, "applied": list}
    """
    analysis = analyze_source(source)

    if not quiet:
        print_analysis(source, analysis)

    if dry_run or not analysis["affected_files"]:
        return {"analysis": analysis, "diffs": [], "applied": []}

    if use_api or apply:
        diffs = generate_diffs_api(source, analysis)
    else:
        diffs = generate_diffs_local(source, analysis)

    if not quiet:
        print_diffs(diffs)

    applied = []
    if apply:
        print(f"\n  Applying changes...")
        applied = apply_diffs(diffs)
        if applied:
            print(f"  Applied to {len(applied)} file(s): {', '.join(applied)}")
        else:
            print(f"  No changes applied (no matching text found).")

    if save:
        save_report(source, analysis, diffs)

    return {"analysis": analysis, "diffs": diffs, "applied": applied}


# ═══════════════════════════════════════════════════════════════════
# ANTENNA PIPELINE — Batch process unprocessed posts
# ═══════════════════════════════════════════════════════════════════

def process_antenna_feed(use_api: bool = False, apply: bool = False,
                         dry_run: bool = False) -> dict:
    """
    Pull unprocessed Antenna posts and run each through the wiki pipeline.
    Returns summary stats.
    """
    print(f"\n{'=' * 65}")
    print(f"  THE ENGINE — ANTENNA → WIKI FEED")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'=' * 65}")

    sources = ingest_antenna_posts()

    if not sources:
        print(f"\n  No unprocessed high-priority posts in Antenna DB.")
        print(f"  (Posts need tier=high/critical and engine_file_target set)")
        return {"processed": 0, "applied_total": 0}

    print(f"\n  Found {len(sources)} unprocessed post(s):")
    for s in sources:
        meta = s["metadata"]
        print(f"    [{meta['tier']}] {meta['relevance_score']:3d}  {meta['title'][:55]}")
    print()

    total_applied = 0
    conn = get_antenna_connection()

    for i, source in enumerate(sources):
        meta = source["metadata"]
        print(f"\n  --- [{i+1}/{len(sources)}] {meta['title'][:55]} ---")

        result = process_source(
            source, use_api=use_api, apply=apply,
            dry_run=dry_run, save=True, quiet=False,
        )

        # Mark as processed in Antenna DB
        if result["applied"]:
            mark_post_wiki_processed(conn, meta["topic_id"], result["applied"])
            total_applied += len(result["applied"])
        elif not dry_run:
            # Mark as processed even without changes, so we don't re-process
            mark_post_wiki_processed(
                conn, meta["topic_id"],
                list(result["analysis"]["affected_files"].keys())[:1] or ["_reviewed"],
            )

    conn.close()

    print(f"\n{'=' * 65}")
    print(f"  ANTENNA FEED COMPLETE")
    print(f"  Posts processed: {len(sources)}")
    print(f"  Wiki files updated: {total_applied}")
    print(f"{'=' * 65}\n")

    return {"processed": len(sources), "applied_total": total_applied}


# ═══════════════════════════════════════════════════════════════════
# WATCH MODE — Continuous polling loop
# ═══════════════════════════════════════════════════════════════════

def watch_loop(interval_minutes: int = 30, use_api: bool = False,
               apply: bool = False):
    """
    Continuously poll the Antenna DB for new posts and process them.
    Runs forever until interrupted.
    """
    print(f"\n{'=' * 65}")
    print(f"  THE ENGINE — WIKI WATCHER (CONTINUOUS MODE)")
    print(f"  Polling every {interval_minutes} minutes")
    print(f"  API mode: {'ON' if use_api else 'OFF'}")
    print(f"  Auto-apply: {'ON' if apply else 'OFF'}")
    print(f"  Press Ctrl+C to stop")
    print(f"{'=' * 65}\n")

    cycle = 0
    while True:
        cycle += 1
        print(f"\n  [Cycle {cycle}] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        try:
            result = process_antenna_feed(use_api=use_api, apply=apply)
            if result["processed"] > 0:
                print(f"  Processed {result['processed']} posts, "
                      f"updated {result['applied_total']} wiki files")
            else:
                print(f"  No new posts to process.")
        except Exception as e:
            print(f"  ERROR in cycle {cycle}: {e}")

        print(f"  Next check in {interval_minutes} minutes...")
        try:
            time.sleep(interval_minutes * 60)
        except KeyboardInterrupt:
            print(f"\n  Watcher stopped after {cycle} cycles.")
            break


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="The Engine — Wiki Update Script (Karpathy LLM Wiki Pattern)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Examples:
          python3 wiki_update.py url "https://www.chiefdelphi.com/t/..."
          python3 wiki_update.py file "team_binder.pdf"
          python3 wiki_update.py text "Team 254 released new CAD for their 2026 intake"
          python3 wiki_update.py antenna                          # Process Antenna posts
          python3 wiki_update.py antenna --apply --use-api        # Process + apply
          python3 wiki_update.py antenna --watch --interval 30    # Poll every 30m
          python3 wiki_update.py --dry-run url "https://..."
          python3 wiki_update.py --use-api url "https://..."
        """),
    )
    parser.add_argument("source_type", choices=["url", "file", "text", "antenna"],
                        help="Type of source to ingest (antenna = read from Antenna DB)")
    parser.add_argument("source_value", nargs="?", default="",
                        help="URL, file path, or text content (not needed for antenna)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show affected pages only, don't generate diffs")
    parser.add_argument("--use-api", action="store_true",
                        help="Use Claude API for precise diff generation")
    parser.add_argument("--apply", action="store_true",
                        help="Apply generated diffs to wiki files (implies --use-api)")
    parser.add_argument("--watch", action="store_true",
                        help="Continuous mode: poll Antenna DB on interval")
    parser.add_argument("--interval", type=int, default=30,
                        help="Watch mode poll interval in minutes (default: 30)")
    parser.add_argument("--no-report", action="store_true",
                        help="Skip saving JSON report")

    args = parser.parse_args()

    # --apply implies --use-api
    if args.apply:
        args.use_api = True

    # ── Antenna mode ──
    if args.source_type == "antenna":
        if args.watch:
            watch_loop(
                interval_minutes=args.interval,
                use_api=args.use_api,
                apply=args.apply,
            )
        else:
            process_antenna_feed(
                use_api=args.use_api,
                apply=args.apply,
                dry_run=args.dry_run,
            )
        return

    # ── Single source mode ──
    if not args.source_value:
        parser.error("source_value is required for url/file/text modes")

    print(f"\n  [1/4] Ingesting source ({args.source_type})...")
    source = ingest_source(args.source_type, args.source_value)
    print(f"         Content: {len(source['content'])} chars")

    print(f"  [2/4] Analyzing against wiki index...")
    process_source(
        source,
        use_api=args.use_api,
        apply=args.apply,
        dry_run=args.dry_run,
        save=not args.no_report,
    )


if __name__ == "__main__":
    main()
