"""
The Blueprint — Assembly Composer (B.6)
Team 2950 — The Devastators

Takes frame spec + mechanism specs and computes the physical layout
of the robot — where each mechanism mounts, volume allocations,
interference checks, and assembly instructions.

This is the integration layer: subsystems snap onto the frame.

Input: Full blueprint spec JSON (frame + intake + scorer + endgame + conveyor)
Output: RobotLayout with:
  - Mechanism mount positions (x, y, z relative to frame origin)
  - Volume envelopes for each mechanism
  - Interference warnings
  - Assembly order with notes
  - CAD placement data for cad_builder.py

Usage:
  python3 assembly_composer.py compose <full_blueprint.json>
  python3 assembly_composer.py compose --2022
"""

import json
import math
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

BASE_DIR = Path(__file__).parent


# ═══════════════════════════════════════════════════════════════════
# MECHANISM PLACEMENT RULES
# ═══════════════════════════════════════════════════════════════════

# Z coordinate system: Z=0 is top of bellypan, Z=25.4mm is top of frame tubes
# Mechanisms mount above the frame. Wheels are below.

# Frame regions (all in inches from frame center):
# Front = +Y, Back = -Y, Left = -X, Right = +X
PLACEMENT_ZONES = {
    "intake": {
        "preferred": "front",
        "z_base": "frame_top",  # mounts on top of frame
        "notes": "Front of robot for forward acquisition",
    },
    "flywheel": {
        "preferred": "back_upper",
        "z_base": "above_conveyor",
        "notes": "Behind/above conveyor exit point",
    },
    "elevator": {
        "preferred": "center_back",
        "z_base": "frame_top",
        "notes": "Center or slight back, tall — keep center of gravity low",
    },
    "arm": {
        "preferred": "center_back",
        "z_base": "frame_top",
        "notes": "Pivot point near frame center for balance",
    },
    "conveyor": {
        "preferred": "center",
        "z_base": "frame_top",
        "notes": "Connects intake to scorer, runs through robot center",
    },
    "climber": {
        "preferred": "back",
        "z_base": "frame_top",
        "notes": "Back of robot — reach behind to grab bar/chain",
    },
    "turret": {
        "preferred": "center_top",
        "z_base": "above_elevator",
        "notes": "On top of elevator carriage or frame center",
    },
}


@dataclass
class MechanismPlacement:
    """Position and envelope of a mechanism on the robot."""
    name: str = ""
    position_in: list = field(default_factory=lambda: [0.0, 0.0, 0.0])  # [x, y, z] from frame center
    position_mm: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    envelope_in: list = field(default_factory=lambda: [0.0, 0.0, 0.0])  # [width, depth, height]
    envelope_mm: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    weight_lb: float = 0.0
    mounting_face: str = "top"  # top, front, back, left, right
    notes: str = ""


@dataclass
class RobotLayout:
    """Complete robot assembly layout."""
    frame_length_in: float = 27.0
    frame_width_in: float = 27.0
    frame_height_in: float = 1.0

    placements: list = field(default_factory=list)
    swerve_modules: list = field(default_factory=list)
    electronics: list = field(default_factory=list)

    total_height_in: float = 0.0
    center_of_gravity_in: list = field(default_factory=lambda: [0.0, 0.0, 0.0])

    interference_warnings: list = field(default_factory=list)
    assembly_order: list = field(default_factory=list)

    notes: list = field(default_factory=list)


def _in_to_mm(inches):
    return round(inches * 25.4, 1)


