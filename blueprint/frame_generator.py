"""
The Blueprint — Parametric Swerve Frame Generator (B.2)
Team 2950 — The Devastators

Generates a complete swerve drivebase specification from parameters:
  - Frame dimensions (length, width, height)
  - Tube stock (size, wall thickness, hole pattern)
  - Swerve module type (Thrifty, SDS MK4i, REV MAXSwerve, WCP X2i)
  - Electronics layout (PDH, RoboRIO, radio, battery)
  - Bellypan and cross-member placement

The output is a FrameSpec JSON that can be:
  1. Pushed to OnShape via the API to create a parametric assembly
  2. Exported as a cut list for manufacturing
  3. Fed into the Assembly Composer (B.6) for full robot generation

Usage:
  python3 frame_generator.py generate [--preset competition]
  python3 frame_generator.py generate --length 28 --width 28 --module thrifty
  python3 frame_generator.py cutlist <spec.json>
  python3 frame_generator.py create-onshape <spec.json>
"""

import json
import math
import sys
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).parent


# ═══════════════════════════════════════════════════════════════════
# SWERVE MODULE DEFINITIONS
# ═══════════════════════════════════════════════════════════════════

class SwerveModuleType(str, Enum):
    THRIFTY = "thrifty"
    SDS_MK4I = "sds_mk4i"
    SDS_MK4N = "sds_mk4n"
    REV_MAXSWERVE = "rev_maxswerve"
    WCP_X2I = "wcp_x2i"


# Module specs: mounting hole pattern, footprint, weight, wheel diameter
SWERVE_MODULES = {
    SwerveModuleType.THRIFTY: {
        "name": "Thrifty Swerve",
        "footprint_in": (3.75, 3.75),  # (length, width) of module base
        "mounting_hole_pattern_in": 2.0,  # bolt circle or square pattern
        "mounting_bolts": "#10-32",
        "wheel_diameter_in": 4.0,
        "height_in": 4.25,  # total height below frame
        "weight_lb": 2.8,
        "drive_ratio": 6.23,
        "steer_ratio": 25.0,
        "max_speed_fps": 14.5,
        "motor_type": "NEO",
        "controller_type": "SparkMax",
    },
    SwerveModuleType.SDS_MK4I: {
        "name": "SDS MK4i",
        "footprint_in": (3.75, 3.75),
        "mounting_hole_pattern_in": 2.625,
        "mounting_bolts": "#10-32",
        "wheel_diameter_in": 4.0,
        "height_in": 4.0,
        "weight_lb": 2.9,
        "drive_ratio": 6.75,  # L2 default
        "steer_ratio": 150.0 / 7.0,
        "max_speed_fps": 16.3,
        "motor_type": "NEO / Kraken",
        "controller_type": "SparkMax / TalonFX",
    },
    SwerveModuleType.SDS_MK4N: {
        "name": "SDS MK4n",
        "footprint_in": (3.75, 3.75),
        "mounting_hole_pattern_in": 2.625,
        "mounting_bolts": "#10-32",
        "wheel_diameter_in": 4.0,
        "height_in": 3.75,
        "weight_lb": 2.7,
        "drive_ratio": 6.75,
        "steer_ratio": 150.0 / 7.0,
        "max_speed_fps": 16.3,
        "motor_type": "NEO / Kraken",
        "controller_type": "SparkMax / TalonFX",
    },
    SwerveModuleType.REV_MAXSWERVE: {
        "name": "REV MAXSwerve",
        "footprint_in": (3.5, 3.5),
        "mounting_hole_pattern_in": 2.0,
        "mounting_bolts": "#10-32",
        "wheel_diameter_in": 3.0,
        "height_in": 3.5,
        "weight_lb": 2.5,
        "drive_ratio": 6.12,
        "steer_ratio": 9424.0 / 203.0,
        "max_speed_fps": 15.8,
        "motor_type": "NEO / NEO Vortex",
        "controller_type": "SparkMax / SparkFlex",
    },
    SwerveModuleType.WCP_X2I: {
        "name": "WCP SwerveX 2i",
        "footprint_in": (3.75, 3.75),
        "mounting_hole_pattern_in": 2.625,
        "mounting_bolts": "#10-32",
        "wheel_diameter_in": 4.0,
        "height_in": 4.0,
        "weight_lb": 3.1,
        "drive_ratio": 6.0,
        "steer_ratio": 25.0,
        "max_speed_fps": 17.0,
        "motor_type": "Kraken X60",
        "controller_type": "TalonFX",
    },
}


