# THE ENGINE — Electrical Systems Standards & Efficiency
# Codename: "The Grid"
# Target: Ready before 2027 season
# Team 2950 — The Devastators
# ═══════════════════════════════════════════════════════════════════

## Overview

Six systems that transform electrical from the team's bottleneck into
a strength. Pre-built harnesses cut wiring from 2 days to 2 hours.
Standards documents let any student wire correctly without asking.
Inspection checklists catch problems before matches, not during them.

Total investment: 18 hours. ROI: saves 20+ hours per season in
debugging, rewiring, and competition downtime.

---

## E.1: Wiring Standards Card (2 hours)
**Target:** Build now, laminate, post in electrical station

| Function | Gauge | Color | Connector | Breaker |
|----------|-------|-------|-----------|---------|
| Drive motors (SPARK MAX) | 10 AWG | Red/Black | Ring terminal → PDH | 40A |
| Mechanism motors | 12 AWG | Red/Black | Ring terminal → PDH | 30-40A |
| Device/aux power | 18 AWG | Red/Black | Wago inline | 20A |
| CAN bus | 22 AWG twisted | Yellow/Green | Dual lever nut | N/A |
| Sensor signal | 24 AWG | Varies | JST or DuPont | N/A |
| LED strips | 18 AWG | Varies | Wago inline | 20A |
| Radio power | 18 AWG | Red/Black | PoE or barrel jack | 20A |
| Main battery | 6 AWG | Red/Black | Anderson SB50 | Main 120A |

Source: Adapted from 3847 Spectrum 2026 build blog electrical standards.

Additional rules (from Spectrum):
- Kraken ring terminals direct to PDH
- Inline Wagos for power distribution
- Dual lever nuts for CAN and signal wires (2-port for swerve, 3-port for LEDs/sensors)
- 8-port Ethernet switch with slim cables
- Power regulator instead of barrel jack for radio
- Thermal pad behind radio for heat dissipation
- Mount radio above bumpers, 6+ inches from motors

---

## E.2: CAN Bus Topology Map (3 hours)
**Target:** After robot design finalized, update each season

Visual diagram showing:
- Every CAN device (ID, type, physical location on robot)
- Daisy-chain wiring order (which device connects to which)
- Physical wire routing path on a top-down robot diagram
- Termination resistor location (120 ohm, end of chain)

Print poster-size, hang in pit. When a device drops offline:
1. Find it on the map
2. Identify the devices immediately before and after in the chain
3. Check the physical connection between them
4. Fix in minutes, not hours

Extends existing CAN_ID_REFERENCE.md with physical routing.

---

## E.3: Pre-Built Wiring Harnesses (8 hours)
**Target:** Offseason, after frame dimensions are locked

Build during offseason, install on new robot in minutes:

| Harness | From → To | Qty | Build Time | Install Time |
|---------|-----------|-----|-----------|-------------|
| Swerve module | PDH → SPARK MAX pair | 4 | 30 min each | 5 min each |
| CAN backbone | roboRIO → all devices | 1 | 60 min | 15 min |
| Limelight power+data | PDH+switch → mount | 2 | 20 min each | 5 min each |
| Radio power | PDH/VRM → radio mount | 1 | 15 min | 2 min |
| Battery leads | Battery → breaker → PDH | 1 | 15 min | 2 min |
| LED strips | PDH → roboRIO → strips | 1 | 30 min | 10 min |

