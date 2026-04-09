#!/usr/bin/env python3
"""
The Engine — Wiki Update Script (Karpathy LLM Wiki Pattern)
Team 2950 — The Devastators

Automated incremental update loop for the design-intelligence wiki.
Takes a new source (URL, file path, or raw text), reads the existing wiki,
identifies which pages are affected, and outputs proposed diffs for human review.

Does NOT auto-commit. Outputs diffs to stdout and optionally writes .patch files.

Usage:
  python3 wiki_update.py url "https://www.chiefdelphi.com/t/..."
  python3 wiki_update.py file "/path/to/team_binder.pdf"
  python3 wiki_update.py text "Team 254 released their 2026 CAD..."
  python3 wiki_update.py file source.md --apply    # Apply changes directly
  python3 wiki_update.py --dry-run url "https://..."  # Show affected pages only

Requires: ANTHROPIC_API_KEY environment variable (uses Claude API for analysis).
"""

import argparse
import json
import os
import sys
import textwrap
from datetime import datetime
from pathlib import Path

WIKI_DIR = Path(__file__).parent.parent / "design-intelligence"
WIKI_INDEX = WIKI_DIR / "WIKI_INDEX.md"

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
            # Try to extract text from PDF
            try:
                import subprocess
                result = subprocess.run(
                    ["python3", "-c", f"""
import sys
try:
    import fitz  # PyMuPDF
    doc = fitz.open("{path}")
    for page in doc:
        print(page.get_text())
except ImportError:
    # Fallback: just note it's a PDF
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
        # Use requests if available, otherwise note the URL
        try:
            import requests
            resp = requests.get(source_value, timeout=30,
                                headers={"User-Agent": "TheEngine/1.0"})
            resp.raise_for_status()
            content = resp.text

            # Strip HTML tags for rough text extraction
            import re
            content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL)
            content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL)
            content = re.sub(r'<[^>]+>', ' ', content)
            content = re.sub(r'\s+', ' ', content).strip()

            # Truncate very long pages
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
# ANALYSIS — Identify affected wiki pages
# ═══════════════════════════════════════════════════════════════════

def analyze_source(source: dict) -> dict:
    """
    Analyze ingested source content and identify which wiki pages are affected.
    Uses keyword matching and entity detection.

    Returns: {
        "affected_files": {filename: [reasons]},
        "detected_teams": [team_numbers],
        "detected_mechanisms": [mechanism_names],
        "detected_keywords": [keywords],
        "contradictions": [potential rule contradictions],
        "summary": str,
    }
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

    # Detect team numbers
    import re
    # Match "team 254", "frc 254", "254's", "#254", "team254", etc.
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
    This is used with the Anthropic API to get specific diffs.
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
Output ONLY the diff in this format:

SECTION: <section heading where change goes>
OLD: <exact text to replace (or "NEW ADDITION" if adding)>
NEW: <replacement text>
REASON: <why this change is needed>

Rules:
- Only propose changes supported by the new source content
- Preserve existing formatting and structure
- Flag contradictions with existing rules — don't silently override them
- If no changes are needed for this page, output: NO_CHANGES_NEEDED
- Keep changes minimal and precise
"""
    return prompt


def generate_diffs_local(source: dict, analysis: dict) -> list[dict]:
    """
    Generate proposed diffs using local heuristic analysis (no API needed).
    Returns a list of proposed changes.
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
            })
            continue

        current = wiki_path.read_text()

        # For now, record what WOULD change and why — actual content generation
        # requires the Claude API (see generate_diffs_api below)
        diffs.append({
            "file": wiki_file,
            "status": "NEEDS_UPDATE",
            "reasons": reasons,
            "current_size": len(current),
            "changes": [f"[Requires Claude API to generate specific changes] Reason: {r}"
                        for r in reasons],
        })

    return diffs


