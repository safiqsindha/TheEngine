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
