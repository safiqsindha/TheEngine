#!/usr/bin/env bash
# Codespace first-time setup for The Engine.
# Runs once when the codespace is created.

set -euo pipefail

echo "=== Setting up The Engine ==="

# Install Python dependencies. Engine modules each have their own requirements
# files; install the union, ignoring missing files.
PIP_REQS=(
  "scout/requirements.txt"
  "eye/requirements.txt"
  "antenna/requirements.txt"
  "blueprint/requirements.txt"
  "requirements.txt"
)
for req in "${PIP_REQS[@]}"; do
  if [ -f "$req" ]; then
    echo ">> pip install -r $req"
    pip install --quiet -r "$req" || echo "   (some packages failed; continuing)"
  fi
done

# Always install the core deps the Engine needs even if no requirements.txt
pip install --quiet \
  anthropic \
  httpx \
  requests \
  python-dotenv \
  rich \
  fastapi \
  "uvicorn[standard]" \
  numpy

# Verify the proxy is reachable
if [ -n "${ANTHROPIC_BASE_URL:-}" ]; then
  echo ">> Checking proxy at $ANTHROPIC_BASE_URL"
  if curl -sf --max-time 5 "$ANTHROPIC_BASE_URL/health" > /dev/null; then
    echo "   proxy reachable ✓"
  else
    echo "   ⚠ proxy not reachable — some commands won't work until your mentor brings it back up"
  fi
fi

cat <<'EOF'

╔════════════════════════════════════════════════════════════════╗
║                  THE ENGINE — READY                            ║
╠════════════════════════════════════════════════════════════════╣
║                                                                ║
║  Default model:  claude-haiku-4-5 (cheap)                      ║
║  Daily budget:   $0.50                                         ║
║  Total budget:   $5.00                                         ║
║                                                                ║
║  Commands to try:                                              ║
║    python3 engine_budget.py        — see your remaining budget ║
║    python3 engine_advisor.py       — chat with the Engine      ║
║    python3 scout/the_scout.py      — fetch event data          ║
║    cat PLAYGROUND.md               — guided missions           ║
║                                                                ║
╚════════════════════════════════════════════════════════════════╝

EOF
