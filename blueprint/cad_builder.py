#!/usr/bin/env python3
"""
The Blueprint — CAD Builder (B.7)
Team 2950 — The Devastators

Takes Blueprint spec output + assembly layout and builds parametric
robot geometry in OnShape via FeatureScript.

Generates simplified but recognizable 3D representations of:
  - Swerve frame (perimeter tubes, cross members, bellypan)
  - Swerve modules (housing + wheel at each corner)
  - Intake (roller assembly + deploy pivot)
  - Flywheel/shooter (wheel housing + motor block)
  - Conveyor (belt path + side rails)
  - Elevator (tube stages + carriage)
  - Climber (telescoping tubes + hook)
  - Turret (bearing ring + platform)
  - Electronics (battery, PDH, RoboRIO bounding boxes)

Usage:
  python3 cad_builder.py build <blueprint_spec.json>
  python3 cad_builder.py build --2022
  python3 cad_builder.py featurescript <blueprint_spec.json>  # output FS only, no API
"""

import json
import sys
from pathlib import Path

from assembly_composer import compose_robot

BASE_DIR = Path(__file__).parent


# ═══════════════════════════════════════════════════════════════════
# FEATURESCRIPT GENERATION
# ═══════════════════════════════════════════════════════════════════

def _mm(inches: float) -> float:
    """Convert inches to mm."""
    return round(inches * 25.4, 2)


def generate_full_featurescript(spec: dict) -> str:
    """
    Generate complete FeatureScript for the robot.
    Uses fCuboid for all geometry — simplified but recognizable.
    """
    layout = compose_robot(spec)
    frame = spec.get("frame", {})

    L = _mm(layout.frame_length_in)
    W = _mm(layout.frame_width_in)
    tw = 50.8  # 2x1 tube width
    th = 25.4  # tube height (1")
    cw = 25.4  # cross member 1x1

    # Frame origin at corner (0,0,0) = front-left-bottom of frame
    # Center of frame at (L/2, W/2, th/2)

    parts = []

    # ── PERIMETER TUBES ──
    parts.append(_cuboid("front_rail", 0, 0, 0, L, tw, th))
    parts.append(_cuboid("back_rail", 0, W - tw, 0, L, W, th))
    parts.append(_cuboid("left_rail", 0, tw, 0, tw, W - tw, th))
    parts.append(_cuboid("right_rail", L - tw, tw, 0, L, W - tw, th))

    # ── CROSS MEMBERS ──
    cross_positions = frame.get("tube_members", [])
    cross_y_vals = []
    for member in cross_positions:
        if member.get("tube_size") == "1x1" and member.get("orientation") == "x":
            # Convert from center-origin to corner-origin
            pos_y = member["position"][1]
            y_mm = L / 2 + _mm(pos_y)
            cross_y_vals.append(y_mm)

    if not cross_y_vals:
        cross_y_vals = [W * 0.25, W * 0.50, W * 0.75]

    for i, cy in enumerate(cross_y_vals):
        parts.append(_cuboid(f"cross_{i}", tw, cy - cw / 2, 0, L - tw, cy + cw / 2, th))

    # ── BELLYPAN ──
    belly_z = -3.175  # 1/8" below frame
    parts.append(_cuboid("bellypan", 1, 1, belly_z, L - 1, W - 1, 0))

    # ── SWERVE MODULES ──
    module_inset = _mm(frame.get("module_inset_in", 2.75))
    mod_body_w = 76.2  # 3" module body
    mod_body_h = 76.2  # height above frame
    wheel_dia = 82.55  # 3.25"
    wheel_w = 38.1  # 1.5"

    module_centers = [
        (module_inset, module_inset),
        (L - module_inset, module_inset),
        (module_inset, W - module_inset),
        (L - module_inset, W - module_inset),
    ]

    for i, (mx, my) in enumerate(module_centers):
        # Module housing (above frame)
        parts.append(_cuboid(f"mod_body_{i}",
            mx - mod_body_w / 2, my - mod_body_w / 2, th,
            mx + mod_body_w / 2, my + mod_body_w / 2, th + mod_body_h))
        # Wheel (below frame)
        parts.append(_cuboid(f"mod_wheel_{i}",
            mx - wheel_w / 2, my - wheel_dia / 2, belly_z - wheel_dia,
            mx + wheel_w / 2, my + wheel_dia / 2, belly_z))

    # ── MECHANISMS (recognizable shapes per mechanism type) ──
    for placement in layout.placements:
        name = placement.name
        px = L / 2 + _mm(placement.position_in[0])
        py = W / 2 + _mm(placement.position_in[1])
        pz = _mm(placement.position_in[2])
        ew = _mm(placement.envelope_in[0])
        ed = _mm(placement.envelope_in[1])
        eh = _mm(placement.envelope_in[2])

        mech_spec = spec.get(name, {})
        parts.extend(_mechanism_geometry(name, px, py, pz, ew, ed, eh, mech_spec))

    # ── ELECTRONICS (simplified bounding boxes) ──
    electronics = frame.get("electronics_placements", [])
    for ep in electronics:
        comp = ep.get("component", ep.get("name", ""))
        pos = ep.get("position", [0, 0])
        ex = L / 2 + _mm(pos[0])
        ey = W / 2 + _mm(pos[1])

        # Envelope sizes from COTS catalog knowledge
        envelopes = {
            "battery": (181, 76, 167),
            "pdh": (152.4, 101.6, 38.1),
            "roborio": (177.8, 88.9, 38.1),
            "radio": (135, 115, 30),
            "main_breaker": (57, 57, 38),
        }
        env = envelopes.get(comp, (50, 50, 25))
        # Electronics sit on the bellypan
        parts.append(_cuboid(f"elec_{comp}",
            ex - env[0] / 2, ey - env[1] / 2, 0,
            ex + env[0] / 2, ey + env[1] / 2, env[2]))

    # ── BUILD FEATURESCRIPT ──
    body_lines = "\n".join(parts)

    fs = f"""FeatureScript 2931;
import(path : "onshape/std/common.fs", version : "2931.0");

// THE ENGINE — Full Robot Blueprint
// Generated by The Blueprint B.7 — CAD Builder
// Frame: {layout.frame_length_in}" x {layout.frame_width_in}"
// Mechanisms: {', '.join(p.name for p in layout.placements)}

annotation {{ "Feature Type Name" : "2950 Blueprint Robot" }}
export const blueprintRobot = defineFeature(function(context is Context, id is Id, definition is map)
    precondition {{}}
    {{
{body_lines}
    }});
"""
    return fs


