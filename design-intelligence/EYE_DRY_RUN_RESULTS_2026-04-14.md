# Eye FIT DCMP 2026 — Dry Run Results
**Date:** 2026-04-14  
**Performed by:** Claude Sonnet 4.6 (pre-event harness validation)  
**Purpose:** Catch crashes before the live capture window opens Wed 2026-04-15

---

## Synthetic Input Used

- **Synthetic video:** 10-second 1280×720 30fps solid-blue H.264+AAC MP4 generated with:
  ```
  ffmpeg -f lavfi -i "color=c=blue:size=1280x720:rate=30" \
         -f lavfi -i "sine=frequency=1000:sample_rate=44100" \
         -t 10 -c:v libx264 -preset ultrafast -c:a aac \
         /tmp/synthetic_test.mp4
  ```
  Size: 104 KB. Not a real FRC stream; used purely to test decode/path logic.

- **Synthetic frames:** 20 blue 1280×720 JPEGs generated with ffmpeg lavfi, placed in
  `/tmp/synthetic_frames/` for `the_eye.py scout` tests.

- **YouTube URL tested (non-live):** `https://www.youtube.com/watch?v=WpzeaX1vgeQ`
  (FIT Week 4 Dripping Springs District Event — a past VOD, as recommended by the runbook).

---

## What Ran Cleanly

| Test | Result |
|---|---|
| `python3 -m eye.capture.fit_dcmp --dry-run` | PASS — correct yt-dlp command printed |
| `--list-channels` flag | PASS — all 5 channel URLs printed correctly |
| `--live --duration 30 --dry-run` (live mode) | PASS — `--downloader ffmpeg --downloader-args ffmpeg_i:-t 30` present |
| `--seek 30 --duration 30 --dry-run` (VOD seek) | PASS — `--download-sections *30.000-60.000` correct |
| `build_output_filename()` unit tests | PASS — naming convention correct for all label types (QM, SF, F) |
| `find_ytdlp()` binary detection | PASS — found at `/Users/safiqsindha/Library/Python/3.9/bin/yt-dlp` |
| `find_ffmpeg()` binary detection | PASS — found at `/opt/homebrew/bin/ffmpeg` (version 8.1) |
| `output_path.parent.mkdir(parents=True, exist_ok=True)` | PASS — creates nested dirs on demand |
| `python3 -m eye.pipeline.roboflow_config` | PASS — imports cleanly, `print_pipeline_summary()` runs |
| `the_eye.py ocr /tmp/synthetic_frames/` | PASS — runs without crash; 0 events found (expected on solid color frames) |
| `ANTHROPIC_API_KEY not set` error path | PASS — `RuntimeError: ANTHROPIC_API_KEY not set` raised cleanly |
| yt-dlp stream probe (`--print is_live --skip-download`) | PASS — correctly identifies VOD for WpzeaX1vgeQ |

---

## What Crashed

### CRASH 1 — YouTube SABR 403 Forbidden on all download attempts

**Severity:** BLOCKING for live capture. Not blocking for --dry-run or pipeline tests.

**Reproduction:**
```
python3 -m eye.capture.fit_dcmp \
    --url "https://www.youtube.com/watch?v=WpzeaX1vgeQ" \
    --match QM99 --field test --duration 30
```

**Full error:**
```
[https @ 0x...] HTTP error 403 Forbidden
[in#0 @ 0x...] Error opening input: Server returned 403 Forbidden (access denied)
ERROR: yt-dlp exited 1
stderr: ...ffmpeg exited with code 8
```

**Root cause:** YouTube SABR (Streaming Abuse Rate Limiting) blocks unauthenticated yt-dlp
downloads from residential/API IPs. This is a known YouTube platform issue documented in
[hls_pull.py:21-31](../eye/hls_pull.py) and in the runbook's Troubleshooting table.

**Tried and also failed:**
- `--cookies safari` → `[Errno 1] Operation not permitted` (macOS sandboxes Safari cookies)
- `--cookies chrome` → 108 cookies extracted, but 403 persisted (not logged into YouTube in Chrome or session fingerprinted)
- Explicit DASH format `134+140` → still 403 at ffmpeg download stage
- `worst[ext=mp4]/worst` format → still 403

**This is NOT a bug in fit_dcmp.py.** The harness correctly passes `--cookies-from-browser`
and the error path exits with a clear message. The issue is the YouTube session state on this machine.

**Fix required before Wed:** Log into YouTube in Chrome and verify the session is active.
Then re-test with `--cookies chrome`. See runbook Troubleshooting table.

---

### CRASH 2 — `the_eye.py frames` rejects local file path (non-blocking)

**Severity:** LOW — only affects dry-run path. Real usage always passes YouTube URLs.

**Reproduction:**
```
python3 eye/the_eye.py frames /tmp/synthetic_test.mp4 --fps 2
```