# ═══════════════════════════════════════════════════════════════════
# TUBE STOCK DEFINITIONS
# ═══════════════════════════════════════════════════════════════════

class TubeSize(str, Enum):
    ONE_BY_ONE = "1x1"
    TWO_BY_ONE = "2x1"
    TWO_BY_TWO = "2x2"


TUBE_STOCK = {
    TubeSize.ONE_BY_ONE: {
        "width_in": 1.0,
        "height_in": 1.0,
        "wall_in": 0.040,
        "hole_spacing_in": 0.5,
        "hole_diameter_in": 0.196,
        "weight_per_inch_lb": 0.054,
    },
    TubeSize.TWO_BY_ONE: {
        "width_in": 2.0,
        "height_in": 1.0,
        "wall_in": 0.040,
        "hole_spacing_in": 0.5,
        "hole_diameter_in": 0.196,
        "weight_per_inch_lb": 0.081,
    },
    TubeSize.TWO_BY_TWO: {
        "width_in": 2.0,
        "height_in": 2.0,
        "wall_in": 0.063,
        "hole_spacing_in": 0.5,
        "hole_diameter_in": 0.196,
        "weight_per_inch_lb": 0.139,
    },
}


# ═══════════════════════════════════════════════════════════════════
# ELECTRONICS FOOTPRINTS
# ═══════════════════════════════════════════════════════════════════

ELECTRONICS = {
    "pdh": {
        "name": "REV Power Distribution Hub",
        "footprint_in": (6.57, 4.88),
        "weight_lb": 0.94,
        "mounting": "#10-32",
        "placement": "center_rear",
    },
    "roborio": {
        "name": "RoboRIO 2",
        "footprint_in": (6.8, 5.5),
        "weight_lb": 0.84,
        "mounting": "#4-40",
        "placement": "center",
    },
    "radio": {
        "name": "Vivid Hosting Radio",
        "footprint_in": (5.5, 3.5),
        "weight_lb": 0.44,
        "mounting": "velcro",
        "placement": "top_accessible",
    },
    "battery": {
        "name": "FRC Battery",
        "footprint_in": (7.13, 3.03),
        "weight_lb": 12.5,
        "mounting": "battery_strap",
        "placement": "center_low",
    },
    "main_breaker": {
        "name": "120A Main Breaker",
        "footprint_in": (2.0, 1.5),
        "weight_lb": 0.22,
        "mounting": "1/4-20",
        "placement": "accessible_side",
    },
}


# ═══════════════════════════════════════════════════════════════════
# FRAME SPEC DATA CLASSES
# ═══════════════════════════════════════════════════════════════════

@dataclass
class TubeMember:
    """A single tube member in the frame."""
    name: str
    length_in: float
    tube_size: str  # "1x1", "2x1", etc
    position: tuple  # (x, y, z) in inches from frame origin (center bottom)
    orientation: str  # "x" (left-right), "y" (front-back), "z" (vertical)
    quantity: int = 1
    holes: int = 0  # number of lightening/mounting holes
    notes: str = ""


@dataclass
class ModulePlacement:
    """Position of a swerve module relative to frame center."""
    name: str  # "front_left", "front_right", etc
    position: tuple  # (x, y) in inches from frame center
    module_type: str


@dataclass
class ElectronicsPlacement:
    """Position of an electronics component on the bellypan."""
    name: str
    component: str  # key from ELECTRONICS dict
    position: tuple  # (x, y) in inches from frame center
    rotation_deg: float = 0


