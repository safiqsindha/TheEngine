# D.1 — Controller Mapping
# The Cockpit | Team 2950 The Devastators
# Print this. Tape it to the driver station shelf.

---

## Driver Controller (Xbox, Port 0)

### Sticks — Always Active

| Input | Action | Notes |
|-------|--------|-------|
| Left Stick | Field-relative translation (X/Y) | Deadband: 0.1 |
| Right Stick X | Field-relative rotation | Deadband: 0.1 |

### Bumpers & Triggers — Every Cycle

| Input | Action | Why Here |
|-------|--------|----------|
| Right Bumper (hold) | Auto-align to AprilTag | Used every scoring approach — robot rotates, you keep driving |
| Left Bumper (hold) | Drive to nearest game piece | Used every collection — robot drives to fuel, you keep rotation |
| Left Trigger (>50%) | Manual aim + auto-feed | Flywheel aims at tag, RPM auto-adjusts by distance |

### D-Pad — Flywheel RPM Presets

| Input | RPM | Range |
|-------|-----|-------|
| D-Pad Right | 2400 | Close (< 1.1m) |
| D-Pad Down | 2500 | Medium-close |
| D-Pad Left | 3000 | Medium-far |
| D-Pad Up | 3500 | Far (> 2.5m) |

### Face Buttons

| Input | Action | Notes |
|-------|--------|-------|
| A | Zero gyro | Press when robot faces away from you. Resets "forward." |
| B (hold) | Vision check | LEDs blink blue = target visible, red = no target |
| X | Auto score sequence | Full pipeline: align → lock → spin → feed → done. 6s timeout. |
| Y (hold) | Lock wheels (X pattern) | Defense hold — robot resists pushing |

### Back Buttons

| Input | Action | Notes |
|-------|--------|-------|
| Back + Start | Reset to practice start pose | Simulation only — does nothing on real robot |

---

## Operator Controller (Xbox, Port 1)

Intake, conveyor, and climber are bound as default commands via the operator controller.
Check `RobotContainer.java` for exact bindings. The operator handles:
- Intake deploy/retract
- Conveyor feed direction
- Climber extend/retract
- Side claw control

---

## Muscle Memory Guide

### Priority 1 — Learn in first 5 sessions
These are every-cycle actions. If you have to think about which button, you're too slow.

1. **Left stick + Right bumper** = drive to target and auto-aim
2. **Left bumper** = drive to game piece
3. **Left trigger** = aim + shoot
4. **A** = zero gyro (do this at start of every match)

### Priority 2 — Learn by competition
5. **X** = one-button score (trust the automation)
6. **D-pad presets** = manual RPM when auto-feed isn't available
7. **Y** = wheel lock for defense

### Priority 3 — Know they exist
8. **B** = vision check LED
9. **Back + Start** = sim reset

---

## Distance-to-RPM Quick Reference

When using left trigger (auto-feed), the robot picks RPM automatically.
When using D-pad presets, use this guide:

```
Close range (touching zone):     D-Pad Right (2400)
1-2 meters from target:          D-Pad Down  (2500)
2-3 meters from target:          D-Pad Left  (3000)
3+ meters / far field:           D-Pad Up    (3500)
```

---

## Auto-Align Behavior

When you hold **Right Bumper**:
- Robot rotates to face the nearest AprilTag scoring target
- You keep full translation control (left stick still works)
- LEDs blink blue while aligning
- Release = immediate return to manual control
- Uses P-controller on Limelight tx offset (kP = 0.05)

When you hold **Left Bumper**:
- Robot drives toward the nearest YOLO-detected game piece
- You keep rotation control (right stick still works)
- Uses Pipeline 1 (neural detection) on the Limelight
- Release = immediate return to manual control

**Important:** The Limelight can only do one thing at a time. While using Left Bumper (game piece tracking), AprilTag tracking is paused. While using Right Bumper (AprilTag align), game piece detection is paused. The code switches pipelines automatically.

---

## Validation Checklist

After the driver memorizes the mapping, run this test during practice:

- [ ] Driver completes 5 full cycles without looking down at the controller
- [ ] Driver can zero gyro, score, and collect without verbal reminders
- [ ] Driver uses auto-align (RB) for every scoring approach
- [ ] Driver uses auto-drive (LB) for every collection approach
- [ ] Driver can wheel-lock (Y) to hold against defense
- [ ] Driver can switch between D-pad presets and auto-feed without hesitation

**Target: all boxes checked within 5 practice sessions.**

---

## Printable Card (cut along dotted line)

```
┌─────────────────────────────────────────────────────┐
│          TEAM 2950 — DRIVER CONTROLLER MAP          │
│─────────────────────────────────────────────────────│
│                                                     │
│  LEFT STICK    Translation (drive)                  │
│  RIGHT STICK   Rotation                             │
│                                                     │
│  RB (hold)     Auto-align to AprilTag               │
│  LB (hold)     Drive to game piece                  │
│  LT (>50%)     Aim + auto-feed                      │
│                                                     │
│  D-Right 2400  D-Down 2500  D-Left 3000  D-Up 3500 │
│                                                     │
│  A  Zero gyro    B  Vision check (LEDs)             │
│  X  Auto score   Y  Lock wheels                     │
│                                                     │
│  Back+Start    Reset pose (sim only)                │
└─────────────────────────────────────────────────────┘
```

---

*Source: `RobotContainer.java` in safiqsindha/2950-robot*
*File: `Constants.java` — OI.kDriverControllerPort = 0, OI.kOperatorControllerPort = 1*
*Last verified: April 8, 2026*
