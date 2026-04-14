# Eye Runbook — FIT DCMP 2026 Capture + Validation (Wed 4/15 → Sat 4/18)
## E.1 Validation Window — Remote Stream Capture, No On-Site Presence
## Last updated: 2026-04-13 (extended with capture harness + minute-by-minute checklist)

> **If we miss this window, the next live FRC footage is January 2027 kickoff.**
> 2950 is NOT competing. This is 100% remote — stream capture from Safiq's Mac.
> Entire pipeline runs locally. No Azure. No cloud. No teammates needed.

---

## QUICK REFERENCE — Stream Discovery

FIT DCMP streams go live each morning on:
- **Primary:** https://www.youtube.com/@FIRSTinTexas/streams
  - Visit this URL on the morning of each event day. The top card(s) = live streams.
  - Copy the URL from the browser address bar (format: `youtube.com/watch?v=XXXXXXXXXXX`).
  - Historically 1–2 concurrent streams (one per competition field). Both broadcast simultaneously.
- **Per-match VODs:** https://www.youtube.com/@texasFRC/videos
  - @texasFRC posts per-match cuts within 30 min of match end. These are the preferred
    source for post-match analysis (Mode A in this runbook).
- **Backup/simulcast:** https://www.twitch.tv/firstinspires (lower quality, 720p cap)
- **TBA event page:** https://www.thebluealliance.com/event/2026txcmp
  - Has links to streams + live match schedule as quals progress.
- **FIRST Updates Now (FUN):** https://www.youtube.com/@FIRSTUpdatesNow/streams
  - Sometimes simulcasts championship events. Check if @FIRSTinTexas is down.

**TBA event key:** `2026txcmp`
**Time zone:** All FIT DCMP match times are **Central Time (CT)**.
**Typical schedule:** Quals 8 AM–6 PM, Playoffs 9 AM–4 PM.

---

## STORAGE PLAN

Local storage layout:
```
TheEngine/eye/.capture/fit_dcmp_2026/
  fit_dcmp_2026-04-15_QM01_field1.mp4   ← per-match VODs from @texasFRC
  fit_dcmp_2026-04-15_QM02_field1.mp4
  ...
TheEngine/eye/.cache/
  <video_id>/match.mp4                   ← full VODs downloaded by the_eye.py
  <video_id>/frames/                     ← extracted frames (JPEGs, ~2–5 MB/match)
  results/<video_id>_report.json         ← Eye analysis output
```

Size estimates:
- Per-match VOD at 720p (~2 min): **80–150 MB**
- Frame cache per match (every 5s, ~30 frames): **~5–15 MB**
- Report JSON per match: **~50–200 KB**
- Total for ~50 quals over 4 days: **~5–8 GB** (VODs) + **~1 GB** (frames)
- **Recommended: capture 10–15 selected matches, not all 50.** Focus on
  high-profile alliances and teams likely to appear at Worlds.

What to capture vs skip:
- **Capture:** Qualification matches. Playoff matches (especially finals).
- **Skip:** Practice day (Wed 4/15 AM), opening ceremony, awards ceremonies,
  inspection queues, down time between divisions.
- **Skip:** Matches where the stream freezes or is clearly broken.

---

## PRE-FLIGHT CHECKLIST (Tuesday 2026-04-14 night — do this before Wed)

**Goal:** confirm the full pipeline works end-to-end so Wed is not debugging day.

**Time required:** ~30 minutes.

### Step 1 — Verify tools (5 min)
```bash
cd "/Users/safiqsindha/Desktop/The Engine/TheEngine"

# Check yt-dlp
yt-dlp --version
# Expected: 2024.x.x or later

# Check ffmpeg
ffmpeg -version | head -1
# Expected: ffmpeg version 6.x or 7.x

# Check Python deps
python3 -c "import pytubefix; print('pytubefix OK')"
python3 -c "import yt_dlp; print('yt-dlp module OK')"
python3 -c "import anthropic; print('anthropic OK')"

# Check API key
python3 -c "import os; k=os.environ.get('ANTHROPIC_API_KEY',''); print('Key set' if k else 'KEY MISSING')"
```

