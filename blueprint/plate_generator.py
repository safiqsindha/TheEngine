#!/usr/bin/env python3
"""
The Blueprint — Custom Plate Generator (CAD Evolution P3)
Team 2950 — The Devastators

Generates the 2-3 custom plates per mechanism that don't exist as COTS.
These are simple rectangular plates with bolt holes derived from the COTS
parts they connect to.

Custom plates in FRC are almost always:
  - 1/8" or 1/4" aluminum (laser/waterjet cut)
  - Rectangular with bolt holes
  - Sometimes with lightening pockets for weight savings

This module generates FeatureScript for each custom plate, ready to
paste into an OnShape Part Studio.

Usage:
  from plate_generator import generate_mechanism_plates
  plates = generate_mechanism_plates(spec)
"""

import math
from dataclasses import dataclass, field, asdict
from typing import Optional


def _mm(inches: float) -> float:
    return round(inches * 25.4, 2)


# ═══════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════

@dataclass
class BoltHole:
    """A single bolt hole in a plate."""
    x_mm: float = 0.0
    y_mm: float = 0.0
    diameter_mm: float = 4.98     # #10-32 clearance
    thread: str = "#10-32"
    purpose: str = ""

    @property
    def radius_mm(self) -> float:
        return self.diameter_mm / 2


@dataclass
class Pocket:
    """A lightening pocket (material removal for weight savings)."""
    x_mm: float = 0.0
    y_mm: float = 0.0
    width_mm: float = 0.0
    height_mm: float = 0.0
    corner_radius_mm: float = 3.0


@dataclass
class CustomPlate:
    """A custom fabricated plate."""
    name: str = ""
    mechanism: str = ""
    width_mm: float = 0.0
    height_mm: float = 0.0
    thickness_mm: float = 3.175     # 1/8" default
    material: str = "6061 aluminum"
    bolt_holes: list = field(default_factory=list)
    pockets: list = field(default_factory=list)
    weight_lb: float = 0.0
    notes: str = ""
    quantity: int = 1               # most plates come in pairs (left/right)

    def compute_weight(self):
        """Compute plate weight (Al 6061 = 0.098 lb/in³)."""
        vol_in3 = (self.width_mm / 25.4) * (self.height_mm / 25.4) * (self.thickness_mm / 25.4)
        # Subtract bolt hole volumes
        for hole in self.bolt_holes:
            hole_vol = math.pi * (hole.radius_mm / 25.4) ** 2 * (self.thickness_mm / 25.4)
            vol_in3 -= hole_vol
        # Subtract pocket volumes
        for pocket in self.pockets:
            pocket_vol = ((pocket.width_mm / 25.4) * (pocket.height_mm / 25.4) *
                         (self.thickness_mm / 25.4) * 0.8)  # 80% depth pocket
            vol_in3 -= pocket_vol
        self.weight_lb = round(max(vol_in3 * 0.098, 0.01), 3)
        return self.weight_lb


# ═══════════════════════════════════════════════════════════════════
# BOLT PATTERNS FROM COTS PARTS
# ═══════════════════════════════════════════════════════════════════

# Standard FRC bolt patterns (derived from COTS catalog mounting data)
BOLT_PATTERNS = {
    "#10-32": 4.98,     # clearance hole diameter mm
    "1/4-20": 6.60,     # clearance hole diameter mm
    "M3": 3.40,
    "M4": 4.50,
    "8mm_bearing": 8.0,
    "1/2_hex_bearing": 12.7,    # for flanged bearing bore
}

# Thrifty elevator bearing block bolt pattern
THRIFTY_BEARING_BLOCK = {
    "bolt_spacing_mm": 38.1,    # center-to-center
    "bolt_diameter_mm": 4.98,   # #10-32
    "bearing_bore_mm": 12.7,    # 1/2" hex
}

# NEO motor face mount pattern
NEO_MOUNT = {
    "bolt_circle_mm": 43.18,    # 1.7" bolt circle diameter
    "bolt_count": 2,
    "bolt_diameter_mm": 4.50,   # M4
    "shaft_hole_mm": 10.0,
}

