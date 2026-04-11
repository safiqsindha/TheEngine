#!/usr/bin/env python3
"""
The Engine — Overlay OCR
Team 2950 — The Devastators

Shared OCR helper used by the Live Scout pipeline and the batch Eye tooling.
Reads FRC score overlays, post-match breakdown screens, and alliance-win
transition cards.

Consolidated from two prior copies:
  - eye/the_eye.py          (class OverlayOCR, easyocr-backed)
  - eye/stream_recorder.py  (class MatchDetector, easyocr-backed)

Design:
  - Backend is PaddleOCR (PP-OCRv5). EasyOCR was accurate enough but slow
    on CPU and shipped a large torch footprint; PP-OCRv5 is faster and
    smaller, and its multi-lang det+rec pipeline matches our needs.
  - The backend is abstracted behind a tiny `readtext(image) -> list[(bbox, text, conf)]`
    contract so downstream parsing code stays identical to the old easyocr
    callers, and tests can inject a FakeReader without installing PaddleOCR.
  - Parsing logic for breakdown screens and transition cards is factored
    into pure functions (`_parse_breakdown`, `_is_transition_text`) that
    operate on already-OCR'd text, so they are covered by offline tests.

Usage:
    from overlay_ocr import OverlayOCR

    ocr = OverlayOCR()                            # real PaddleOCR backend
    bd = ocr.read_breakdown_screen("frame.jpg")
    if bd["is_breakdown"]:
        ...

    # For tests:
    fake = FakeReader(canned_results)
    ocr = OverlayOCR(reader=fake)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Protocol

# ─── Tunables ───

MIN_CONF = 0.5          # Confidence floor for structured parsing
MIN_SELECT_CONF = 0.4   # Softer floor for live overlay scraping
TEAM_NUM_MIN = 200      # Team numbers must exceed this (filters out score values)
TEAM_NUM_MAX = 99999
SCORE_VALUE_MAX = 500   # FRC alliance scores rarely exceed this (Reefscape 2025 cap was ~250)
LEFT_ALLIANCE_FRAC = 0.4    # x < width * 0.4 → red
RIGHT_ALLIANCE_FRAC = 0.6   # x > width * 0.6 → blue


# ─── Reader protocol ───


class Reader(Protocol):
    """Thin OCR contract. readtext() must return easyocr-style tuples:

        [((x1,y1),(x2,y2),(x3,y3),(x4,y4)), "text", confidence_float]

    This is the same shape easyocr's reader returns, which is what the
    legacy parsing code expects.
    """

    def readtext(self, image: Any) -> list[tuple[list[list[float]], str, float]]:
        ...


# ─── PaddleOCR backend ───


class _PaddleReader:
    """PaddleOCR adapter. Lazily imports paddleocr so tests don't need it."""

    def __init__(self, lang: str = "en"):
        try:
            from paddleocr import PaddleOCR
        except ImportError as e:
            raise ImportError(
                "paddleocr not installed. "
                "Run: pip3 install 'paddleocr>=3.0' paddlepaddle"
            ) from e

        # PP-OCRv5 mobile rec + server det: good accuracy, reasonable CPU speed
        self._ocr = PaddleOCR(
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            lang=lang,
        )

    def readtext(self, image: Any) -> list[tuple[list[list[float]], str, float]]:
        """Run PaddleOCR and convert to easyocr-style tuples.

        `image` may be a file path (str or Path) or a numpy array.
        """
        if isinstance(image, Path):
            image = str(image)

        raw = self._ocr.predict(image) if hasattr(self._ocr, "predict") else self._ocr.ocr(image)
        return _normalize_paddle_output(raw)