@dataclass
class FrameSpec:
    """Complete parametric frame specification."""
    # Metadata
    name: str = "2950 Swerve Frame"
    version: str = "1.0"
    generator: str = "The Blueprint B.2"

    # Overall dimensions (inches, outside-to-outside including bumpers)
    frame_length_in: float = 28.0
    frame_width_in: float = 28.0
    frame_height_in: float = 4.0  # tube height (usually 1-2 tube widths)
    bumper_thickness_in: float = 3.5

    # Tube stock
    perimeter_tube: str = "2x1"
    cross_tube: str = "1x1"
    tube_wall_in: float = 0.040

    # Swerve
    module_type: str = "thrifty"
    module_inset_in: float = 2.5  # how far module center is from frame edge

    # Bellypan
    bellypan: bool = True
    bellypan_material: str = "1/8 polycarbonate"
    bellypan_weight_lb: float = 0.0  # computed

    # Computed members
    tube_members: list = field(default_factory=list)
    module_placements: list = field(default_factory=list)
    electronics_placements: list = field(default_factory=list)
    cross_member_count: int = 0

    # Weight budget
    frame_weight_lb: float = 0.0
    module_weight_lb: float = 0.0
    electronics_weight_lb: float = 0.0
    total_weight_lb: float = 0.0

    # Manufacturing
    cut_list: list = field(default_factory=list)

    # Validation
    within_frame_perimeter: bool = True
    max_dimension_in: float = 0.0
    bumper_perimeter_in: float = 0.0


# ═══════════════════════════════════════════════════════════════════
# PRESETS
# ═══════════════════════════════════════════════════════════════════

PRESETS = {
    "competition": {
        "description": "Standard 28x28 competition frame (Team 2950 default)",
        "frame_length_in": 28.0,
        "frame_width_in": 28.0,
        "perimeter_tube": "2x1",
        "cross_tube": "1x1",
        "module_type": "thrifty",
        "module_inset_in": 2.5,
        "bellypan": True,
    },
    "compact": {
        "description": "Small 24x24 frame for tight field navigation",
        "frame_length_in": 24.0,
        "frame_width_in": 24.0,
        "perimeter_tube": "2x1",
        "cross_tube": "1x1",
        "module_type": "rev_maxswerve",
        "module_inset_in": 2.0,
        "bellypan": True,
    },
    "long": {
        "description": "Extended 32x28 frame for long-reach mechanisms",
        "frame_length_in": 32.0,
        "frame_width_in": 28.0,
        "perimeter_tube": "2x1",
        "cross_tube": "2x1",
        "module_type": "sds_mk4i",
        "module_inset_in": 2.75,
        "bellypan": True,
    },
    "everybot": {
        "description": "Simple 26x26 frame for Everybot-style builds",
        "frame_length_in": 26.0,
        "frame_width_in": 26.0,
        "perimeter_tube": "1x1",
        "cross_tube": "1x1",
        "module_type": "thrifty",
        "module_inset_in": 2.5,
        "bellypan": True,
    },
}


# ═══════════════════════════════════════════════════════════════════
# FRAME GENERATOR
# ═══════════════════════════════════════════════════════════════════

