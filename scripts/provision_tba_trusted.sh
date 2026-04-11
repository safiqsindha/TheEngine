#!/usr/bin/env bash
# The Engine — Live Scout U pipeline (TBA uploader) credential provisioner
# Team 2950 — The Devastators
#
# One-shot helper that stores TBA Trusted v1 credentials in Azure Key
# Vault under the exact secret names that infra/bicep/parameters.dev.json
# references (`tba-trusted-auth-id` and `tba-trusted-auth-secret`), then
# runs workers/tba_uploader.py in --dry-run mode to verify the HMAC-MD5
# signing path is wired correctly before ever POSTing to TBA for real.
#
# This script is the "U prereq" step from LIVE_SCOUT_PHASE2_REMAINING.md
# §5. The human steps it CANNOT replace (because TBA staff must approve
# them manually and out-of-band) are:
#   1. Registering the team's TBA account
#   2. Requesting trusted access for your event key(s)
#   3. Waiting for TBA staff to approve (typically 1-3 days)
#   4. Generating the auth_id / auth_secret pair on TBA's Account page
#
# Once you have an approved auth_id + auth_secret, run this script to
# store them + verify. See GATE_2_HANDOFF.md §7 for the full registration
# walkthrough.
#
# Usage:
#     export KEYVAULT_NAME=livescout-dev-kv
#     export TBA_TRUSTED_AUTH_ID=42
#     export TBA_TRUSTED_AUTH_SECRET=deadbeef...
#     scripts/provision_tba_trusted.sh
#
# Flags:
#     --skip-dry-run     Store + verify, but don't run the uploader dry-run
#     --event 2026txbel  Event key used for the dry-run (default 2026txbel)
#     --debug            Print extra az CLI output
#
# Exit codes:
#     0  — secrets stored, verified, and (unless --skip-dry-run) dry-run OK
#     1  — missing required inputs or az CLI not available
#     2  — secret set failed
#     3  — secret verify readback mismatched
#     4  — dry-run uploader failed
#
# SAFETY:
# This script never writes to TBA. The dry-run uploader reads Live Scout
# state and logs what it WOULD POST, but the HTTP transport is short-
# circuited. Flipping `tbaUploaderDryRun=false` in parameters.dev.json
# is a separate deployment step you do AFTER you've reviewed the dry-run
# output.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
AUTH_ID_SECRET_NAME="tba-trusted-auth-id"
AUTH_SECRET_SECRET_NAME="tba-trusted-auth-secret"
DEFAULT_EVENT="2026txbel"

SKIP_DRY_RUN=0
EVENT="$DEFAULT_EVENT"
DEBUG=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-dry-run) SKIP_DRY_RUN=1; shift ;;
    --event)        EVENT="$2"; shift 2 ;;
    --debug)        DEBUG=1; shift ;;
    -h|--help)
      sed -n '1,40p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "  Unknown flag: $1" >&2
      echo "  Try --help" >&2
      exit 1
      ;;
  esac
done

# ─── Preflight ───

if ! command -v az >/dev/null 2>&1; then
  echo "  az CLI not found. Install with: brew install azure-cli" >&2
  exit 1
fi

if [[ -z "${KEYVAULT_NAME:-}" ]]; then
  echo "  KEYVAULT_NAME is not set." >&2
  echo "  Example:  export KEYVAULT_NAME=livescout-dev-kv" >&2
  exit 1
fi

if [[ -z "${TBA_TRUSTED_AUTH_ID:-}" ]]; then
  echo "  TBA_TRUSTED_AUTH_ID is not set." >&2
  echo "  This is a short integer-like identifier from TBA's Account page." >&2
  echo "  See GATE_2_HANDOFF.md §7 for the registration walkthrough." >&2
  exit 1
fi

if [[ -z "${TBA_TRUSTED_AUTH_SECRET:-}" ]]; then
  echo "  TBA_TRUSTED_AUTH_SECRET is not set." >&2
  echo "  This is the long hex string from TBA's Account page (only shown once)." >&2
  exit 1
fi

