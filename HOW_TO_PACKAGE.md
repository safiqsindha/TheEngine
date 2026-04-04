# How to Package The Engine for Sharing

Quick guide to bundle everything the programming mentor needs.

---

## Option 1: Share the Git Repo (Recommended)

If the mentor has git access, this is the cleanest approach:

```bash
cd ~/Desktop/The\ Engine/constructicon
git add -A
git commit -m "The Engine: complete Phase 1-5 codebase for mentor review"
git push origin main
```

Then share the GitHub/GitLab URL. They clone it and run:
```bash
JAVA_HOME=~/wpilib/2026/jdk ./gradlew check
```

That's it — 181 tests pass, code is formatted, everything works.

---

## Option 2: Zip the Whole Project

If git isn't an option:

```bash
cd ~/Desktop/The\ Engine

# Create a clean zip excluding build artifacts and IDE files
zip -r TheEngine_Constructicon.zip constructicon/ \
  -x "constructicon/.gradle/*" \
  -x "constructicon/build/*" \
  -x "constructicon/.idea/*" \
  -x "constructicon/*.iml" \
  -x "constructicon/.classpath" \
  -x "constructicon/.project" \
  -x "constructicon/.settings/*" \
  -x "constructicon/bin/*"
```

This produces a ~30-40 MB zip (the ONNX model is 10 MB of that).

---

## Option 3: Minimal "Read This First" Package

If you just want to share the documentation for a conversation before
handing over code:

```bash
cd ~/Desktop/The\ Engine/constructicon

# Just the docs
zip TheEngine_Docs.zip \
  MENTOR_BRIEFING.md \
  WHAT_WE_BUILT.md \
  PROGRESS.md \
  CAN_ID_REFERENCE.md \
  hardware_config.ini \
  design-intelligence/ARCHITECTURE.md \
  design-intelligence/AUTONOMOUS_DESIGN.md \
  design-intelligence/YOLO_TRAINING_GUIDE.md
```

This is <1 MB and gives the mentor full context without the code.

---

## What the Mentor Needs Installed

To build and test the code, the mentor needs:

| Tool | How to Get It |
|------|--------------|
| **WPILib 2026** | https://docs.wpilib.org — installs JDK, Gradle, VS Code, sim tools |
| **Git** | Comes with macOS/Linux; Windows: https://git-scm.com |

That's it. Everything else (YAGSL, AdvantageKit, Choreo, etc.) is pulled
automatically by Gradle on first build.

Optional but useful:
- **AdvantageScope** — For viewing robot logs (https://github.com/Mechanical-Advantage/AdvantageScope)
- **REV Hardware Client** — For flashing SPARK MAX CAN IDs
- **Limelight web UI** — For uploading the YOLO model (http://limelight.local:5801)

---

## Key Files to Point the Mentor To

Tell them to read in this order:

1. **`MENTOR_BRIEFING.md`** — Full technical overview (what changed, why, how)
2. **`PROGRESS.md`** — Phase-by-phase checklist of what's done vs. TODO
3. **`RobotContainer.java`** — All button bindings and auto chooser
4. **`Constants.java`** — Every tuning value

Then they can explore the code. Every feature has a matching test file.

---

## Verify It Works Before Sharing

Run this before packaging:

```bash
cd ~/Desktop/The\ Engine/constructicon
JAVA_HOME=~/wpilib/2026/jdk ./gradlew check
```

Expected output:
```
BUILD SUCCESSFUL
181 tests passed
```

If it fails, fix the issue before sharing. The build gates catch everything.
