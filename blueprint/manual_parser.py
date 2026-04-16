"""Ensemble game-manual parser with consensus voting.

Phase-2 kickoff automation. Parses an FRC game manual PDF through N
independent LLM calls, then merges the results by majority vote. Fields
where all parses agree are *locked*; fields with a majority (but not
unanimous) are *tentative*; fields with no majority are *ambiguous*.

The module is deliberately dependency-light — only `anthropic` and `pypdf`
beyond the stdlib. Tests inject a fake ``parse_fn`` to avoid real LLM calls.

Typical flow::

    parses = parse_manual("reefscape_2025.pdf", n_parses=3)
    merged, conflict = consensus(parses)
    diff_md = render_diff_markdown(parses, conflict)
    # ... mentor resolves conflicts ...
    final_md = finalize(merged, resolutions={...})
"""
from __future__ import annotations

import json
import os
import re
import statistics
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ManualParse:
    """Structured parse of a single LLM call on a game manual."""

    scoring: dict = field(default_factory=dict)  # {auto: [...], teleop: [...], endgame: [...]}
    game_pieces: list = field(default_factory=list)
    field_zones: list = field(default_factory=list)
    possession_limits: dict = field(default_factory=dict)
    ranking_points: list = field(default_factory=list)
    penalty_rules: list = field(default_factory=list)
    critical_constraints: dict = field(default_factory=dict)  # weight/size/start
    raw_text: str = ""  # for audit

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ConflictReport:
    """Per-field breakdown of consensus status."""

    locked_fields: list = field(default_factory=list)  # fully agreed
    tentative_fields: list = field(default_factory=list)  # majority
    ambiguous_fields: list = field(default_factory=list)  # no majority


# Fields that participate in the top-level vote. ``raw_text`` is excluded
# because it's a per-parse audit trail, not a structured output.
_TOP_LEVEL_FIELDS: tuple = (
    "scoring",
    "game_pieces",
    "field_zones",
    "possession_limits",
    "ranking_points",
    "penalty_rules",
    "critical_constraints",
)

_REQUIRED_JSON_KEYS: tuple = _TOP_LEVEL_FIELDS


# ---------------------------------------------------------------------------
# JSON schema + prompt
# ---------------------------------------------------------------------------

JSON_SCHEMA_DESCRIPTION = """\
{
  "scoring": {
    "auto":    [{"name": str, "points": int, "location": str}],
    "teleop":  [{"name": str, "points": int, "location": str}],
    "endgame": [{"name": str, "points": int, "location": str}]
  },
  "game_pieces": [{"name": str, "count_on_field": int, "notes": str}],
  "field_zones": [{"name": str, "alliance_scope": str, "notes": str}],
  "possession_limits": {"max_simultaneous": int, "notes": str},
  "ranking_points": [{"name": str, "criterion": str}],
  "penalty_rules":  [{"id": str, "severity": str, "summary": str}],
  "critical_constraints": {
    "weight_lbs": float,
    "max_height_in": float,
    "frame_perimeter_in": float,
    "starting_config": str
  }
}
"""

PROMPT_TEMPLATE = """\
You are an FRC game-manual structured-extraction agent. Read the manual
text below and emit a single JSON object matching this schema *exactly*:

{schema}

Rules:
- Output ONLY the JSON object, no prose, no code fences.
- Use null for unknown numeric fields, empty list for unknown list fields.
- `points` must be integers; `weight_lbs`, `max_height_in`, `frame_perimeter_in` are floats.
- Extract every scoring action you can find; do not paraphrase names.
- CRITICAL — emit ONE `scoring[]` entry for each distinct
  (phase, game_piece, field_location) combination. Do NOT combine game
  pieces into a single entry even if they share a row in a rulebook table.
  If a location accepts multiple pieces with different point values,
  emit one entry per piece. The `name` field MUST uniquely identify the
  (piece, location) pair — e.g. "Cargo in Cargo Ship" and
  "Hatch on Cargo Ship" are two separate entries, never merged into
  "game piece on cargo ship".

Worked example — 2-piece game (Reefscape 2025 has coral + algae):
If the manual says auto coral scored on L1 trough = 3 pts, auto coral on
L4 = 7 pts, auto algae in processor = 6 pts, auto algae in net = 4 pts,
emit FOUR separate scoring.auto entries:
  {{"name": "Coral on L1 (auto)", "points": 3, "location": "reef_l1"}}
  {{"name": "Coral on L4 (auto)", "points": 7, "location": "reef_l4"}}
  {{"name": "Algae in Processor (auto)", "points": 6, "location": "processor"}}
  {{"name": "Algae in Net (auto)", "points": 4, "location": "barge_net"}}
Never collapse these into a single "game piece scored" row. Do the same
for teleop and endgame. When in doubt, split.

Manual text:
<<<
{text}
>>>
"""


