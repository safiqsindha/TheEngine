# THE ENGINE — Elevator Design Specification
# Codename: "The Lift"
# Pre-Season Build Project: May-December 2026
# Target: Competition-ready configurable elevator for January 2027 kickoff
# Team 2950 — The Devastators
# ═══════════════════════════════════════════════════════════════════

## Design Philosophy

Build a 254-caliber elevator during the off-season that is ready to
install on any robot frame on kickoff day. The only parameters that
change per game are travel height, carriage mounting pattern, and
spring rate. Everything else is locked, tested, and proven before
the game is even announced.

Source: 254 binders (2019, 2022, 2023, 2025), 1323 2025 robot,
Thrifty Elevator bearing block geometry, WCP GreyT Cascade reference.

**Never build a telescoping arm. Always an elevator.**

---

## Architecture: 2-Stage Continuous Elevator

### Why Continuous Over Cascade

Cascade elevators move one stage at a time — stage 1 extends fully,
then stage 2 begins extending. The carriage doesn't move until stage 1
is done. This means half the travel happens at the end.

Continuous elevators move all stages simultaneously using a 2:1
rigging ratio. The carriage moves the entire time. For the same
motor power, continuous is faster because the carriage has constant
velocity throughout the travel, not zero-then-full.

254 uses continuous in every elevator they've built (2019, 2023, 2025).
The rigging is more complex but the speed advantage is significant.

### How Continuous Rigging Works

```
Motor → Gearbox → Drive Sprocket/Pulley

Belt/chain path (continuous 2:1):

  Fixed anchor point (robot frame)
  │
  ├── Belt goes UP inner rail of Stage 1
  │   │
  │   └── Over idler pulley at TOP of Stage 1
  │       │
  │       └── Belt goes DOWN to carriage (Stage 2)
  │           │
  │           └── Fixed anchor point (carriage)

When the motor turns:
  - Stage 1 rises at speed X
  - Stage 2 (carriage) rises at speed 2X (because the belt
    gives it 2:1 mechanical advantage)
  - Total carriage speed = Stage 1 speed + belt speed = 2X
  - Total travel = Stage 1 travel + Stage 2 travel
```

For a 48" total travel with 2 stages:
- Each stage travels ~24"
- Carriage moves 48" total
- At any moment, carriage velocity = 2× stage 1 velocity

---

## Specifications

### Structural

