# Eye Runbook — FIT DCMP Live Test (Wed 2026-04-15 → Sat 2026-04-18)

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

*Written by Opus 2026-04-11 in the same session as MONDAY_KICKOFF_2026-04-13.md.
Consume Anthropic API credits, not Claude Code conversation cap. Run from the
TheEngine working directory.*
