#!/usr/bin/env python3
"""
The Engine — THE EYE
Team 2950 — The Devastators

Vision-based match scouting from FRC match video streams.

Architecture:
  Layer 0: pytubefix + ffmpeg      — video capture, frame extraction (FREE)
  Layer 1: EasyOCR                 — score breakdown screens, match boundaries (FREE)
  Layer 2: Vision LLM (swappable)  — overlay reading, qualitative scouting (CHEAP)
  Layer 3: Opus advisor            — strategic synthesis per team (RARE)

The vision backend is abstracted behind VisionBackend — currently Haiku API,
designed to swap in a local model (Gemma, Qwen-VL, etc.) later.

Usage:
  # Full analysis of a match video
  python3 the_eye.py analyze <youtube_url> [--focus 2950,3035] [--tier key] [--backend haiku]

  # Just extract frames (no API calls)
  python3 the_eye.py frames <youtube_url> [--fps 5]

  # Analyze already-extracted frames
  python3 the_eye.py scout <frames_dir> [--focus 2950,3035] [--tier key] [--backend haiku]

  # OCR-only analysis (free, no API)
  python3 the_eye.py ocr <frames_dir>

Options:
  --tier    Frame selection tier: key (12 frames), scored (~50 score-change), all (every frame)
  --fps     Frame extraction rate in seconds (default: 5)
  --backend Vision backend: haiku, sonnet, opus, gemma, qwen, moondream, yolo
  --focus   Comma-separated team numbers to focus on

Environment:
  ANTHROPIC_API_KEY — required for API vision backends (not needed for ocr/local/yolo)
"""

import base64
import json
import os
import subprocess
import sys
import time
from abc import ABC, abstractmethod
from pathlib import Path

CACHE_DIR = Path(__file__).parent / ".cache"
RESULTS_DIR = CACHE_DIR / "results"

DEFAULT_FPS_INTERVAL = 5  # seconds between frames
AUTO_END_S = 18
ENDGAME_START_S = 150

# Frame tier system:
#   key    — 12 most informative frames (default, cheapest)
#   scored — ~50 frames where score changes detected via OCR
#   all    — every extracted frame at extraction fps
VALID_TIERS = ("key", "scored", "all")
DEFAULT_TIER = "key"


# ─── Video Pipeline ───


def download_video(url: str, output_dir: Path) -> Path:
    """Download YouTube video using pytubefix."""
    try:
        from pytubefix import YouTube
    except ImportError:
        print("  Run: pip3 install pytubefix")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "match.mp4"

    if output_path.exists():
        print(f"  Using cached video: {output_path}")
        return output_path

    print(f"  Downloading: {url}")
    yt = YouTube(url)
    print(f"  Title: {yt.title}")
    print(f"  Length: {yt.length}s")

    stream = (yt.streams
              .filter(progressive=True, file_extension="mp4")
              .order_by("resolution").desc().first())
    if not stream:
        print("  ERROR: No downloadable stream found")
        return None

    stream.download(output_path=str(output_dir), filename="match.mp4")
    print(f"  Saved: {output_path} ({output_path.stat().st_size / 1e6:.1f}MB)")
    return output_path


def extract_frames(video_path: Path, output_dir: Path,
                   interval: int = DEFAULT_FPS_INTERVAL) -> list:
    """Extract frames at regular intervals using ffmpeg."""
    output_dir.mkdir(parents=True, exist_ok=True)

    for f in output_dir.glob("frame_*.jpg"):
        f.unlink()

    cmd = [
        "ffmpeg", "-i", str(video_path),
        "-vf", f"fps=1/{interval}",
        "-q:v", "2",
        str(output_dir / "frame_%03d.jpg"),
        "-y", "-loglevel", "error"
    ]
    subprocess.run(cmd, capture_output=True)

    frames = sorted(output_dir.glob("frame_*.jpg"))
    labeled = []
    for i, f in enumerate(frames):
        ts = i * interval
        if ts < AUTO_END_S:
            phase = "auto"
        elif ts < ENDGAME_START_S:
            phase = "teleop"
        else:
            phase = "endgame"
        labeled.append({
            "path": str(f), "filename": f.name,
            "timestamp_s": ts, "phase": phase,
        })

    print(f"  Extracted {len(frames)} frames (every {interval}s)")
    return labeled