| Parameter | Value | Source/Reasoning |
|-----------|-------|-----------------|
| Tube profile | 2" × 1" rectangular | FRC standard, all vendors stock it |
| Wall thickness | 0.0625" (1/16") | 254 standard. Lightest available. Saves ~40% weight vs 0.125" |
| Material | 6061-T6 aluminum | Standard FRC aluminum |
| Stages | 2 (configurable to 1 if game needs <24" travel) | 254 uses 2-stage for any reach >24" |
| Stage 1 inner width | 2.0" (fits inside frame tubes if needed) | Nests inside frame uprights |
| Stage 2 inner width | 1.0" tube rides inside Stage 1 using bearing blocks | Standard continuous nesting |
| Total width of elevator assembly | ~5-6" (both rails + spacing) | Compact enough for center or side mount |
| Rail length (configurable) | 24"-36" per stage tube (total travel = 2× stage length) | Set on kickoff day from prediction engine |

### Drive System

| Parameter | Value | Source/Reasoning |
|-----------|-------|-----------------|
| Drive method | 9mm HTD3 timing belt | 254 standard. Belt inside tube = protected from damage |
| Why belt over chain | No stretch, no skip, enclosed, lighter, quieter | Chain (#25H) stretches and can skip under side loads |
| Belt path | Inside the 2x1 tubes, routed through slots | Protected from contact damage. 254's signature move |
| Drive pulley | 18T HTD3 on hex shaft at bottom of Stage 1 | Standard ratio |
| Idler pulleys | Flanged bearing idlers at direction changes | Maintain belt tension and routing |
| Belt tensioning | Adjustable idler position (slotted mounting holes) | Must be adjustable — belt stretches slightly over time |

### Motors & Gearbox

| Parameter | Value | Source/Reasoning |
|-----------|-------|-----------------|
| Motors | 2× Kraken X60 (preferred) OR 2× NEO Brushless | 254 uses Krakens. NEO works if budget constrained |
| Gearbox | Single-stage reduction, ~5:1 to 10:1 depending on load | Higher ratio = more torque, lower speed. Lower ratio = faster, less torque |
| Gearbox mounting | Bottom of Stage 1, fixed to robot frame | Weight stays low. Motor + gearbox = heaviest part of elevator |
| Gear ratio selection guide | See table below | |

| End Effector Weight | Recommended Ratio | Travel Speed (est.) |
|--------------------|--------------------|---------------------|
| Light (<5 lbs) — shooter, claw | 5:1 | ~0.3s for 48" travel |
| Medium (5-10 lbs) — wrist + claw | 7:1 | ~0.4s for 48" travel |
| Heavy (10-15 lbs) — wrist + roller + hopper | 10:1 | ~0.5s for 48" travel |

254's 2025 elevator: 2 Krakens, travels 52" in 0.3 seconds. That's
the benchmark. Target sub-0.5s for any configuration.

### Bearing Blocks

| Parameter | Value | Source/Reasoning |
|-----------|-------|-----------------|
| Type | Thrifty Elevator bearing blocks (starting point) | Best value, proven design, fits any 2x1 tube |
| Stage spacing | 0.5" horizontal between stages | Thrifty standard. Compact. |
| Bearings per block | 2× V-groove or delrin rollers | Low friction, self-aligning |
| Blocks per stage | 4 (2 top, 2 bottom of each moving stage) | Minimum for stability. 254 uses 4 per stage. |
| Vertical lost travel | 0" (Thrifty design eliminates dead travel) | Full tube length = full travel |
| Mounting | Bolt to tube ends with #10-32 hardware | Standard FRC hardware |

### Sensors & Control

| Parameter | Value | Source/Reasoning |
|-----------|-------|-----------------|
| Position sensing | Relative encoder on motor (Kraken built-in or NEO hall) | Primary position feedback |
| Home sensor | Hall effect sensor at bottom of travel | Zero position reference. 254 standard. |
| Zeroing | On enable, elevator slowly lowers until hall effect triggers | Auto-zero on every enable. Never assume position. |
| Soft limits | Software-enforced maximum and minimum extension | No hard mechanical stops. Saves weight and impact energy. |
| Control method | Motion profile (trapezoidal or S-curve) + feedforward + PID | Feedforward does 90% of the work. PID corrects the last 10%. |
| Feedforward components | kS (static friction) + kG (gravity) + kV (velocity) + kA (acceleration) | kG is the most important — it compensates for gravity pulling the elevator down |
| Position accuracy | ±0.5" at any height | Sufficient for all FRC scoring tasks |
| Update rate | 50Hz (20ms loop, standard FRC) | Standard WPILib periodic |

### Weight Assist: Constant Force Springs

| Parameter | Value | Source/Reasoning |
|-----------|-------|-----------------|
| Purpose | Offset the weight of the carriage + end effector so motors only handle acceleration, not gravity | 254 uses springs on every elevator. Without springs, motors fight gravity constantly = slower, hotter, higher current draw |
| Type | Constant force springs (NOT gas springs) | Constant force = same assist at any extension. Gas springs vary with extension. |
| Spring force | Equal to weight of carriage + end effector + Stage 2 tubes | If the spring perfectly offsets gravity, the motor sees zero load at constant velocity |
| Mounting | One spring per side, anchored to Stage 1 top, pulling Stage 2 upward | Symmetric loading prevents twisting |
| Selection | Measure carriage + mechanism weight → buy springs within 10% of that force | Slight under-spring is better than over-spring (elevator should fall gently when unpowered) |
| Source | WCP constant force springs (multiple force ratings available) | Standard FRC component |
| Adjustment | On kickoff day, swap springs to match actual end effector weight | Keep 3-4 different spring ratings in The Vault |

### Weight Budget

| Component | Estimated Weight |
|-----------|-----------------|
| Stage 1 tubes (2× 30" of 2x1x0.0625") | 1.2 lbs |
| Stage 2 tubes (2× 30" of 2x1x0.0625") | 1.2 lbs |
| Bearing blocks (8 total) | 1.6 lbs |
| Belt + pulleys + hardware | 0.8 lbs |
| Constant force springs (2) | 0.6 lbs |
| Gearbox + mounting plate | 1.5 lbs |
| Motors (2× Kraken X60) | 2.4 lbs |
| Carriage plate | 0.8 lbs |
| Hex shaft + bearings + spacers | 0.6 lbs |
| Fasteners + misc | 0.5 lbs |
| **TOTAL ELEVATOR (no end effector)** | **~11.2 lbs** |

254's target: elevator + end effector combined under 20 lbs. With
an 11.2 lb elevator, you have 8.8 lbs for the end effector. That's
plenty for a wrist + claw/roller mechanism.

---

## Configurable Parameters (Set on Kickoff Day)

These are the ONLY things that change per game:

| Parameter | How to Set | Time to Change |
|-----------|-----------|---------------|
| Total travel height | Cut tubes to length. Formula: tube_length = desired_travel / 2 + bearing_block_height | 1 hour (cut 4 tubes) |
| Gear ratio | Swap gearbox stage (pre-build 2-3 ratios during off-season) | 30 minutes |
| Constant force spring rate | Swap springs based on end effector weight | 15 minutes |
| Carriage mounting holes | Drill carriage plate for end effector bolt pattern | 1 hour |
| Soft limit values | Change 2 numbers in software constants file | 5 minutes |

**Total time to configure for new game: ~3 hours**

Compare to designing and building an elevator from scratch: 2-3 WEEKS.

---

## OnShape Configuration Setup

The elevator template in OnShape should have these Configurations:

```
Configuration Variables:
  TRAVEL_HEIGHT_IN     = 48     (range: 24 to 60)
  TUBE_WALL_IN         = 0.0625 (options: 0.0625, 0.125)
  MOTOR_TYPE           = "Kraken X60" (options: "Kraken X60", "NEO")
  GEAR_RATIO           = 7     (range: 5 to 12)
  BELT_WIDTH_MM        = 9     (options: 9, 15)
  CARRIAGE_WIDTH_IN    = 8     (range: 4 to 12)
  SPRING_FORCE_LBS     = 8     (range: 2 to 20)

Derived Dimensions (auto-calculated):
  TUBE_LENGTH          = TRAVEL_HEIGHT_IN / 2 + 4 (4" for bearing blocks)
  BELT_LENGTH          = f(TUBE_LENGTH, pulley_positions)
  FRAME_MOUNT_HEIGHT   = TUBE_LENGTH + 2 (clearance above frame)
```

---

## Build Schedule (Pre-Season)

### Phase 1: Study (May 2026) — 10 hours

- [ ] Download 254's 2025 Undertow CAD from their public release
- [ ] Measure every dimension of their elevator assembly
- [ ] Document: tube lengths, belt routing, bearing block positions, gearbox mounting, carriage geometry, spring mounting
- [ ] Download Thrifty Elevator CAD from OnShape
- [ ] Compare 254 bearing blocks to Thrifty bearing blocks — document differences
- [ ] Download WCP GreyT Cascade Elevator CAD for reference
- [ ] Read FRCDesign.org cascade elevator examples page
- [ ] Write a 1-page summary: "What we're stealing from 254 and what we're using from Thrifty"

### Phase 2: Design (June 2026) — 20 hours

- [ ] Create new OnShape document: "2950 Elevator Template v1"
- [ ] Model Stage 1 rails (2x1x0.0625" tube, configurable length)
- [ ] Model Stage 2 rails (nested inside Stage 1)
- [ ] Add Thrifty bearing blocks (derive from Thrifty OnShape CAD)
- [ ] Model continuous belt routing inside tubes
- [ ] Design belt slot in tube walls (CNC or drill + file)
- [ ] Model gearbox mounting plate at bottom
- [ ] Model carriage plate with configurable bolt pattern
- [ ] Add constant force spring mounting points
- [ ] Add hall effect sensor mount at bottom of travel
- [ ] Add all Configurations (height, motor, ratio, belt, carriage, spring)
- [ ] Test: set configuration to 24", verify model rebuilds correctly
- [ ] Test: set configuration to 48", verify model rebuilds correctly
- [ ] Test: set configuration to 60", verify model rebuilds correctly
- [ ] Export BOM for 48" configuration (default build)

### Phase 3: Build v1 (July 2026) — 20 hours

- [ ] Order materials (Thrifty bearing blocks, belt, pulleys, tube, springs, hardware)
- [ ] Order motors + gearbox if not already owned
- [ ] Cut 4 tubes to 28" (for 48" total travel — default test configuration)
- [ ] Cut belt slots in tubes (if using belt-inside-tube routing)
- [ ] Assemble Stage 1 on test stand (plywood base with uprights)
- [ ] Assemble Stage 2 inside Stage 1 with bearing blocks
- [ ] Route belt through tubes, over pulleys, attach to carriage and anchor
- [ ] Mount gearbox + motors at bottom
- [ ] Wire motors (CAN + power)
- [ ] Mount hall effect sensor
- [ ] Wire hall effect to roboRIO DIO port
- [ ] Write basic elevator subsystem in Java:
  - ElevatorSubsystem.java (position PID + feedforward)
  - ElevatorConstants.java (soft limits, kS, kG, kV, kA)
  - ZeroElevatorCommand.java (slow down until hall effect triggers)
  - MoveToPositionCommand.java (motion profile to target height)
- [ ] Bench test: power on, zero, move to 24", move to 48", move to 0"
- [ ] Celebrate — the elevator moves

### Phase 4: Test v1 (August 2026) — 10 hours

- [ ] Measure travel speed: time from 0" to 48" full extension
  - Target: <0.5 seconds
  - If >0.8 seconds: increase gear ratio or add motor
- [ ] Measure positional accuracy: command 24.0", measure actual with ruler
  - Target: ±0.5"
  - If >±1": tune PID gains
- [ ] Measure deflection under load: hang 10 lbs from carriage, extend to 48"
  - Measure horizontal deflection at top
  - Target: <0.25" deflection
  - If >0.5": bearing blocks are too loose or tubes are twisted
- [ ] Run 50 full-travel cycles (0→48→0 repeatedly)
  - Monitor motor temperature (should stay <60°C)
  - Listen for belt skip, grinding, or unusual noise
  - Check bearing block wear after 50 cycles
- [ ] Simulated defense test: while elevator is at 24", push sideways with 30 lbs force
  - Elevator should not skip, jam, or lose position
  - Belt-inside-tube should protect from this
- [ ] Document all measurements and issues in a test report

### Phase 5: Build v2 (September 2026) — 15 hours

Based on v1 test results, improve:

- [ ] If belt routing had issues → redesign tube slots, add guides
- [ ] If too slow → swap gearbox ratio, evaluate adding second motor
- [ ] If too heavy → switch to thinner carriage plate, lighter hardware
- [ ] If bearing blocks wore unevenly → shim or replace with tighter tolerances
- [ ] If springs were wrong force → order correct springs, test new balance
- [ ] If deflection was too high → add cross-bracing between rails
- [ ] Rebuild with improvements
- [ ] Re-run all Phase 4 tests on v2

### Phase 6: Competition Simulation (October 2026) — 10 hours

- [ ] Run 100+ full cycles (simulating a full competition day of 10 matches × 10 cycles)
- [ ] Run with actual estimated end effector weight (hang appropriate weight)
- [ ] Practice "hot swap" scenarios:
  - Change carriage plate mounting holes (simulate kickoff day)
  - Change spring force (simulate different end effector)
  - Change soft limits in code (simulate different game heights)
  - Time each change — target: all changes done in <3 hours total
- [ ] Run elevator for 30 minutes continuous cycling (thermal stress test)
- [ ] Drop test: command elevator to full height, cut power, verify controlled descent
  - Springs should allow gentle descent, not free-fall
  - If elevator crashes down: springs are too weak or motor braking is insufficient

### Phase 7: Lock & Document (November 2026) — 5 hours

- [ ] Finalize OnShape CAD with all v2 improvements
- [ ] Lock Configurations — verify all 3 height settings rebuild correctly
- [ ] Write assembly guide: "How to configure and build this elevator in 4 hours"
- [ ] Write integration guide: "How to mount this on a robot frame"
- [ ] Export final BOM with vendor links and prices
- [ ] Write software guide: "How to tune elevator gains for a new weight"
- [ ] Commit all Java code to TheEngine repo under /subsystems/elevator/
- [ ] Backup OnShape document (export STEP + drawings)

### Phase 8: Shelf (December 2026) — 0 hours

Elevator sits on shelf. All documentation is done. All spare parts
are in The Vault. Software is tested and committed.

On kickoff day in January 2027:
1. Prediction engine says "48 inch elevator needed"
2. Tubes are already cut to 28" from testing (or cut new tubes: 1 hour)
3. Carriage plate gets new holes drilled for end effector: 1 hour
4. Springs get swapped for actual end effector weight: 15 minutes
5. Soft limits get updated in code: 5 minutes
6. Elevator is installed on robot frame: 2 hours
7. **Total: 4 hours from kickoff to installed, tested elevator**

---

## Software Architecture

### ElevatorSubsystem.java

```java
// Key methods:
public void setTargetHeight(double heightInches)
  // Generates trapezoidal motion profile to target height
  // Uses feedforward (kS + kG + kV + kA) + PID correction

public double getCurrentHeight()
  // Reads motor encoder, converts rotations to inches
  // Uses gear ratio + pulley circumference for conversion

public boolean atTarget()
  // Returns true if within ±0.5" of target height

public void zero()
  // Slowly lowers elevator until hall effect triggers
  // Resets encoder to 0 at that position

public void holdPosition()
  // Maintains current position using kG feedforward + PID
  // This is what runs when no command is active
```

### Key Constants

```java
public static final double GEAR_RATIO = 7.0;
public static final double PULLEY_CIRCUMFERENCE_IN = 1.432 * Math.PI; // 18T HTD3
public static final double CONTINUOUS_RATIO = 2.0; // 2:1 for continuous rigging

// Feedforward gains (MUST be tuned on actual hardware)
public static final double kS = 0.12;  // Static friction compensation
public static final double kG = 0.35;  // Gravity compensation (MOST IMPORTANT)
public static final double kV = 0.10;  // Velocity feedforward
public static final double kA = 0.02;  // Acceleration feedforward

// Soft limits
public static final double MIN_HEIGHT_IN = 0.0;
public static final double MAX_HEIGHT_IN = 48.0; // CHANGE ON KICKOFF DAY

// Motion profile constraints
public static final double MAX_VELOCITY_IN_PER_SEC = 150.0;
public static final double MAX_ACCELERATION_IN_PER_SEC2 = 400.0;
```

### Tuning Procedure (Do Once on Hardware, Repeat When Weight Changes)

1. Set all gains to zero
2. Slowly increase kG until elevator holds position at any height without drifting
3. Verify: if you manually push elevator down 2", does it return? If yes, kG is close
4. Add small kS (0.05-0.2) — this compensates for friction in bearing blocks
5. Command a slow move (12 in/s). Increase kV until elevator tracks the profile
6. Command a fast move (full speed). Increase kA until acceleration is smooth
7. Add PID (start with P only) to eliminate steady-state position error
8. Test rapid up-down-up-down cycles. Verify no overshoot or oscillation.

---

## Failure Modes & Mitigations

| Failure | Cause | Mitigation |
|---------|-------|------------|
| Belt skip | Side load from defense, belt too loose | Belt inside tube (protected). Tension check before each match. |
| Belt break | Fatigue, sharp edge rubbing on belt | Deburr all tube edges. Inspect belt weekly. Carry spare belt. |
| Motor overheat | Running at high current for too long | Constant force springs reduce motor load. Monitor temp in code. |
| Bearing block wear | Grit between bearing and tube | Wipe tubes clean before each match. Carry spare bearing blocks. |
| Hall effect fails | Wire breaks, sensor dies | Carry spare sensor + wire. Zero manually via software button as backup. |
| Elevator won't lower | Code bug, belt jam | Soft limits must allow manual override. Spring force ensures gravity descent even without motor. |
| Tube bending | Excessive side load, thin wall | 0.0625" wall can bend. If this is an issue in v1, upgrade to 0.125" wall for outer stage only. |
| Carriage plate cracks | Fatigue at bolt holes, impact | Use 1/4" aluminum plate minimum. Round all hole edges. Inspect after each event. |

---

## Spare Parts to Stock in The Vault

| Item | Quantity | Why |
|------|----------|-----|
| 9mm HTD belt (correct length) | 2 | Belt is the #1 wear item |
| Thrifty Elevator bearing blocks | 1 spare set (4 blocks) | Bearing wear |
| Constant force springs (3 force ratings) | 2 each | Different end effector weights |
| Hall effect sensor + wire harness | 2 | Sensor is fragile |
| 2x1x0.0625" tube, 36" length | 2 | In case a tube bends |
| Hex shaft, 12" length | 1 | Drive shaft spare |
| HTD pulleys (18T) | 2 | Pulley spare |
| #10-32 hardware assortment | 50+ | Always running low on hardware |

---

*Elevator Design Specification | THE ENGINE | Team 2950 The Devastators*
*Pre-Season Build: May-December 2026 | Target: 4-hour kickoff day integration*
