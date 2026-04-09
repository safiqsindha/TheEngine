#!/usr/bin/env python3
"""
The Blueprint — Dry Run Script (B.7)
Team 2950 — The Devastators

Runs the full Oracle → Blueprint pipeline for any game year.
Takes an oracle prediction JSON and outputs:
  1. All mechanism specs
  2. BOM rollup
  3. Assembly layout
  4. FeatureScript for OnShape
  5. CSV export

Usage:
  python3 run_dry_run.py 2022_rapid_react_oracle.json
  python3 run_dry_run.py 2024_crescendo_oracle.json
  python3 run_dry_run.py 2023_charged_up_oracle.json
"""

import json
import sys
from dataclasses import asdict
from pathlib import Path

BASE_DIR = Path(__file__).parent

# Generators
from frame_generator import generate_frame
from intake_generator import generate_intake
from flywheel_generator import generate_flywheel
from elevator_generator import generate_elevator
from arm_generator import generate_arm
from conveyor_generator import generate_conveyor
from climber_generator import generate_climber
from turret_generator import generate_turret
from bom_rollup import BOMRollup, MotorAllocation, export_bom_csv, export_bom_json
from assembly_composer import compose_robot, display_layout
from cad_builder import generate_full_featurescript, generate_real_frame_featurescript
from motor_model import MOTOR_DB