Each harness:
- Cut to measured length for your frame size
- Both ends pre-terminated (crimped, soldered, or Wago'd)
- Labeled with heat-shrink labels (e.g., "FL-DRIVE", "CAN-3")
- Tested with multimeter before storage
- Stored coiled with twist ties in labeled bags

The swerve harnesses (4) never change because your frame corners
are always the same. That's 4 harnesses you build ONCE and reuse
every season.

---

## E.4: PDH Slot Assignment Template (1 hour)
**Target:** Build now, update on kickoff day

| Slot | Breaker | Assignment | Harness Label |
|------|---------|-----------|--------------|
| 0 | 40A | Drive FL | DRIVE-FL |
| 1 | 40A | Drive FR | DRIVE-FR |
| 2 | 40A | Drive BL | DRIVE-BL |
| 3 | 40A | Drive BR | DRIVE-BR |
| 4 | 40A | Steer FL | STEER-FL |
| 5 | 40A | Steer FR | STEER-FR |
| 6 | 40A | Steer BL | STEER-BL |
| 7 | 40A | Steer BR | STEER-BR |
| 8-9 | 40A | Elevator (×2) | ELEV-L, ELEV-R |
| 10 | 30A | Intake roller | INTAKE-ROLL |
| 11 | 30A | Intake deploy | INTAKE-DEP |
| 12 | 30A | Scorer / shooter | SCORE |
| 13 | 30A | Climber | CLIMB |
| 14 | 20A | Limelight 1 | LL-1 |
| 15 | 20A | Limelight 2 | LL-2 |
| 16-19 | 20A | Spare / sensors / LEDs | SPARE-1 to SPARE-4 |

Slots 0-7 (drivetrain) are permanent. Slots 8-15 update on kickoff
day based on actual mechanism motor count. Having this template
means no slot conflicts and no last-minute rewiring.

---

## E.5: Electrical Inspection Checklist (2 hours)
**Target:** Before first 2027 event

Thorough inspection done at event load-in and after any major repair.
Takes 15 minutes. Catches problems before they cause match failures.

### Power System
- [ ] Battery voltage > 12.5V (measured with multimeter)
- [ ] Battery connector zip-tied
- [ ] Main breaker NordLock washers torqued
- [ ] Main breaker shroud installed
- [ ] All Anderson connectors fully seated (push test each one)
- [ ] All PDH breakers seated and correct amperage

### CAN Bus
- [ ] Every CAN device responding (run PitCrewDiagnosticCommand)
- [ ] Termination resistor present (measure 60 ohm between CAN-H/L with everything on)
- [ ] All lever nuts fully latched (tug test every connection)
- [ ] No CAN wire chafing against sharp edges

### Motors
- [ ] Every motor spins freely in correct direction
- [ ] No unusual noise or vibration from any motor
- [ ] Motor wire connections secure (tug test ring terminals)

### Sensors & Vision
- [ ] Both Limelights booted and streaming
- [ ] Ethernet cables clicked in (both ends, both cameras)
- [ ] Gyro reading stable (not drifting while stationary)
- [ ] All encoder values updating on SmartDashboard

### Network
- [ ] Radio mounted above bumper line
- [ ] Radio 6+ inches from nearest motor
- [ ] Thermal pad behind radio confirmed
- [ ] Radio LED solid (not blinking)
- [ ] Ethernet switch all ports showing link

### Safety
- [ ] No exposed wire (all connections insulated)
- [ ] Wire routing clear of moving mechanisms
- [ ] E-stop button accessible and functional
- [ ] Battery securely strapped (metal buckle strap)

---

## E.6: Brownout Prevention Kit (2 hours to assemble)
**Target:** Before first 2027 event

A dedicated small toolbox/pouch with everything for electrical
diagnosis and repair at competition:

### Diagnostic Tools
- Multimeter (pre-set to DC voltage, keep spare 9V battery)
- CAN termination resistor (120 ohm, spare)
- Wire stripper (for 10-24 AWG)

### Spare Connectors
- Wago inline connectors (10)
- Dual lever nuts, 2-port (10)
- Dual lever nuts, 3-port (5)
- Pre-crimped ring terminals, 10 AWG (5)
- Pre-crimped ring terminals, 12 AWG (5)
- Anderson SB50 connector (1 spare)

### Spare Components
- 40A breakers (2 spare)
- 30A breakers (2 spare)
- 20A breakers (2 spare)
- Spare SPARK MAX (1, if budget allows)
- Spare CAN wire (3 ft, pre-twisted pair)

### Consumables
- Electrical tape (1 roll)
- Cable ties, small + medium (20 each)
- Heat shrink assortment (pre-cut)
- Zip ties for battery connector

### Reference
- Laminated wiring standards card (E.1)
- Laminated CAN topology map (E.2)
- Laminated PDH slot assignment (E.4)

When something breaks at competition, grab this kit. Everything
you need is in one place. No digging through a general toolbox.

---

## Integration with Other Engine Systems

| Electrical System | Connects To |
|------------------|-------------|
| E.2 CAN Map | PitCrewDiagnosticCommand (Phase 4.7) — auto-detects missing devices |
| E.4 PDH Template | Constants.java CAN IDs — must match slot assignments |
| E.5 Inspection | Pre-match checklist (P.2) — electrical subset |
| E.5 Inspection | Wear tracking (P.4) — electrical component cycle counts |
| All | Robot Reports (P.1) — log all electrical failures |

---

*Architecture document — The Grid | THE ENGINE | Team 2950 The Devastators*