def generate_frame(
    frame_length_in: float = 28.0,
    frame_width_in: float = 28.0,
    perimeter_tube: str = "2x1",
    cross_tube: str = "1x1",
    module_type: str = "thrifty",
    module_inset_in: float = 2.5,
    bellypan: bool = True,
    name: str = "2950 Swerve Frame",
) -> FrameSpec:
    """
    Generate a complete parametric swerve frame specification.

    Args:
        frame_length_in: Outside-to-outside frame length (front to back)
        frame_width_in: Outside-to-outside frame width (left to right)
        perimeter_tube: Tube size for perimeter rails ("1x1", "2x1", "2x2")
        cross_tube: Tube size for cross members ("1x1", "2x1")
        module_type: Swerve module type (see SwerveModuleType enum)
        module_inset_in: Distance from frame edge to module center
        bellypan: Whether to include a bellypan
        name: Name for the frame spec

    Returns:
        Complete FrameSpec with all geometry, weight, and cut list computed.
    """
    spec = FrameSpec(name=name)
    spec.frame_length_in = frame_length_in
    spec.frame_width_in = frame_width_in
    spec.perimeter_tube = perimeter_tube
    spec.cross_tube = cross_tube
    spec.module_type = module_type
    spec.module_inset_in = module_inset_in
    spec.bellypan = bellypan

    peri_tube = TUBE_STOCK[TubeSize(perimeter_tube)]
    cross_tube_spec = TUBE_STOCK[TubeSize(cross_tube)]
    module = SWERVE_MODULES[SwerveModuleType(module_type)]

    # ── Validate frame perimeter ──
    max_dim = max(frame_length_in, frame_width_in)
    spec.max_dimension_in = max_dim
    spec.bumper_perimeter_in = 2 * (frame_length_in + frame_width_in)
    spec.within_frame_perimeter = max_dim <= 36  # FRC max frame perimeter rule

    # ── Perimeter tubes ──
    tube_width = peri_tube["width_in"]
    tube_height = peri_tube["height_in"]
    spec.frame_height_in = tube_height

    # Front and back rails (run left-right)
    front_back_length = frame_width_in - (2 * tube_width)  # subtract corners
    spec.tube_members.append(asdict(TubeMember(
        name="front_rail",
        length_in=front_back_length,
        tube_size=perimeter_tube,
        position=(0, frame_length_in / 2 - tube_width / 2, 0),
        orientation="x",
        quantity=1,
        holes=int(front_back_length / peri_tube["hole_spacing_in"]),
        notes="Front perimeter rail",
    )))
    spec.tube_members.append(asdict(TubeMember(
        name="back_rail",
        length_in=front_back_length,
        tube_size=perimeter_tube,
        position=(0, -(frame_length_in / 2 - tube_width / 2), 0),
        orientation="x",
        quantity=1,
        holes=int(front_back_length / peri_tube["hole_spacing_in"]),
        notes="Back perimeter rail",
    )))

    # Left and right rails (run front-back, full length including corners)
    side_length = frame_length_in
    spec.tube_members.append(asdict(TubeMember(
        name="left_rail",
        length_in=side_length,
        tube_size=perimeter_tube,
        position=(-(frame_width_in / 2 - tube_width / 2), 0, 0),
        orientation="y",
        quantity=1,
        holes=int(side_length / peri_tube["hole_spacing_in"]),
        notes="Left perimeter rail",
    )))
    spec.tube_members.append(asdict(TubeMember(
        name="right_rail",
        length_in=side_length,
        tube_size=perimeter_tube,
        position=(frame_width_in / 2 - tube_width / 2, 0, 0),
        orientation="y",
        quantity=1,
        holes=int(side_length / peri_tube["hole_spacing_in"]),
        notes="Right perimeter rail",
    )))

    # ── Cross members ──
    # Place cross members between module pairs and in the center
    inner_width = frame_width_in - (2 * tube_width)
    cross_length = inner_width

    # Front cross member (between front modules)
    front_cross_y = frame_length_in / 2 - module_inset_in
    spec.tube_members.append(asdict(TubeMember(
        name="front_cross",
        length_in=cross_length,
        tube_size=cross_tube,
        position=(0, front_cross_y, 0),
        orientation="x",
        quantity=1,
        holes=int(cross_length / cross_tube_spec["hole_spacing_in"]),
        notes="Front cross member (module support)",
    )))

    # Back cross member (between back modules)
    back_cross_y = -(frame_length_in / 2 - module_inset_in)
    spec.tube_members.append(asdict(TubeMember(
        name="back_cross",
        length_in=cross_length,
        tube_size=cross_tube,
        position=(0, back_cross_y, 0),
        orientation="x",
        quantity=1,
        holes=int(cross_length / cross_tube_spec["hole_spacing_in"]),
        notes="Back cross member (module support)",
    )))

    # Center cross member
    spec.tube_members.append(asdict(TubeMember(
        name="center_cross",
        length_in=cross_length,
        tube_size=cross_tube,
        position=(0, 0, 0),
        orientation="x",
        quantity=1,
        holes=int(cross_length / cross_tube_spec["hole_spacing_in"]),
        notes="Center cross member (electronics/battery support)",
    )))

    # Additional mid-span cross members for longer frames
    extra_crosses = 0
    if frame_length_in > 28:
        # Add cross members at 1/4 and 3/4 span
        quarter_y = frame_length_in / 4
        spec.tube_members.append(asdict(TubeMember(
            name="quarter_front_cross",
            length_in=cross_length,
            tube_size=cross_tube,
            position=(0, quarter_y / 2, 0),
            orientation="x",
            quantity=1,
            notes="Quarter-span cross member (stiffness)",
        )))
        spec.tube_members.append(asdict(TubeMember(
            name="quarter_back_cross",
            length_in=cross_length,
            tube_size=cross_tube,
            position=(0, -quarter_y / 2, 0),
            orientation="x",
            quantity=1,
            notes="Quarter-span cross member (stiffness)",
        )))
        extra_crosses = 2

    spec.cross_member_count = 3 + extra_crosses

    # ── Swerve module placements ──
    mx = frame_width_in / 2 - module_inset_in
    my = frame_length_in / 2 - module_inset_in

    spec.module_placements = [
        asdict(ModulePlacement("front_left", (-mx, my), module_type)),
        asdict(ModulePlacement("front_right", (mx, my), module_type)),
        asdict(ModulePlacement("back_left", (-mx, -my), module_type)),
        asdict(ModulePlacement("back_right", (mx, -my), module_type)),
    ]

    # Module center-to-center distances (for YAGSL config)
    module_spacing_x = 2 * mx
    module_spacing_y = 2 * my

    # ── Electronics placement ──
    spec.electronics_placements = [
        asdict(ElectronicsPlacement("battery", "battery", (0, -2), 0)),
        asdict(ElectronicsPlacement("pdh", "pdh", (0, -frame_length_in / 4), 0)),
        asdict(ElectronicsPlacement("roborio", "roborio", (0, frame_length_in / 6), 0)),
        asdict(ElectronicsPlacement("radio", "radio", (0, frame_length_in / 4), 0)),
        asdict(ElectronicsPlacement("main_breaker", "main_breaker",
                                     (frame_width_in / 4, 0), 0)),
    ]

    # ── Bellypan ──
    if bellypan:
        # 1/8" polycarbonate: ~0.0065 lb/in² (density 0.043 lb/in³ * 0.125" + 20% for mounting tabs)
        bellypan_area = (frame_length_in - 2 * tube_width) * (frame_width_in - 2 * tube_width)
        spec.bellypan_weight_lb = round(bellypan_area * 0.0065, 2)

    # ── Weight budget ──
    frame_weight = 0
    for member in spec.tube_members:
        tube_spec = TUBE_STOCK.get(TubeSize(member["tube_size"]))
        if tube_spec:
            frame_weight += member["length_in"] * tube_spec["weight_per_inch_lb"] * member["quantity"]

    spec.frame_weight_lb = round(frame_weight, 2)
    spec.module_weight_lb = round(4 * module["weight_lb"], 2)

    electronics_weight = sum(e["weight_lb"] for e in ELECTRONICS.values())
    spec.electronics_weight_lb = round(electronics_weight, 2)

    spec.total_weight_lb = round(
        spec.frame_weight_lb
        + spec.module_weight_lb
        + spec.electronics_weight_lb
        + spec.bellypan_weight_lb,
        2
    )

    # ── Cut list ──
    cuts = {}
    for member in spec.tube_members:
        key = f"{member['tube_size']} @ {member['length_in']:.2f}in"
        cuts[key] = cuts.get(key, 0) + member["quantity"]

    spec.cut_list = [
        {"description": k, "quantity": v} for k, v in sorted(cuts.items())
    ]

    return spec