# ---------------------------------------------------------------------------
# PDF extraction
# ---------------------------------------------------------------------------


def extract_pdf_text(pdf_path: str) -> str:
    """Extract text from a PDF using pypdf. Returns empty string on failure."""
    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover - pypdf is a declared dep
        raise RuntimeError("pypdf is required for manual_parser; `pip install pypdf`")

    reader = PdfReader(pdf_path)
    chunks: list = []
    for page in reader.pages:
        try:
            chunks.append(page.extract_text() or "")
        except Exception:  # pragma: no cover - malformed PDFs
            continue
    return "\n".join(chunks)


FIRST_HTML_URL_TEMPLATE = (
    "https://firstfrc.blob.core.windows.net/frc{year}/Manual/HTML/{year}GameManual.htm"
)


def first_html_url(year: int) -> str:
    """Return FIRST's official HTML manual URL for a given kickoff year.

    Only 2024+ manuals are published in HTML. Earlier seasons are PDF-only.
    """
    return FIRST_HTML_URL_TEMPLATE.format(year=year)


def extract_html_text(source: str) -> str:
    """Extract text from an HTML manual, preserving table structure.

    ``source`` may be either a local file path or an ``http(s)://`` URL. The
    returned text embeds every ``<table>`` as a markdown pipe-table so the
    LLM sees per-cell scoring values instead of the collapsed linear text
    that ``pypdf`` produces on PDF inputs.

    Non-table paragraphs are preserved in reading order. Headings become
    ``#`` lines so the model can still anchor section context.

    Requires ``beautifulsoup4``. Handles FIRST's cp1252-encoded HTML files.
    """
    try:
        from bs4 import BeautifulSoup  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "beautifulsoup4 required for HTML manuals — `pip install beautifulsoup4`"
        ) from exc

    if source.startswith(("http://", "https://")):
        try:
            from urllib.request import Request, urlopen
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("urllib unavailable") from exc
        req = Request(source, headers={"User-Agent": "Mozilla/5.0 (TheEngine manual_parser)"})
        with urlopen(req, timeout=60) as resp:
            raw = resp.read()
    else:
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(source)
        raw = path.read_bytes()

    # FIRST publishes HTML as Windows-1252. Fall back to utf-8 for safety.
    try:
        soup = BeautifulSoup(raw, "html.parser", from_encoding="cp1252")
    except Exception:  # pragma: no cover
        soup = BeautifulSoup(raw, "html.parser")

    # Remove noisy/invisible containers that waste tokens.
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()

    parts: list[str] = []
    body = soup.body if soup.body else soup
    for el in body.descendants:  # type: ignore[union-attr]
        name = getattr(el, "name", None)
        if name is None:
            continue
        if name == "table":
            parts.append(_table_to_markdown(el))
        elif name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            level = int(name[1])
            text = el.get_text(" ", strip=True)
            if text:
                parts.append(f"\n{'#' * level} {text}\n")
    # Pull in paragraph text in document order. (We didn't grab paragraphs in
    # the loop above because tables contain <p>s that would double-count.)
    # Simpler: rebuild by walking top-level blocks.
    parts = []
    for block in _iter_blocks(body):
        if getattr(block, "name", None) == "table":
            parts.append(_table_to_markdown(block))
        elif getattr(block, "name", None) in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            level = int(block.name[1])
            text = block.get_text(" ", strip=True)
            if text:
                parts.append(f"\n{'#' * level} {text}\n")
        else:
            text = block.get_text(" ", strip=True) if hasattr(block, "get_text") else str(block)
            if text:
                parts.append(text)
    return "\n".join(parts)