def run_full_pipeline(oracle_path: str):
    """Run the complete Blueprint pipeline from Oracle JSON."""
    with open(oracle_path) as f:
        oracle = json.load(f)

    game = oracle.get("game_name", "Unknown")
    year = oracle.get("season_year", 0)
    print(f"\n{'═' * 65}")
    print(f"  THE ENGINE — FULL BLUEPRINT DRY RUN")
    print(f"  {year} {game}")
    print(f"{'═' * 65}\n")

    specs = {}
    log = []

    # ── Frame ──
    dt = oracle["drivetrain"]
    module_type = dt.get("module", "sds_mk4i")

    try:
        frame = generate_frame(
            frame_length_in=dt.get("frame_length_in", 27.0),
            frame_width_in=dt.get("frame_width_in", 27.0),
            module_type=module_type,
        )
        specs["frame"] = asdict(frame)
        log.append(f"[OK] Frame: {dt['frame_length_in']}\"x{dt['frame_width_in']}\" {dt.get('module', 'sds_mk4i')}, {frame.total_weight_lb} lb")
    except Exception as e:
        log.append(f"[FAIL] Frame: {e}")
        specs["frame"] = {"frame_length_in": 27.0, "frame_width_in": 27.0, "frame_height_in": 1.0, "total_weight_lb": 40.0}

    # ── Intake ──
    intake_cfg = oracle.get("intake", {})
    if intake_cfg:
        game_piece = intake_cfg.get("game_piece", "")
        # Extract diameter from game piece description
        piece_dia = 4.5  # default
        if "9.5" in game_piece:
            piece_dia = 9.5
        elif "14" in game_piece:
            piece_dia = 14.0
        elif "12.5" in game_piece:
            piece_dia = 12.5

        # Piece weight
        piece_weight = 0.5
        if "0.59" in game_piece or "9.5 oz" in game_piece:
            piece_weight = 0.59
        elif "0.44" in game_piece:
            piece_weight = 0.44
        elif "0.55" in game_piece:
            piece_weight = 0.55
        elif "0.8" in game_piece:
            piece_weight = 0.8

        intake_type = intake_cfg.get("type", "over_bumper")
        roller_material = intake_cfg.get("roller_material", "flex_wheels")
        deploy = intake_cfg.get("deploy", True)

        try:
            intake_spec = generate_intake(
                intake_type=intake_type,
                game_piece_diameter_in=piece_dia,
                roller_material=roller_material,
                deploy_type="pivot" if deploy else "none",
                drivetrain_speed_fps=dt.get("speed_fps", 16.0),
                frame_width_in=dt.get("frame_width_in", 27.0),
                preset_name=f"{year}_{game.lower().replace(' ', '_')}",
            )
            specs["intake"] = asdict(intake_spec)
            log.append(f"[OK] Intake: {intake_type}, {piece_dia}\" piece, {intake_spec.total_weight_lb} lb")
        except Exception as e:
            log.append(f"[FAIL] Intake: {e}")

    # ── Scorer ──
    scorer_cfg = oracle.get("scorer", {})
    if scorer_cfg:
        method = scorer_cfg.get("method", "")

        if method == "flywheel":
            # Extract piece parameters
            piece_mass = piece_weight if intake_cfg else 0.5

            try:
                flywheel_spec = generate_flywheel(
                    wheel_diameter_in=6.0,
                    wheel_count=2,
                    motor_type="neo_vortex",
                    motor_count=scorer_cfg.get("motors", 2),
                    gear_ratio=1.0,
                    target_rpm=4000.0,
                    piece_mass_lb=piece_mass,
                    piece_diameter_in=piece_dia if intake_cfg else 4.5,
                    preset_name=f"{year}_shooter",
                )
                specs["flywheel"] = asdict(flywheel_spec)
                log.append(f"[OK] Flywheel: {flywheel_spec.target_rpm} RPM, {flywheel_spec.total_weight_lb} lb")
            except Exception as e:
                log.append(f"[FAIL] Flywheel: {e}")

            # Add conveyor/indexer between intake and shooter
            try:
                conveyor_spec = generate_conveyor(
                    path_length_in=24.0,
                    game_piece_diameter_in=piece_dia if intake_cfg else 4.5,
                    staging_count=2,
                    motor_type="neo_550",
                    motor_count=1,
                    gear_ratio=5.0,
                    preset_name=f"{year}_indexer",
                )
                specs["conveyor"] = asdict(conveyor_spec)
                log.append(f"[OK] Conveyor: {conveyor_spec.path_length_in}\" path, {conveyor_spec.total_weight_lb} lb")
            except Exception as e:
                log.append(f"[FAIL] Conveyor: {e}")

        elif method == "elevator":
            height = scorer_cfg.get("height_in", 48.0)
            if height <= 0:
                height = 48.0
            motor_count = scorer_cfg.get("motors", 2)

            try:
                elev_spec = generate_elevator(
                    travel_height_in=height,
                    end_effector_weight_lb=8.0,
                    motor_type="kraken_x60" if motor_count >= 2 else "neo",
                    motor_count=motor_count,
                    rigging_type="continuous",
                    name=f"2950 {game} Elevator",
                )
                specs["elevator"] = asdict(elev_spec)
                log.append(f"[OK] Elevator: {height}\" travel, {elev_spec.stage_count} stages, {elev_spec.total_weight_lb} lb")
            except Exception as e:
                log.append(f"[FAIL] Elevator: {e}")

            # Wrist if specified
            if scorer_cfg.get("has_wrist", False):
                try:
                    arm_spec = generate_arm(
                        arm_length_in=8.0,
                        com_distance_in=4.0,
                        arm_mass_lb=1.5,
                        end_effector_weight_lb=2.0,
                        motor_type="neo_550",
                        motor_count=1,
                        gear_ratio=50.0,
                        start_angle_deg=-45.0,
                        end_angle_deg=90.0,
                        preset_name=f"{year}_wrist",
                    )
                    specs["arm"] = asdict(arm_spec)
                    log.append(f"[OK] Wrist: {arm_spec.total_weight_lb} lb")
                except Exception as e:
                    log.append(f"[FAIL] Wrist: {e}")

    # ── Turret ──
    if scorer_cfg.get("turret", "none") != "none":
        try:
            turret_spec = generate_turret(
                preset_name=f"{year}_turret",
            )
            specs["turret"] = asdict(turret_spec)
            log.append(f"[OK] Turret: {turret_spec.total_weight_lb} lb")
        except Exception as e:
            log.append(f"[FAIL] Turret: {e}")

    # ── Endgame ──
    endgame_cfg = oracle.get("endgame", {})
    if endgame_cfg and endgame_cfg.get("type", "none") not in ("none", "park_only"):
        style_map = {"hook_winch": "winch", "telescope": "telescope"}
        climb_style = style_map.get(endgame_cfg["type"], "winch")
        climb_height = endgame_cfg.get("height_in", 26.0)
        if climb_height <= 0:
            climb_height = 26.0

        try:
            climber_spec = generate_climber(
                climb_height_in=climb_height,
                robot_weight_lb=125.0,
                climb_style=climb_style,
                motor_type="neo",
                motor_count=endgame_cfg.get("motors", 2),
                gear_ratio=60.0,
                spool_diameter_in=1.25,
                preset_name=f"{year}_{endgame_cfg['type']}",
            )
            specs["climber"] = asdict(climber_spec)
            log.append(f"[OK] Climber: {climb_style}, {climb_height}\", {climber_spec.total_weight_lb} lb")
        except Exception as e:
            log.append(f"[FAIL] Climber: {e}")

    # ── BOM Rollup ──
    print("  Building BOM rollup...")
    bom = BOMRollup()
    frame_weight = specs.get("frame", {}).get("total_weight_lb", 40.0)
    bom.drivetrain_weight_lb = frame_weight

    # Register mechanisms
    for mech_name in ["intake", "flywheel", "conveyor", "elevator", "arm", "climber", "turret"]:
        if mech_name not in specs:
            continue
        s = specs[mech_name]
        motor_type = s.get("motor_type", s.get("roller_motor_type", "neo"))
        bom.mechanisms[mech_name] = {
            "preset": s.get("preset_name", mech_name),
            "weight_lb": s.get("total_weight_lb", 0),
            "motor_type": motor_type,
            "motor_count": s.get("motor_count", s.get("roller_motor_count", 1)),
            "current_limit_a": s.get("current_limit_a", 40.0),
            "peak_current_a": s.get("peak_current_a", s.get("spinup_peak_current_a", 40.0)),
            "holding_current_a": s.get("holding_current_a", 5.0),
            "parts": s.get("parts_list", []),
            "software_constants": s.get("software_constants", {}),
        }

    # Aggregate
    bom.mechanism_weight_lb = round(sum(m["weight_lb"] for m in bom.mechanisms.values()), 2)
    bom.total_weight_lb = round(bom.mechanism_weight_lb + bom.drivetrain_weight_lb +
                                 bom.bumper_weight_lb + bom.battery_weight_lb + bom.electronics_weight_lb, 2)
    bom.weight_margin_lb = round(125.0 - bom.total_weight_lb, 2)
    bom.weight_ok = bom.weight_margin_lb >= 0

    # Motors
    bom.motors = [
        MotorAllocation("drivetrain_drive", "kraken_x60", "Kraken X60", 4, 40.0, 40.0, 5.0),
        MotorAllocation("drivetrain_steer", "neo_550", "NEO 550", 4, 20.0, 20.0, 2.0),
    ]
    for mech_name, mech in bom.mechanisms.items():
        mt = mech["motor_type"]
        motor_name = MOTOR_DB[mt].name if mt in MOTOR_DB else mt
        bom.motors.append(MotorAllocation(
            mech_name, mt, motor_name, mech["motor_count"],
            mech["current_limit_a"], mech["peak_current_a"], mech["holding_current_a"],
        ))

    bom.total_motor_count = sum(m.count for m in bom.motors)
    bom.total_can_devices = bom.total_motor_count + 3
    bom.peak_current_total_a = round(sum(m.peak_current_a * m.count for m in bom.motors), 1)
    bom.sustained_current_total_a = round(sum(m.holding_current_a * m.count for m in bom.motors), 1)

    for mech_name, mech in bom.mechanisms.items():
        for part in mech.get("parts", []):
            bom.combined_parts.append({**part, "mechanism": mech_name})

    bom.notes = []
    if bom.weight_ok:
        bom.notes.append(f"Weight margin: {bom.weight_margin_lb} lb — {'healthy' if bom.weight_margin_lb > 10 else 'tight'}")
    else:
        bom.notes.append(f"OVERWEIGHT by {abs(bom.weight_margin_lb)} lb")

    specs["bom_rollup"] = asdict(bom)

    # ── Assembly Layout ──
    print("  Computing assembly layout...")
    full_spec = {**specs, "game": game, "year": year}
    layout = compose_robot(full_spec)
    display_layout(layout)

    # ── Output ──
    output = {
        "game": game,
        "year": year,
        "generated_by": "The Engine — Full Blueprint Pipeline",
        "rules_applied": "CROSS_SEASON_PATTERNS R1-R19",
        **specs,
        "scoring_analysis": oracle.get("scoring_analysis", {}),
        "auto_strategy": {
            "primary": f"{oracle.get('autonomous', {}).get('estimated_pieces', 1)}-piece auto",
            "actions": oracle.get("autonomous", {}).get("priority_actions", []),
        },
        "build_order": oracle.get("build_order", []),
    }

    # Save outputs
    stem = f"{year}_{game.lower().replace(' ', '_')}"
    json_path = BASE_DIR / f"{stem}_full_blueprint.json"
    with open(json_path, "w") as f:
        json.dump(output, f, indent=2)

    csv_path = BASE_DIR / f"{stem}_bom.csv"
    export_bom_csv(bom, str(csv_path))

    fs_code = generate_full_featurescript(full_spec)
    fs_path = BASE_DIR / f"{stem}_featurescript.fs"
    with open(fs_path, "w") as f:
        f.write(fs_code)

    # Real frame FeatureScript (hollow tubes, cutouts, bolt holes)
    real_fs_code = generate_real_frame_featurescript(full_spec)
    real_fs_path = BASE_DIR / f"{stem}_real_frame.fs"
    with open(real_fs_path, "w") as f:
        f.write(real_fs_code)

    # Assembly manifest (COTS parts list with positions)
    from assembly_builder import generate_manifest, display_manifest
    manifest = generate_manifest(full_spec)
    manifest_path = BASE_DIR / f"{stem}_assembly_manifest.json"
    with open(manifest_path, "w") as f:
        from dataclasses import asdict as _asdict
        json.dump(_asdict(manifest), f, indent=2)

    # Print summary
    print(f"\n{'═' * 65}")
    print(f"  PIPELINE COMPLETE — {year} {game}")
    print(f"{'═' * 65}")
    print(f"\n  Generation Log:")
    for entry in log:
        print(f"    {entry}")
    print(f"\n  WEIGHT: {bom.total_weight_lb} lb / 125 lb (margin: {bom.weight_margin_lb} lb)")
    print(f"  MOTORS: {bom.total_motor_count} total, {bom.total_can_devices} CAN devices")
    print(f"  ASSEMBLY: {manifest.total_instances} COTS part instances, {manifest.total_cots_parts} unique parts")
    print(f"\n  Output Files:")
    print(f"    Blueprint JSON:     {json_path.name}")
    print(f"    BOM CSV:            {csv_path.name}")
    print(f"    FeatureScript:      {fs_path.name}")
    print(f"    Real Frame FS:      {real_fs_path.name}")
    print(f"    Assembly Manifest:  {manifest_path.name}")
    print(f"\n{'═' * 65}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 run_dry_run.py <oracle_prediction.json>")
        print("\nAvailable predictions:")
        for f in sorted(BASE_DIR.glob("*_oracle.json")):
            print(f"  {f.name}")
        sys.exit(0)

    run_full_pipeline(sys.argv[1])
