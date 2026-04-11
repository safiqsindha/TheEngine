# D.2 — Dashboard Layout Design
# The Cockpit | Team 2950 The Devastators
# Configure Shuffleboard or Elastic Dashboard to match this spec.

---

## Core Principle

The driver should NEVER read text during a match. Everything mid-match is communicated through color, position, and size. Text is for pre-match setup and pit crew diagnostics.

---

## Screen Layout

```
┌───────────────────────────────────────────────────────────────────┐
│  1:47   │  ███ SCORING ███  │  12.4V  │  Cycles: 7  │  Avg: 4.8s│  TOP STRIP
├───────────────────────────────────────────────────────────────────┤
│                                                                   │
│                                                                   │
│                    DRIVER CAMERA FEED                              │  MAIN AREA
│                    (Limelight stream or USB fisheye)               │  (70-80%)
│                                                                   │
│                                                                   │
│   ┌────────────┐                           ┌────────────┐         │
│   │ AUTO MODE  │                           │  FLYWHEEL  │         │
│   │ Score+Leave│                           │  2800 RPM  │         │
│   └────────────┘                           │  ■■■■■■■□  │         │
│                                            └────────────┘         │
├───────────────────────────────────────────────────────────────────┤
│  CAN: 17/17  │  Gyro: 127°  │  Vision: 2 tags  │  Speed: 3.2 m/s│  BOTTOM STRIP
└───────────────────────────────────────────────────────────────────┘
```

---

## Top Strip — Glanceable Status

Always visible. Driver reads this peripherally without moving their eyes from the field.

| Widget | NT Key | Type | Size |
|--------|--------|------|------|
| Match Time | `FMSInfo/MatchTime` | Large number | 80pt font |
| Robot State | Custom (see State Colors below) | Color block | Full width bar |
| Battery Voltage | `RobotController/BatteryVoltage` | Number + color | Green >12V, Yellow >11V, Red <11V |
| Cycle Count | `CycleTracker/TotalCycles` | Number | 40pt font |
| Avg Cycle Time | `CycleTracker/AverageCycleTime` | Number (1 decimal) | 40pt font |

---

## State Colors

The robot state bar changes color based on the current superstructure state. The driver reads this with peripheral vision — no text needed during a match.

| State | Color | RGB | When |
|-------|-------|-----|------|
| IDLE | Dark gray | `#404040` | No game piece, not targeting |
| INTAKING | Blue pulse | `#2196F3` | Intake deployed, seeking game piece |
| HOLDING | Solid green | `#4CAF50` | Game piece acquired and secured |
| ALIGNING | Cyan pulse | `#00BCD4` | Auto-align active (RB held) |
| SCORING | Yellow pulse | `#FFEB3B` | Ejecting game piece |
| CLIMBING | Purple pulse | `#9C27B0` | Climber engaged |
| ERROR | Red flash | `#F44336` | Stall detected, CAN fault, or mechanism error |
| ENDGAME | Orange pulse | `#FF9800` | < 30 seconds remaining |

### Implementation
Publish state as a string to `SmartDashboard/RobotState`. In Shuffleboard, use a "Single Color Display" widget that maps string values to colors. Or use the LED strip on the robot (already implemented in `LEDs.java`).

---

## Main Area — Camera Feed

**80% of the screen.** This is what the driver sees most of the match.

### Camera Options (pick one)

| Option | Pros | Cons |
|--------|------|------|
| Limelight stream (`http://limelight.local:5800`) | Already on the robot, shows AprilTag overlays | Switches between pipelines |
| USB fisheye camera via CameraServer | Dedicated feed, always shows intake area | Extra camera + USB bandwidth |
| No camera (field-eyes only) | Zero latency, no screen distraction | Can't confirm game piece acquisition remotely |

**Recommended:** Start with the Limelight stream. If bandwidth is an issue or pipeline switching causes drops, add a dedicated USB camera later.

