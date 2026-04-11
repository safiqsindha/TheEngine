#!/usr/bin/env bash
# The Engine — Live Scout T3 synthesis worker key provisioner
# Team 2950 — The Devastators
#
# One-shot helper that stores an Anthropic API key in Azure Key Vault
# under the exact secret name that infra/bicep/parameters.dev.json
# references (`anthropic-api-key`), then runs a live smoke test of the
# synthesis worker against that key to prove end-to-end wiring.
#
# This script is the "T3 prereq" step from LIVE_SCOUT_PHASE2_REMAINING.md
# §5. The human steps it replaces are:
#   1. `az keyvault secret set` (with the right name)
#   2. `az keyvault secret show` (to verify)
#   3. a manual smoke test invocation
#
# What this script will NOT do (cannot be automated):
#   - Create an Anthropic account for you
#   - Mint the API key (you do that at https://console.anthropic.com/)
#   - Pay the bill (you add payment at the Anthropic console)
#   - Create the Key Vault (it must already exist)
#
# Usage:
#     export KEYVAULT_NAME=livescout-dev-kv
#     export ANTHROPIC_API_KEY=sk-ant-api03-...
#     scripts/provision_anthropic_key.sh
#
#     # or pass both on the command line:
#     KEYVAULT_NAME=livescout-dev-kv ANTHROPIC_API_KEY=sk-ant-... scripts/provision_anthropic_key.sh
#
# Flags:
#     --skip-smoke-test   Store the secret and verify, but don't call Anthropic
#     --event 2026txbel   Override the default event key used in the smoke test
#     --our-team 2950     Override the default our_team for the smoke test
#     --debug             Print extra az CLI output
#
# Exit codes:
#     0  — secret stored, verified, and (unless --skip-smoke-test) smoke tested
#     1  — missing required inputs or az CLI not available
#     2  — secret set failed
#     3  — secret verify readback mismatched
#     4  — smoke test failed

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SECRET_NAME="anthropic-api-key"
DEFAULT_EVENT="2026txbel"
DEFAULT_OUR_TEAM="2950"

SKIP_SMOKE=0
EVENT="$DEFAULT_EVENT"
OUR_TEAM="$DEFAULT_OUR_TEAM"
DEBUG=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-smoke-test) SKIP_SMOKE=1; shift ;;
    --event)           EVENT="$2"; shift 2 ;;
    --our-team)        OUR_TEAM="$2"; shift 2 ;;
    --debug)           DEBUG=1; shift ;;
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

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  echo "  ANTHROPIC_API_KEY is not set." >&2
  echo "  Mint one at https://console.anthropic.com/ then:" >&2
  echo "    export ANTHROPIC_API_KEY=sk-ant-api03-..." >&2
  exit 1
fi

if [[ ! "$ANTHROPIC_API_KEY" =~ ^sk-ant- ]]; then
  echo "  WARNING: ANTHROPIC_API_KEY does not start with 'sk-ant-'." >&2
  echo "  Continuing anyway, but double-check you copied the right value." >&2
fi

AZ_VERBOSITY="none"
if [[ "$DEBUG" -eq 1 ]]; then AZ_VERBOSITY="info"; fi

# ─── Confirm target ───

echo "  ┌─ Anthropic key provisioning ──────────────────────────"
echo "  │ Key Vault   : $KEYVAULT_NAME"
echo "  │ Secret name : $SECRET_NAME"
echo "  │ Smoke test  : event=$EVENT team=$OUR_TEAM"
if [[ "$SKIP_SMOKE" -eq 1 ]]; then
  echo "  │               (skipped)"
fi
echo "  └────────────────────────────────────────────────────────"
echo
read -r -p "  Proceed? [y/N] " reply
if [[ ! "$reply" =~ ^[Yy]$ ]]; then
  echo "  Aborted."
  exit 0
fi

# ─── 1. Store the secret ───

echo
echo "  [1/3] Storing secret in Key Vault..."
if ! az keyvault secret set \
    --vault-name "$KEYVAULT_NAME" \
    --name "$SECRET_NAME" \
    --value "$ANTHROPIC_API_KEY" \
    --output none \
    --verbose 2>/dev/null; then
  echo "  ERROR: az keyvault secret set failed." >&2
  echo "  Most common causes:" >&2
  echo "    - You're not logged in:    run 'az login'" >&2
  echo "    - Wrong subscription:      run 'az account set --subscription <id>'" >&2
  echo "    - No vault permissions:    grant yourself 'Key Vault Secrets Officer' role" >&2
  echo "    - Wrong vault name:        run 'az keyvault list -o table' to find the right one" >&2
  exit 2
fi
echo "  [1/3] OK — secret stored."

# ─── 2. Verify the readback ───

echo
echo "  [2/3] Verifying readback..."
STORED_VALUE="$(
  az keyvault secret show \
    --vault-name "$KEYVAULT_NAME" \
    --name "$SECRET_NAME" \
    --query value -o tsv 2>/dev/null
)"

if [[ "$STORED_VALUE" != "$ANTHROPIC_API_KEY" ]]; then
  echo "  ERROR: readback value does not match what we wrote." >&2
  exit 3
fi
MASKED="${STORED_VALUE:0:15}...${STORED_VALUE: -4}"
echo "  [2/3] OK — readback matches ($MASKED)."

# ─── 3. Smoke test ───

if [[ "$SKIP_SMOKE" -eq 1 ]]; then
  echo
  echo "  [3/3] Skipped (--skip-smoke-test)."
  echo
  echo "  Done. The synthesis worker can now read anthropic-api-key from"
  echo "  $KEYVAULT_NAME when the Bicep deployment runs."
  exit 0
fi

echo
echo "  [3/3] Running local smoke test against synthesis_worker..."
echo "  (this makes one real Anthropic API call — it will cost a few cents)"
read -r -p "  Proceed with smoke test? [y/N] " reply
if [[ ! "$reply" =~ ^[Yy]$ ]]; then
  echo "  Smoke test skipped. Secret is stored and verified."
  exit 0
fi

cd "$REPO_ROOT"
ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
STATE_BACKEND=local \
python3 -m workers.synthesis_worker \
  --event "$EVENT" \
  --our-team "$OUR_TEAM" \
  --debug \
  || {
    echo "  ERROR: smoke test failed." >&2
    echo "  The secret is stored in Key Vault, but the synthesis worker" >&2
    echo "  could not complete a live Anthropic call. Common causes:" >&2
    echo "    - Key is valid but has no usage quota (add payment method)" >&2
    echo "    - State file has no teams data yet (run Mode A first)" >&2
    echo "    - Transient Anthropic 5xx — re-run the smoke test" >&2
    exit 4
  }

echo
echo "  [3/3] OK — smoke test passed."
echo
echo "  ┌─ DONE ─────────────────────────────────────────────────"
echo "  │ anthropic-api-key is live in $KEYVAULT_NAME."
echo "  │ Next deploy picks it up automatically via parameters.dev.json."
echo "  └────────────────────────────────────────────────────────"
