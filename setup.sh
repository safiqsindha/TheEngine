#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# THE ENGINE — Environment Setup Script
# FRC Team 2950 | Run this ONCE on a fresh machine before opening Cursor.
# ═══════════════════════════════════════════════════════════════════════════════

set -e
echo "╔══════════════════════════════════════════════════════╗"
echo "║       THE ENGINE — Environment Setup                ║"
echo "║       FRC Team 2950 (The Devastators)               ║"
echo "╚══════════════════════════════════════════════════════╝"

# ── 1. Check prerequisites ──
echo ""
echo "[1/7] Checking prerequisites..."

command -v java >/dev/null 2>&1 || { echo "ERROR: Java not found. Install WPILib first: https://docs.wpilib.org"; exit 1; }
JAVA_VER=$(java -version 2>&1 | head -1 | cut -d'"' -f2 | cut -d'.' -f1)
if [ "$JAVA_VER" -lt 17 ]; then
    echo "ERROR: Java 17+ required, found Java $JAVA_VER"
    exit 1
fi
echo "  ✓ Java $JAVA_VER found"

command -v git >/dev/null 2>&1 || { echo "ERROR: Git not found. Install from https://git-scm.com"; exit 1; }
echo "  ✓ Git found"

# ── 2. Initialize git ──
echo ""
echo "[2/7] Initializing git repository..."
if [ ! -d ".git" ]; then
    git init
    git add -A
    git commit -m "[Setup] Initial scaffold from The Engine template"
    echo "  ✓ Git repo initialized with initial commit"
else
    echo "  ✓ Git repo already exists"
fi

# ── 3. Gradle wrapper ──
echo ""
echo "[3/7] Verifying Gradle wrapper..."
if [ -f "gradlew" ]; then
    chmod +x gradlew
    echo "  ✓ Gradle wrapper found and made executable"
else
    echo "  WARNING: No gradlew found. Run 'gradle wrapper' or copy from a WPILib project."
fi

# ── 4. Install vendordeps ──
echo ""
echo "[4/7] Installing vendordeps..."
mkdir -p vendordeps

VENDORDEPS=(
    "https://broncbotz3481.github.io/YAGSL-Lib/yagsl/yagsl.json"
    "https://software-metadata.revrobotics.com/REVLib-2026.json"
    "https://maven.ctr-electronics.com/release/com/ctre/phoenix6/latest/Phoenix6-frc2026-latest.json"
    "https://github.com/Mechanical-Advantage/AdvantageKit/releases/latest/download/AdvantageKit.json"
    "https://sleipnirgroup.github.io/ChoreoLib/dep/ChoreoLib.json"
)

for url in "${VENDORDEPS[@]}"; do
    filename=$(basename "$url")
    echo "  Downloading $filename..."
    if curl -fsSL "$url" -o "vendordeps/$filename" 2>/dev/null; then
        echo "    ✓ $filename downloaded"
    else
        echo "    ✗ FAILED to download $filename from $url"
        echo "      You may need to download this manually."
    fi
done

# ── 5. Build (downloads all Gradle dependencies) ──
echo ""
echo "[5/7] Running first build (this downloads all dependencies — may take 2-5 min)..."
if ./gradlew build --no-daemon 2>&1; then
    echo "  ✓ Build successful!"
else
    echo ""
    echo "  ✗ Build failed. Common fixes:"
    echo "    - Check internet connection (Gradle needs to download dependencies)"
    echo "    - Verify WPILib 2026 is installed"
    echo "    - Check vendordeps/ directory has all JSON files"
    echo "    - Run './gradlew build --stacktrace' for detailed error"
fi

# ── 6. Verify simulation launches ──
echo ""
echo "[6/7] Verifying simulation can launch..."
echo "  (Skipping — run './gradlew simulateJava' manually to test)"
echo "  ✓ Skipped (manual step)"

# ── 7. Summary ──
echo ""
echo "[7/7] Setup complete!"
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║ NEXT STEPS:                                         ║"
echo "║                                                     ║"
echo "║ 1. Answer HARDWARE_QUESTIONNAIRE.md                 ║"
echo "║    (gear ratio, gyro type, CAN IDs, chassis dims)   ║"
echo "║                                                     ║"
echo "║ 2. Open project in Cursor IDE                       ║"
echo "║                                                     ║"
echo "║ 3. Read ARCHITECTURE.md (Cursor should read this    ║"
echo "║    before generating any code)                      ║"
echo "║                                                     ║"
echo "║ 4. Start Phase 1 Block 1:                           ║"
echo "║    'As Validation & Safety, run ./gradlew build      ║"
echo "║     and confirm zero errors.'                       ║"
echo "║                                                     ║"
echo "║ 5. Follow prompts in CURSOR_PROMPTS.md              ║"
echo "╚══════════════════════════════════════════════════════╝"