def generate_diffs_api(source: dict, analysis: dict) -> list[dict]:
    """
    Generate proposed diffs using Claude API for precise content updates.
    Requires ANTHROPIC_API_KEY environment variable.
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

            diffs.append({
                "file": wiki_file,
                "status": "DIFF_GENERATED",
                "reasons": reasons,
                "diff": diff_text,
            })
        except Exception as e:
            diffs.append({
                "file": wiki_file,
                "status": "API_ERROR",
                "reasons": reasons,
                "error": str(e),
            })

    return diffs


# ═══════════════════════════════════════════════════════════════════
# OUTPUT
# ═══════════════════════════════════════════════════════════════════

def print_analysis(source: dict, analysis: dict):
    """Print the analysis results."""
    print(f"\n{'═' * 65}")
    print(f"  THE ENGINE — WIKI UPDATE ANALYSIS")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'═' * 65}")

    # Source info
    meta = source.get("metadata", {})
    if source["type"] == "url":
        print(f"\n  Source: {meta.get('url', 'unknown')}")
    elif source["type"] == "file":
        print(f"\n  Source: {meta.get('name', 'unknown')} ({meta.get('size', 0)} bytes)")
    else:
        print(f"\n  Source: inline text ({meta.get('length', 0)} chars)")

    # Summary
    print(f"  {analysis['summary']}")

    # Detected entities
    if analysis["detected_teams"]:
        print(f"\n  Teams detected: {', '.join(analysis['detected_teams'])}")
    if analysis["detected_mechanisms"]:
        print(f"  Mechanisms: {', '.join(analysis['detected_mechanisms'])}")
    if analysis["detected_keywords"]:
        print(f"  Keywords: {', '.join(analysis['detected_keywords'])}")

    # Affected files
    if analysis["affected_files"]:
        print(f"\n  AFFECTED WIKI PAGES ({len(analysis['affected_files'])}):")
        for filename, reasons in sorted(analysis["affected_files"].items()):
            print(f"    {filename}")
            for reason in reasons:
                print(f"      - {reason}")
    else:
        print(f"\n  No wiki pages affected by this source.")

    # Contradictions
    if analysis["contradictions"]:
        print(f"\n  ⚠ CONTRADICTIONS DETECTED:")
        for c in analysis["contradictions"]:
            print(f"    - {c}")

    print(f"\n{'═' * 65}\n")


def print_diffs(diffs: list[dict]):
    """Print proposed diffs."""
    if not diffs:
        print("  No diffs generated.")
        return

    print(f"\n{'─' * 65}")
    print(f"  PROPOSED CHANGES")
    print(f"{'─' * 65}")

    for diff in diffs:
        print(f"\n  [{diff['status']}] {diff['file']}")
        for reason in diff.get("reasons", []):
            print(f"    Reason: {reason}")

        if diff.get("diff"):
            print(f"\n{textwrap.indent(diff['diff'], '    ')}")
        elif diff.get("changes"):
            for change in diff["changes"]:
                print(f"    {change}")
        elif diff.get("error"):
            print(f"    Error: {diff['error']}")

    print(f"\n{'─' * 65}\n")


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
        "diffs": [{k: v for k, v in d.items() if k != "current_size"} for d in diffs],
    }

    report_dir = Path(__file__).parent.parent / "design-intelligence" / "_updates"
    report_dir.mkdir(exist_ok=True)
    report_path = report_dir / f"update_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"  Report saved: {report_path.relative_to(report_dir.parent.parent)}")
    return report_path


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
          python3 wiki_update.py --dry-run url "https://..."
          python3 wiki_update.py --use-api url "https://..."
        """),
    )
    parser.add_argument("source_type", choices=["url", "file", "text"],
                        help="Type of source to ingest")
    parser.add_argument("source_value", help="URL, file path, or text content")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show affected pages only, don't generate diffs")
    parser.add_argument("--use-api", action="store_true",
                        help="Use Claude API for precise diff generation")
    parser.add_argument("--save-report", action="store_true", default=True,
                        help="Save JSON report (default: true)")
    parser.add_argument("--no-report", action="store_true",
                        help="Skip saving JSON report")

    args = parser.parse_args()

    # Step 1: Ingest
    print(f"\n  [1/4] Ingesting source ({args.source_type})...")
    source = ingest_source(args.source_type, args.source_value)
    print(f"         Content: {len(source['content'])} chars")

    # Step 2: Analyze
    print(f"  [2/4] Analyzing against wiki index...")
    analysis = analyze_source(source)

    # Step 3: Print analysis
    print_analysis(source, analysis)

    if args.dry_run:
        print("  (--dry-run: skipping diff generation)")
        return

    if not analysis["affected_files"]:
        print("  No pages affected — nothing to update.")
        return

    # Step 4: Generate diffs
    print(f"  [3/4] Generating diffs for {len(analysis['affected_files'])} pages...")
    if args.use_api:
        diffs = generate_diffs_api(source, analysis)
    else:
        diffs = generate_diffs_local(source, analysis)

    print_diffs(diffs)

    # Step 5: Save report
    if not args.no_report:
        print(f"  [4/4] Saving report...")
        save_report(source, analysis, diffs)

    print("  Done. Review the proposed changes above, then apply manually or with --use-api.")


if __name__ == "__main__":
    main()