# Kraken/Falcon motor face mount
KRAKEN_MOUNT = {
    "bolt_circle_mm": 50.8,     # 2" bolt circle diameter
    "bolt_count": 4,
    "bolt_diameter_mm": 4.98,   # #10-32
    "shaft_hole_mm": 10.0,
}


def _bolt_circle(cx: float, cy: float, radius_mm: float,
                 count: int, diameter_mm: float, purpose: str,
                 start_angle_deg: float = 0) -> list[BoltHole]:
    """Generate bolt holes on a circular pattern."""
    holes = []
    for i in range(count):
        angle = math.radians(start_angle_deg + i * 360 / count)
        holes.append(BoltHole(
            x_mm=cx + radius_mm * math.cos(angle),
            y_mm=cy + radius_mm * math.sin(angle),
            diameter_mm=diameter_mm,
            purpose=purpose,
        ))
    return holes


def _bolt_grid(cx: float, cy: float, cols: int, rows: int,
               spacing_x_mm: float, spacing_y_mm: float,
               diameter_mm: float, purpose: str) -> list[BoltHole]:
    """Generate bolt holes on a rectangular grid."""
    holes = []
    x_start = cx - (cols - 1) * spacing_x_mm / 2
    y_start = cy - (rows - 1) * spacing_y_mm / 2
    for c in range(cols):
        for r in range(rows):
            holes.append(BoltHole(
                x_mm=x_start + c * spacing_x_mm,
                y_mm=y_start + r * spacing_y_mm,
                diameter_mm=diameter_mm,
                purpose=purpose,
            ))
    return holes


# ═══════════════════════════════════════════════════════════════════
# PLATE GENERATORS PER MECHANISM
# ═══════════════════════════════════════════════════════════════════

def generate_elevator_carriage(spec: dict) -> CustomPlate:
    """
    Elevator carriage plate — connects bearing blocks to end effector.

    Pattern:
    - 4x Thrifty bearing block bolt patterns (2 per side, for 2 rail pairs)
    - Center mounting holes for end effector (arm pivot or claw)
    - 1/4" aluminum for load bearing
    """
    elev = spec.get("elevator", {})
    travel = elev.get("travel_height_in", 48)

    # Plate size based on rail spacing
    rail_spacing_mm = 152.4  # 6" between rails (typical)
    plate_w = rail_spacing_mm + 80  # 80mm margin for bearing blocks
    plate_h = 150  # 6" tall for mounting

    plate = CustomPlate(
        name="elevator_carriage",
        mechanism="elevator",
        width_mm=plate_w,
        height_mm=plate_h,
        thickness_mm=6.35,  # 1/4"
        material="6061 aluminum",
        quantity=1,
        notes=f"Carriage for {travel}\" elevator. Mounts bearing blocks + end effector.",
    )

    # Bearing block bolt patterns (2 per side = 4 blocks)
    block_spacing_y = 100  # vertical spacing between upper/lower blocks
    for side in [-1, 1]:  # left and right rails
        cx = plate_w / 2 + side * rail_spacing_mm / 2
        for vert in [-1, 1]:  # upper and lower blocks
            cy = plate_h / 2 + vert * block_spacing_y / 2
            # 2 bolts per block
            plate.bolt_holes.extend(_bolt_grid(
                cx, cy, 1, 2,
                0, THRIFTY_BEARING_BLOCK["bolt_spacing_mm"],
                THRIFTY_BEARING_BLOCK["bolt_diameter_mm"],
                "bearing_block",
            ))

    # Center mounting holes for end effector
    plate.bolt_holes.extend(_bolt_grid(
        plate_w / 2, plate_h / 2, 2, 2,
        40, 40, 4.98, "end_effector_mount",
    ))

    # Lightening pocket in center
    if plate_w > 120 and plate_h > 120:
        plate.pockets.append(Pocket(
            x_mm=plate_w / 2, y_mm=plate_h / 2,
            width_mm=plate_w - 80, height_mm=plate_h - 80,
        ))

    plate.compute_weight()
    return plate


