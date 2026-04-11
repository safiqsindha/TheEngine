"""I3 — Mode A integration test against cached frames.

Exercises the full Mode A pipeline (run_mode_a → scan_frames_for_breakdown
→ _parse_breakdown → build_live_match_from_ocr → LiveMatch validation →
optional pick_board state mutation) end-to-end against a real cached set
of frames pulled from a FIRST in Texas VOD (eye/.cache/WpzeaX1vgeQ/frames).

The OCR layer is replayed from a frozen JSON snapshot of real PaddleOCR
output (tests/scout/fixtures/wpzeax_ocr_cache.json) so that:

  1. The test runs in milliseconds (no PaddleOCR in CI)
  2. The result is byte-stable across machines (no model randomness)
  3. We still exercise the real _parse_breakdown logic, the real LiveMatch
     dataclass validation, and the real run_mode_a orchestrator

To regenerate the OCR fixture from the cached frames (after a parsing
heuristic change or on a new frame set), run this file directly with
``python -m tests.scout.test_mode_a_integration --regen``.

Golden record:
  match_key   : 2026txdri_qm32
  red teams   : [4364, 9311, 10032]
  blue teams  : [2950, 3035, 7521]
  red_score   : 42      (from OCR)
  blue_score  : 151     (from OCR)
  winner      : blue
  timer_state : post
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eye"))
sys.path.insert(0, str(ROOT / "scout"))

from overlay_ocr import _parse_breakdown  # noqa: E402
from workers.mode_a import run_mode_a  # noqa: E402

# ─── Fixture locations ───

FIXTURES_DIR = Path(__file__).parent / "fixtures"
OCR_CACHE_PATH = FIXTURES_DIR / "wpzeax_ocr_cache.json"
FRAMES_DIR = ROOT / "eye" / ".cache" / "WpzeaX1vgeQ" / "frames"

# Source frame dimensions (frame_001.jpg → frame_039.jpg are all 640x360)
FRAME_WIDTH = 640
FRAME_HEIGHT = 360


# ─── Cached-OCR adapter ───


class _CachedOverlayOCR:
    """Drop-in OverlayOCR that replays a frozen OCR snapshot.

    Real `_parse_breakdown` is invoked, so any change to the parsing
    heuristic shows up in this test. Only PaddleOCR + cv2 are bypassed.
    """

    def __init__(self, cache: dict[str, list[dict[str, Any]]]):
        self._cache = cache

    def read_breakdown_screen(self, frame_path: str) -> dict[str, Any]:
        name = Path(frame_path).name
        dets = self._cache.get(name)
        if dets is None:
            return {}
        results = [(d["bbox"], d["text"], d["conf"]) for d in dets]
        return _parse_breakdown(results, FRAME_WIDTH, FRAME_HEIGHT)

    def is_transition_screen(self, frame_path: str) -> bool:
        # The cached window covers the post-match breakdown, no transition cards.
        return False


# ─── TBA stub ───


def _fake_event_matches(event_key: str) -> list[dict[str, Any]]:
    """Stub TBA fetcher: returns one finalized qm32 entry matching the
    teams visible in the breakdown frame, with no scores yet (Mode A's
    job is to fill scores from OCR before TBA catches up)."""
    return [
        {
            "comp_level": "qm",
            "match_number": 32,
            "set_number": None,
            "actual_time": 1_700_000_000,
            "alliances": {
                "red": {
                    "team_keys": ["frc4364", "frc9311", "frc10032"],
                    "score": -1,  # TBA hasn't posted yet
                },
                "blue": {
                    "team_keys": ["frc2950", "frc3035", "frc7521"],
                    "score": -1,
                },
            },
        }
    ]


# ─── Fixture loading ───


def _load_ocr_cache() -> dict[str, list[dict[str, Any]]]:
    if not OCR_CACHE_PATH.exists():
        pytest.skip(
            f"OCR cache fixture missing: {OCR_CACHE_PATH}. "
            f"Regenerate with: python -m tests.scout.test_mode_a_integration --regen"
        )
    return json.loads(OCR_CACHE_PATH.read_text())


def _frame_paths_30_to_39() -> list[Path]:
    """Return the post-match window frames the cache covers."""
    if not FRAMES_DIR.exists():
        pytest.skip(f"Cached frames missing: {FRAMES_DIR}")
    paths = sorted(FRAMES_DIR.glob("frame_*.jpg"))
    if len(paths) < 39:
        pytest.skip(f"Expected ≥39 cached frames, found {len(paths)}")
    return paths[29:39]


# ─── The integration test ───


def test_mode_a_end_to_end_against_cached_breakdown():
    """Drive run_mode_a() with real frame paths + replayed OCR + stubbed TBA.

    Asserts the resulting LiveMatch matches the hand-validated golden
    record. This is the Gate 1 acceptance test (LIVE_SCOUT_PHASE1_BUILD §I3).
    """
    cache = _load_ocr_cache()
    frames = _frame_paths_30_to_39()
    ocr = _CachedOverlayOCR(cache)

    live_match = run_mode_a(
        event_key="2026txdri",
        explicit_match_short="qm32",
        source_video_id="WpzeaX1vgeQ",
        source_tier="vod",
        frames=frames,
        ocr=ocr,
        matches_fetcher=_fake_event_matches,
    )

    assert live_match is not None, "run_mode_a returned None"

    # Identity / structural fields
    assert live_match.match_key == "2026txdri_qm32"
    assert live_match.event_key == "2026txdri"
    assert live_match.match_num == 32
    assert live_match.comp_level == "qm"

    # Team set anchored from TBA stub (frc-prefix stripped, order preserved)
    assert live_match.red_teams == [4364, 9311, 10032]
    assert live_match.blue_teams == [2950, 3035, 7521]

    # Scores derived from real PaddleOCR output via _parse_breakdown
    assert live_match.red_score == 42
    assert live_match.blue_score == 151
    assert live_match.winning_alliance == "blue"

    # Provenance + state flags
    assert live_match.timer_state == "post"
    assert live_match.source_video_id == "WpzeaX1vgeQ"
    assert live_match.source_tier == "vod"
    # Confidence is the DEFAULT_OCR_CONFIDENCE constant from mode_a (0.85)
    assert live_match.confidence == pytest.approx(0.85)


def test_mode_a_writes_cached_breakdown_into_pick_board_state():
    """The same end-to-end run, but also exercises append_live_match() +
    recompute_team_aggregates() by passing a blank pick_board state."""
    from pick_board import _blank_state  # type: ignore[attr-defined]

    cache = _load_ocr_cache()
    frames = _frame_paths_30_to_39()
    ocr = _CachedOverlayOCR(cache)
    state = _blank_state()

    live_match = run_mode_a(
        event_key="2026txdri",
        explicit_match_short="qm32",
        source_video_id="WpzeaX1vgeQ",
        source_tier="vod",
        frames=frames,
        ocr=ocr,
        matches_fetcher=_fake_event_matches,
        state=state,
    )

    assert live_match is not None
    assert "live_matches" in state
    assert "2026txdri_qm32" in state["live_matches"]

    persisted = state["live_matches"]["2026txdri_qm32"]
    assert persisted["red_score"] == 42
    assert persisted["blue_score"] == 151
    assert persisted["winning_alliance"] == "blue"
    assert persisted["red_teams"] == [4364, 9311, 10032]
    assert persisted["blue_teams"] == [2950, 3035, 7521]

    # recompute_team_aggregates was called via append_live_match's contract,
    # but a blank state has an empty teams DB so no per-team rows update.
    # That's fine — the aggregate path is unit-tested separately in
    # tests/scout/test_pick_board_live_aggregation.py against a populated DB.


# ─── Fixture regeneration helper (manual) ───


def _regenerate_fixture() -> None:
    """Re-run real PaddleOCR over the cached frames and rewrite the JSON
    snapshot. Slow (~15s on first run, model lazy-loads) — only meant to
    be invoked manually after a parsing-layer change."""
    import cv2  # noqa: PLC0415
    from overlay_ocr import OverlayOCR  # noqa: PLC0415

    if not FRAMES_DIR.exists():
        raise SystemExit(f"frames dir missing: {FRAMES_DIR}")
    paths = sorted(FRAMES_DIR.glob("frame_*.jpg"))[29:39]
    if not paths:
        raise SystemExit("no frames in 30..39 range")

    ocr = OverlayOCR()
    out: dict[str, list[dict[str, Any]]] = {}
    for fp in paths:
        img = cv2.imread(str(fp))
        if img is None:
            print(f"  skip (unreadable): {fp.name}")
            continue
        raw = ocr.reader.readtext(img)
        out[fp.name] = [
            {"bbox": [list(map(float, p)) for p in bbox],
             "text": str(text), "conf": float(conf)}
            for (bbox, text, conf) in raw
        ]
        print(f"  {fp.name}: {len(raw)} detections")

    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    OCR_CACHE_PATH.write_text(json.dumps(out, indent=2))
    print(f"wrote {OCR_CACHE_PATH} ({OCR_CACHE_PATH.stat().st_size} bytes)")


if __name__ == "__main__":
    if "--regen" in sys.argv:
        _regenerate_fixture()
    else:
        print("Run via pytest, or pass --regen to refresh the OCR fixture.")