def _iter_blocks(root) -> "list":  # type: ignore[no-untyped-def]
    """Yield top-level block-like elements in document order, skipping tables' innards.

    When we encounter a <table>, we yield the table and skip its descendants so
    we don't double-count the prose inside cells.
    """
    from bs4 import Tag  # type: ignore

    out: list = []
    if not hasattr(root, "children"):
        return out
    stack: list = list(root.children)
    while stack:
        node = stack.pop(0)
        if not isinstance(node, Tag):
            continue
        if node.name == "table":
            out.append(node)
            continue
        if node.name in {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li"}:
            out.append(node)
            continue
        # Recurse into children for divs/sections/etc.
        stack = list(node.children) + stack
    return out


def _table_to_markdown(table) -> str:  # type: ignore[no-untyped-def]
    """Render a BeautifulSoup <table> as a markdown pipe-table block.

    Expands ``rowspan`` and ``colspan`` so every logical cell is materialized
    at its true (row, col) position. Spanned cells are duplicated into each
    covered grid position, which is the shape Sonnet/Haiku needs to read a
    2-level header + spanned category column correctly.

    Without this, FRC manuals (which use rowspan for category labels like
    NOTES / STAGE and colspan for header groupings) collapse into orphaned
    rows the LLM can't align to columns.
    """
    rows = table.find_all("tr")
    if not rows:
        return ""

    # Pass 1: build a sparse grid[row][col] -> text, expanding spans.
    grid: list[list[str]] = []
    for _ in rows:
        grid.append([])

    # Track occupied cells so we can skip over them when spans collide.
    occupied: dict[tuple[int, int], bool] = {}

    for r_idx, tr in enumerate(rows):
        col = 0
        for cell in tr.find_all(["td", "th"]):
            # Advance past any already-occupied columns (from rowspan above).
            while occupied.get((r_idx, col), False):
                col += 1
            rowspan = int(cell.get("rowspan", "1") or "1")
            colspan = int(cell.get("colspan", "1") or "1")
            text = cell.get_text(" ", strip=True).replace("|", "/").replace("\n", " ")
            for dr in range(rowspan):
                for dc in range(colspan):
                    occupied[(r_idx + dr, col + dc)] = True
                    # Grow the target row as needed.
                    while len(grid[r_idx + dr]) <= col + dc:
                        grid[r_idx + dr].append("")
                    # Duplicate the cell text across every spanned position so
                    # the LLM sees the category label on every row it covers.
                    grid[r_idx + dr][col + dc] = text
            col += colspan

    # Normalize width.
    width = max((len(r) for r in grid), default=0)
    if width == 0:
        return ""
    for r in grid:
        while len(r) < width:
            r.append("")

    lines: list[str] = []
    lines.append("| " + " | ".join(grid[0]) + " |")
    lines.append("|" + "|".join(["---"] * width) + "|")
    for r in grid[1:]:
        lines.append("| " + " | ".join(r) + " |")
    return "\n" + "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# LLM parse call
# ---------------------------------------------------------------------------


ParseFn = Callable[[str, str], dict]


# Ordered by specificity — robot-weight rule first, then looser fallbacks.
# The bumper rule (R407) also contains "weigh no more than" so we must find
# the robot weight rule preferentially.
_WEIGHT_PATTERNS = [
    r"ROBOT\s+weight\s+(?:limit|must\s+not\s+exceed)",
    r"R10[0-9].{0,20}ROBOT\s+weight",
    r"125(?:\.[05])?\s*(?:lbs?|pounds?)",
    r"maximum\s+(?:ROBOT\s+)?weight",
    r"weigh\s+no\s+more\s+than",
]


def build_parse_window(manual_text: str, head_chars: int = 115_000, tail_chars: int = 10_000) -> str:
    """Build an LLM-facing window that stays under the 30k tokens/min cap.

    Keeps the head of the manual (scoring summary + most of the scoring rules)
    and splices in a targeted excerpt around weight-constraint language if it
    lives past the head cut. Returns concatenated text with a visible divider.
    """
    if len(manual_text) <= head_chars:
        return manual_text
    head = manual_text[:head_chars]
    rest = manual_text[head_chars:]
    splice = ""
    for pat in _WEIGHT_PATTERNS:
        m = re.search(pat, rest, re.IGNORECASE)
        if m:
            center = m.start()
            half = tail_chars // 2
            lo = max(0, center - half)
            hi = min(len(rest), center + half)
            splice = rest[lo:hi]
            break
    if not splice:
        return head
    return head + "\n\n<<< ROBOT RULES EXCERPT >>>\n\n" + splice


def _call_with_rate_limit_retry(client, model, prompt, max_retries=4):
    """Invoke the Anthropic client with exponential backoff on 429s.

    Sonnet 4.5 caps at 30k input tokens/min on the starter tier; 3 parses of
    ~30k tokens each reliably trip the limit without pacing.
    """
    import time as _time

    from anthropic import RateLimitError

    delay = 25.0
    for attempt in range(max_retries):
        try:
            return client.messages.create(
                model=model,
                max_tokens=8192,
                messages=[{"role": "user", "content": prompt}],
            )
        except RateLimitError:
            if attempt == max_retries - 1:
                raise
            _time.sleep(delay)
            delay = min(delay * 1.6, 90.0)
    raise RuntimeError("unreachable")


def _default_parse_fn(manual_text: str, model: str) -> dict:
    """Default LLM parse call — uses Anthropic client. Real API.

    Only invoked when the caller does not inject a fake ``parse_fn``.
    Tests must inject. Requires ``ANTHROPIC_API_KEY`` in env.
    """
    try:
        from anthropic import Anthropic
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("anthropic SDK required — `pip install anthropic`") from exc

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    client = Anthropic()
    # Window sized for Sonnet 4.5 at 30k input-tokens/min: ~115k head + 10k
    # targeted robot-rules excerpt keeps us under ~32k tokens per call without
    # dropping R103 weight (which sits ~130k chars into the 2024 HTML).
    prompt = PROMPT_TEMPLATE.format(
        schema=JSON_SCHEMA_DESCRIPTION,
        text=build_parse_window(manual_text),
    )
    resp = _call_with_rate_limit_retry(client, model, prompt)
    raw = "".join(getattr(b, "text", "") for b in resp.content)
    return _coerce_json(raw)


def _coerce_json(raw: str) -> dict:
    """Extract the first JSON object from a model response."""
    raw = raw.strip()
    # Strip code fences if present
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    # Find first {...} block greedily
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise ValueError(f"no JSON object found in model response: {raw[:200]!r}")
    result: dict = json.loads(m.group(0))
    return result


def validate_parse_dict(data: dict) -> None:
    """Raise a clear error if required schema keys are missing."""
    missing = [k for k in _REQUIRED_JSON_KEYS if k not in data]
    if missing:
        raise ValueError(
            f"manual parse missing required fields: {missing}. "
            f"Got keys: {sorted(data.keys())}"
        )


def parse_manual(
    pdf_path: str,
    n_parses: int = 3,
    model: str = "claude-sonnet-4-5",
    parse_fn: Optional[ParseFn] = None,
    inter_parse_delay_s: float = 0.0,
) -> list[ManualParse]:
    """Parse ``pdf_path`` through ``n_parses`` independent LLM calls.

    Parameters
    ----------
    pdf_path : str — path to a game-manual PDF (or .txt for testing).
    n_parses : int — number of independent parses to run (odd is best).
    model    : str — Anthropic model id; ignored when ``parse_fn`` is injected.
    parse_fn : callable(text, model) -> dict — dependency injection point
               for tests. When None, the default Anthropic-backed parser runs.
    """
    # Dispatch by extension / scheme. URLs route to HTML extractor.
    if pdf_path.startswith(("http://", "https://")):
        text = extract_html_text(pdf_path)
    else:
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(pdf_path)
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            text = extract_pdf_text(str(path))
        elif suffix in {".htm", ".html"}:
            text = extract_html_text(str(path))
        else:
            text = path.read_text()

    fn: ParseFn = parse_fn if parse_fn is not None else _default_parse_fn

    import time as _time
    results: list = []
    for i in range(n_parses):
        if i > 0 and inter_parse_delay_s > 0:
            _time.sleep(inter_parse_delay_s)
        data = fn(text, model)
        validate_parse_dict(data)
        results.append(
            ManualParse(
                scoring=data.get("scoring", {}) or {},
                game_pieces=list(data.get("game_pieces") or []),
                field_zones=list(data.get("field_zones") or []),
                possession_limits=data.get("possession_limits", {}) or {},
                ranking_points=list(data.get("ranking_points") or []),
                penalty_rules=list(data.get("penalty_rules") or []),
                critical_constraints=data.get("critical_constraints", {}) or {},
                raw_text=text,
            )
        )
    return results


# ---------------------------------------------------------------------------
# Consensus
# ---------------------------------------------------------------------------


def _normalize(value: Any) -> Any:
    """Canonical form for exact-match voting.

    - Strings: lowercase + strip.
    - Lists: recursively normalized + sorted by JSON repr (order-insensitive).
    - Dicts: recursively normalized.
    - Numerics / None / bool: passthrough.
    """
    if isinstance(value, str):
        return value.strip().lower()
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        norm = [_normalize(v) for v in value]
        try:
            norm.sort(key=lambda x: json.dumps(x, sort_keys=True, default=str))
        except TypeError:
            pass
        return norm
    return value


def _hashable(value: Any) -> str:
    """Stable hashable key for a normalized value."""
    return json.dumps(_normalize(value), sort_keys=True, default=str)


def _vote(values: list) -> tuple[str, Any, list]:
    """Vote across ``values``. Returns (status, winner, alternatives).

    status in {"locked", "tentative", "ambiguous"}.
    """
    if not values:
        return "ambiguous", None, []
    buckets: dict = {}
    for v in values:
        key = _hashable(v)
        buckets.setdefault(key, []).append(v)
    if len(buckets) == 1:
        return "locked", values[0], []
    # rank buckets by count desc
    ranked = sorted(buckets.items(), key=lambda kv: -len(kv[1]))
    top_key, top_vals = ranked[0]
    top_count = len(top_vals)
    n = len(values)
    if top_count > n / 2:
        alts = [kv[1][0] for kv in ranked[1:]]
        return "tentative", top_vals[0], alts
    alts = [kv[1][0] for kv in ranked]
    return "ambiguous", None, alts


def _median_numeric(values: list, tol: float = 0.05) -> tuple[str, Any, list]:
    """Numeric consensus: locked if all equal, tentative if within ``tol``
    relative range, else ambiguous.
    """
    clean = [v for v in values if isinstance(v, (int, float)) and v is not None]
    if len(clean) != len(values) or not clean:
        return _vote(values)
    if len(set(clean)) == 1:
        return "locked", clean[0], []
    lo, hi = min(clean), max(clean)
    pivot = max(abs(lo), abs(hi), 1e-9)
    if (hi - lo) / pivot <= tol:
        med = statistics.median(clean)
        alts = [v for v in clean if v != med]
        return "tentative", med, alts
    return "ambiguous", None, clean


def _consensus_scoring(parses: list) -> tuple[dict, list, list, list]:
    """Per-phase, per-action-name consensus on the scoring tree.

    Returns (merged_scoring, locked_paths, tentative_entries, ambiguous_entries)
    where ``*_entries`` are dicts describing each tentative/ambiguous path.
    """
    merged: dict = {}
    locked_paths: list = []
    tentative: list = []
    ambiguous: list = []

    phases = set()
    for p in parses:
        phases.update(p.scoring.keys())

    for phase in sorted(phases):
        phase_entries = [p.scoring.get(phase, []) or [] for p in parses]
        # Collect all action names observed
        names = []
        seen = set()
        for lst in phase_entries:
            for entry in lst:
                n = str(entry.get("name", "")).strip().lower()
                if n and n not in seen:
                    seen.add(n)
                    names.append(n)

        merged_phase: list = []
        for name in names:
            # Gather matching entry from each parse
            per_parse: list = []
            for lst in phase_entries:
                match = next(
                    (e for e in lst if str(e.get("name", "")).strip().lower() == name),
                    None,
                )
                per_parse.append(match)

            present = [e for e in per_parse if e is not None]
            if len(present) < len(parses):
                # Not every parse saw this action — ambiguous presence
                ambiguous.append(
                    {
                        "path": f"scoring.{phase}.{name}",
                        "reason": "presence",
                        "options": present,
                    }
                )
                if present:
                    merged_phase.append(present[0])
                continue

            # Vote on points + location
            pts_values = [e.get("points") for e in present]
            loc_values = [e.get("location") for e in present]
            pts_status, pts_winner, pts_alts = _median_numeric(pts_values)
            loc_status, loc_winner, loc_alts = _vote(loc_values)

            chosen = dict(present[0])
            chosen["points"] = pts_winner if pts_winner is not None else present[0].get("points")
            chosen["location"] = loc_winner if loc_winner is not None else present[0].get("location")

            path_pts = f"scoring.{phase}.{name}.points"
            path_loc = f"scoring.{phase}.{name}.location"
            if pts_status == "locked":
                locked_paths.append(path_pts)
            elif pts_status == "tentative":
                tentative.append({"path": path_pts, "chosen": pts_winner, "alternatives": pts_alts})
            else:
                ambiguous.append({"path": path_pts, "options": pts_values})

            if loc_status == "locked":
                locked_paths.append(path_loc)
            elif loc_status == "tentative":
                tentative.append({"path": path_loc, "chosen": loc_winner, "alternatives": loc_alts})
            else:
                ambiguous.append({"path": path_loc, "options": loc_values})

            merged_phase.append(chosen)

        merged[phase] = merged_phase

    return merged, locked_paths, tentative, ambiguous


def _flag_phase_location_overlaps(
    merged_scoring: dict, report: ConflictReport
) -> None:
    """Post-check: if two entries share (phase, location) but have different
    ``points`` values, flag both as TENTATIVE (not locked).

    This catches the dual-piece-game failure mode where Haiku collapsed
    two pieces at the same location into a single entry with one piece's
    points — the sibling entry with a different-points value reveals the
    overlap. Any locked paths for the overlapping entries are demoted.
    """
    for phase, entries in (merged_scoring or {}).items():
        # Group by normalized location
        by_loc: dict = {}
        for e in entries or []:
            loc = str(e.get("location", "")).strip().lower()
            if not loc:
                continue
            by_loc.setdefault(loc, []).append(e)

        for loc, group in by_loc.items():
            if len(group) < 2:
                continue
            pts = {e.get("points") for e in group if e.get("points") is not None}
            if len(pts) < 2:
                continue  # all agree on points — not an overlap conflict

            names = sorted({str(e.get("name", "")) for e in group})
            note = (
                f"phase={phase} location={loc!r} has {len(group)} entries with "
                f"differing points={sorted(pts, key=lambda x: (x is None, x))}; "
                f"names={names}. Likely multi-piece scoring collision — review "
                f"each (piece, location, points) triple."
            )
            for e in group:
                name = str(e.get("name", "")).strip().lower()
                pts_path = f"scoring.{phase}.{name}.points"
                loc_path = f"scoring.{phase}.{name}.location"
                # Demote from locked if present
                for p in (pts_path, loc_path):
                    if p in report.locked_fields:
                        report.locked_fields.remove(p)
                # Add tentative entry with the overlap note
                if not any(
                    t.get("path") == pts_path for t in report.tentative_fields
                ):
                    report.tentative_fields.append(
                        {
                            "path": pts_path,
                            "chosen": e.get("points"),
                            "alternatives": sorted(pts - {e.get("points")}),
                            "note": note,
                        }
                    )


def consensus(parses: list) -> tuple[ManualParse, ConflictReport]:
    """Merge ``parses`` via majority vote, return (merged, conflict_report)."""
    if not parses:
        raise ValueError("consensus requires at least one parse")

    report = ConflictReport()
    merged = ManualParse(raw_text=parses[0].raw_text)

    # Scoring handled specially (nested / name-keyed)
    merged.scoring, sc_locked, sc_tent, sc_amb = _consensus_scoring(parses)
    report.locked_fields.extend(sc_locked)
    report.tentative_fields.extend(sc_tent)
    report.ambiguous_fields.extend(sc_amb)

    # Remaining top-level fields: exact-match vote on the whole value
    for fname in _TOP_LEVEL_FIELDS:
        if fname == "scoring":
            continue
        values = [getattr(p, fname) for p in parses]
        status, winner, alts = _vote(values)
        if status == "locked":
            setattr(merged, fname, winner)
            report.locked_fields.append(fname)
        elif status == "tentative":
            setattr(merged, fname, winner)
            report.tentative_fields.append(
                {"path": fname, "chosen": winner, "alternatives": alts}
            )
        else:
            # Ambiguous — pick first parse's value as placeholder
            setattr(merged, fname, values[0])
            report.ambiguous_fields.append({"path": fname, "options": alts or values})

    # Post-check: flag (phase, location) collisions as tentative.
    _flag_phase_location_overlaps(merged.scoring, report)

    return merged, report


# ---------------------------------------------------------------------------
# Diff rendering
# ---------------------------------------------------------------------------


def render_diff_markdown(parses: list, conflict: ConflictReport) -> str:
    """Render a reviewer-friendly markdown diff of the ensemble."""
    lines: list = []
    n = len(parses)
    lines.append(f"# Manual Parse — Ensemble Diff ({n} parses)")
    lines.append("")
    lines.append(f"- Locked fields: **{len(conflict.locked_fields)}**")
    lines.append(f"- Tentative fields: **{len(conflict.tentative_fields)}**")
    lines.append(f"- Ambiguous fields: **{len(conflict.ambiguous_fields)}**")
    lines.append("")

    if conflict.locked_fields:
        lines.append("## Locked (unanimous)")
        for path in conflict.locked_fields:
            lines.append(f"- `{path}`")
        lines.append("")

    if conflict.tentative_fields:
        lines.append("## Tentative (majority)")
        for entry in conflict.tentative_fields:
            lines.append(f"### `{entry['path']}`")
            lines.append(f"- chosen: `{entry.get('chosen')!r}`")
            alts = entry.get("alternatives") or []
            if alts:
                lines.append(f"- alternatives: `{alts!r}`")
            lines.append("")

    if conflict.ambiguous_fields:
        lines.append("## Ambiguous (no majority) — MENTOR REVIEW REQUIRED")
        for entry in conflict.ambiguous_fields:
            lines.append(f"### `{entry['path']}`")
            opts = entry.get("options") or []
            for i, opt in enumerate(opts):
                lines.append(f"- option {i}: `{opt!r}`")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Finalize — emit KICKOFF_TEMPLATE markdown
# ---------------------------------------------------------------------------


def _apply_resolution(obj: Any, path: str, value: Any) -> Any:
    """Apply a dotted-path resolution on a nested dict structure."""
    parts = path.split(".")
    if not parts:
        return obj
    head, rest = parts[0], parts[1:]
    if not rest:
        if isinstance(obj, dict):
            obj[head] = value
        return obj
    if isinstance(obj, dict):
        obj.setdefault(head, {})
        obj[head] = _apply_resolution(obj[head], ".".join(rest), value)
    return obj


def finalize(consensus_parse: ManualParse, resolutions: Optional[dict] = None) -> str:
    """Emit the KICKOFF_TEMPLATE markdown for the finalized parse.

    ``resolutions`` maps dotted-paths (e.g. ``"scoring.auto.Leave.points"``)
    to mentor-chosen values, overriding anything ambiguous.
    """
    data = consensus_parse.to_dict()
    data.pop("raw_text", None)
    if resolutions:
        for path, value in resolutions.items():
            _apply_resolution(data, path, value)

    lines: list = []
    lines.append("# Kickoff Template — Game Manual Summary")
    lines.append("")
    lines.append("## Critical Constraints")
    cc = data.get("critical_constraints") or {}
    for k, v in sorted(cc.items()):
        lines.append(f"- **{k}**: {v}")
    lines.append("")

    lines.append("## Scoring")
    scoring = data.get("scoring") or {}
    for phase in ("auto", "teleop", "endgame"):
        entries = scoring.get(phase) or []
        if not entries:
            continue
        lines.append(f"### {phase.title()}")
        for e in entries:
            lines.append(
                f"- **{e.get('name')}** — {e.get('points')} pts @ {e.get('location', '—')}"
            )
        lines.append("")

    lines.append("## Game Pieces")
    for p in data.get("game_pieces") or []:
        lines.append(f"- {p.get('name')} (×{p.get('count_on_field', '?')}) — {p.get('notes', '')}")
    lines.append("")

    lines.append("## Field Zones")
    for z in data.get("field_zones") or []:
        lines.append(f"- {z.get('name')} — alliance_scope={z.get('alliance_scope')}")
    lines.append("")

    lines.append("## Ranking Points")
    for rp in data.get("ranking_points") or []:
        lines.append(f"- **{rp.get('name')}** — {rp.get('criterion')}")
    lines.append("")

    lines.append("## Possession Limits")
    pl = data.get("possession_limits") or {}
    for k, v in sorted(pl.items()):
        lines.append(f"- {k}: {v}")
    lines.append("")

    lines.append("## Penalty Rules")
    for pr in data.get("penalty_rules") or []:
        lines.append(
            f"- `{pr.get('id')}` ({pr.get('severity')}) — {pr.get('summary')}"
        )
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "ManualParse",
    "ConflictReport",
    "parse_manual",
    "consensus",
    "render_diff_markdown",
    "finalize",
    "extract_pdf_text",
    "validate_parse_dict",
    "JSON_SCHEMA_DESCRIPTION",
    "PROMPT_TEMPLATE",
]