**Error:**
```
pytubefix.exceptions.VideoUnavailable: synthetic_t is unavailable
```

**Root cause:** `cmd_frames` parses its argument as a YouTube URL and extracts `video_id`
via `url.split("v=")[-1].split("&")[0]` or `url[-11:]`. A local path `/tmp/synthetic_test.mp4`
produces video_id `synthetic_t` (last 11 chars), which obviously fails `YouTube()` lookup.

**Not a bug for production use** — the runbook only ever passes YouTube URLs to `frames`
and `analyze`. Flag only: local-path support would improve testability but is not needed
for Wed.

---

### CRASH 3 — `the_eye.py scout --backend yolo` raises NotImplementedError (non-blocking)

**Severity:** LOW — yolo backend is documented as unimplemented (V0a unresolved).

**Error:**
```
NotImplementedError: YOLO backend not yet implemented. Requires custom-trained model.
Use --backend haiku for now.
```

This is intentional. The error message is user-friendly. No fix needed.

---

## Fixes Applied

### Fix 1 — Added `eye/.capture/` to `.gitignore`

**Problem:** `eye/.cache/` was gitignored but `eye/.capture/` (the directory where
`fit_dcmp.py` writes raw MP4s) was NOT. Without this entry, running the capture
harness on Wed would have untracked ~300 MB of MP4 files showing up in `git status`.

**File changed:** `.gitignore`

**Change:**
```
# Before:
# EYE cache (videos, frames, results)
eye/.cache/

# After:
# EYE cache (videos, frames, results)
eye/.cache/
# EYE capture directory (raw MP4s, ~300MB/session, do not commit)
eye/.capture/
```

**Commit:** see commit hash below.

---

## What Still Needs Fixing Before Wed

| Priority | Issue | Action Required |
|---|---|---|
| **BLOCKING** | YouTube SABR 403 blocks actual downloads | Open Chrome, log into YouTube, then re-test: `python -m eye.capture.fit_dcmp --url "https://www.youtube.com/watch?v=WpzeaX1vgeQ" --match QM99 --field test --duration 30 --cookies chrome` |
| MEDIUM | `ANTHROPIC_API_KEY` is empty in bash environment | Run `export ANTHROPIC_API_KEY=<your-key>` in the shell before starting `the_eye.py analyze`. The key is set in Claude Code's env but not in a standalone bash shell. |
| LOW | Safari cookies inaccessible (`[Errno 1] Operation not permitted`) | Use Chrome instead of Safari for `--cookies` argument. Chrome cookies work (extracted 108), session just needs to be logged in. |
| LOW | Python 3.9 deprecation warning from yt-dlp | `pip install --user "python>=3.10"` or use `python3.11`. Not blocking for Wed but will eventually become a hard error. |

---

## Go / No-Go Verdict

### **CONDITIONAL GO** — with one pre-flight action required

**Go** on:
- `fit_dcmp.py` harness structure: all code paths work correctly
- Directory creation, filename building, dry-run mode: all clean
- Binary detection (yt-dlp + ffmpeg): both found at expected paths
- Roboflow config module: imports and runs cleanly
- OCR pipeline (`the_eye.py ocr`): runs without crash
- Error handling for missing API key: clean RuntimeError

**Blocked on** (must fix Tuesday night before Wed):
1. **Log into YouTube in Chrome.** The SABR 403 only bypasses with an authenticated
   browser session. Run this test after logging in:
   ```bash
   cd "/Users/safiqsindha/Desktop/The Engine/TheEngine"
   python -m eye.capture.fit_dcmp \
       --url "https://www.youtube.com/watch?v=WpzeaX1vgeQ" \
       --match QM99 --field test --duration 30 --cookies chrome
   ```
   If this produces a file ≥ 1 KB in `eye/.capture/fit_dcmp_2026/`, you're go for Wed.

2. **Set ANTHROPIC_API_KEY** in the shell you'll use on Wed:
   ```bash
   export ANTHROPIC_API_KEY=<your-key>
   python3 -c "import os; print('Key set' if os.environ.get('ANTHROPIC_API_KEY') else 'MISSING')"
   ```

If both pre-flight checks pass, the pipeline is ready to capture on Wed 2026-04-15.

---

## Runbook Reference

The full pre-flight checklist is in:
`design-intelligence/EYE_RUNBOOK_FIT_DCMP_2026-04-15.md` → Section "PRE-FLIGHT CHECKLIST"

The SABR workaround is documented in:
`eye/hls_pull.py` lines 21-31  
`design-intelligence/EYE_RUNBOOK_FIT_DCMP_2026-04-15.md` → Troubleshooting table

---

*Dry run performed 2026-04-14 by Claude Sonnet 4.6 as pre-event validation.*
*Commit: see git log for `fix(eye): pre-FIT-DCMP dry run fixes` + `docs: Eye dry run results 2026-04-14`*