def _mechanism_geometry(name: str, px: float, py: float, pz: float,
                        ew: float, ed: float, eh: float,
                        mech_spec: dict) -> list[str]:
    """
    Generate recognizable FeatureScript geometry for each mechanism type.
    Returns a list of fCuboid call strings that together form the mechanism shape.

    Instead of a single bounding box, each mechanism gets multiple parts that
    visually represent its real structure (side plates, rollers, wheels, tubes, etc.)
    """
    parts = []
    plate_t = 6.35  # 1/4" plate thickness

    if name == "intake":
        # Over-bumper pivoting intake:
        # Two side plates + two roller shafts + back plate
        roller_dia = _mm(mech_spec.get("roller_od_in", 4.0))
        intake_w = ew

        # Left side plate
        parts.append(_cuboid(f"{name}_plate_L",
            px - intake_w / 2, py - ed / 2, pz,
            px - intake_w / 2 + plate_t, py + ed / 2, pz + eh))
        # Right side plate
        parts.append(_cuboid(f"{name}_plate_R",
            px + intake_w / 2 - plate_t, py - ed / 2, pz,
            px + intake_w / 2, py + ed / 2, pz + eh))
        # Bottom roller (full width between plates)
        roller_r = roller_dia / 2
        parts.append(_cuboid(f"{name}_roller_bottom",
            px - intake_w / 2 + plate_t, py + ed / 2 - roller_dia, pz,
            px + intake_w / 2 - plate_t, py + ed / 2, pz + roller_dia))
        # Top roller
        parts.append(_cuboid(f"{name}_roller_top",
            px - intake_w / 2 + plate_t, py + ed / 2 - roller_dia, pz + eh - roller_dia,
            px + intake_w / 2 - plate_t, py + ed / 2, pz + eh))
        # Back plate (connecting side plates at pivot end)
        parts.append(_cuboid(f"{name}_back_plate",
            px - intake_w / 2, py - ed / 2, pz,
            px + intake_w / 2, py - ed / 2 + plate_t, pz + eh))
        # Pivot shaft (at bottom rear)
        shaft_r = 6.35  # 1/2" hex = ~12.7mm across
        parts.append(_cuboid(f"{name}_pivot_shaft",
            px - intake_w / 2, py - ed / 2, pz,
            px + intake_w / 2, py - ed / 2 + shaft_r * 2, pz + shaft_r * 2))

    elif name == "flywheel":
        # Dual flywheel shooter:
        # Two flywheel wheels (square approximation) + hood + side plates
        wheel_dia = _mm(mech_spec.get("wheel_diameter_in", 4.0))
        wheel_w = 38.1  # 1.5" wide
        wheel_r = wheel_dia / 2
        spacing = 50.8  # 2" between wheels

        # Left side plate
        parts.append(_cuboid(f"{name}_plate_L",
            px - ew / 2, py - ed / 2, pz,
            px - ew / 2 + plate_t, py + ed / 2, pz + eh))
        # Right side plate
        parts.append(_cuboid(f"{name}_plate_R",
            px + ew / 2 - plate_t, py - ed / 2, pz,
            px + ew / 2, py + ed / 2, pz + eh))
        # Flywheel wheel 1 (bottom)
        parts.append(_cuboid(f"{name}_wheel_1",
            px - wheel_w / 2, py - wheel_r, pz,
            px + wheel_w / 2, py + wheel_r, pz + wheel_dia))
        # Flywheel wheel 2 (top, offset)
        parts.append(_cuboid(f"{name}_wheel_2",
            px - wheel_w / 2, py - wheel_r, pz + spacing,
            px + wheel_w / 2, py + wheel_r, pz + spacing + wheel_dia))
        # Hood (curved approximation — flat plate at angle, front face)
        parts.append(_cuboid(f"{name}_hood",
            px - ew / 2 + plate_t, py + wheel_r, pz,
            px + ew / 2 - plate_t, py + wheel_r + plate_t, pz + eh))
        # Back plate
        parts.append(_cuboid(f"{name}_back",
            px - ew / 2 + plate_t, py - ed / 2, pz,
            px + ew / 2 - plate_t, py - ed / 2 + plate_t, pz + eh))

    elif name == "conveyor":
        # Belt conveyor / indexer:
        # Two side rails + belt surface + end rollers
        rail_w = 25.4  # 1" rail
        belt_t = 3.175  # 1/8" belt

        # Left rail
        parts.append(_cuboid(f"{name}_rail_L",
            px - ew / 2, py - ed / 2, pz,
            px - ew / 2 + rail_w, py + ed / 2, pz + eh))
        # Right rail
        parts.append(_cuboid(f"{name}_rail_R",
            px + ew / 2 - rail_w, py - ed / 2, pz,
            px + ew / 2, py + ed / 2, pz + eh))
        # Belt surface (flat, runs the length)
        parts.append(_cuboid(f"{name}_belt",
            px - ew / 2 + rail_w, py - ed / 2, pz + eh / 2 - belt_t,
            px + ew / 2 - rail_w, py + ed / 2, pz + eh / 2 + belt_t))
        # Front roller
        roller_dia = _mm(mech_spec.get("roller_diameter_in", 2.0))
        parts.append(_cuboid(f"{name}_roller_front",
            px - ew / 2 + rail_w, py + ed / 2 - roller_dia, pz + eh / 2 - roller_dia / 2,
            px + ew / 2 - rail_w, py + ed / 2, pz + eh / 2 + roller_dia / 2))
        # Back roller
        parts.append(_cuboid(f"{name}_roller_back",
            px - ew / 2 + rail_w, py - ed / 2, pz + eh / 2 - roller_dia / 2,
            px + ew / 2 - rail_w, py - ed / 2 + roller_dia, pz + eh / 2 + roller_dia / 2))

    elif name == "climber":
        # Telescope climber:
        # Outer tube + inner tube (extended) + spool block at base
        outer_w = 38.1  # 1.5" outer tube
        inner_w = 25.4  # 1" inner tube
        base_h = 76.2   # 3" base block for gearbox/spool

        # Outer tube (bottom portion)
        outer_h = min(eh * 0.4, _mm(24))  # outer tube is bottom 40%
        parts.append(_cuboid(f"{name}_outer_tube",
            px - outer_w / 2, py - outer_w / 2, pz,
            px + outer_w / 2, py + outer_w / 2, pz + outer_h))
        # Inner tube (extends from outer tube upward)
        parts.append(_cuboid(f"{name}_inner_tube",
            px - inner_w / 2, py - inner_w / 2, pz + base_h,
            px + inner_w / 2, py + inner_w / 2, pz + eh))
        # Base block (gearbox + spool housing)
        parts.append(_cuboid(f"{name}_base",
            px - outer_w, py - outer_w, pz,
            px + outer_w, py + outer_w, pz + base_h))
        # Hook at top (small block)
        hook_w = 50.8  # 2" hook
        hook_h = 25.4  # 1" tall
        parts.append(_cuboid(f"{name}_hook",
            px - hook_w / 2, py - 12.7, pz + eh,
            px + hook_w / 2, py + 12.7, pz + eh + hook_h))

    else:
        # Fallback: bounding box for unknown mechanisms
        parts.append(_cuboid(f"mech_{name}",
            px - ew / 2, py - ed / 2, pz,
            px + ew / 2, py + ed / 2, pz + eh))

    return parts


