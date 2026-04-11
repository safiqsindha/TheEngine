# V0b — Azure GPU SKU Selection for vision-worker

**Status:** decision doc, 2026-04-11. Resolves the "pick an Azure GPU SKU for the vision worker (or accept CPU latency)" prereq from `LIVE_SCOUT_PHASE2_REMAINING.md §5`.

**Owner:** Safiq (decision) + Claude (implementation).

**Depends on:** `V0a_MODEL_SELECTION.md`. If V0a resolves to Path C (stay fake), **V0b is moot and defaults to no GPU** (empty `visionGpuSku`). The rest of this doc is only relevant if V0a resolves to Path A.

---

## Options

Azure Container Apps ships with two GPU SKUs, both under the serverless Consumption workload profile:

| SKU | GPU | VRAM | vCPUs | Memory | Architecture | Best for |
|---|---|---|---|---|---|---|
| `Consumption-GPU-NC8as-T4` | NVIDIA T4 | 16 GB | 8 | 56 GiB | Turing | **Inference** of small (<10 GB) models |
| `Consumption-GPU-NC24ads-A100-v4` | NVIDIA A100 | 80 GB | 24 | 220 GiB | Ampere | Training + inference of large (>10 GB) models |

Plus the implicit third option — **no GPU, CPU-only** — which is what the current Bicep `visionGpuSku=""` default does.

### Relevant YOLO model sizes

| Model | Params | Typical VRAM at 1280×720 inference |
|---|---|---|
| YOLOv8n / YOLOv11n / YOLO26n | ~3M | <1 GB |
| YOLOv8s / YOLOv11s / YOLO26s | ~11M | <2 GB |
| YOLOv8m / YOLOv11m / YOLO26m | ~26M | ~3 GB |
| YOLOv8l / YOLOv11l / YOLO26l | ~44M | ~5 GB |

Every sane FRC vision model is nano or small. **Every single one of these fits on a T4 with ~10 GB to spare.** A100 is overkill by two orders of magnitude.

---

## Cost estimate

Pricing for Azure Container Apps GPU is **not** on the public pricing page — Microsoft's docs say to reference VM pricing as a proxy and check Azure Cost Management after deployment for the authoritative numbers.

**T4 VM proxy**: the `Standard_NC4as_T4_v3` VM (the closest non-Container-Apps equivalent) runs ~$0.32/GPU-hour pay-as-you-go. The `NC8as_T4_v3` profile used by ACA is larger (8 vCPU / 56 GiB) but the GPU is the same single T4.

**Expected cron duty cycle:**

- Cron: `*/10 * * * *` → 144 invocations/day
- Each invocation processes 1 match's worth of frames (~60 frames at 5s intervals over a 5-minute window)
- YOLOv8n inference on T4 at 1280×720 ≈ **~4ms/frame** → ~0.25s of GPU wall time per invocation
- **But:** ACA bills per-second of container runtime, not per-second of GPU kernel time. Cold start + model load + inference + shutdown = **~30-60s per invocation**.
- 144 invocations × 45s average = **108 minutes/day = 1.8 hours/day**

At ~$0.32/GPU-hour that's roughly **$0.58/day** = **~$17/month** for the T4 SKU.

**A100 VM proxy**: ~$3.67/GPU-hour → ~$200/month. **~12× the cost for zero quality improvement on a nano-class YOLO model.**

**CPU-only proxy**: the regular Consumption profile at ~$0.000024/vCPU-second. Same 1.8 hours/day × 8 vCPU = ~14.4 vCPU-hours/day = $0.35/day = **~$10/month**. Saves ~$7/month vs T4 — but see the latency analysis below.

### Cost summary

| SKU | Estimated monthly cost | Quality outcome |
|---|---|---|
| CPU only (no GPU) | ~$10 | Acceptable only for nano models; see latency |
| T4 (`NC8as-T4`) | ~$17 | Correct choice for any YOLO-nano/small inference |
| A100 (`NC24ads-A100-v4`) | ~$200 | **Do not do this** for inference |

All numbers are estimates — **the only authoritative source is Azure Cost Management after one week of running** per the Microsoft Q&A thread on ACA GPU billing.

---

## Latency analysis (the real tradeoff)

For a `*/10 * * * *` cron, we have a **10-minute budget** per invocation before the next tick starts. Either SKU fits comfortably. The question is whether CPU inference fits.

**YOLOv8n at 1280×720 on CPU** (modern x86, 8 vCPU): ~80-120ms/frame. For 60 frames that's ~6-8 seconds of inference. Model load + warmup + extraction time + shutdown pushes total invocation wall time to ~45-60 seconds. **Well under the 10-minute budget.**

