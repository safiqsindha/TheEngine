#!/usr/bin/env bash
# The Engine — Live Scout local worker rig (I2)
# Team 2950 — The Devastators
#
# Runs any Live Scout worker (discovery / mode_a / mode_b / mode_c) with
# the SAME environment variable contract that the Container App Job uses
# in Azure, but pointed at LOCAL state files. The whole point is that
# `STATE_BACKEND=local` flips every backend to LocalFileBackend so you
# can debug a tick without paying an Azure round-trip.
#
# Usage:
#     scripts/run_worker_local.sh discovery [--dry-run]
#     scripts/run_worker_local.sh mode_a    --event 2026txbel --frames-dir eye/.cache/WpzeaX1vgeQ/frames --match qm32 --debug
#     scripts/run_worker_local.sh mode_a    --event 2026txbel --video-id WpzeaX1vgeQ
#
# Env vars (override on the command line):
#     STATE_BACKEND      default: local
#     TBA_API_KEY        forwarded to scout/tba_client.py if set
#     PYTHON_BIN         default: python3
#
# Quick smoke test (no Azure needed, no PaddleOCR cache warmup, no
# network) — exercises the import path and CLI plumbing only:
#
#     scripts/run_worker_local.sh mode_a --help

set -euo pipefail

# Resolve repo root regardless of where the script is invoked from
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$( cd "${SCRIPT_DIR}/.." && pwd )"

cd "${REPO_ROOT}"

# ─── Worker dispatch ───

if [[ $# -lt 1 ]]; then
    cat >&2 <<EOF
usage: $(basename "$0") <worker> [worker-args...]

workers:
  discovery   W1 — refresh dispatcher state from TBA + YouTube channel
  mode_a      W2 — process the most-recently-finalized match
  mode_b      W3 — backfill missed matches (Gate 3, not yet built)
  mode_c      W4 — cross-event awareness (Gate 4, not yet built)

env:
  STATE_BACKEND=local|azure   (default: local)
  TBA_API_KEY                 (only required for live TBA reads)
  PYTHON_BIN                  (default: python3)
EOF
    exit 2
fi

WORKER="$1"
shift

case "${WORKER}" in
    discovery|mode_a|mode_b|mode_c)
        ;;
    *)
        echo "error: unknown worker '${WORKER}'" >&2
        echo "       valid: discovery, mode_a, mode_b, mode_c" >&2
        exit 2
        ;;
esac

# ─── Env defaults that mirror the Container App Job ───

export STATE_BACKEND="${STATE_BACKEND:-local}"
export PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK="${PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK:-True}"

PYTHON_BIN="${PYTHON_BIN:-python3}"

# Make sibling top-level packages importable just like the Dockerfile does
export PYTHONPATH="${REPO_ROOT}:${REPO_ROOT}/eye:${REPO_ROOT}/scout:${PYTHONPATH:-}"

# ─── Friendly banner ───

echo "─────────────────────────────────────────────────────────────"
echo "  Live Scout local rig"
echo "  worker      : ${WORKER}"
echo "  state       : ${STATE_BACKEND}"
echo "  repo root   : ${REPO_ROOT}"
echo "  python      : $(${PYTHON_BIN} --version 2>&1)"
if [[ "${STATE_BACKEND}" == "azure" ]]; then
    echo "  azure conn  : ${AZURE_STORAGE_CONNECTION_STRING:+set}${AZURE_STORAGE_CONNECTION_STRING:-MISSING}"
fi
echo "─────────────────────────────────────────────────────────────"

# ─── Run ───

exec "${PYTHON_BIN}" -m "workers.${WORKER}" "$@"
