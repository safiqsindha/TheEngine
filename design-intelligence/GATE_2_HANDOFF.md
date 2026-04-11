# Live Scout Gate 2 — Azure handoff

This doc lists every manual step you (the human) need to do once you're
ready to actually run Live Scout in the cloud. Everything in this list
requires either an `az login` session, a GitHub repo Settings page, or
billing decisions — none of it can be automated by Claude without your
Azure credentials.

The code, tests, Dockerfile, Bicep template, GitHub Action, and local
dev rig are all already in the repo and exercised by the test suite.
The only thing left is wiring this repo to a real Azure subscription.

> **You can defer this entire doc until you actually need to run a
> cron in Azure.** Mode A runs locally today via `scripts/run_worker_local.sh`
> and that's enough to scout an event off your laptop.

---

## Acceptance criteria (LIVE_SCOUT_PHASE1_BUILD §Gate 2)

You're done with Gate 2 when:

1. `az containerapp job execution start --name <env>-mode-a` succeeds
2. The job execution shows up in the Azure portal with `Succeeded` state
3. The Storage Table `livescoutstate` has a `dispatcher/current` row
   updated within the last 15 minutes (proving discovery cron is running)
4. The Storage Blob `pick_board.json` updates after a finalized match
   (proving Mode A → pick_board state path is alive end-to-end)

---

## What's already done (no action needed)

- ✅ `workers/state_backend.py` — `LocalFileBackend` + `AzureTableBackend`
  + `AzureBlobBackend`, env-var-driven factory, 30 unit tests
- ✅ `workers/discovery.py` — migrated to use the backend, all 21 W1
  tests still pass
- ✅ `workers/Dockerfile` — multi-stage, PaddleOCR baked in, ffmpeg + libgl
  for cv2, model warmup at build time
- ✅ `workers/requirements.txt` — pinned runtime deps including
  `azure-data-tables` + `azure-storage-blob`
- ✅ `infra/bicep/main.bicep` — Storage Account + Tables + Blob container
  + Log Analytics + Container Apps Env + Container Registry + Container
  App Job × 2 (mode-a, discovery), wired to a single template parameter
  for environment name + image tag + TBA key