def generate_from_preset(preset_name: str) -> FrameSpec:
    """Generate a frame from a named preset."""
    if preset_name not in PRESETS:
        raise ValueError(f"Unknown preset '{preset_name}'. Available: {list(PRESETS.keys())}")
    params = {k: v for k, v in PRESETS[preset_name].items() if k != "description"}
    params["name"] = f"2950 {preset_name.title()} Frame"
    return generate_frame(**params)


# ═══════════════════════════════════════════════════════════════════
# OUTPUT FORMATTERS
# ═══════════════════════════════════════════════════════════════════

def print_summary(spec: FrameSpec):
    """Print a human-readable summary of the frame spec."""
    module = SWERVE_MODULES[SwerveModuleType(spec.module_type)]
    mx = spec.frame_width_in / 2 - spec.module_inset_in
    my = spec.frame_length_in / 2 - spec.module_inset_in

    print(f"\n{'═' * 60}")
    print(f"  {spec.name}")
    print(f"  Generated by {spec.generator}")
    print(f"{'═' * 60}")
    print(f"\n  DIMENSIONS")
    print(f"    Frame:          {spec.frame_length_in}\" x {spec.frame_width_in}\"")
    print(f"    With bumpers:   {spec.frame_length_in + 2*spec.bumper_thickness_in:.1f}\" x {spec.frame_width_in + 2*spec.bumper_thickness_in:.1f}\"")
    print(f"    Frame height:   {spec.frame_height_in}\"")
    print(f"    Perimeter:      {spec.bumper_perimeter_in}\" (max 120\")")
    print(f"    Within rules:   {'YES' if spec.within_frame_perimeter else 'NO — EXCEEDS MAX'}")

    print(f"\n  SWERVE MODULES")
    print(f"    Type:           {module['name']}")
    print(f"    Wheel:          {module['wheel_diameter_in']}\" diameter")
    print(f"    Drive ratio:    {module['drive_ratio']}:1")
    print(f"    Max speed:      {module['max_speed_fps']} ft/s")
    print(f"    Motors:         {module['motor_type']} + {module['controller_type']}")
    print(f"    Spacing:        {2*mx:.1f}\" x {2*my:.1f}\" (center-to-center)")

    print(f"\n  STRUCTURE")
    print(f"    Perimeter:      {spec.perimeter_tube} tube")
    print(f"    Cross members:  {spec.cross_member_count}x {spec.cross_tube} tube")
    print(f"    Bellypan:       {spec.bellypan_material if spec.bellypan else 'None'}")

    print(f"\n  WEIGHT BUDGET")
    print(f"    Frame tubes:    {spec.frame_weight_lb} lb")
    print(f"    Swerve modules: {spec.module_weight_lb} lb (4x {module['weight_lb']} lb)")
    print(f"    Electronics:    {spec.electronics_weight_lb} lb")
    print(f"    Bellypan:       {spec.bellypan_weight_lb} lb")
    print(f"    ─────────────────────────")
    print(f"    DRIVEBASE TOTAL: {spec.total_weight_lb} lb")
    print(f"    Remaining for mechanisms: {125 - spec.total_weight_lb:.1f} lb (of 125 lb limit)")

    print(f"\n  CUT LIST")
    for cut in spec.cut_list:
        print(f"    {cut['quantity']}x  {cut['description']}")

    print(f"\n  YAGSL CONFIG VALUES")
    print(f"    Module spacing X: {2*mx:.3f} inches ({2*mx*0.0254:.4f} m)")
    print(f"    Module spacing Y: {2*my:.3f} inches ({2*my*0.0254:.4f} m)")
    print(f"    Wheel diameter:   {module['wheel_diameter_in']}\" ({module['wheel_diameter_in']*0.0254:.4f} m)")
    print(f"    Drive gear ratio: {module['drive_ratio']}")
    print(f"    Steer gear ratio: {module['steer_ratio']}")
    print(f"    Max speed:        {module['max_speed_fps']} ft/s ({module['max_speed_fps']*0.3048:.3f} m/s)")

    print(f"\n{'═' * 60}\n")