### Camera Mount Position
- Looking down at the intake from the robot's top frame rail
- Wide-angle / fisheye lens preferred
- Driver uses this to confirm: "Did we grab it?" without turning their head

---

## Flywheel Status Widget

Bottom-right of main area. Shows current flywheel state.

| State | Display |
|-------|---------|
| Off | Gray bar, "OFF" |
| Spinning up | Yellow bar filling, showing target RPM |
| Ready | Green bar full, "READY" |
| Firing | Green flash, "FIRING" |

**NT Keys:**
- `Flywheel/TargetRPM` — what we're aiming for
- `Flywheel/CurrentRPM` — actual speed
- `Flywheel/AtTarget` — boolean, true when within 10% of target

---

## Auto Selector

Visible only pre-match. Hidden or minimized once match starts.

| Widget | NT Key | Type |
|--------|--------|------|
| Auto Mode Chooser | `SmartDashboard/SendableChooser` | Combo box |

### Available Modes
- Leave Only (default)
- Leave Only (Raw)
- Shoot Only
- Score + Leave
- 2 Coral
- 3 Coral
- Full Autonomous

---

## Bottom Strip — Pit Crew Diagnostics

Useful for pit crew between matches. Driver ignores this during the match.

| Widget | NT Key | What It Shows |
|--------|--------|---------------|
| CAN Device Count | `Diagnostic/CANDeviceCount` | "17/17" = all good, anything less = problem |
| Gyro Heading | `Swerve/Heading` | Current heading in degrees |
| Vision Tags | `Vision/TagCount` | Number of AprilTags currently visible |
| Robot Speed | `Swerve/RobotSpeed` | Current speed in m/s |
| Module States | `Swerve/Module[0-3]/State` | Per-module health (optional, for debugging) |

---

## Pre-Match vs Match Mode

### Pre-Match (robot disabled)
- Auto selector visible and full-size
- All diagnostic widgets shown
- Camera feed at 50% size
- Full telemetry text visible

### Match Active (robot enabled)
- Auto selector hidden
- Camera feed maximized to 80%
- Only top strip + state color visible
- Bottom strip dims (still readable if needed)

### Post-Match (robot disabled after match)
- Cycle summary auto-displays:
  - Total cycles
  - Average cycle time
  - Best/worst cycle
  - Scoring accuracy %
  - Climb result

---

## Shuffleboard Setup Instructions

1. Open Shuffleboard on the driver station laptop
2. Connect to the robot (it auto-detects via NetworkTables)
3. Create a new tab called "MATCH"
4. Drag widgets from the NetworkTables tree into the positions described above
5. Right-click each widget to set size and display properties
6. Save the layout as `2950_match_layout.json`
7. Set Shuffleboard to load this layout on startup:
   - File → Preferences → Default Layout → select `2950_match_layout.json`

### Alternative: Elastic Dashboard
Elastic (https://github.com/Gold872/elastic-dashboard) supports custom CSS theming and is lighter weight than Shuffleboard. Same NT keys, better performance.

---

## NetworkTables Key Reference

All keys the dashboard reads, in one place:

```
FMSInfo/MatchTime              → match countdown
RobotController/BatteryVoltage → battery level
SmartDashboard/RobotState      → state color
SmartDashboard/SendableChooser → auto mode selector
Swerve/Heading                 → gyro heading
Swerve/RobotSpeed              → current speed
Flywheel/TargetRPM             → flywheel target
Flywheel/CurrentRPM            → flywheel actual
Flywheel/AtTarget              → ready boolean
Vision/TagCount                → visible AprilTags
Vision/HasTarget               → boolean
CycleTracker/TotalCycles       → cycle count
CycleTracker/AverageCycleTime  → avg cycle seconds
Diagnostic/CANDeviceCount      → CAN health
Diagnostic/Summary             → pit diagnostic result
```

---

*Last verified: April 8, 2026*
*Source: `RobotContainer.java`, `VisionSubsystem.java`, `Flywheel.java`, `LEDs.java`*
