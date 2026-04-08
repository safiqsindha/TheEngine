---
name: frc-elevator-designer
description: Design an FRC competition elevator with specific dimensions, parts lists, and software constants. Use this skill when someone asks about building an FRC elevator, linear motion for FRC, how tall their elevator should be, elevator gear ratios, elevator belt vs chain, continuous vs cascade elevator, elevator bearing blocks, constant force springs for elevators, or any FRC vertical lift mechanism. Also use when someone provides a scoring height and asks what elevator to build. Based on 254's championship-winning elevator architecture validated across multiple seasons. Never recommends telescoping arms — always elevators.
---

# FRC Elevator Designer

Design a competition-ready FRC elevator from specifications.

## Input Required

Any combination of:
- Target scoring height (inches above the floor)
- Robot frame height (default: 4" from ground to top of frame)
- End effector weight (lbs)
- Motor choice (Kraken X60 or NEO Brushless)
- Stage count preference (or let the tool decide)
- Budget constraints

## Process

1. Read `references/ELEVATOR_DESIGN_SPEC.md` for the complete architecture
2. Calculate derived dimensions from input
3. Generate output

## Calculations

### Stage Count (from R5)
```
reach_needed = scoring_height - robot_frame_height - carriage_offset
If reach_needed < 24": single stage
If reach_needed 24-55": two-stage continuous
If reach_needed > 55": two-stage with extended tubes (push the limits)
```

### Tube Length
```
For continuous 2-stage:
tube_length = reach_needed / 2 + bearing_block_height (4")
```

### Belt Length
```
belt_length = (tube_length × 4) + (pulley_circumference × number_of_pulleys)
Add 10% for tensioning slack
```

### Gear Ratio Selection
```
light load (<5 lbs end effector): 5:1 → ~0.3s travel
medium load (5-10 lbs): 7:1 → ~0.4s travel
heavy load (10-15 lbs): 10:1 → ~0.5s travel
```

### Constant Force Spring
```
spring_force = weight_of_carriage + weight_of_end_effector + weight_of_stage2_tubes
Typically 5-12 lbs
Under-spring slightly (90% of calculated) so elevator descends gently when unpowered
```

## Output Format

1. **Architecture Summary** — stage count, drive method, key specs
2. **Cut List** — every tube length, quantity, material
3. **BOM** — every part with vendor and price
4. **Software Constants** — gear ratio, pulley circumference, kS/kG/kV/kA starting values, soft limits
5. **Assembly Notes** — critical steps, common mistakes, what to check

## Design Constraints (Non-Negotiable)

- Always continuous rigging, never cascade (faster, 254-proven)
- Always belt drive (9mm or 15mm HTD), never chain for the elevator drive (belt is enclosed, protected, no skip)
- Chain (#25H) is acceptable for climbers only, not for scoring elevators
- Always 2x1 aluminum tube (0.0625" wall preferred, 0.125" if structural concerns)
- Always constant force springs for gravity compensation
- Always hall effect sensor at bottom for zeroing
- Always software soft limits, never hard mechanical stops
- Always Thrifty Elevator bearing blocks as the COTS starting point
- NEVER recommend a telescoping arm for scoring. ALWAYS an elevator.