**YOLOv8n at 1280×720 on T4:** ~4ms/frame. For 60 frames that's ~240ms of inference. Total invocation ~30-40 seconds (dominated by container start + model load, not inference). ~15-20s faster than CPU.

**Conclusion:** for the `*/10 * * * *` cadence, CPU is fine. The GPU gains us ~15 seconds of wall time per invocation at a cost of ~$7/month extra.

### When would we actually need a GPU?

Only if we get into two scenarios:

1. **Mode A cadence.** If we decide to run vision inference on the live HLS stream at `* * * * *` (every minute, not every 10), we blow past the CPU budget. At 60 frames × 100ms/frame = 6s inference × 1 tick/minute = 10% duty cycle → ~4.3 hours/day of CPU time = ~$31/month on CPU vs ~$17/month on T4. **GPU actually becomes cheaper** because the per-second rate is higher but the wall time is 10× lower.

2. **Higher frame rate.** If we drop the frame interval from 5s to 1s, we get 300 frames per 5-minute window instead of 60. CPU inference time jumps to ~30-40 seconds per invocation — still under the 10-minute budget, but we've eaten most of the slack.

---

## Recommendation

**Resolved: no GPU. `visionGpuSku=""` stays the default.**

### Why

1. **If V0a → Path C (recommended)**, `MODEL_NAME=fake` means the vision worker does no inference at all and spends ~1 second per invocation. A GPU is actively wasteful.

2. **If V0a → Path A**, the compound pipeline runs YOLOv8n × 2 models on 60 frames at `*/10 * * * *`. CPU inference is ~10-15 seconds total per invocation. **That's fine** — we have a 10-minute budget. Saving 10 seconds per invocation for $7/month is a bad trade.

3. **If V0a → Path B**, single YOLOv8n on 60 frames = ~6-8 seconds. Even more clearly CPU-appropriate.

4. **Cost discipline.** The Live Scout monthly bill is currently dominated by the Anthropic API call (~$3-8/month for one Opus call per day) and Storage Blob (~$1/month). Adding $17/month for a GPU that saves 15 seconds per cron invocation nearly triples the infrastructure line item for near-zero operational benefit.

### When to revisit

Trigger a V0b re-evaluation if **any** of these happen:

- V0a resolves to a YOLOv8**m** or larger (unlikely — FRC YOLO models are nearly always nano)
- Mode A cadence moves to `*/1 * * * *` (every minute) — CPU duty cycle becomes uncomfortable
- Frame interval drops to 1s or lower (frames per invocation 5×)
- Off-season data engine produces a custom model with >25M params (>3GB VRAM)

---

## What Path A would actually use

If Safiq overrules V0a Path C and ships Path A this season, the Bicep change is one line:

```bicep
// infra/bicep/parameters.dev.json
{
  "visionGpuSku": { "value": "" }  // ← still empty; CPU is correct for Path A too
}
```

i.e. **even Path A does not need a GPU.** The only way V0b becomes "yes, use T4" is if we move Mode A vision inference to the live `* * * * *` cron, which is not on any roadmap right now.

---

## Decision needed from Safiq

Pick one:

- **[ ] Stay CPU-only (recommended)** — `visionGpuSku=""` in both dev + prod parameter files, revisit only on the triggers above
- **[ ] T4 anyway** — flip `visionGpuSku="Consumption-GPU-NC8as-T4"` because the ~15s latency savings + peace of mind is worth $7/month
- **[ ] A100** — do not pick this

Default is already CPU-only, so "resolved: stay CPU" is a zero-code-change outcome that just requires closing this doc.

---

## Sources

- [Comparing GPU types in Azure Container Apps (MS Learn)](https://learn.microsoft.com/en-us/azure/container-apps/gpu-types)
- [Using serverless GPUs in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/gpu-serverless-overview)
- [Azure Container Apps pricing page](https://azure.microsoft.com/en-us/pricing/details/container-apps/)
- [Microsoft Q&A thread on ACA GPU billing](https://learn.microsoft.com/en-us/answers/questions/5823616/azure-container-app-consuption-profile-gpu-cost-ca)
- [NC4as_T4_v3 pricing reference (Vantage)](https://instances.vantage.sh/azure/vm/nc4ast4-v3)
- [NC8as_T4_v3 pricing reference (Vantage)](https://instances.vantage.sh/azure/vm/nc8ast4-v3)