def select_key_frames(frames: list, max_frames: int = 12) -> list:
    """Select most informative frames: auto, mid-teleop, endgame, final."""
    if len(frames) <= max_frames:
        return frames

    selected = set()
    selected.add(0)
    selected.add(len(frames) - 1)

    # All auto and endgame frames
    for i, f in enumerate(frames):
        if f["phase"] in ("auto", "endgame"):
            selected.add(i)

    # Evenly-spaced teleop
    teleop = [i for i, f in enumerate(frames) if f["phase"] == "teleop"]
    if teleop:
        remaining = max_frames - len(selected)
        step = max(1, len(teleop) // max(1, remaining))
        for j in range(0, len(teleop), step):
            selected.add(teleop[j])
            if len(selected) >= max_frames:
                break

    return [frames[i] for i in sorted(selected)][:max_frames]


def select_scored_frames(frames: list, ocr: "OverlayOCR" = None,
                         max_frames: int = 50) -> list:
    """Select frames where score changes are detected via OCR.

    Scans frames for breakdown/transition screens and score deltas.
    Falls back to denser even sampling if OCR unavailable.
    """
    if len(frames) <= max_frames:
        return frames

    # Always include first, last, auto, and endgame frames
    selected = set()
    selected.add(0)
    selected.add(len(frames) - 1)
    for i, f in enumerate(frames):
        if f["phase"] in ("auto", "endgame"):
            selected.add(i)

    if ocr:
        # Use OCR to detect score-change frames by reading scores
        # and picking frames where the score differs from previous
        prev_text = ""
        for i, f in enumerate(frames):
            if i in selected:
                continue
            bd = ocr.read_breakdown_screen(f["path"])
            if bd.get("is_breakdown"):
                selected.add(i)
                continue
            # Quick OCR check — just read top overlay region for score text
            text = ocr.read_top_overlay(f["path"])
            if text != prev_text and text:
                selected.add(i)
                prev_text = text

            if len(selected) >= max_frames:
                break

    # Fill remaining slots with evenly-spaced teleop
    if len(selected) < max_frames:
        teleop = [i for i, f in enumerate(frames) if f["phase"] == "teleop" and i not in selected]
        remaining = max_frames - len(selected)
        step = max(1, len(teleop) // max(1, remaining))
        for j in range(0, len(teleop), step):
            selected.add(teleop[j])
            if len(selected) >= max_frames:
                break

    return [frames[i] for i in sorted(selected)][:max_frames]


def select_frames_by_tier(frames: list, tier: str = DEFAULT_TIER,
                          ocr: "OverlayOCR" = None) -> list:
    """Select frames based on tier setting."""
    if tier == "all":
        return frames
    elif tier == "scored":
        return select_scored_frames(frames, ocr=ocr)
    else:  # "key" (default)
        return select_key_frames(frames, max_frames=12)


# ─── OCR Layer (Free) ───
#
# The OverlayOCR implementation lives in eye/overlay_ocr.py so the Live Scout
# workers and this batch tool share a single PaddleOCR-backed reader.

from overlay_ocr import OverlayOCR  # noqa: E402


# ─── Vision Backend (Swappable) ───


class VisionBackend(ABC):
    """Abstract vision backend — swap between API and local models."""

    @abstractmethod
    def analyze_frames(self, frames: list, focus_teams: list = None) -> list:
        """Analyze frames and return structured observations."""
        pass

    @abstractmethod
    def name(self) -> str:
        pass


ANTHROPIC_MODELS = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-6",
}


class AnthropicVisionBackend(VisionBackend):
    """Anthropic API vision backend — supports Haiku, Sonnet, and Opus."""

    SCOUTING_PROMPT = """You are an FRC match scout analyzing video frames from a FIRST Robotics Competition match.

For each frame, extract structured observations as JSON:
```json
{
  "timestamp": "<from overlay or estimated>",
  "phase": "auto|teleop|endgame|post_match",
  "scores": {"red": <n>, "blue": <n>},
  "timer": "<match timer>",
  "red_teams": [<team numbers>],
  "blue_teams": [<team numbers>],
  "observations": [
    {
      "team": <number or "unknown">,
      "alliance": "red|blue",
      "action": "<what they're doing>",
      "zone": "<field zone>",
      "mechanism_note": "<issues or standout performance>",
      "defense": "<describe if playing/receiving defense>"
    }
  ],
  "field_state": "<game piece distribution, field control>",
  "notable": "<anything unusual — tipped robot, breakdown, exceptional play>"
}
```

Read team numbers, scores, and timer from the score overlay at the top of the frame.
Be precise about what you can actually see. Don't guess — if you can't identify a robot, say "unknown"."""

    def __init__(self, model_key: str = "haiku"):
        try:
            import anthropic
        except ImportError:
            raise ImportError("pip3 install anthropic")

        self.model_key = model_key
        self.model_id = ANTHROPIC_MODELS.get(model_key, model_key)

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            for p in [Path(__file__).parent.parent / ".anthropic_key",
                       Path.home() / ".anthropic_key"]:
                if p.exists():
                    api_key = p.read_text().strip()
                    break
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")

        self.client = anthropic.Anthropic(api_key=api_key)

    def name(self) -> str:
        return f"{self.model_key}-vision"

    def analyze_frames(self, frames: list, focus_teams: list = None) -> list:
        all_results = []
        batch_size = 4

        focus_str = ""
        if focus_teams:
            focus_str = (f"\nPay special attention to teams: "
                         f"{', '.join(str(t) for t in focus_teams)}.")

        for batch_start in range(0, len(frames), batch_size):
            batch = frames[batch_start:batch_start + batch_size]
            content = []
            descs = []

            for f in batch:
                descs.append(f"Frame at {f['timestamp_s']}s ({f['phase']})")
                with open(f["path"], "rb") as fh:
                    data = base64.b64encode(fh.read()).decode("utf-8")
                content.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/jpeg",
                               "data": data},
                })

            content.append({
                "type": "text",
                "text": (f"Analyze these {len(batch)} FRC match frames. "
                         f"Frames: {', '.join(descs)}. "
                         f"Return a JSON array with one object per frame.{focus_str}"),
            })

            print(f"    Analyzing frames {batch_start+1}-{batch_start+len(batch)}...")
            try:
                response = self.client.messages.create(
                    model=self.model_id,
                    max_tokens=2000,
                    system=self.SCOUTING_PROMPT,
                    messages=[{"role": "user", "content": content}],
                )
                text = response.content[0].text
                usage = response.usage
                print(f"      [{self.model_key}] {usage.input_tokens} in / {usage.output_tokens} out")

                # Parse JSON from response
                start = text.find("[")
                end = text.rfind("]") + 1
                if start >= 0 and end > start:
                    all_results.extend(json.loads(text[start:end]))
                else:
                    start = text.find("{")
                    end = text.rfind("}") + 1
                    if start >= 0 and end > start:
                        all_results.append(json.loads(text[start:end]))
                    else:
                        all_results.append({"raw": text, "parse_error": True})
            except json.JSONDecodeError:
                all_results.append({"raw": text, "parse_error": True})
            except Exception as e:
                print(f"      ERROR: {e}")
                all_results.append({"error": str(e)})

            time.sleep(0.5)

        return all_results