def _cuboid(name: str, x1: float, y1: float, z1: float,
            x2: float, y2: float, z2: float) -> str:
    """Generate a single fCuboid call."""
    return f"""        // {name}
        fCuboid(context, id + "{name}", {{
            "corner1" : vector({x1:.1f}, {y1:.1f}, {z1:.1f}) * millimeter,
            "corner2" : vector({x2:.1f}, {y2:.1f}, {z2:.1f}) * millimeter
        }});"""


# ═══════════════════════════════════════════════════════════════════
# REAL TUBE FRAME — Hollow extrusions with cutouts
# ═══════════════════════════════════════════════════════════════════

def generate_real_frame_featurescript(spec: dict) -> str:
    """
    Generate FeatureScript for a real tube frame with:
    - Hollow 2x1 perimeter tubes (0.040" wall)
    - Hollow 1x1 cross members (0.063" wall)
    - Bellypan (1/8" polycarb)
    - Module cutouts in perimeter rails
    - Bolt holes at module mounting pattern + tube junctions
    - Gusset pads at corners and cross member junctions

    Uses opExtrudeBody for hollow profiles via sketch + extrude.
    """
    layout = compose_robot(spec)
    frame = spec.get("frame", {})

    L = _mm(layout.frame_length_in)
    W = _mm(layout.frame_width_in)

    # Tube dimensions
    tw = 50.8   # 2x1 outer width (2")
    td = 25.4   # 2x1 outer depth (1")
    wall_2x1 = 1.016   # 0.040" wall
    cw = 25.4   # 1x1 outer (1")
    wall_1x1 = 1.6     # 0.063" wall
    belly_t = 3.175     # 1/8" bellypan

    # Module cutout
    module_inset = _mm(frame.get("module_inset_in", 2.75))
    cutout_size = _mm(frame.get("module_cutout_in", 3.75))

    # Cross member positions
    cross_positions = frame.get("tube_members", [])
    cross_y_vals = []
    for member in cross_positions:
        if member.get("tube_size") == "1x1" and member.get("orientation") == "x":
            pos_y = member["position"][1]
            y_mm = W / 2 + _mm(pos_y)
            cross_y_vals.append(y_mm)
    if not cross_y_vals:
        cross_y_vals = [W * 0.25, W * 0.50, W * 0.75]

    # Module centers (corner-origin)
    module_centers = [
        (module_inset, module_inset),
        (L - module_inset, module_inset),
        (module_inset, W - module_inset),
        (L - module_inset, W - module_inset),
    ]

    body = []

    # Helper: hollow tube via outer cuboid - inner cuboid boolean
    def hollow_tube(name, x1, y1, z1, x2, y2, z2, wall):
        """Generate a hollow tube using cuboid subtract."""
        body.append(f"        // {name} (hollow tube)")
        body.append(f"        fCuboid(context, id + \"{name}_outer\", {{")
        body.append(f"            \"corner1\" : vector({x1:.2f}, {y1:.2f}, {z1:.2f}) * millimeter,")
        body.append(f"            \"corner2\" : vector({x2:.2f}, {y2:.2f}, {z2:.2f}) * millimeter")
        body.append(f"        }});")
        body.append(f"        fCuboid(context, id + \"{name}_inner\", {{")
        body.append(f"            \"corner1\" : vector({x1+wall:.2f}, {y1+wall:.2f}, {z1+wall:.2f}) * millimeter,")
        body.append(f"            \"corner2\" : vector({x2-wall:.2f}, {y2-wall:.2f}, {z2-wall:.2f}) * millimeter")
        body.append(f"        }});")
        body.append(f"        opBoolean(context, id + \"{name}_hollow\", {{")
        body.append(f"            \"tools\" : qCreatedBy(id + \"{name}_inner\", EntityType.BODY),")
        body.append(f"            \"targets\" : qCreatedBy(id + \"{name}_outer\", EntityType.BODY),")
        body.append(f"            \"operationType\" : BooleanOperationType.SUBTRACTION")
        body.append(f"        }});")

    def solid_cuboid(name, x1, y1, z1, x2, y2, z2):
        """Generate a solid cuboid."""
        body.append(f"        // {name}")
        body.append(f"        fCuboid(context, id + \"{name}\", {{")
        body.append(f"            \"corner1\" : vector({x1:.2f}, {y1:.2f}, {z1:.2f}) * millimeter,")
        body.append(f"            \"corner2\" : vector({x2:.2f}, {y2:.2f}, {z2:.2f}) * millimeter")
        body.append(f"        }});")

    def module_cutout(name, cx, cy, size):
        """Cut a square hole for swerve module mounting."""
        hs = size / 2
        body.append(f"        // {name} — module cutout")
        body.append(f"        fCuboid(context, id + \"{name}_cut\", {{")
        body.append(f"            \"corner1\" : vector({cx-hs:.2f}, {cy-hs:.2f}, {-5:.2f}) * millimeter,")
        body.append(f"            \"corner2\" : vector({cx+hs:.2f}, {cy+hs:.2f}, {td+5:.2f}) * millimeter")
        body.append(f"        }});")
        body.append(f"        opBoolean(context, id + \"{name}_boolean\", {{")
        body.append(f"            \"tools\" : qCreatedBy(id + \"{name}_cut\", EntityType.BODY),")
        body.append(f"            \"targets\" : qAllNonMeshSolidBodies(),")
        body.append(f"            \"operationType\" : BooleanOperationType.SUBTRACTION")
        body.append(f"        }});")

    def bolt_hole(name, cx, cy, z_bottom, z_top, diameter_mm):
        """Drill a bolt hole through frame tubes."""
        r = diameter_mm / 2
        body.append(f"        // {name} — bolt hole (d={diameter_mm:.1f}mm)")
        body.append(f"        fCylinder(context, id + \"{name}\", {{")
        body.append(f"            \"topCenter\" : vector({cx:.2f}, {cy:.2f}, {z_top:.2f}) * millimeter,")
        body.append(f"            \"bottomCenter\" : vector({cx:.2f}, {cy:.2f}, {z_bottom:.2f}) * millimeter,")
        body.append(f"            \"radius\" : {r:.2f} * millimeter")
        body.append(f"        }});")
        body.append(f"        opBoolean(context, id + \"{name}_drill\", {{")
        body.append(f"            \"tools\" : qCreatedBy(id + \"{name}\", EntityType.BODY),")
        body.append(f"            \"targets\" : qAllNonMeshSolidBodies(),")
        body.append(f"            \"operationType\" : BooleanOperationType.SUBTRACTION")
        body.append(f"        }});")

    # ── PERIMETER TUBES (hollow 2x1) ──
    hollow_tube("front_rail", 0, 0, 0, L, tw, td, wall_2x1)
    hollow_tube("back_rail", 0, W - tw, 0, L, W, td, wall_2x1)
    hollow_tube("left_rail", 0, tw, 0, tw, W - tw, td, wall_2x1)
    hollow_tube("right_rail", L - tw, tw, 0, L, W - tw, td, wall_2x1)

    # ── CROSS MEMBERS (hollow 1x1) ──
    for i, cy in enumerate(cross_y_vals):
        hollow_tube(f"cross_{i}", tw, cy - cw/2, 0, L - tw, cy + cw/2, td, wall_1x1)

    # ── BELLYPAN ──
    solid_cuboid("bellypan", wall_2x1, wall_2x1, -belly_t, L - wall_2x1, W - wall_2x1, 0)

    # ── MODULE CUTOUTS ──
    for i, (mx, my) in enumerate(module_centers):
        module_cutout(f"mod_cutout_{i}", mx, my, cutout_size)

    # ── MODULE BOLT HOLES (4 per module, #10-32 = 4.98mm) ──
    bolt_dia = 4.98  # #10-32 clearance hole
    bolt_offset = cutout_size / 2 + 5  # 5mm outside cutout edge
    for i, (mx, my) in enumerate(module_centers):
        for j, (dx, dy) in enumerate([(-1,-1), (1,-1), (-1,1), (1,1)]):
            bolt_hole(f"mod_bolt_{i}_{j}",
                      mx + dx * bolt_offset, my + dy * bolt_offset,
                      -1, td + 1, bolt_dia)

    # ── GUSSET BOLT HOLES at corners ──
    inset = tw + 10  # holes in rail for gusset mounting
    for i, (cx, cy) in enumerate([(inset, inset), (L-inset, inset),
                                   (inset, W-inset), (L-inset, W-inset)]):
        for j, (dx, dy) in enumerate([(0, 10), (0, -10), (10, 0), (-10, 0)]):
            bolt_hole(f"gusset_bolt_{i}_{j}", cx+dx, cy+dy, -1, td+1, bolt_dia)

    # ── CROSS MEMBER JUNCTION BOLT HOLES ──
    for ci, cy in enumerate(cross_y_vals):
        # Left and right junction
        for side, sx in enumerate([tw/2, L - tw/2]):
            bolt_hole(f"cross_bolt_{ci}_{side}_a", sx, cy - 8, -1, td+1, bolt_dia)
            bolt_hole(f"cross_bolt_{ci}_{side}_b", sx, cy + 8, -1, td+1, bolt_dia)

    # ── SWERVE MODULES (visual — above + below frame) ──
    mod_body_w = 76.2
    mod_body_h = 76.2
    wheel_dia = 82.55
    wheel_w = 38.1
    for i, (mx, my) in enumerate(module_centers):
        solid_cuboid(f"mod_body_{i}",
            mx - mod_body_w/2, my - mod_body_w/2, td,
            mx + mod_body_w/2, my + mod_body_w/2, td + mod_body_h)
        solid_cuboid(f"mod_wheel_{i}",
            mx - wheel_w/2, my - wheel_dia/2, -belly_t - wheel_dia,
            mx + wheel_w/2, my + wheel_dia/2, -belly_t)

    # ── MECHANISMS (bounding box envelopes) ──
    for placement in layout.placements:
        name = placement.name
        px = L/2 + _mm(placement.position_in[0])
        py = W/2 + _mm(placement.position_in[1])
        pz = _mm(placement.position_in[2])
        ew = _mm(placement.envelope_in[0])
        ed = _mm(placement.envelope_in[1])
        eh = _mm(placement.envelope_in[2])
        solid_cuboid(f"mech_{name}",
            px - ew/2, py - ed/2, pz,
            px + ew/2, py + ed/2, pz + eh)

    # ── ELECTRONICS ──
    electronics = frame.get("electronics_placements", [])
    envelopes = {
        "battery": (181, 76, 167), "pdh": (152.4, 101.6, 38.1),
        "roborio": (177.8, 88.9, 38.1), "radio": (135, 115, 30),
        "main_breaker": (57, 57, 38),
    }
    for ep in electronics:
        comp = ep.get("component", ep.get("name", ""))
        pos = ep.get("position", [0, 0])
        ex = L/2 + _mm(pos[0])
        ey = W/2 + _mm(pos[1])
        env = envelopes.get(comp, (50, 50, 25))
        solid_cuboid(f"elec_{comp}",
            ex - env[0]/2, ey - env[1]/2, 0,
            ex + env[0]/2, ey + env[1]/2, env[2])

    # ── BUILD FEATURESCRIPT ──
    body_lines = "\n".join(body)
    mech_names = ', '.join(p.name for p in layout.placements)

    fs = f"""FeatureScript 2931;
import(path : "onshape/std/common.fs", version : "2931.0");

// THE ENGINE — Real Tube Frame Robot Blueprint
// Generated by The Blueprint — CAD Builder (Evolution P1)
// Frame: {layout.frame_length_in}" x {layout.frame_width_in}"
// Tubes: 2x1 perimeter (0.040" wall), 1x1 cross members (0.063" wall)
// Module cutouts: {cutout_size:.1f}mm square at {len(module_centers)} corners
// Mechanisms: {mech_names}

annotation {{ "Feature Type Name" : "2950 Real Frame Robot" }}
export const blueprintRealFrame = defineFeature(function(context is Context, id is Id, definition is map)
    precondition {{}}
    {{
{body_lines}
    }});
"""
    return fs