def save_spec(spec: FrameSpec, output_path: Optional[str] = None) -> str:
    """Save the frame spec to JSON. Returns the file path."""
    if output_path is None:
        safe_name = spec.name.lower().replace(" ", "_")
        output_path = str(BASE_DIR / f"{safe_name}_spec.json")

    data = asdict(spec)
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    return output_path


def print_cutlist(spec: FrameSpec):
    """Print a manufacturing-ready cut list."""
    print(f"\n{'═' * 50}")
    print(f"  CUT LIST — {spec.name}")
    print(f"{'═' * 50}")
    print(f"  {'QTY':<5} {'TUBE':<8} {'LENGTH':<12} {'NOTES'}")
    print(f"  {'─'*5} {'─'*8} {'─'*12} {'─'*20}")

    for member in spec.tube_members:
        print(f"  {member['quantity']:<5} {member['tube_size']:<8} {member['length_in']:<12.2f} {member['notes']}")

    if spec.bellypan:
        peri = TUBE_STOCK[TubeSize(spec.perimeter_tube)]
        bp_l = spec.frame_length_in - 2 * peri["width_in"]
        bp_w = spec.frame_width_in - 2 * peri["width_in"]
        print(f"  {'1':<5} {'polycarb':<8} {f'{bp_l:.1f} x {bp_w:.1f}':<12} Bellypan ({spec.bellypan_material})")

    print(f"\n  Total tube cuts: {sum(m['quantity'] for m in spec.tube_members)}")
    print(f"  Total tube length: {sum(m['length_in'] * m['quantity'] for m in spec.tube_members):.1f} inches")
    print(f"{'═' * 50}\n")