# Backwards compatibility alias
HaikuVisionBackend = AnthropicVisionBackend


class LocalVisionBackend(VisionBackend):
    """Placeholder for local vision model (Gemma, Qwen-VL, etc).

    To implement:
      1. Load model in __init__ (e.g. transformers pipeline)
      2. Process frames through model in analyze_frames
      3. Parse output into same JSON structure as HaikuVisionBackend

    Expected model candidates:
      - google/gemma-3-4b-it (lightweight, fast on CPU)
      - Qwen/Qwen2.5-VL-7B-Instruct (strong vision, needs GPU)
      - vikhyatk/moondream2 (tiny, edge-friendly)
    """

    def __init__(self, model_name: str = "gemma-3-4b"):
        self.model_name = model_name
        # TODO: Load model
        raise NotImplementedError(
            f"Local vision backend ({model_name}) not yet implemented. "
            f"Use --backend haiku for now."
        )

    def name(self) -> str:
        return f"local-{self.model_name}"

    def analyze_frames(self, frames: list, focus_teams: list = None) -> list:
        raise NotImplementedError


class YOLOVisionBackend(VisionBackend):
    """Placeholder for YOLO-based real-time detection on Jetson/GPU.

    Architecture (planned):
      - YOLO runs at 30+ fps, detects robots, game pieces, scoring events
      - Flags "interesting" frames (score changes, defense, breakdowns)
      - Flagged frames get passed to a vision LLM for qualitative analysis
      - Result: near-zero latency detection + deep analysis only where needed

    Expected models:
      - YOLOv8/v9 custom-trained on FRC field elements
      - Runs on Jetson Orin Nano ($250) or any CUDA GPU
    """

    def __init__(self):
        raise NotImplementedError(
            "YOLO backend not yet implemented. Requires custom-trained model. "
            "Use --backend haiku for now."
        )

    def name(self) -> str:
        return "yolo"

    def analyze_frames(self, frames: list, focus_teams: list = None) -> list:
        raise NotImplementedError


