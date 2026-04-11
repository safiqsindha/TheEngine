# Post-Season Purchase List — The Engine

Deferred items that need budget approval before the next build season. The 2026 season is over for Team 2950 — all items are off-season investments evaluated against 2027 readiness milestones, not any in-season deadline.

**Last updated:** 2026-04-11

---

## Tier 1 — High value, clear ROI

### Mac Mini (M-series, 16 GB unified memory)
**Estimated cost:** $599–$799 (M4 base)
**Why:** Currently all LLM inference runs on Safiq's MacBook Pro. As the number of Engine subsystems grows (Antenna bot + vision worker + synthesis worker + pick_board + EYE), running them simultaneously on the MacBook during a competition means no laptop for anything else. A dedicated Mac Mini running all workers frees the MacBook for operator use.
**Prerequisites before purchase:**
- Confirm the competition network environment (some venues block ports; needs testing)
- Verify `workers/Dockerfile` image can build for arm64/M-series without architecture issues
- Decide whether it runs as a local server or deploys workers via Azure

**Decision gate:** at first off-season scrimmage / fall event, once we have a real venue network to test against. No urgency before then.

---

### Roboflow subscription (Starter or Growth tier)
**Estimated cost:** $0 (free tier: 10k images) → $49/mo (Starter: 100k images + training)
**Why:** The vision rewrite strategy (see `VISION_PLAN_EVAL.md`) relies on Roboflow Universe for open-corpus FRC robot footage. The free tier caps at 10k images and doesn't include AutoBatch training. The Starter tier ($49/mo) gives us 100k images + AutoBatch + team workspace. Growth tier ($249/mo) adds version history + API priority.
**Recommendation:** Start on free tier for the harvest phase (just downloading datasets). Upgrade to Starter only when we need to train a custom model — that's a summer 2026 task (per V0a decision in `V0a_MODEL_SELECTION.md`).

**Decision gate:** after we've harvested open datasets and confirmed the free tier is limiting us.

---

## Tier 2 — Medium value, timing-dependent

### Azure GPU SKU upgrade for vision worker
**Current state:** `visionGpuSku=""` (CPU-only) is the default and stays that way through 2026 season per V0b decision in `V0b_GPU_SELECTION.md`. Inference fits in the 10-minute cron budget on CPU for our V0a model paths.
**When this changes:** if the custom-trained model (summer 2026 off-season data engine) exceeds ~25M parameters, or if Mode A cadence moves to `* * * * *` (every minute). At that point, upgrade to `Standard_NC6s_v3` (~$0.90/hr) or `Standard_NC4as_T4_v3` (~$0.52/hr spot).
**Estimated cost:** $7–$15/event-weekend when active (spin up before first match, spin down after last match)

**Decision gate:** after V0a custom training, benchmark CPU vs GPU latency on the trained model.

---

### Raspberry Pi 5 (stand-alone EYE frame capture device)
**Estimated cost:** ~$80 + case + SD card + USB-C power
**Why:** Currently the EYE vision worker runs on the MacBook alongside everything else. A Pi 5 mounted at pit-side could run the frame capture loop independently, freeing the MacBook. The worker already uses `eye/eye_bridge.py`'s file-based state, so a Pi could write frames to a shared SMB mount or local cache and the MacBook's worker reads them.
**Prerequisites:**
- Verify YOLOv8n inference on Pi 5 CPU meets the frame-rate floor (~5 fps)
- Network: Pi needs to reach the MacBook OR an Azure endpoint for state sync
- Power: pit tables have outlets but venue availability varies

**Decision gate:** at first off-season event running the full Engine stack, if MacBook resource contention is observed.

---

## Tier 3 — Low priority / exploratory

### Vertex AI credits (for summer 2026 Gemma+SAM3.1 data engine)
**Estimated cost:** unknown — depends on dataset size and training runs
**Reference:** `design-intelligence/ROADMAP_2028.md` off-season vision track
**Notes:** The data engine ships in summer 2026. Google Research Cloud credits may be available for FRC teams; check with FIRST/Mentors before paying out of pocket.

### External USB-C SSD for match footage archiving
**Estimated cost:** $60–$90 (2 TB)
**Why:** Storing VOD segments locally across a full regional generates 100-300 GB. The MacBook's SSD is already pressured. If streaming download rate exceeds available disk space during quals, the vision worker will start dropping frames.
**Size estimate:** ~15 GB/hour of 1080p30 stream → ~30-45 GB per full event day → 60-90 GB for a 2-day regional.

---

## Not on the list (and why)

| Item | Reason |
|---|---|
| Roboflow Enterprise ($499/mo) | Growth tier overkill for one team; free → Starter is the right ladder |
| NVIDIA Jetson Orin | Overkill for our model size; Pi 5 + CPU is sufficient for YOLOv8n |
| Cloud GPUs (Vast.ai, Lambda) | Azure Container Apps + GPU SKU is cheaper and already wired in the Bicep template |
| Dedicated WiFi router | Venue WiFi is usually fine; hotspot is the fallback; router adds setup complexity |

---

## Change log

- **2026-04-11** — initial list compiled from `VISION_PLAN_EVAL.md §5`, `V0a_MODEL_SELECTION.md`, `V0b_GPU_SELECTION.md`, and the session-summary pickup notes.