def compose_robot(spec: dict) -> RobotLayout:
    """
    Compose a full robot layout from a blueprint spec.
    Determines where each mechanism mounts and checks for interference.
    """
    frame = spec.get("frame", {})
    layout = RobotLayout(
        frame_length_in=frame.get("frame_length_in", 27.0),
        frame_width_in=frame.get("frame_width_in", 27.0),
        frame_height_in=frame.get("frame_height_in", 1.0),
    )

    L = layout.frame_length_in
    W = layout.frame_width_in
    H = layout.frame_height_in
    bumper_t = frame.get("bumper_thickness_in", 3.5)

    # Available interior space (inside perimeter tubes)
    tube_w = 2.0  # 2x1 tube width
    interior_x = L - 2 * tube_w
    interior_y = W - 2 * tube_w

    # ── Swerve modules ──
    module_placements = frame.get("module_placements", [])
    module_inset = frame.get("module_inset_in", 2.75)
    for mp in module_placements:
        layout.swerve_modules.append({
            "name": mp["name"],
            "position_in": mp["position"],
            "position_mm": [_in_to_mm(p) for p in mp["position"]],
            "module_type": mp.get("module_type", "sds_mk4i"),
        })
    if not module_placements:
        # Default MK4i positions
        for name, px, py in [
            ("front_left", -L/2 + module_inset, W/2 - module_inset),
            ("front_right", L/2 - module_inset, W/2 - module_inset),
            ("back_left", -L/2 + module_inset, -W/2 + module_inset),
            ("back_right", L/2 - module_inset, -W/2 + module_inset),
        ]:
            layout.swerve_modules.append({
                "name": name,
                "position_in": [px, py],
                "position_mm": [_in_to_mm(px), _in_to_mm(py)],
                "module_type": "sds_mk4i",
            })

    # ── Electronics placements (from frame spec) ──
    electronics = frame.get("electronics_placements", [])
    for ep in electronics:
        layout.electronics.append(ep)

    # ── Mechanism placement ──
    # Track occupied vertical space
    z_cursor = H  # start at top of frame (inches)
    mechanism_names = []

    # Intake — front of robot
    intake = spec.get("intake", {})
    if intake:
        iw = intake.get("intake_width_in", interior_x)
        id_depth = intake.get("game_piece_diameter_in", 6.0) + 4.0  # piece + structure
        ih = intake.get("game_piece_diameter_in", 6.0) + 2.0
        deploy = intake.get("deploy_type", "none") != "none"

        placement = MechanismPlacement(
            name="intake",
            position_in=[0.0, W/2 - bumper_t - id_depth/2, H],
            envelope_in=[iw, id_depth, ih],
            weight_lb=intake.get("total_weight_lb", 7.0),
            mounting_face="front",
            notes="Over-bumper" if intake.get("intake_type") == "over_bumper" else "Under-bumper",
        )
        placement.position_mm = [_in_to_mm(p) for p in placement.position_in]
        placement.envelope_mm = [_in_to_mm(e) for e in placement.envelope_in]
        layout.placements.append(placement)
        mechanism_names.append("intake")

    # Conveyor — center of robot, connects intake to scorer
    conveyor = spec.get("conveyor", {})
    if conveyor:
        cw = 12.0  # conveyor width
        cd = conveyor.get("path_length_in", 24.0)
        ch = conveyor.get("game_piece_diameter_in", 6.0) + 2.0

        placement = MechanismPlacement(
            name="conveyor",
            position_in=[0.0, 0.0, H],
            envelope_in=[cw, cd, ch],
            weight_lb=conveyor.get("total_weight_lb", 3.0),
            mounting_face="top",
            notes=f"{conveyor.get('staging_count', 1)} staging positions",
        )
        placement.position_mm = [_in_to_mm(p) for p in placement.position_in]
        placement.envelope_mm = [_in_to_mm(e) for e in placement.envelope_in]
        layout.placements.append(placement)
        mechanism_names.append("conveyor")
        z_cursor = max(z_cursor, H + ch)

    # Flywheel/shooter — back-upper, above conveyor exit
    flywheel = spec.get("flywheel", {})
    if flywheel:
        fw = 10.0  # shooter width
        fd = 8.0  # shooter depth
        fh = flywheel.get("wheel_diameter_in", 6.0) + 2.0

        placement = MechanismPlacement(
            name="flywheel",
            position_in=[0.0, -W/4, z_cursor],
            envelope_in=[fw, fd, fh],
            weight_lb=flywheel.get("total_weight_lb", 4.0),
            mounting_face="top",
            notes=f"{flywheel.get('wheel_diameter_in', 6.0)}\" wheels, {flywheel.get('target_rpm', 3000)} RPM",
        )
        placement.position_mm = [_in_to_mm(p) for p in placement.position_in]
        placement.envelope_mm = [_in_to_mm(e) for e in placement.envelope_in]
        layout.placements.append(placement)
        mechanism_names.append("flywheel")
        z_cursor = max(z_cursor, placement.position_in[2] + fh)

    # Elevator — center-back, tall
    elevator = spec.get("elevator", {})
    if elevator:
        ew = 12.0
        ed = 6.0
        eh = elevator.get("travel_height_in", 48.0) + 6.0  # travel + base structure

        placement = MechanismPlacement(
            name="elevator",
            position_in=[0.0, -2.0, H],
            envelope_in=[ew, ed, eh],
            weight_lb=elevator.get("total_weight_lb", 12.0),
            mounting_face="top",
            notes=f"{elevator.get('stage_count', 2)} stages, {elevator.get('travel_height_in', 48)}\" travel",
        )
        placement.position_mm = [_in_to_mm(p) for p in placement.position_in]
        placement.envelope_mm = [_in_to_mm(e) for e in placement.envelope_in]
        layout.placements.append(placement)
        mechanism_names.append("elevator")
        z_cursor = max(z_cursor, H + eh)

    # Arm — center-back pivot
    arm = spec.get("arm", {})
    if arm:
        arm_len = arm.get("arm_length_in", 24.0)
        aw = 6.0
        ad = arm_len
        ah = arm_len  # arm sweeps through vertical arc

        placement = MechanismPlacement(
            name="arm",
            position_in=[0.0, -2.0, H + 2.0],
            envelope_in=[aw, ad, ah],
            weight_lb=arm.get("total_weight_lb", 8.0),
            mounting_face="top",
            notes=f"{arm_len}\" reach, {arm.get('start_angle_deg', -30)}° to {arm.get('end_angle_deg', 110)}°",
        )
        placement.position_mm = [_in_to_mm(p) for p in placement.position_in]
        placement.envelope_mm = [_in_to_mm(e) for e in placement.envelope_in]
        layout.placements.append(placement)
        mechanism_names.append("arm")
        z_cursor = max(z_cursor, H + 2.0 + ah)

    # Climber — back of robot
    climber = spec.get("climber", {})
    if climber:
        climb_h = climber.get("climb_height_in", 26.0)
        cw = 8.0
        cd = 4.0

        placement = MechanismPlacement(
            name="climber",
            position_in=[0.0, -W/2 + tube_w + cd/2, H],
            envelope_in=[cw, cd, climb_h + 4.0],
            weight_lb=climber.get("total_weight_lb", 8.0),
            mounting_face="back",
            notes=f"{climber.get('climb_style', 'winch')} climber, {climb_h}\" travel",
        )
        placement.position_mm = [_in_to_mm(p) for p in placement.position_in]
        placement.envelope_mm = [_in_to_mm(e) for e in placement.envelope_in]
        layout.placements.append(placement)
        mechanism_names.append("climber")
        z_cursor = max(z_cursor, H + climb_h + 4.0)

    # Turret — on top of elevator or frame center
    turret = spec.get("turret", {})
    if turret:
        tod = turret.get("turret_od_in", 12.0)
        th = 4.0  # turret height

        turret_z = z_cursor if elevator else H
        placement = MechanismPlacement(
            name="turret",
            position_in=[0.0, 0.0, turret_z],
            envelope_in=[tod, tod, th],
            weight_lb=turret.get("total_weight_lb", 5.0),
            mounting_face="top",
            notes=f"{tod}\" bearing, on {'elevator' if elevator else 'frame'}",
        )
        placement.position_mm = [_in_to_mm(p) for p in placement.position_in]
        placement.envelope_mm = [_in_to_mm(e) for e in placement.envelope_in]
        layout.placements.append(placement)
        mechanism_names.append("turret")

    # ── Total robot height ──
    layout.total_height_in = round(z_cursor, 1)

    # ── Center of gravity estimate ──
    total_weight = sum(p.weight_lb for p in layout.placements)
    frame_weight = frame.get("total_weight_lb", 40.0)
    total_weight += frame_weight

    if total_weight > 0:
        cg_x = sum(p.position_in[0] * p.weight_lb for p in layout.placements) / total_weight
        cg_y = sum(p.position_in[1] * p.weight_lb for p in layout.placements) / total_weight
        cg_z = (sum(p.position_in[2] * p.weight_lb for p in layout.placements) +
                frame_weight * H / 2) / total_weight
        layout.center_of_gravity_in = [round(cg_x, 2), round(cg_y, 2), round(cg_z, 2)]

    # ── Interference checks ──
    for i, p1 in enumerate(layout.placements):
        for p2 in layout.placements[i+1:]:
            if _check_overlap(p1, p2):
                layout.interference_warnings.append(
                    f"{p1.name} and {p2.name} volumes overlap — review clearances"
                )

    # Height warning
    if layout.total_height_in > 48:
        layout.interference_warnings.append(
            f"Robot height {layout.total_height_in}\" — check game-specific height limits"
        )

    # CG warning
    cg_y = layout.center_of_gravity_in[1]
    if abs(cg_y) > W * 0.15:
        layout.interference_warnings.append(
            f"CG offset {cg_y:.1f}\" from center — robot may tip during accel/decel"
        )

    # ── Assembly order ──
    # Build order: frame first, then mechanisms in dependency order
    layout.assembly_order = [
        {"step": 1, "task": "Drivetrain — assemble swerve frame + modules", "subsystem": "frame"},
    ]
    step = 2
    # Scorer before intake (scorer alignment is more critical)
    if "flywheel" in mechanism_names:
        layout.assembly_order.append({"step": step, "task": "Flywheel shooter — mount and align", "subsystem": "flywheel"})
        step += 1
    if "elevator" in mechanism_names:
        layout.assembly_order.append({"step": step, "task": "Elevator — mount rails + rigging", "subsystem": "elevator"})
        step += 1
    if "arm" in mechanism_names:
        layout.assembly_order.append({"step": step, "task": "Arm — mount pivot + motor", "subsystem": "arm"})
        step += 1
    if "turret" in mechanism_names:
        layout.assembly_order.append({"step": step, "task": "Turret — mount bearing + drive", "subsystem": "turret"})
        step += 1
    if "conveyor" in mechanism_names:
        layout.assembly_order.append({"step": step, "task": "Conveyor — mount belt + sensors", "subsystem": "conveyor"})
        step += 1
    if "intake" in mechanism_names:
        layout.assembly_order.append({"step": step, "task": "Intake — mount + test deploy", "subsystem": "intake"})
        step += 1
    if "climber" in mechanism_names:
        layout.assembly_order.append({"step": step, "task": "Climber — mount + test travel", "subsystem": "climber"})
        step += 1
    layout.assembly_order.append({"step": step, "task": "Electronics — wire all mechanisms", "subsystem": "electronics"})
    layout.assembly_order.append({"step": step + 1, "task": "Bumpers — attach + verify frame perimeter", "subsystem": "bumpers"})

    return layout