def generate_intake_side_plates(spec: dict) -> CustomPlate:
    """
    Intake side plates — mount roller bearings and deploy pivot.

    Pattern:
    - 2x bearing bores for roller shaft
    - 1x pivot bore for deploy shaft
    - Frame mounting bolt holes
    """
    intake = spec.get("intake", {})
    roller_count = intake.get("roller_count", 2)
    deploy = intake.get("deploy_type", "pivot") != "none"

    # Plate based on intake width and roller count
    plate_w = 100 + roller_count * 50  # grow with roller count
    plate_h = 120

    plate = CustomPlate(
        name="intake_side_plate",
        mechanism="intake",
        width_mm=plate_w,
        height_mm=plate_h,
        thickness_mm=3.175,  # 1/8"
        material="6061 aluminum",
        quantity=2,  # left + right pair
        notes=f"Intake side plates. {roller_count} rollers" + (", deploy pivot" if deploy else ""),
    )

    # Roller bearing bores
    roller_spacing = plate_w / (roller_count + 1)
    for i in range(roller_count):
        cx = roller_spacing * (i + 1)
        plate.bolt_holes.append(BoltHole(
            x_mm=cx, y_mm=plate_h * 0.6,
            diameter_mm=12.7,  # 1/2" hex bearing bore
            purpose="roller_bearing",
        ))

    # Deploy pivot bore (if deployed)
    if deploy:
        plate.bolt_holes.append(BoltHole(
            x_mm=plate_w * 0.1, y_mm=plate_h * 0.3,
            diameter_mm=12.7,  # 1/2" pivot shaft
            purpose="deploy_pivot",
        ))

    # Frame mounting holes (top edge)
    plate.bolt_holes.extend(_bolt_grid(
        plate_w / 2, plate_h * 0.9, 3, 1,
        30, 0, 4.98, "frame_mount",
    ))

    plate.compute_weight()
    return plate


def generate_shooter_plates(spec: dict) -> list[CustomPlate]:
    """
    Flywheel shooter plates — side plates + backplate.

    Pattern:
    - 2x side plates with flywheel bearing bores + motor mount
    - 1x backplate/hood for ball containment
    """
    flywheel = spec.get("flywheel", {})
    wheel_dia_mm = _mm(flywheel.get("wheel_diameter_in", 6.0))
    motor_count = flywheel.get("motor_count", 2)
    motor_type = flywheel.get("motor_type", "neo_vortex")

    plates = []

    # Side plates
    side_w = wheel_dia_mm + 60  # margin around wheel
    side_h = wheel_dia_mm + 80

    side_plate = CustomPlate(
        name="shooter_side_plate",
        mechanism="flywheel",
        width_mm=side_w,
        height_mm=side_h,
        thickness_mm=3.175,
        material="6061 aluminum",
        quantity=2,
        notes=f"Shooter side plates. {wheel_dia_mm:.0f}mm wheels, {motor_count} motors.",
    )

    # Flywheel bearing bore (center)
    side_plate.bolt_holes.append(BoltHole(
        x_mm=side_w / 2, y_mm=side_h / 2,
        diameter_mm=12.7,  # 1/2" hex bearing bore
        purpose="flywheel_bearing",
    ))

    # Motor mount pattern
    mount = KRAKEN_MOUNT if motor_type in ("kraken_x60", "falcon_500") else NEO_MOUNT
    motor_x = side_w / 2
    motor_y = side_h * 0.25
    side_plate.bolt_holes.extend(_bolt_circle(
        motor_x, motor_y,
        mount["bolt_circle_mm"] / 2,
        mount["bolt_count"],
        mount["bolt_diameter_mm"],
        "motor_mount",
    ))
    # Motor shaft hole
    side_plate.bolt_holes.append(BoltHole(
        x_mm=motor_x, y_mm=motor_y,
        diameter_mm=mount["shaft_hole_mm"],
        purpose="motor_shaft",
    ))

    # Frame mounting holes
    side_plate.bolt_holes.extend(_bolt_grid(
        side_w / 2, side_h * 0.9, 2, 1,
        40, 0, 4.98, "frame_mount",
    ))

    side_plate.compute_weight()
    plates.append(side_plate)

    # Backplate / hood
    hood_w = side_w
    hood_h = wheel_dia_mm * 0.6  # partial wrap around ball

    hood = CustomPlate(
        name="shooter_hood",
        mechanism="flywheel",
        width_mm=hood_w,
        height_mm=hood_h,
        thickness_mm=3.175,
        material="polycarbonate",
        quantity=1,
        notes="Shooter hood/backplate. Guides game piece into flywheel.",
    )

    # Bolt holes to attach to side plates
    hood.bolt_holes.extend(_bolt_grid(
        hood_w / 2, hood_h / 2, 2, 2,
        hood_w - 20, hood_h - 20, 4.98, "side_plate_mount",
    ))

    hood.compute_weight()
    plates.append(hood)

    return plates