def get_backend(name: str = "haiku") -> VisionBackend:
    """Factory for vision backends."""
    if name in ANTHROPIC_MODELS:
        return AnthropicVisionBackend(model_key=name)
    elif name in ("local", "gemma", "qwen", "moondream"):
        model = name if name != "local" else "gemma-3-4b"
        return LocalVisionBackend(model)
    elif name == "yolo":
        return YOLOVisionBackend()
    else:
        valid = list(ANTHROPIC_MODELS.keys()) + ["gemma", "qwen", "moondream", "yolo"]
        raise ValueError(f"Unknown backend: {name}. Options: {', '.join(valid)}")


# ─── Synthesis ───


def synthesize_report(observations: list, ocr_data: dict = None,
                      focus_teams: list = None) -> dict:
    """Combine vision observations + OCR into structured scouting report."""
    teams = {}
    score_progression = []

    for obs in observations:
        if not isinstance(obs, dict) or obs.get("parse_error") or obs.get("error"):
            continue

        # Score progression
        scores = obs.get("scores", {})
        if scores:
            score_progression.append({
                "timestamp": obs.get("timestamp", ""),
                "phase": obs.get("phase", ""),
                "red": scores.get("red", 0),
                "blue": scores.get("blue", 0),
            })

        # Per-team observations
        for robot in obs.get("observations", []):
            team = robot.get("team")
            if not team or team == "unknown":
                continue
            team_key = str(int(team) if isinstance(team, (int, float)) else team)

            if team_key not in teams:
                teams[team_key] = {
                    "team": int(team_key) if team_key.isdigit() else team_key,
                    "alliance": robot.get("alliance", "unknown"),
                    "auto": [], "teleop": [], "endgame": [],
                    "defense": [], "mechanisms": [], "zones": set(),
                }

            td = teams[team_key]
            phase = obs.get("phase", "teleop")
            action = robot.get("action", "")

            if phase == "auto":
                td["auto"].append(action)
            elif phase in ("teleop", "teleop_start"):
                td["teleop"].append(action)
            elif phase == "endgame":
                td["endgame"].append(action)

            if robot.get("defense"):
                td["defense"].append(robot["defense"])
            if robot.get("mechanism_note"):
                td["mechanisms"].append(robot["mechanism_note"])
            if robot.get("zone"):
                td["zones"].add(robot["zone"])

    # Serialize sets
    for td in teams.values():
        td["zones"] = list(td["zones"])

    # Merge OCR breakdown data if available
    breakdown = {}
    if ocr_data and ocr_data.get("is_breakdown"):
        breakdown = ocr_data

    # Find final scores
    final_scores = {}
    if score_progression:
        last = score_progression[-1]
        final_scores = {"red": last.get("red", 0), "blue": last.get("blue", 0)}

    report = {
        "final_scores": final_scores,
        "score_progression": score_progression,
        "breakdown": breakdown,
        "teams": teams,
        "n_frames": len(observations),
    }

    if focus_teams:
        report["focus_teams"] = {
            str(t): teams.get(str(t), {"team": t, "no_data": True})
            for t in focus_teams
        }

    return report


def print_report(report: dict):
    """Pretty-print scouting report."""
    print(f"\n  THE EYE — MATCH SCOUTING REPORT")
    print(f"  {'─' * 60}")

    scores = report.get("final_scores", {})
    if scores:
        print(f"  Final: Red {scores.get('red', '?')} — Blue {scores.get('blue', '?')}")
    print(f"  Frames analyzed: {report.get('n_frames', 0)}")

    # Score progression sparkline
    prog = report.get("score_progression", [])
    if prog:
        r_scores = [p.get("red", 0) for p in prog]
        b_scores = [p.get("blue", 0) for p in prog]
        print(f"  Red  progression: {' → '.join(str(s) for s in r_scores)}")
        print(f"  Blue progression: {' → '.join(str(s) for s in b_scores)}")

    source = report.get("focus_teams", report.get("teams", {}))
    for key, td in source.items():
        if td.get("no_data"):
            print(f"\n  Team {key}: No observations")
            continue

        print(f"\n  Team {td.get('team', key)} ({td.get('alliance', '?')})")
        print(f"  {'─' * 40}")
        if td.get("auto"):
            print(f"  Auto: {'; '.join(td['auto'][:3])}")
        if td.get("teleop"):
            print(f"  Teleop: {'; '.join(td['teleop'][:5])}")
        if td.get("endgame"):
            print(f"  Endgame: {'; '.join(td['endgame'][:3])}")
        if td.get("zones"):
            print(f"  Zones: {', '.join(td['zones'])}")
        if td.get("defense"):
            print(f"  Defense: {'; '.join(td['defense'][:3])}")
        mechs = [m for m in td.get("mechanisms", []) if m]
        if mechs:
            print(f"  Mechanisms: {'; '.join(mechs[:3])}")

    print()


