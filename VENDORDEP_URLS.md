# ═══════════════════════════════════════════════════════════════════════════════
# VENDORDEP INSTALLATION — Block 1
# ═══════════════════════════════════════════════════════════════════════════════
#
# Run these in your WPILib VS Code (Ctrl+Shift+P → "WPILib: Manage Vendor Libraries"
# → "Install new libraries (online)") OR use the Gradle CLI shown below.
#
# After installing all vendordeps, run: ./gradlew build
# This caches all Java libraries locally.
#
# ═══════════════════════════════════════════════════════════════════════════════

# ── YAGSL (Swerve kinematics) ──
# https://docs.yagsl.com
https://broncbotz3481.github.io/YAGSL-Lib/yagsl/yagsl.json

# ── AdvantageKit (Deterministic logging) ──
# https://github.com/Mechanical-Advantage/AdvantageKit
https://github.com/Mechanical-Advantage/AdvantageKit/releases/latest/download/AdvantageKit.json

# ── CTRE Phoenix 6 (Kraken X60, CANcoder, Pigeon 2.0, SignalLogger) ──
# https://v6.docs.ctr-electronics.com
https://maven.ctr-electronics.com/release/com/ctre/phoenix6/latest/Phoenix6-frc2026-latest.json

# ── ChoreoLib (Trajectory following) ──
# https://choreo.autos
https://lib.choreo.autos/dep/ChoreoLib2026.json

# ── REVLib (CONDITIONAL — only if REV hardware in BOM) ──
# https://docs.revrobotics.com
# https://software-metadata.revrobotics.com/REVLib-2026.json

# ═══════════════════════════════════════════════════════════════════════════════
# NOTES:
# ═══════════════════════════════════════════════════════════════════════════════
#
# 1. URCL is NOT installed. We use CTRE SignalLogger instead (comes with Phoenix 6).
# 2. PathPlannerLib is NOT installed. Choreo is the sole trajectory pipeline.
# 3. The vendordep URLs above are for WPILib 2026. If the season hasn't started
#    yet and 2026 vendordeps aren't published, use the 2025 equivalents and
#    update when 2026 versions are released.
# 4. YAGSL may require a specific WPILib version. Check docs.yagsl.com for
#    compatibility matrix.
# 5. After installing, vendordep JSON files will appear in the vendordeps/
#    directory of your project. Commit these to git.
#
# ═══════════════════════════════════════════════════════════════════════════════
# VERIFICATION CHECKLIST (Gate 1.1):
# ═══════════════════════════════════════════════════════════════════════════════
#
# [ ] ./gradlew build completes with zero errors
# [ ] vendordeps/ directory contains JSON files for each library
# [ ] Spotless auto-formats code on build (check for reformatted files)
# [ ] SpotBugs produces no medium-confidence findings
# [ ] Simulation launches: ./gradlew simulateJava