if (( ${#TBA_TRUSTED_AUTH_SECRET} < 16 )); then
  echo "  WARNING: TBA_TRUSTED_AUTH_SECRET is only ${#TBA_TRUSTED_AUTH_SECRET} chars." >&2
  echo "  TBA secrets are typically 40+ hex chars. Double-check you copied the full value." >&2
fi

# ─── Confirm target ───

MASKED_SECRET="${TBA_TRUSTED_AUTH_SECRET:0:4}...${TBA_TRUSTED_AUTH_SECRET: -4}"
echo "  ┌─ TBA Trusted provisioning ────────────────────────────"
echo "  │ Key Vault    : $KEYVAULT_NAME"
echo "  │ auth_id      : $TBA_TRUSTED_AUTH_ID"
echo "  │ auth_secret  : $MASKED_SECRET"
echo "  │ Dry-run test : event=$EVENT"
if [[ "$SKIP_DRY_RUN" -eq 1 ]]; then
  echo "  │                (skipped)"
fi
echo "  └────────────────────────────────────────────────────────"
echo
read -r -p "  Proceed? [y/N] " reply
if [[ ! "$reply" =~ ^[Yy]$ ]]; then
  echo "  Aborted."
  exit 0
fi

# ─── 1. Store both secrets ───

echo
echo "  [1/4] Storing auth_id in Key Vault..."
if ! az keyvault secret set \
    --vault-name "$KEYVAULT_NAME" \
    --name "$AUTH_ID_SECRET_NAME" \
    --value "$TBA_TRUSTED_AUTH_ID" \
    --output none 2>/dev/null; then
  echo "  ERROR: az keyvault secret set (auth_id) failed." >&2
  echo "  See the Anthropic provisioning script for common causes." >&2
  exit 2
fi
echo "  [1/4] OK — auth_id stored."

echo
echo "  [2/4] Storing auth_secret in Key Vault..."
if ! az keyvault secret set \
    --vault-name "$KEYVAULT_NAME" \
    --name "$AUTH_SECRET_SECRET_NAME" \
    --value "$TBA_TRUSTED_AUTH_SECRET" \
    --output none 2>/dev/null; then
  echo "  ERROR: az keyvault secret set (auth_secret) failed." >&2
  echo "  NOTE: auth_id WAS stored successfully — you may want to clean it up" >&2
  echo "  with: az keyvault secret delete --vault-name $KEYVAULT_NAME --name $AUTH_ID_SECRET_NAME" >&2
  exit 2
fi
echo "  [2/4] OK — auth_secret stored."

# ─── 3. Verify both readbacks ───

echo
echo "  [3/4] Verifying readbacks..."
STORED_ID="$(
  az keyvault secret show \
    --vault-name "$KEYVAULT_NAME" \
    --name "$AUTH_ID_SECRET_NAME" \
    --query value -o tsv 2>/dev/null
)"
STORED_SECRET="$(
  az keyvault secret show \
    --vault-name "$KEYVAULT_NAME" \
    --name "$AUTH_SECRET_SECRET_NAME" \
    --query value -o tsv 2>/dev/null
)"

if [[ "$STORED_ID" != "$TBA_TRUSTED_AUTH_ID" ]]; then
  echo "  ERROR: auth_id readback mismatched." >&2
  exit 3
fi
if [[ "$STORED_SECRET" != "$TBA_TRUSTED_AUTH_SECRET" ]]; then
  echo "  ERROR: auth_secret readback mismatched." >&2
  exit 3
fi
echo "  [3/4] OK — both readbacks match."

# ─── 4. Dry-run uploader ───

if [[ "$SKIP_DRY_RUN" -eq 1 ]]; then
  echo
  echo "  [4/4] Skipped (--skip-dry-run)."
  echo
  echo "  Done. Both secrets live in $KEYVAULT_NAME."
  echo "  Next deploy picks them up automatically via parameters.dev.json."
  echo
  echo "  REMINDER: tbaUploaderDryRun=true is still set in parameters.dev.json."
  echo "  When you're ready to actually POST videos to TBA:"
  echo "      az deployment group create ... --parameters tbaUploaderDryRun=false"
  exit 0
fi

echo
echo "  [4/4] Running workers.tba_uploader in --dry-run mode..."
echo "  (this will NOT POST to TBA — it just validates the signing path)"

cd "$REPO_ROOT"
TBA_TRUSTED_AUTH_ID="$TBA_TRUSTED_AUTH_ID" \
TBA_TRUSTED_AUTH_SECRET="$TBA_TRUSTED_AUTH_SECRET" \
TBA_UPLOADER_DRY_RUN=true \
STATE_BACKEND=local \
python3 -m workers.tba_uploader \
  --event "$EVENT" \
  --dry-run \
  --debug \
  || {
    echo "  ERROR: dry-run uploader failed." >&2
    echo "  Secrets ARE stored in Key Vault, but the local worker could" >&2
    echo "  not complete a dry-run tick. Common causes:" >&2
    echo "    - No live_matches in local state (run Mode A first)" >&2
    echo "    - TBA_TRUSTED_AUTH_SECRET is malformed (dry-run still validates signing)" >&2
    exit 4
  }

echo
echo "  [4/4] OK — dry-run completed without errors."
echo
echo "  ┌─ DONE ─────────────────────────────────────────────────"
echo "  │ Both TBA Trusted secrets are live in $KEYVAULT_NAME."
echo "  │ tbaUploaderDryRun=true is STILL set (safe default)."
echo "  │"
echo "  │ To flip to live posting when you're ready:"
echo "  │   az deployment group create \\"
echo "  │     --resource-group \$RG \\"
echo "  │     --template-file infra/bicep/main.bicep \\"
echo "  │     --parameters @infra/bicep/parameters.dev.json \\"
echo "  │     --parameters tbaUploaderDryRun=false"
echo "  └────────────────────────────────────────────────────────"