# ─── Commands ───


def parse_common_args(args, start=0):
    """Parse common CLI flags: --focus, --backend, --tier, --fps."""
    opts = {
        "focus_teams": None,
        "backend_name": "haiku",
        "tier": DEFAULT_TIER,
        "fps": DEFAULT_FPS_INTERVAL,
    }
    i = start
    while i < len(args):
        if args[i] == "--focus" and i + 1 < len(args):
            opts["focus_teams"] = [int(t) for t in args[i + 1].split(",")]
            i += 2
        elif args[i] == "--backend" and i + 1 < len(args):
            opts["backend_name"] = args[i + 1]
            i += 2
        elif args[i] == "--tier" and i + 1 < len(args):
            tier = args[i + 1]
            if tier not in VALID_TIERS:
                print(f"  Invalid tier '{tier}'. Options: {', '.join(VALID_TIERS)}")
                return None
            opts["tier"] = tier
            i += 2
        elif args[i] == "--fps" and i + 1 < len(args):
            opts["fps"] = int(args[i + 1])
            i += 2
        else:
            i += 1
    return opts


def cmd_analyze(args):
    """Full pipeline: download → frames → OCR + vision → report."""
    if not args:
        print("Usage: the_eye.py analyze <youtube_url> [--focus 2950] [--tier key] [--backend haiku] [--fps 5]")
        return

    url = args[0]
    opts = parse_common_args(args, start=1)
    if opts is None:
        return

    video_id = url.split("v=")[-1].split("&")[0] if "v=" in url else url[-11:]
    video_dir = CACHE_DIR / video_id
    frames_dir = video_dir / "frames"

    # Download
    video_path = download_video(url, video_dir)
    if not video_path:
        return

    # Extract frames
    frames = extract_frames(video_path, frames_dir, interval=opts["fps"])
    if not frames:
        return

    # OCR on last few frames (look for breakdown screen)
    print(f"  Running OCR on final frames...")
    ocr = OverlayOCR()
    ocr_data = {}
    for f in reversed(frames[-5:]):
        bd = ocr.read_breakdown_screen(f["path"])
        if bd.get("is_breakdown"):
            ocr_data = bd
            print(f"    Found breakdown screen at {f['timestamp_s']}s")
            break

    # Select frames by tier
    selected = select_frames_by_tier(frames, tier=opts["tier"], ocr=ocr)
    print(f"  Tier '{opts['tier']}': selected {len(selected)}/{len(frames)} frames")
    print(f"  Vision backend: {opts['backend_name']}")

    backend = get_backend(opts["backend_name"])
    observations = backend.analyze_frames(selected, opts["focus_teams"])

    # Synthesize
    report = synthesize_report(observations, ocr_data, opts["focus_teams"])
    report["source"] = {"video_url": url, "video_id": video_id,
                         "backend": backend.name(),
                         "tier": opts["tier"], "fps": opts["fps"],
                         "frames_total": len(frames),
                         "frames_analyzed": len(selected)}

    # Save
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result_path = RESULTS_DIR / f"{video_id}_report.json"
    save_data = json.loads(json.dumps(report, default=str))
    result_path.write_text(json.dumps(save_data, indent=2))
    print(f"  Saved: {result_path}")

    print_report(report)
    return report


def cmd_frames(args):
    """Download and extract frames only (no API calls)."""
    if not args:
        print("Usage: the_eye.py frames <youtube_url> [--fps 5]")
        return

    url = args[0]
    opts = parse_common_args(args, start=1)
    if opts is None:
        return

    video_id = url.split("v=")[-1].split("&")[0] if "v=" in url else url[-11:]
    video_dir = CACHE_DIR / video_id
    frames_dir = video_dir / "frames"

    video_path = download_video(url, video_dir)
    if not video_path:
        return

    frames = extract_frames(video_path, frames_dir, interval=opts["fps"])
    print(f"\n  Frames in: {frames_dir}")
    for f in frames:
        print(f"    {f['filename']}  t={f['timestamp_s']:3d}s  {f['phase']}")