# ═══════════════════════════════════════════════════════════════════
# ONSHAPE INTEGRATION
# ═══════════════════════════════════════════════════════════════════

def create_onshape_document(spec: FrameSpec) -> dict:
    """Create an OnShape document from a frame spec."""
    from onshape_api import create_document

    doc = create_document(
        name=spec.name,
        description=f"Parametric swerve frame: {spec.frame_length_in}x{spec.frame_width_in} "
                    f"with {SWERVE_MODULES[SwerveModuleType(spec.module_type)]['name']}"
    )
    print(f"Created OnShape document: {doc['url']}")

    # Save spec alongside the document reference
    spec_path = save_spec(spec)
    print(f"Saved spec to: {spec_path}")

    return doc


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print("The Blueprint — Swerve Frame Generator (B.2)")
        print()
        print("Usage:")
        print("  python3 frame_generator.py generate [--preset NAME]")
        print("  python3 frame_generator.py generate --length 28 --width 28 --module thrifty")
        print("  python3 frame_generator.py cutlist <spec.json>")
        print("  python3 frame_generator.py presets")
        print("  python3 frame_generator.py create-onshape [--preset NAME]")
        print()
        print("Presets:", ", ".join(PRESETS.keys()))
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "presets":
        print("\nAvailable presets:")
        for name, preset in PRESETS.items():
            print(f"  {name:<14} {preset['description']}")
            print(f"               {preset['frame_length_in']}x{preset['frame_width_in']}\" | "
                  f"{preset['perimeter_tube']} perimeter | {preset['module_type']}")
        print()

    elif cmd == "generate":
        # Parse args
        args = sys.argv[2:]
        if "--preset" in args:
            idx = args.index("--preset")
            preset_name = args[idx + 1] if idx + 1 < len(args) else "competition"
            spec = generate_from_preset(preset_name)
        else:
            # Parse individual params with defaults
            params = {}
            for i in range(0, len(args) - 1, 2):
                key = args[i].lstrip("-")
                val = args[i + 1]
                if key in ("length", "frame_length_in"):
                    params["frame_length_in"] = float(val)
                elif key in ("width", "frame_width_in"):
                    params["frame_width_in"] = float(val)
                elif key in ("module", "module_type"):
                    params["module_type"] = val
                elif key in ("perimeter", "perimeter_tube"):
                    params["perimeter_tube"] = val
                elif key in ("cross", "cross_tube"):
                    params["cross_tube"] = val
                elif key in ("inset", "module_inset_in"):
                    params["module_inset_in"] = float(val)
            spec = generate_frame(**params)

        print_summary(spec)
        path = save_spec(spec)
        print(f"Spec saved to: {path}")

    elif cmd == "cutlist":
        if len(sys.argv) < 3:
            print("Usage: python3 frame_generator.py cutlist <spec.json>")
            sys.exit(1)
        with open(sys.argv[2]) as f:
            data = json.load(f)
        spec = FrameSpec(**{k: v for k, v in data.items() if k in FrameSpec.__dataclass_fields__})
        print_cutlist(spec)

    elif cmd == "create-onshape":
        args = sys.argv[2:]
        if "--preset" in args:
            idx = args.index("--preset")
            preset_name = args[idx + 1] if idx + 1 < len(args) else "competition"
            spec = generate_from_preset(preset_name)
        else:
            spec = generate_from_preset("competition")
        print_summary(spec)
        create_onshape_document(spec)

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