def generate_climber_plates(spec: dict) -> CustomPlate:
    """
    Climber spool mount plate — holds spool, motor, and bearings.
    """
    climber = spec.get("climber", {})
    motor_type = climber.get("motor_type", "neo")

    plate = CustomPlate(
        name="climber_spool_plate",
        mechanism="climber",
        width_mm=100,
        height_mm=80,
        thickness_mm=6.35,  # 1/4" for load
        material="6061 aluminum",
        quantity=1,
        notes="Climber spool mount. Holds spool shaft + motor.",
    )

    # Spool bearing bore
    plate.bolt_holes.append(BoltHole(
        x_mm=50, y_mm=40,
        diameter_mm=12.7,  # 1/2" hex
        purpose="spool_bearing",
    ))

    # Motor mount
    mount = KRAKEN_MOUNT if motor_type in ("kraken_x60", "falcon_500") else NEO_MOUNT
    plate.bolt_holes.extend(_bolt_circle(
        50, 40, mount["bolt_circle_mm"] / 2,
        mount["bolt_count"], mount["bolt_diameter_mm"],
        "motor_mount",
    ))

    # Frame mounting
    plate.bolt_holes.extend(_bolt_grid(
        50, 10, 2, 1, 60, 0, 4.98, "frame_mount",
    ))

    plate.compute_weight()
    return plate


def generate_arm_pivot_plate(spec: dict) -> CustomPlate:
    """
    Arm pivot plate — mounts on elevator carriage or frame,
    holds arm pivot shaft bearings.
    """
    arm = spec.get("arm", {})
    motor_type = arm.get("motor_type", "neo_550")

    plate = CustomPlate(
        name="arm_pivot_plate",
        mechanism="arm",
        width_mm=80,
        height_mm=100,
        thickness_mm=6.35,  # 1/4"
        material="6061 aluminum",
        quantity=2,  # left + right
        notes="Arm pivot plates. Hold pivot shaft bearings + gearbox mount.",
    )

    # Pivot bearing bore
    plate.bolt_holes.append(BoltHole(
        x_mm=40, y_mm=60,
        diameter_mm=12.7,  # 1/2" hex
        purpose="pivot_bearing",
    ))

    # Gearbox/motor mount
    plate.bolt_holes.extend(_bolt_grid(
        40, 30, 2, 2, 30, 20,
        4.98, "gearbox_mount",
    ))

    # Mounting to carriage/frame
    plate.bolt_holes.extend(_bolt_grid(
        40, 90, 2, 1, 40, 0, 4.98, "carriage_mount",
    ))

    plate.compute_weight()
    return plate


# ═══════════════════════════════════════════════════════════════════
# MAIN GENERATOR
# ═══════════════════════════════════════════════════════════════════

def generate_mechanism_plates(spec: dict) -> list[CustomPlate]:
    """
    Generate all custom plates needed for the robot's mechanisms.
    Returns a list of CustomPlate objects.
    """
    plates = []

    if "elevator" in spec:
        plates.append(generate_elevator_carriage(spec))

    if "intake" in spec:
        plates.append(generate_intake_side_plates(spec))

    if "flywheel" in spec:
        plates.extend(generate_shooter_plates(spec))

    if "climber" in spec:
        plates.append(generate_climber_plates(spec))

    if "arm" in spec:
        plates.append(generate_arm_pivot_plate(spec))

    return plates