def _check_overlap(p1: MechanismPlacement, p2: MechanismPlacement) -> bool:
    """Check if two mechanism bounding boxes overlap."""
    for axis in range(3):
        p1_min = p1.position_in[axis] - p1.envelope_in[axis] / 2
        p1_max = p1.position_in[axis] + p1.envelope_in[axis] / 2
        p2_min = p2.position_in[axis] - p2.envelope_in[axis] / 2
        p2_max = p2.position_in[axis] + p2.envelope_in[axis] / 2
        if p1_max <= p2_min or p2_max <= p1_min:
            return False  # separated on this axis
    return True


def display_layout(layout: RobotLayout):
    print(f"\n{'═' * 65}")
    print(f"  2950 ROBOT ASSEMBLY LAYOUT")
    print(f"  Generated by The Blueprint B.6 — Assembly Composer")
    print(f"{'═' * 65}")

    print(f"\n  FRAME: {layout.frame_length_in}\" x {layout.frame_width_in}\" x {layout.frame_height_in}\"")
    print(f"  TOTAL HEIGHT: {layout.total_height_in}\"")
    print(f"  CENTER OF GRAVITY: ({layout.center_of_gravity_in[0]}\", {layout.center_of_gravity_in[1]}\", {layout.center_of_gravity_in[2]}\")")

    print(f"\n  SWERVE MODULES ({len(layout.swerve_modules)})")
    for sm in layout.swerve_modules:
        print(f"    {sm['name']:12s} at ({sm['position_in'][0]:+.1f}\", {sm['position_in'][1]:+.1f}\") — {sm['module_type']}")

    print(f"\n  MECHANISM PLACEMENTS ({len(layout.placements)})")
    print(f"    {'Name':<12s} {'Position (in)':<24s} {'Envelope (in)':<20s} {'Weight':<8s} {'Notes'}")
    print(f"    {'─' * 80}")
    for p in layout.placements:
        pos = f"({p.position_in[0]:+.1f}, {p.position_in[1]:+.1f}, {p.position_in[2]:+.1f})"
        env = f"{p.envelope_in[0]:.0f}x{p.envelope_in[1]:.0f}x{p.envelope_in[2]:.0f}"
        print(f"    {p.name:<12s} {pos:<24s} {env:<20s} {p.weight_lb:<7.1f}lb {p.notes}")

    if layout.interference_warnings:
        print(f"\n  ⚠ WARNINGS")
        for w in layout.interference_warnings:
            print(f"    • {w}")

    print(f"\n  ASSEMBLY ORDER")
    for step in layout.assembly_order:
        print(f"    {step['step']:2d}. {step['task']}")

    print(f"\n{'═' * 65}\n")


def main():
    args = sys.argv[1:]
    if not args:
        print("Usage:")
        print("  python3 assembly_composer.py compose <full_blueprint.json>")
        print("  python3 assembly_composer.py compose --2022")
        return

    if args[0] == "compose":
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

        layout = compose_robot(spec)
        display_layout(layout)

        # Save layout
        out_path = spec_path.with_name(spec_path.stem + "_layout.json")
        with open(out_path, "w") as f:
            json.dump(asdict(layout), f, indent=2, default=str)
        print(f"Layout saved to: {out_path}")


if __name__ == "__main__":
    main()