### Step 2 — Test capture harness (10 min)
Use any past FRC YouTube VOD — NOT a FIT DCMP stream (event hasn't started):
```bash
# Dry-run: just print the command
python -m eye.capture.fit_dcmp \
    --url "https://www.youtube.com/watch?v=WpzeaX1vgeQ" \
    --match QM99 --field test --dry-run

# Real capture: grab 60 seconds of a past FRC VOD
python -m eye.capture.fit_dcmp \
    --url "https://www.youtube.com/watch?v=WpzeaX1vgeQ" \
    --match QM99 --field test --duration 60

# Confirm file appeared
ls -lh eye/.capture/fit_dcmp_2026/
```

### Step 3 — Test full Eye pipeline (15 min)
```bash
# Run full analyze on any past FRC YouTube match
python3 eye/the_eye.py analyze \
    "https://www.youtube.com/watch?v=WpzeaX1vgeQ" \
    --tier key --backend haiku

# Expected output:
#   THE EYE — MATCH SCOUTING REPORT
#   Final: Red X — Blue Y
#   ...
#   Saved: eye/.cache/results/WpzeaX1vgeQ_report.json
```

If Step 3 succeeds → you're ready for Wednesday. If it fails → see Troubleshooting below.

### Step 4 — Confirm storage space (1 min)
```bash
df -h ~/Desktop
# Need at least 10 GB free for the weekend captures.
# If tight: clear old cache dirs in eye/.cache/ before Wed.
```

---

## MINUTE-BY-MINUTE RUNBOOK — Each Event Day (Wed 4/15 → Sat 4/18)

**Context:** Quals run most of the day. You check in 2–3 times per day, not continuously.
Total active time per day: ~30–45 minutes. This is not a "watch every match" operation.

---

### MORNING CHECK-IN (8:00–8:15 AM CT each day)

**8:00 AM** — Open @FIRSTinTexas/streams in browser
- URL: https://www.youtube.com/@FIRSTinTexas/streams
- Look for cards labeled "LIVE" — those are today's streams.
- Copy the URL of each live stream (usually 1–2 streams labeled by field or division).
- Note the URL(s) in a scratch doc or Slack message to yourself:
  ```
  Wed 4/15 Field 1: https://www.youtube.com/watch?v=XXXXXXXXXXX
  Wed 4/15 Field 2: https://www.youtube.com/watch?v=YYYYYYYYYYY
  ```

**8:05 AM** — Open TBA event page and note match schedule
- URL: https://www.thebluealliance.com/event/2026txcmp#matches
- Note which match numbers are quals (QM01, QM02...) vs practice vs playoffs.
- The day's match list gives you a sense of when to check @texasFRC for per-match VODs.

**8:10 AM** — Spot-check stream quality (optional)
- Play 30 seconds of the live stream in the browser.
- Confirm the scoreboard overlay is visible (top of frame, red/blue score + timer).
- If the overlay is missing or too small → note it. OCR will struggle; plan for Mode A only.

---

### MID-DAY CHECK-IN (1:00–1:30 PM CT each day)

**1:00 PM** — Open @texasFRC/videos
- URL: https://www.youtube.com/@texasFRC/videos
- Sort by "Latest". Look for matches posted since morning.
- @texasFRC naming convention: "[Event] Qualification Match XX" or similar.
- Pick 2–3 interesting matches to capture. Prioritize:
  - High-scoring matches (look for title mentions of high scores)
  - Top-ranked teams (cross-reference TBA rankings if curious)
  - Any teams likely at Worlds (nationally known Texas teams: 3310, 2056 if TX, etc.)

**1:05 PM** — Capture 2–3 per-match VODs using the harness
```bash
cd "/Users/safiqsindha/Desktop/The Engine/TheEngine"

# Replace QM12 and the URL with real values from @texasFRC
python -m eye.capture.fit_dcmp \
    --url "https://www.youtube.com/watch?v=VOD_ID_1" \
    --match QM12 --date 2026-04-15

python -m eye.capture.fit_dcmp \
    --url "https://www.youtube.com/watch?v=VOD_ID_2" \
    --match QM15 --date 2026-04-15
```

**1:10 PM** — Run Eye pipeline against the first captured file
```bash
# Option A: analyze the downloaded file directly (preferred — avoids re-download)
python3 eye/the_eye.py analyze \
    "https://www.youtube.com/watch?v=VOD_ID_1" \
    --tier scored --backend haiku

# The URL is used to check the cache. If already downloaded, it uses the cached file.
# The report lands in: eye/.cache/results/<video_id>_report.json
```

**1:20 PM** — Sanity check 1 report
```bash
python3 -c "
import json
r = json.load(open('eye/.cache/results/<video_id>_report.json'))
print('Final scores:', r.get('final_scores'))
print('Teams observed:', list(r.get('teams', {}).keys()))
print('Frames analyzed:', r.get('n_frames'))
"
```

Compare final_scores against TBA. If within ±10 points → pipeline working.

---

### EVENING CHECK-IN (7:00–7:30 PM CT each day)

**7:00 PM** — Check @texasFRC/videos for afternoon matches
- Capture 1–2 playoff or high-scoring qual matches posted since 1 PM.
- Use the same capture harness command as above.

**7:10 PM** — Run Eye on 1 playoff match if available
- Playoffs have cleaner strategy signal (fewer robots, more defined roles).
- Use `--tier key` for speed (playoffs are longer — key tier caps at 12 frames).

**7:20 PM** — Log observations in scratch notes
Write 2–3 bullet points per match:
- Did the pipeline run without crashing?
- Did the report show the right approximate winner?
- Any notable robot behavior the Eye caught?

---

### SATURDAY FINAL SESSION (4/18, after Playoffs wrap, ~5 PM CT)

**5:00 PM** — Capture 2–3 playoff/finals matches from @texasFRC
- Finals VODs usually posted within 60 min of match end.
- Run Eye on all of them: `--tier scored --backend haiku`

**5:30 PM** — File inventory
```bash
# Count captured files
ls -1 eye/.capture/fit_dcmp_2026/ | wc -l

# Total size
du -sh eye/.capture/fit_dcmp_2026/
du -sh eye/.cache/

# List any zero-byte or tiny files (potential corrupt captures)
find eye/.capture/fit_dcmp_2026/ -name "*.mp4" -size -1k
```

**5:45 PM** — Sample run on 3 matches end-to-end
Pick 3 matches (1 early qual, 1 late qual, 1 playoff) and run the full pipeline:
```bash
for VIDEO_ID in ID1 ID2 ID3; do
    python3 eye/the_eye.py analyze \
        "https://www.youtube.com/watch?v=$VIDEO_ID" \
        --tier scored --backend haiku
    echo "---"
done
```

**6:00 PM** — Write the debrief doc
Save to: `design-intelligence/EYE_FIT_CMP_RESULTS_2026-04-18.md`
Template:
```
# Eye FIT DCMP 2026 — Weekend Results
Date: 2026-04-18

## Matches processed
- QM01: [winner correct? y/n] [notes]
- QM12: ...
- SF1M1: ...

## What worked
- ...

## What broke / surprised
- ...

## OCR accuracy
- Score within ±10 pts: X/Y matches
- Overlay readable: [720p vs 480p stream quality notes]

## Recommendation for Worlds
- Mode A (post-match VOD) or Mode B (live segment)?
- Backend: haiku sufficient or switch to sonnet?
- Tier: key or scored?
```

---

## POST-CAPTURE CHECKLIST (Sunday 4/19 or Monday 4/20)

### 1. File inventory
```bash
cd "/Users/safiqsindha/Desktop/The Engine/TheEngine"

echo "=== Capture files ==="
ls -lh eye/.capture/fit_dcmp_2026/

echo "=== Report files ==="
ls -lh eye/.cache/results/

echo "=== Corrupt check (files < 1MB are suspect) ==="
find eye/.capture/fit_dcmp_2026/ -name "*.mp4" -size -1M -print

echo "=== Frame dirs ==="
du -sh eye/.cache/*/frames/ 2>/dev/null | sort -h
```

### 2. Sample run — 3 matches end-to-end
If you haven't already done the Saturday session, do it now:
- Pick 1 qual from Wed, 1 qual from Fri, 1 playoff from Sat.
- Run `python3 eye/the_eye.py analyze <url> --tier scored --backend haiku` on each.
- Document what worked, what broke.

### 3. What NOT to attempt this weekend
- No bumper OCR or per-team attribution (that's Week 2 Roboflow wire-up)
- No model training or labeling (off-season scope, June/July)
- No Scout integration or pick_board feed (Eye E.3, deferred to October)
- No Azure deployment (that's the Worlds test)
- No YOLO backend (model doesn't exist for the 2026 game yet)

### 4. Commit the results
```bash
cd "/Users/safiqsindha/Desktop/The Engine/TheEngine"
git add design-intelligence/EYE_FIT_CMP_RESULTS_2026-04-18.md
git add eye/.cache/results/  # report JSONs only, not full MP4s
git commit -m "Eye E.1: FIT DCMP 2026 capture results + debrief"
```

### 5. Decide for Monday kickoff
Add a one-liner to `MONDAY_KICKOFF_2026-04-13.md` under Section 1:
```
FIT DCMP smoke test complete (4/15-4/18). Results: EYE_FIT_CMP_RESULTS_2026-04-18.md.
[Pipeline works / has issues — next: ...].
```

---

## WHAT THIS UNLOCKS

If FIT DCMP capture is solid:
- **Worlds (4/29–5/2):** Azure deploy test with Mode A live cron. Same pipeline,
  just running in the cloud instead of on Safiq's Mac.
- **Week 2 (4/20–4/27):** Wire Roboflow supervision pipeline using cached FIT DCMP
  VODs as the test corpus. W2.2a–W2.4 tasks from ENGINE_AUDIT_2026-04-13.md.
- **Off-season (June/July):** Use FIT DCMP + Worlds footage as training data for
  bumper OCR validation and zone polygon calibration.

---

**Purpose:** Run The Eye locally against the FIRST In Texas District Championship
broadcast (4/15-4/18). Confirm the vision pipeline works end-to-end on real
championship-quality footage *before* Worlds (4/29-5/2), where we'll do the
**5-consecutive-match local-model demo**. This is **local-only** — no Azure,
no Bicep, no infra changes.

**Why now:**
- FIT DCMP is the **only dress rehearsal** before Worlds. After Worlds we
  wait until off-season starts post-June for any other live event window.
- FIT DCMP is 4 days; Worlds is 4 days; ~10 days between them. Miss this, lose
  the rehearsal.
- API spend (Haiku frames) is **separate from Claude Code conversation budget**.
  Running this against 5-10 matches costs ~$1-2 in Anthropic credits, not
  weekly cap.

**Two backend modes — pick one:**
- **Mode H (Haiku API)** — works today, costs API credits, validates the OCR +
  pipeline plumbing but does NOT validate the local model path. Use this for
  the FIT DCMP weekend.
- **Mode L (local compound model)** — only available after the W2.2 wire-up
  (week of Mon 4/20). FIT DCMP is realistically Mode H; **Worlds is Mode L
  only**. The cached FIT DCMP VODs from Mode H become the regression set for
  tuning Mode L the following week.

**Critical constraint for Worlds (locked):** the Worlds demo runs **Mode L
only**, no API fallback. "5 consecutive matches, fully local, no API." If
Mode L isn't ready by Mon 4/27, the Worlds demo doesn't happen — we either
ship Path A locally or we wait for off-season.

**What you need before starting:**
- ANTHROPIC_API_KEY in env ✅ (verified set)
- ffmpeg ✅ (verified at `/opt/homebrew/bin/ffmpeg`)
- pytubefix Python module ✅ (used by `the_eye.py`)
- yt_dlp Python module ✅ (used by `hls_pull.py` for live mode only)
- ~30 min of attention spread across the weekend
- The FIT CMP YouTube/Twitch URL (find via firstinspires.org event page or FRCGameDay channel)

---

## Mode A — Post-match VOD analysis (RECOMMENDED, run this first)

**Idea:** FRCGameDay posts per-match VODs to YouTube within ~30 min of each
match ending. Wait for the VOD, then run the full pipeline. Simple, robust,
no live-stream gymnastics.

**Steps:**

1. **Find the FIT CMP event page:**
   - Go to firstinspires.org → events → FIT District Championship 2026
   - Confirm the broadcast YouTube channel (probably FRCGameDay or a Texas-specific channel)
   - Bookmark the channel's "Live" or "Recent uploads" page

2. **Pick a match to test on:**
   - Wait for any qualification match to end + ~30 min
   - Grab the YouTube URL of the per-match VOD (NOT the full-day stream)
   - URL format will be `https://www.youtube.com/watch?v=XXXXXXXXXXX`

3. **Run analyze:**
   ```bash
   cd "/Users/safiqsindha/Desktop/The Engine/TheEngine"
   python3 eye/the_eye.py analyze \
       "https://www.youtube.com/watch?v=XXXXXXXXXXX" \
       --tier scored \
       --backend haiku
   ```

   What this does:
   - Downloads the VOD via pytubefix → `eye/.cache/<video_id>/match.mp4`
   - Extracts frames every 5s via ffmpeg → `eye/.cache/<video_id>/frames/`
   - Runs OCR over the frames to find score-change moments (free, no API)
   - Selects ~50 scored frames + auto/endgame frames
   - Sends them to Claude Haiku for qualitative scouting
   - Writes a report → `eye/.cache/results/<video_id>_report.json`

4. **Read the report:**
   ```bash
   python3 -c "import json; r=json.load(open('eye/.cache/results/XXXXXXXXXXX_report.json')); print(json.dumps(r, indent=2))"
   ```
   Or just open it in your editor — it's plain JSON.

5. **Sanity-check vs TBA:**
   - Pull the same match from TBA (Statbotics or thebluealliance.com)
   - Compare: did the Eye report the right winner? Right rough score? Did it
     identify the obvious cycles / climbs / penalties?
   - **Goal:** "in the right ballpark" — not pixel-perfect. We're testing the
     pipeline, not the model accuracy.

6. **Repeat for 4-5 matches:**
   - Mix qualification + playoff
   - Mix high-scoring + low-scoring matches
   - Mix matches with obvious vs subtle scoring patterns

7. **Write a 1-paragraph debrief:**
   - Save as `design-intelligence/EYE_FIT_CMP_RESULTS_2026-04-XX.md`
   - What worked, what didn't, what surprised you
   - Did SABR / 403s show up? (See troubleshooting below)
   - Was 12-frame "key" tier enough or do you need "scored" tier?
   - Was Haiku enough or do you wish it were Sonnet?

---

## Mode B — Live segment processing (OPTIONAL, only if Mode A is solid)

**Idea:** Pull a 60s segment off the *live* HLS stream while a match is
happening, extract frames, run scout on them. Doesn't wait for the VOD post.
More fragile (SABR, cookies, timing) but faster feedback.

**Steps:**

1. **Find the live YouTube URL** (the active stream, not a VOD)

2. **Pull a 60-second segment:**
   ```bash
   cd "/Users/safiqsindha/Desktop/The Engine/TheEngine"
   python3 -c "
   from eye.hls_pull import pull_hls_segment
   path = pull_hls_segment(
       'https://www.youtube.com/watch?v=LIVESTREAM_ID',
       duration_sec=60,
       extra_args=['--cookies-from-browser', 'chrome']
   )
   print('Segment:', path)
   "
   ```

   That `--cookies-from-browser chrome` flag is the SABR workaround per
   `hls_pull.py:21-31`. If you don't have Chrome, swap for Safari/Firefox/Edge.

3. **Extract frames manually:**
   ```bash
   mkdir -p eye/.cache/livesegment/frames
   ffmpeg -i /tmp/<segment>.mp4 -vf fps=1/2 -q:v 2 \
       eye/.cache/livesegment/frames/frame_%03d.jpg
   ```

4. **Run scout on the frames:**
   ```bash
   python3 eye/the_eye.py scout eye/.cache/livesegment/frames/ \
       --tier key --backend haiku
   ```

5. **Read the result, repeat as desired.**

**Mode B caveats:**
- A 60s segment is one cycle, not a full match. Don't expect a "winner" output.
- Use this as a "did vision actually see the robot doing the thing" test, not
  a match-prediction test.
- If `pull_hls_segment` 403s with no cookies, it WILL also fail with cookies if
  YouTube has fingerprinted the cookies as bot traffic. Fall back to Mode A.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `pytubefix.exceptions.VideoUnavailable` on Mode A | Video is age-restricted, region-locked, or just-published-not-yet-indexed | Wait 5 min and retry. If persistent, use Mode B with cookies. |
| `403 Forbidden` from yt-dlp / ffmpeg on Mode B | YouTube SABR enforcement (documented in hls_pull.py:21-31) | Add `--cookies-from-browser chrome` (or your browser). Last resort: manually export `cookies.txt` from a logged-in browser. |
| Frames extracted but the report says "no events detected" | Low broadcast resolution (480p) breaking OCR | Re-run with `--tier scored` (uses score-delta detection instead of pure key-frame pick) or `--tier all --fps 1` (denser sampling) |
| `ANTHROPIC_API_KEY not set` | Env var lost between shells | `export ANTHROPIC_API_KEY=...` in the shell you're running from |
| Report exists but `cycles: []` is empty | Haiku didn't recognize the game piece | Expected for an unfamiliar game. The Eye was trained on REBUILT-era game pieces. For 2026 game pieces it's testing transfer. Note this in the debrief — it's data, not a bug. |
| Pipeline runs but takes >5 min per match | "scored" tier on a long playoff match can hit ~80-100 frames | Use `--tier key` instead, which caps at 12 frames (~30s end-to-end) |
| Eye reports the wrong winner | Score breakdown OCR misread, OR Haiku misread the overlay | Pull the report's `frames_used` list, look at the actual JPEGs. If OCR is wrong → known limitation, log it. If Haiku is wrong → try `--backend sonnet` for that match (10x cost but 10x better) |

---

## Budget guardrails

- **Per match (Mode A, default tier=scored, backend=haiku):** ~50 frames × Haiku Vision pricing ≈ **$0.10-0.20 per match**
- **5 matches:** ~$0.50-1.00
- **10 matches:** ~$1-2
- **If you switch to `--backend sonnet`:** multiply by ~10
- **Hard cap:** if you find yourself running >15 matches, stop and ask whether
  this is still a smoke test or has crept into a benchmark suite. Smoke test is
  ~5-10 matches.

These come from your **Anthropic API account**, not the Claude Code weekly cap.
The Claude Code cap is for *me* (this conversation). Running `the_eye.py`
directly doesn't touch it.

---

## What "success" looks like for this weekend

Minimum bar to call this a win:
- [ ] At least 1 match runs end-to-end without crashing
- [ ] The report file lands in `eye/.cache/results/`
- [ ] You can compare the report to TBA and the comparison is "in the right ballpark"
- [ ] You document one surprise, one bug, or one improvement idea in the debrief doc

Stretch goals:
- [ ] 5 matches processed
- [ ] Mode B (live segment) runs at least once
- [ ] The debrief doc identifies a concrete improvement worth a follow-up workstream

---

## What this UNLOCKS for Worlds

If FIT CMP local test is solid, **Worlds becomes the Azure deploy test:**

- Flip `MODEL_NAME=fake` → `MODEL_NAME=haiku` in `infra/bicep/parameters.dev.json`
- Run `az bicep build` + deploy
- The `mode_a.py` cron pulls live segments every 10 min during the broadcast
- `vision_worker.py` runs the same pipeline you ran locally, just in Azure
- Reports flow into the Azure storage backend

**Do not flip the Azure switch until FIT CMP local results say it's worth it.**
The MCP architecture decision (Tier A of Monday's kickoff) might also reshape
this — the Eye pipeline isn't blocked by MCP, but the priority order matters.

---

## What this does NOT do

- Not a YOLO benchmark (the YOLO backend is "fake" — V0a unresolved as of 2026-04-11)
- Not a real-time scouting system (Mode B is segment-by-segment, not continuous)
- Not a TBA upload (TBA Trusted v1 uploader is in `workers/tba_uploader.py` and
  is NOT wired into this runbook — local-only means we read TBA, we don't write to it)
- Not an Azure test (that's Worlds)
- Not validation of `eye_bridge.py` → `pick_board` → Discord bot pipeline. That's
  a separate test that can wait for off-season.

---

## After the weekend

When FIT CMP wraps Sunday night:
1. Save the debrief doc to `design-intelligence/EYE_FIT_CMP_RESULTS_2026-04-XX.md`
2. Commit `eye/.cache/results/*_report.json` to a branch (NOT main — they're
   bulky JSON snapshots, gitignored elsewhere). Or just leave them locally.
3. Add a one-liner to `MONDAY_KICKOFF_2026-04-13.md` Section 1 with "FIT CMP
   smoke test ran, results in EYE_FIT_CMP_RESULTS"
4. Decide for Monday whether the Eye work jumps in priority. If FIT CMP showed
   real promise, Eye E.1 (offseason batch) might move from August to May.

---

## CAPTURE HARNESS REFERENCE

Capture script: `eye/capture/fit_dcmp.py`
```bash
# Full help
python -m eye.capture.fit_dcmp --help

# List stream channel URLs
python -m eye.capture.fit_dcmp --list-channels

# Dry-run any URL
python -m eye.capture.fit_dcmp --url "https://youtube.com/watch?v=..." --match QM01 --dry-run
```

Roboflow config stub: `eye/pipeline/roboflow_config.py`
```bash
# Print pipeline summary + what's needed for Week 2 wire-up
python -m eye.pipeline.roboflow_config
```

---

*Originally written by Opus 2026-04-11. Extended 2026-04-13 with capture harness,
minute-by-minute checklist, storage plan, and post-capture section.
API spend uses Anthropic API account credits, NOT Claude Code weekly cap.
Run all commands from the TheEngine working directory.*