def cmd_scout(args):
    """Analyze already-extracted frames."""
    if not args:
        print("Usage: the_eye.py scout <frames_dir> [--focus 2950] [--tier key] [--backend haiku]")
        return

    frames_dir = Path(args[0])
    opts = parse_common_args(args, start=1)
    if opts is None:
        return

    frame_files = sorted(frames_dir.glob("frame_*.jpg"))
    if not frame_files:
        print(f"  No frames in {frames_dir}")
        return

    frames = []
    for i, f in enumerate(frame_files):
        ts = i * DEFAULT_FPS_INTERVAL
        phase = "auto" if ts < AUTO_END_S else ("endgame" if ts >= ENDGAME_START_S else "teleop")
        frames.append({"path": str(f), "filename": f.name,
                       "timestamp_s": ts, "phase": phase})

    # Select frames by tier
    ocr = OverlayOCR() if opts["tier"] == "scored" else None
    selected = select_frames_by_tier(frames, tier=opts["tier"], ocr=ocr)
    print(f"  {len(frame_files)} frames, tier '{opts['tier']}': selected {len(selected)}")

    backend = get_backend(opts["backend_name"])
    observations = backend.analyze_frames(selected, opts["focus_teams"])
    report = synthesize_report(observations, focus_teams=opts["focus_teams"])

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result_path = RESULTS_DIR / f"scout_{int(time.time())}.json"
    save_data = json.loads(json.dumps(report, default=str))
    result_path.write_text(json.dumps(save_data, indent=2))

    print_report(report)


def cmd_ocr(args):
    """OCR-only analysis — free, no API calls."""
    if not args:
        print("Usage: the_eye.py ocr <frames_dir>")
        return

    frames_dir = Path(args[0])
    frame_files = sorted(frames_dir.glob("frame_*.jpg"))
    if not frame_files:
        print(f"  No frames in {frames_dir}")
        return

    print(f"  Scanning {len(frame_files)} frames with OCR (no API calls)...")
    ocr = OverlayOCR()

    # Find breakdown screens and transitions
    breakdowns = []
    transitions = []

    for f in frame_files:
        bd = ocr.read_breakdown_screen(str(f))
        if bd.get("is_breakdown"):
            breakdowns.append({"frame": f.name, "data": bd})
            print(f"    BREAKDOWN: {f.name} — teams: {bd.get('teams', {})}")

        if ocr.is_transition_screen(str(f)):
            transitions.append(f.name)
            print(f"    TRANSITION: {f.name}")

    print(f"\n  Found {len(breakdowns)} breakdown screens, {len(transitions)} transitions")

    if breakdowns:
        print(f"\n  Breakdown data:")
        for bd in breakdowns:
            teams = bd["data"].get("teams", {})
            print(f"    Red: {teams.get('red', [])}")
            print(f"    Blue: {teams.get('blue', [])}")


COMMANDS = {
    "analyze": ("Full pipeline: download → OCR + vision → report", cmd_analyze),
    "frames":  ("Download and extract frames only", cmd_frames),
    "scout":   ("Analyze frames with vision backend", cmd_scout),
    "ocr":     ("OCR-only analysis (free, no API)", cmd_ocr),
}


def main():
    print(f"\n  THE EYE — Vision Match Scouting")
    print(f"  Team 2950 The Devastators\n")

    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("  Commands:")
        for name, (desc, _) in COMMANDS.items():
            print(f"    {name:10s}  {desc}")
        print()
        print("  Examples:")
        print("    python3 the_eye.py analyze https://youtube.com/watch?v=... --focus 2950")
        print("    python3 the_eye.py analyze https://youtube.com/watch?v=... --tier scored --backend sonnet")
        print("    python3 the_eye.py analyze https://youtube.com/watch?v=... --tier all --fps 1 --backend haiku")
        print("    python3 the_eye.py scout .cache/WpzeaX1vgeQ/frames/ --tier key --backend haiku")
        print("    python3 the_eye.py ocr .cache/WpzeaX1vgeQ/frames/")
        print()
        print("  Tiers:    key (12 frames, default), scored (~50 score-change), all (every frame)")
        print("  Backends: haiku (default), sonnet, opus, gemma*, qwen*, moondream*, yolo*")
        print("            * = not yet implemented, coming soon")
        print()
        return

    cmd = sys.argv[1]
    _, handler = COMMANDS[cmd]
    handler(sys.argv[2:])


if __name__ == "__main__":
    main()