def _normalize_paddle_output(raw: Any) -> list[tuple[list[list[float]], str, float]]:
    """Flatten PaddleOCR output into easyocr-style (bbox, text, conf) tuples.

    Handles both the legacy `.ocr()` shape `[[[box, (text, conf)], ...]]`
    and the newer `.predict()` shape which returns a list of result objects
    with `rec_polys`, `rec_texts`, `rec_scores` attributes or dict keys.
    """
    out: list[tuple[list[list[float]], str, float]] = []
    if raw is None:
        return out

    for page in raw:
        if page is None:
            continue

        # Newer .predict() API — object or dict with rec_polys/rec_texts/rec_scores
        polys = _get(page, "rec_polys")
        texts = _get(page, "rec_texts")
        scores = _get(page, "rec_scores")
        if polys is not None and texts is not None and scores is not None:
            for bbox, text, conf in zip(polys, texts, scores):
                out.append((_bbox_to_list(bbox), str(text), float(conf)))
            continue

        # Legacy .ocr() API — list of [bbox, (text, conf)]
        if isinstance(page, list):
            for entry in page:
                if entry is None or len(entry) != 2:
                    continue
                bbox, (text, conf) = entry
                out.append((_bbox_to_list(bbox), str(text), float(conf)))

    return out


def _get(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _bbox_to_list(bbox: Any) -> list[list[float]]:
    """Coerce a bbox (numpy array, list of points, etc.) into list-of-lists."""
    try:
        return [[float(p[0]), float(p[1])] for p in bbox]
    except (TypeError, IndexError):
        return []


# ─── Pure parsing helpers (tested without images) ───


def _is_transition_text(text_upper: str) -> bool:
    """True if the text blob from a center crop looks like an alliance-win card."""
    return "WINS" in text_upper and "ALLIANCE" in text_upper


def _parse_breakdown(
    results: list[tuple[list[list[float]], str, float]],
    img_width: int,
    img_height: int,
) -> dict[str, Any]:
    """Parse readtext results into a breakdown-screen dict.

    Returns {"is_breakdown": False} if the screen doesn't look like a post-match
    breakdown. Otherwise returns a structured dict with teams + raw_texts +
    winner inference.
    """
    texts = [t for (_, t, c) in results if c > MIN_CONF]
    text_upper = " ".join(texts).upper()

    is_breakdown = (
        "WINNER" in text_upper
        or "RANKING POINTS" in text_upper
        or ("RED" in text_upper and "BLUE" in text_upper and "FUEL" in text_upper)
    )
    if not is_breakdown:
        return {"is_breakdown": False}

    # Collect all high-confidence numeric detections with centroid + bbox area
    numbers: list[dict[str, float]] = []
    for (bbox, text, conf) in results:
        if conf <= MIN_CONF or not text.isdigit():
            continue
        if not bbox:
            continue
        cx = (bbox[0][0] + bbox[2][0]) / 2
        cy = (bbox[0][1] + bbox[2][1]) / 2
        # bbox area as a proxy for font size — alliance scores are rendered
        # much larger than team numbers and sub-scores
        bw = abs(bbox[2][0] - bbox[0][0])
        bh = abs(bbox[2][1] - bbox[0][1])
        numbers.append({
            "value": int(text), "x": cx, "y": cy, "conf": conf,
            "area": bw * bh,
        })

    teams: dict[str, list[int]] = {"red": [], "blue": []}
    left_cut = img_width * LEFT_ALLIANCE_FRAC
    right_cut = img_width * RIGHT_ALLIANCE_FRAC
    for n in numbers:
        val = int(n["value"])
        if not (TEAM_NUM_MIN <= val <= TEAM_NUM_MAX):
            continue
        if n["x"] < left_cut:
            teams["red"].append(val)
        elif n["x"] > right_cut:
            teams["blue"].append(val)

    # Score extraction: per side, the largest-area number ≤ SCORE_VALUE_MAX
    # is almost always the alliance final score (rendered in huge type).
    # Final scores are typically centered next to the RED/BLUE labels rather
    # than at the far edges, so use a midline split (not the conservative
    # 0.4/0.6 split that team-number detection uses).
    scores: dict[str, Optional[int]] = {"red": None, "blue": None}
    midline = img_width * 0.5
    red_candidates = [n for n in numbers if n["x"] < midline and 0 <= n["value"] <= SCORE_VALUE_MAX]
    blue_candidates = [n for n in numbers if n["x"] > midline and 0 <= n["value"] <= SCORE_VALUE_MAX]
    if red_candidates:
        scores["red"] = int(max(red_candidates, key=lambda n: n["area"])["value"])
    if blue_candidates:
        scores["blue"] = int(max(blue_candidates, key=lambda n: n["area"])["value"])

    # Winner: prefer the score-derived answer when both sides have a score.
    # Fall back to the WINNER-keyword heuristic if scores are missing.
    winner: Optional[str] = None
    if scores["red"] is not None and scores["blue"] is not None:
        if scores["red"] > scores["blue"]:
            winner = "red"
        elif scores["blue"] > scores["red"]:
            winner = "blue"
        else:
            winner = "tie"
    elif "WINNER" in text_upper:
        mid = img_width * 0.5
        right_big = any(n["x"] > mid and n["value"] > 50 for n in numbers)
        winner = "blue" if right_big else "red"

    return {
        "is_breakdown": True,
        "raw_texts": texts,
        "teams": teams,
        "scores": scores,
        "winner": winner,
    }


# ─── OverlayOCR class ───


class OverlayOCR:
    """Shared OCR helper for FRC score overlays and breakdown screens."""

    def __init__(self, reader: Optional[Reader] = None):
        """Create an OverlayOCR.

        Args:
            reader: Optional custom reader (must expose .readtext()). If
                None, a PaddleOCR-backed reader is instantiated lazily.
        """
        self._reader: Optional[Reader] = reader

    @property
    def reader(self) -> Reader:
        """The underlying OCR reader. Instantiated on first access."""
        if self._reader is None:
            self._reader = _PaddleReader()
        return self._reader

    # ─── High-level screen classifiers ───

    def read_breakdown_screen(self, frame_path: str) -> dict[str, Any]:
        """Read a post-match breakdown screen. Returns {"is_breakdown": False}
        if the frame doesn't look like one."""
        img = _imread(frame_path)
        if img is None:
            return {}
        h, w = img.shape[:2]
        results = self.reader.readtext(img)
        return _parse_breakdown(results, img_width=w, img_height=h)

    def is_transition_screen(self, frame_path: str) -> bool:
        """True if the frame is an ALLIANCE WINS transition card."""
        img = _imread(frame_path)
        if img is None:
            return False
        h, w = img.shape[:2]
        center = img[int(h * 0.3):int(h * 0.7), int(w * 0.2):int(w * 0.8)]
        results = self.reader.readtext(center)
        text_upper = " ".join(t for (_, t, c) in results if c > MIN_CONF).upper()
        return _is_transition_text(text_upper)

    def read_top_overlay(self, frame_path: str) -> str:
        """Read the live score bar along the top 12% of the frame.

        Returns a space-joined string of detected tokens above the
        soft-confidence floor. Used by Mode A live workers to detect
        score changes cheaply (no parsing).
        """
        img = _imread(frame_path)
        if img is None:
            return ""
        h, _ = img.shape[:2]
        top_bar = img[0:int(h * 0.12), :]
        results = self.reader.readtext(top_bar)
        return " ".join(t for (_, t, c) in results if c > MIN_SELECT_CONF).strip()

    def detect_match_boundaries(self, frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Scan a list of frame dicts (with 'path' + 'timestamp_s') for match
        boundary events. Returns transition + breakdown events in order."""
        boundaries: list[dict[str, Any]] = []
        for i, f in enumerate(frames):
            if self.is_transition_screen(f["path"]):
                boundaries.append({
                    "frame_idx": i,
                    "timestamp_s": f.get("timestamp_s", 0),
                    "type": "transition",
                })
            bd = self.read_breakdown_screen(f["path"])
            if bd.get("is_breakdown"):
                boundaries.append({
                    "frame_idx": i,
                    "timestamp_s": f.get("timestamp_s", 0),
                    "type": "breakdown",
                    "data": bd,
                })
        return boundaries


# ─── cv2 wrapper (for monkeypatching in tests) ───


def _imread(frame_path: str) -> Any:
    """Read an image from disk. Factored out so tests can stub it."""
    import cv2  # Local import: tests that monkeypatch this never hit cv2
    return cv2.imread(str(frame_path))