# ═══════════════════════════════════════════════════════════════════
# ONSHAPE API — Create document + upload FeatureScript
# ═══════════════════════════════════════════════════════════════════

def build_robot_document(spec: dict, name: str = "2950 Blueprint Robot") -> dict:
    """
    Create an OnShape document and upload the robot FeatureScript.
    Returns document URL and metadata.
    """
    from onshape_api import get_client

    client = get_client()

    # Step 1: Create document
    print(f"  Creating OnShape document: {name}...")
    doc_response = client.documents_api.create_document({
        "name": name,
        "description": "Generated by The Engine — Full Blueprint Pipeline",
        "isPublic": True,
    })
    doc_id = doc_response.id
    workspace_id = doc_response.default_workspace.id
    doc_url = f"https://cad.onshape.com/documents/{doc_id}"
    print(f"  Document created: {doc_url}")

    # Step 2: Get the default Part Studio
    elements = client.documents_api.get_elements_in_document(
        doc_id, "w", workspace_id
    )
    part_studio_id = None
    for elem in elements:
        if elem.element_type == "PARTSTUDIO":
            part_studio_id = elem.id
            break
    print(f"  Part Studio ID: {part_studio_id}")

    # Step 3: Create a Feature Studio for the FeatureScript
    print(f"  Creating Feature Studio...")
    fs_response = client.api_client.call_api(
        f"/api/featurestudios/d/{doc_id}/w/{workspace_id}",
        "POST",
        body={"name": "2950 Blueprint Builder"},
        header_params={"Content-Type": "application/json", "Accept": "application/json"},
        response_type="object",
    )
    # Parse feature studio element ID
    if hasattr(fs_response, 'id'):
        fs_id = fs_response.id
    elif isinstance(fs_response, dict):
        fs_id = fs_response.get("id", "")
    else:
        fs_id = str(fs_response)
    print(f"  Feature Studio ID: {fs_id}")

    # Step 4: Generate and upload FeatureScript
    print(f"  Generating FeatureScript...")
    fs_code = generate_full_featurescript(spec)

    # Get microversion
    doc_info = client.documents_api.get_document(doc_id)
    mv = ""
    if hasattr(doc_info, 'default_workspace') and hasattr(doc_info.default_workspace, 'microversion'):
        mv = doc_info.default_workspace.microversion

    print(f"  Uploading FeatureScript ({len(fs_code)} chars)...")
    try:
        client.api_client.call_api(
            f"/api/featurestudios/d/{doc_id}/w/{workspace_id}/e/{fs_id}",
            "POST",
            body={"contents": fs_code, "serializationVersion": "1.2.17", "sourceMicroversion": mv},
            header_params={"Content-Type": "application/json", "Accept": "application/json"},
            response_type="object",
        )
        print(f"  FeatureScript uploaded successfully!")
    except Exception as e:
        print(f"  FeatureScript upload note: {e}")
        print(f"  You can manually paste the FeatureScript into the Feature Studio tab.")

    # Step 5: Save FeatureScript locally as backup
    fs_path = BASE_DIR / "generated_featurescript.fs"
    with open(fs_path, "w") as f:
        f.write(fs_code)
    print(f"  FeatureScript saved locally: {fs_path}")

    print(f"\n  NEXT STEP: In OnShape, click the '2950 Blueprint Builder' tab,")
    print(f"  then in Part Studio 1, click '+' > Custom features > '2950 Blueprint Robot'")

    return {
        "document_id": doc_id,
        "workspace_id": workspace_id,
        "part_studio_id": part_studio_id,
        "feature_studio_id": fs_id,
        "url": doc_url,
        "name": name,
    }


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