- ✅ `infra/bicep/parameters.dev.json` — example parameter file with
  Key Vault references for secrets (you'll fill in the Key Vault ID)
- ✅ `.github/workflows/mode-a-build.yml` — pytest → docker build → ACR
  push → optional Bicep deploy + smoke job. Manual-only trigger so it
  doesn't fire until you flip it on.
- ✅ `scripts/run_worker_local.sh` — local dev rig that runs any worker
  with the same env contract Azure uses, but pointed at local files

---

## §1 — Prepare Azure (one-time)

You need an Azure subscription with at least:

- Container Apps (jobs + environment)
- Container Registry (Basic SKU is fine, ~$5/month)
- Storage Account (Standard_LRS, ~$0.05/GB/month)
- Log Analytics workspace (PerGB, you control retention)

Estimated steady-state cost at 1-minute Mode A cron + 15-minute discovery
cron during a 2-day event weekend: ~$3-5 total. Outside of event
weekends, if you stop the schedule, the cost drops to just storage
($0.10/month).

### 1a. Pick names

Decide on a short environment name (3-20 chars, lowercase) — this
prefixes every resource. Suggested:

- `livescout-prod` for the real thing
- `livescout-dev` for testing

Pick a region close to where the FRC streams originate. For Texas
events, `eastus` or `southcentralus` are both fine.

### 1b. Create the resource group

```bash
RG=livescout-rg
LOC=eastus

az group create --name "$RG" --location "$LOC"
```

### 1c. Create a service principal for GitHub Actions

```bash
SUB_ID=$(az account show --query id -o tsv)

az ad sp create-for-rbac \
  --name "livescout-gha" \
  --role contributor \
  --scopes "/subscriptions/$SUB_ID/resourceGroups/$RG" \
  --sdk-auth
```

This prints a JSON blob. **Copy the entire blob** — you'll paste it
into the GitHub `AZURE_CREDENTIALS` secret in §2.

### 1d. (Optional) Use Key Vault for the TBA API key

If you want to keep the TBA key out of GitHub secrets, create a Key
Vault and put the key there:

```bash
KV_NAME=livescout-kv-$RANDOM

az keyvault create --name "$KV_NAME" --resource-group "$RG" --location "$LOC"
az keyvault secret set --vault-name "$KV_NAME" --name "tba-api-key" --value "$YOUR_TBA_KEY"
```

Then update `infra/bicep/parameters.dev.json` to reference the vault:

```json
{
  "tbaApiKey": {
    "reference": {
      "keyVault": { "id": "/subscriptions/<SUB_ID>/resourceGroups/<RG>/providers/Microsoft.KeyVault/vaults/<KV_NAME>" },
      "secretName": "tba-api-key"
    }
  }
}
```

Otherwise you can pass the TBA key as a plain GitHub secret in §2.

---

## §2 — Set GitHub repo secrets

Go to **Settings → Secrets and variables → Actions → New repository secret**
and add each of these:

| Secret name | Value | Required? |
|---|---|---|
| `AZURE_CREDENTIALS` | The full JSON from `az ad sp create-for-rbac --sdk-auth` in §1c | Yes |
| `AZURE_SUBSCRIPTION_ID` | Output of `az account show --query id -o tsv` | Yes |
| `AZURE_RESOURCE_GROUP` | The `$RG` value you used in §1b (e.g. `livescout-rg`) | Yes |
| `ACR_NAME` | The name of the registry the Bicep template will create. Pattern: `${env_name_no_dashes}acr` (e.g. `livescoutprodacr`) | Yes |
| `TBA_API_KEY` | Your Blue Alliance read API key (https://www.thebluealliance.com/account) | Yes |
| `ENVIRONMENT_NAME` | Override for `livescout-prod`. Optional. | No |

> **Why is `ACR_NAME` set in advance?** The first run of the workflow
> wants to push to the registry, but the registry is created by the
> Bicep template — chicken-and-egg. Either deploy the Bicep template
> ONCE manually first (see §3a) or comment out the build step on the
> first run, deploy, then re-enable the build.

---

## §3 — First deploy

### 3a. Deploy the Bicep template manually (creates the registry)

```bash
cd <repo>
az deployment group create \
  --resource-group "$RG" \
  --template-file infra/bicep/main.bicep \
  --parameters environmentName=livescout-prod \
               tbaApiKey="$YOUR_TBA_KEY" \
               imageTag=placeholder
```

This will fail at the Container App Job step because the
`mode-a-worker:placeholder` image doesn't exist yet. That's expected —
the Storage Account, Tables, Blob container, ACR, and Container Apps
Environment will all be created successfully. Note the registry login
server from the output.

### 3b. Trigger the GitHub Action

Go to **Actions → Live Scout — build & deploy Mode A → Run workflow**.

Set **deploy** to `true` on the first run. This will:

1. Run the live_scout pytest suite (~0.2s)
2. Build the worker image (~5 min on first run, ~30s subsequent)
3. Push to ACR
4. Re-deploy the Bicep template with the real image tag
5. Trigger one Mode A execution as a smoke test

Watch the run log — the smoke test step prints the `az containerapp
job execution list` command you can use to inspect what happened.

### 3c. Verify

```bash
# Did the smoke job run?
az containerapp job execution list \
  --name livescout-prod-mode-a \
  --resource-group "$RG" \
  --output table

# Did discovery write a dispatcher row?
az storage entity show \
  --table-name livescoutstate \
  --partition-key dispatcher \
  --row-key current \
  --connection-string "$(az storage account show-connection-string -g $RG -n livescoutprodsa -o tsv)"

# Did Mode A write to the pick board blob?
az storage blob download \
  --container-name livescoutstate \
  --name pick_board.json \
  --file /tmp/pick_board.json \
  --connection-string "$(az storage account show-connection-string -g $RG -n livescoutprodsa -o tsv)"

cat /tmp/pick_board.json | jq '.live_matches | keys'
```

---

## §4 — Gotchas / things to know

- **Image size**: PaddleOCR + paddlepaddle is ~400 MB compressed. First
  cron tick after a fresh deploy pulls the image once and caches it on
  the Container Apps Environment node. Subsequent ticks are fast.
- **Cold starts**: Container App Jobs spin up a fresh container for
  every execution. Cold start is ~10-15s. PaddleOCR model weights are
  baked into the image so they don't add to that.
- **Timeouts**: `replicaTimeout: 600` (10 min). If a single tick takes
  longer than this, the execution is killed and `Failed` shows up in
  the portal. Investigate by inspecting the logs in Log Analytics.
- **Cost protection**: when you're not at an event, set the schedule
  to `*/0 * * * *` (or just disable the job in the portal) to stop
  paying compute time. Storage cost is negligible.
- **Cron schedules in Bicep**: defaults are every 1 min for Mode A and
  every 15 min for discovery. Tune via `modeACronExpression` /
  `discoveryCronExpression` parameters before running `az deployment`.

---

## §5 — Local development (no Azure required)

The whole pipeline runs locally with `STATE_BACKEND=local`. This is
the default if you don't set the env var.

```bash
# Discovery — refresh dispatcher state from TBA + YouTube
scripts/run_worker_local.sh discovery --dry-run

# Mode A — process a specific cached match
scripts/run_worker_local.sh mode_a \
  --event 2026txdri \
  --match qm32 \
  --frames-dir eye/.cache/WpzeaX1vgeQ/frames \
  --debug

# Run the test suite (no PaddleOCR install required for tests)
python -m pytest tests/live_scout/
```

The local file backend writes to:

- Dispatcher state → `workers/.state/dispatcher.json`
- Pick board state → `~/.scout/state.json` (matches existing scout/ tooling)

---

## §6 — Switching from local to Azure (and back)

The same code path serves both. Flip via env var:

```bash
# Local mode (default)
STATE_BACKEND=local scripts/run_worker_local.sh mode_a --event 2026txbel

# Talk to real Azure resources from your laptop
export STATE_BACKEND=azure
export AZURE_STORAGE_CONNECTION_STRING="$(az storage account show-connection-string -g $RG -n livescoutprodsa -o tsv)"
export TBA_API_KEY="$YOUR_TBA_KEY"
scripts/run_worker_local.sh mode_a --event 2026txbel
```

Useful for debugging a production issue without re-deploying — same
code, same data, your local logs.

---

## §7 — Phase 2: TBA Trusted User registration

The U pipeline (eye/match_boundary.py + scout/tba_writer.py + workers/tba_uploader.py)
publishes post-match video links back to The Blue Alliance via TBA's
Trusted v1 API. This requires a human-completed registration step that
CANNOT be automated from inside The Engine.

### Prerequisites

1. **Team TBA account.** Sign into https://www.thebluealliance.com/ with
   the team's TBA account (the one that already administers Team 2950
   on TBA). If the team does not have a shared TBA account yet, create
   one using a shared mentor email — individual mentor accounts should
   not own trusted-API credentials.

2. **Request trusted access for an event.** Under Account → My Events,
   request trusted access for the specific event key(s) we plan to
   upload videos for (e.g. `2026txbel`). TBA staff approve these
   manually and grant access per event, not globally.

3. **Generate an auth_id + auth_secret pair.** Once trusted access is
   approved, the TBA UI exposes an "auth_id" (short integer-like
   identifier) and an "auth_secret" (long hex string). Copy both — the
   secret is only shown once. If it gets lost, regenerate from the
   same page.

### Store credentials in Key Vault

```bash
# Once per environment — name MUST match parameters.dev.json / parameters.prod.json
az keyvault secret set \
  --vault-name $KEYVAULT_NAME \
  --name tba-trusted-auth-id \
  --value "$TBA_TRUSTED_AUTH_ID"

az keyvault secret set \
  --vault-name $KEYVAULT_NAME \
  --name tba-trusted-auth-secret \
  --value "$TBA_TRUSTED_AUTH_SECRET"
```

Both secrets are referenced by `infra/bicep/main.bicep` via the
`@secure` params `tbaTrustedAuthId` and `tbaTrustedAuthSecret`.

### Dry-run until the secret lands

The Bicep template defaults `tbaUploaderDryRun=true`, and the worker
has a second env-driven guard via `TBA_UPLOADER_DRY_RUN`. Before real
credentials are in place, the uploader will iterate state, log every
match it *would* upload, and short-circuit the HTTP transport. This
means you can deploy the whole Phase 2 stack — including the uploader
cron job — without risking a bad POST to TBA.

When you're ready to go live:

```bash
# Flip dry-run off for the next deploy
az deployment group create \
  --resource-group $RG \
  --template-file infra/bicep/main.bicep \
  --parameters tbaUploaderDryRun=false environmentName=livescout-prod ...
```

### Debugging a failed upload

The uploader prints one of these status strings per match:

| status              | meaning                                              |
|---------------------|------------------------------------------------------|
| `processed`         | TBA accepted the POST (200 OK)                       |
| `already_uploaded`  | TBA said "already exists" (treated as success)       |
| `skipped_no_video`  | LiveMatch had no real YouTube id (frame dir only)    |
| `skipped_already_marked` | `tba_uploaded=True` was already on the record   |
| `error:http_400`    | Bad body or wrong match_key shape — do not retry     |
| `error:http_401`    | Auth fail — check auth_id/secret in Key Vault        |
| `error:http_403`    | Event not in your trusted scope — ask TBA staff      |
| `error:http_5xx`    | TBA transient — retried 3x, will retry next cron     |

When you see `error:http_401` or `error:http_403`, the uploader's
auth state is wrong. Regenerate the auth_secret on TBA, re-set the
Key Vault secret, and redeploy. The `tba_uploaded` flag is NOT set
on error paths, so matches are safe to re-upload on the next tick.

---

## §8 — Phase 2: Anthropic API key for the synthesis worker

The T3 synthesis worker (workers/synthesis_worker.py) calls the
Anthropic API for end-of-day strategic briefs. Register an Anthropic
API key under the team's account and drop it in Key Vault:

```bash
az keyvault secret set \
  --vault-name $KEYVAULT_NAME \
  --name anthropic-api-key \
  --value "$ANTHROPIC_API_KEY"
```

This is referenced by `infra/bicep/main.bicep` via the secure param
`anthropicApiKey`. Without it the synthesis-worker cron job still
deploys and runs, but every tick logs a missing-key error and exits
non-zero.

The model defaults to `claude-opus-4-6` (Bicep param
`synthesisAnthropicModel`). Override in `parameters.*.json` if you
need to point at a different snapshot.

---

## §9 — Phase 2: Vision worker model selection (V0a)

`eye/vision_yolo.py` ships with a `FakeYOLOModel` that returns empty
event lists for every frame. The Bicep template sets
`MODEL_NAME=fake` by default, so the vision-worker cron runs end-to-end
but no-ops. To switch to a real model:

1. Pick a Roboflow Universe FRC YOLO model (or train your own — see
   the Gemma+SAM3.1 auto-labeling backlog entry in
   LIVE_SCOUT_PHASE2_REMAINING.md §Off-season backlog).
2. Implement the loader in `eye/vision_yolo.py::_load_real_model`,
   replacing the `NotImplementedError` with a weights fetch and a
   wrapper that exposes `.infer(frame_path) -> list[VisionEvent]`.
3. Flip the Bicep param `visionModelName` from `"fake"` to the real
   model id, and if you need a GPU SKU, set `visionGpuSku` to the
   target Azure Container Apps SKU.