def plates_to_featurescript(plates: list[CustomPlate]) -> str:
    """Convert custom plates to FeatureScript geometry."""
    body = []

    for plate in plates:
        name = plate.name
        w = plate.width_mm
        h = plate.height_mm
        t = plate.thickness_mm

        # Create plate body
        body.append(f"        // {name} ({plate.mechanism}) — {plate.material}, {plate.quantity}x")
        body.append(f"        fCuboid(context, id + \"{name}\", {{")
        body.append(f"            \"corner1\" : vector(0, 0, 0) * millimeter,")
        body.append(f"            \"corner2\" : vector({w:.2f}, {h:.2f}, {t:.2f}) * millimeter")
        body.append(f"        }});")

        # Drill bolt holes
        for i, hole in enumerate(plate.bolt_holes):
            body.append(f"        // {name} bolt {i}: {hole.purpose}")
            body.append(f"        fCylinder(context, id + \"{name}_hole_{i}\", {{")
            body.append(f"            \"topCenter\" : vector({hole.x_mm:.2f}, {hole.y_mm:.2f}, {t + 1:.2f}) * millimeter,")
            body.append(f"            \"bottomCenter\" : vector({hole.x_mm:.2f}, {hole.y_mm:.2f}, -1) * millimeter,")
            body.append(f"            \"radius\" : {hole.radius_mm:.2f} * millimeter")
            body.append(f"        }});")
            body.append(f"        opBoolean(context, id + \"{name}_drill_{i}\", {{")
            body.append(f"            \"tools\" : qCreatedBy(id + \"{name}_hole_{i}\", EntityType.BODY),")
            body.append(f"            \"targets\" : qCreatedBy(id + \"{name}\", EntityType.BODY),")
            body.append(f"            \"operationType\" : BooleanOperationType.SUBTRACTION")
            body.append(f"        }});")

        # Cut lightening pockets
        for i, pocket in enumerate(plate.pockets):
            body.append(f"        // {name} pocket {i}: lightening")
            depth = t * 0.8  # 80% depth
            body.append(f"        fCuboid(context, id + \"{name}_pocket_{i}\", {{")
            body.append(f"            \"corner1\" : vector({pocket.x_mm - pocket.width_mm/2:.2f}, {pocket.y_mm - pocket.height_mm/2:.2f}, {t - depth:.2f}) * millimeter,")
            body.append(f"            \"corner2\" : vector({pocket.x_mm + pocket.width_mm/2:.2f}, {pocket.y_mm + pocket.height_mm/2:.2f}, {t + 1:.2f}) * millimeter")
            body.append(f"        }});")
            body.append(f"        opBoolean(context, id + \"{name}_pocket_cut_{i}\", {{")
            body.append(f"            \"tools\" : qCreatedBy(id + \"{name}_pocket_{i}\", EntityType.BODY),")
            body.append(f"            \"targets\" : qCreatedBy(id + \"{name}\", EntityType.BODY),")
            body.append(f"            \"operationType\" : BooleanOperationType.SUBTRACTION")
            body.append(f"        }});")

    return "\n".join(body)


def display_plates(plates: list[CustomPlate]):
    """Pretty-print custom plates summary."""
    total_weight = sum(p.weight_lb * p.quantity for p in plates)
    total_count = sum(p.quantity for p in plates)

    print(f"\n  CUSTOM PLATES ({total_count} pieces, {total_weight:.2f} lb total)")
    for p in plates:
        holes = len(p.bolt_holes)
        pockets = len(p.pockets)
        print(f"    {p.name:25s}  {p.width_mm:.0f}x{p.height_mm:.0f}x{p.thickness_mm:.1f}mm"
              f"  {p.material:20s}  {holes} holes  {p.weight_lb:.3f} lb x{p.quantity}")


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    if len(sys.argv) < 2:
        print("Usage: python3 plate_generator.py <blueprint_spec.json>")
        sys.exit(0)

    with open(sys.argv[1]) as f:
        spec = json.load(f)

    plates = generate_mechanism_plates(spec)
    display_plates(plates)

    # Generate FeatureScript
    fs_body = plates_to_featurescript(plates)
    print(f"\n  FeatureScript: {len(fs_body)} chars, {len(fs_body.splitlines())} lines")