def main():
    args = sys.argv[1:]
    if not args:
        print("Usage:")
        print("  python3 cad_builder.py build --2022")
        print("  python3 cad_builder.py build <blueprint_spec.json>")
        print("  python3 cad_builder.py featurescript --2022       # FS output only, no API")
        return

    # Load spec
    if len(args) > 1 and args[1] == "--2022":
        spec_path = BASE_DIR / "2022_rapid_react_full_blueprint.json"
    elif len(args) > 1:
        spec_path = Path(args[1])
    else:
        spec_path = BASE_DIR / "2022_rapid_react_full_blueprint.json"

    if not spec_path.exists():
        print(f"Spec not found: {spec_path}")
        return

    with open(spec_path) as f:
        spec = json.load(f)

    game = spec.get("game", "Robot")
    year = spec.get("year", "2022")

    if args[0] == "featurescript":
        # Generate FeatureScript only, no API calls
        fs_code = generate_full_featurescript(spec)
        out_path = BASE_DIR / "generated_featurescript.fs"
        with open(out_path, "w") as f:
            f.write(fs_code)
        print(f"FeatureScript generated: {out_path}")
        print(f"  Paste into OnShape Feature Studio to create geometry.")

    elif args[0] == "build":
        print(f"\n{'═' * 65}")
        print(f"  THE ENGINE — CAD BUILDER")
        print(f"  Building {year} {game} robot in OnShape")
        print(f"{'═' * 65}\n")

        result = build_robot_document(
            spec,
            name=f"2950 {game} {year} — The Engine Blueprint",
        )

        print(f"\n{'═' * 65}")
        print(f"  CAD DOCUMENT READY")
        print(f"  URL: {result['url']}")
        print(f"  Document ID: {result['document_id']}")
        print(f"{'═' * 65}\n")

        result_path = BASE_DIR / "cad_build_result.json"
        with open(result_path, "w") as f:
            json.dump(result, f, indent=2)
        print(f"Build result saved: {result_path}")


if __name__ == "__main__":
    main()
