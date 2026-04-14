#!/usr/bin/env python3
"""
blueprint/generators/elevator_rev2.py
Team 2950 — The Devastators

Phase 1 MCP elevator generator (B-MCP.2).
Implements: oracle → physics → MCP call sequence → Onshape assembly URL.

End-to-end path:
  oracle.py → ElevatorInputs → compute_elevator_physics() → build_elevator_assembly()
            → 50-60 mcp__onshape__* calls → cad.onshape.com URL

Usage:
  python3 blueprint/generators/elevator_rev2.py --game 2026_rebuilt
  python3 blueprint/generators/elevator_rev2.py --game 2026_rebuilt --dry-run
  python3 blueprint/generators/elevator_rev2.py --game 2026_rebuilt \\
      --doc-id <existing_onshape_doc_id> --check-interference

Account limit note:
  Free Onshape accounts are limited to 5 documents. Provide --doc-id with an
  existing document ID to reuse rather than create. If --doc-id is omitted,
  create_document is attempted (fails with 409 on full accounts).

Cascade coupling limitation (Phase 1 accepted):
  MCP has no create_linear_mate_relation tool. Phase 1 creates 2 independent
  Slider mates (one per stage). Cascade 2:1 coupling must be enforced manually
  or via a future eval_featurescript call. See BLUEPRINT_REV2_COPY_PARAMETRIZE.md
  Section 7 for rationale.

Do NOT import or call: cad_builder, assembly_builder, insert_cots.
Do NOT modify: oracle.py, motor_model.py, bom_rollup.py, assembly_composer.py.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Path setup — allow running from project root or blueprint/generators/
# ---------------------------------------------------------------------------
_HERE = Path(__file__).parent
_BLUEPRINT_DIR = _HERE.parent
if str(_BLUEPRINT_DIR) not in sys.path:
    sys.path.insert(0, str(_BLUEPRINT_DIR))

from motor_model import MOTOR_DB  # noqa: E402 — after path setup
from cots_parts.elevator_parts import (  # noqa: E402
    ELEVATOR_PARTS,
    resolve,
    resolve_spring_for_load,
    resolve_bearing_block,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ESTIMATED_END_EFFECTOR_LB: float = 5.0   # wrist + claw placeholder
BEARING_BLOCK_HEIGHT_IN:   float = 4.0   # lost travel at bearing blocks
TUBE_WEIGHT_PER_IN_LB:     float = 0.035 # 2x1x0.0625 tube linear density
TUBE_SPEC:                 str   = "2x1x0.0625"
BELT_SPEC:                 str   = "9mm HTD3"
PULLEY_TEETH:              int   = 18
MOTOR_COUNT:               int   = 2

# WCP stock spring ratings (lb) — spring_force rounds to nearest below load
_WCP_SPRING_RATINGS = [4, 8, 12, 16]

# Stage count thresholds
_STROKE_2STAGE_THRESHOLD_IN: float = 40.0  # >= 40" requires 2-stage

# Tube lengths available in elevator_parts (by length_in)
_TUBE_KEY_BY_LENGTH: dict[int, str] = {
    24: "stage_rail_2x1_24in",
    28: "stage_rail_2x1_28in",
    30: "stage_rail_2x1_30in",
    36: "stage_rail_2x1_36in",
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ElevatorInputs:
    """Oracle-derived inputs to the physics layer."""
    target_stroke_in:   float
    carriage_load_lb:   float
    game_piece_mass_lb: float
    motor_pref:         str   = "kraken_x60"
    rigging:            str   = "cascade"
    weight_budget_lb:   float = 20.0


@dataclass
class ElevatorPhysicsResult:
    """Fully-resolved physics decisions. No side effects, no I/O."""
    stage_count:              int
    tube_length_in:           float   # per stage
    tube_spec:                str
    carriage_plate_thickness_in: float
    motor_count:              int
    motor_type:               str
    gear_ratio:               int     # 5, 7, or 10
    belt_spec:                str
    pulley_teeth:             int
    spring_force_lb:          float
    spring_part_key:          str
    stage_part_key:           str     # key into ELEVATOR_PARTS
    carriage_part_key:        str
    layout_mm:                dict    # computed positions, keyed by instance role

    # Derived weight estimate (lb)
    estimated_weight_lb:      float = 0.0


@dataclass
class AssemblyResult:
    """Result returned by build_elevator_assembly()."""
    document_url:    str
    document_id:     str
    workspace_id:    str
    element_id:      str
    instance_count:  int
    slider_count:    int
    missing_parts:   list[str] = field(default_factory=list)
    wall_time_sec:   float = 0.0
    dry_run:         bool  = False

    def __str__(self) -> str:
        if self.dry_run:
            return "[DRY RUN] No Onshape document created."
        return (
            f"Assembly URL: {self.document_url}\n"
            f"  Instances : {self.instance_count}\n"
            f"  Slider mates: {self.slider_count}\n"
            f"  Wall time : {self.wall_time_sec:.1f}s"
        )


# ---------------------------------------------------------------------------
# Public interface — parse oracle output
# ---------------------------------------------------------------------------

def parse_oracle_output(oracle_json: dict) -> ElevatorInputs:
    """
    Extract ElevatorInputs from oracle.py's OracleOutput dict.
    Raises ValueError if required keys are missing or scorer != 'elevator'.
    """
    scorer = oracle_json.get("scorer", {})
    if scorer.get("type") != "elevator":
        raise ValueError(
            f"parse_oracle_output: scorer type is '{scorer.get('type')}', "
            "expected 'elevator'. Run oracle.py for a game that produces an "
            "elevator scorer (e.g., 2026_rebuilt)."
        )

    game_piece_mass_lb = float(scorer.get("game_piece_mass_lb", 1.0))
    carriage_load_lb = (
        game_piece_mass_lb + ESTIMATED_END_EFFECTOR_LB
    )

    return ElevatorInputs(
        target_stroke_in   = float(scorer.get("target_height_in", 48.0)),
        carriage_load_lb   = carriage_load_lb,
        game_piece_mass_lb = game_piece_mass_lb,
        motor_pref         = scorer.get("motor_preference", "kraken_x60"),
        rigging            = scorer.get("rigging", "cascade"),
        weight_budget_lb   = float(
            oracle_json.get("weight_budget", {}).get("scorer_lb", 20.0)
        ),
    )


# ---------------------------------------------------------------------------
# Physics layer — pure function
# ---------------------------------------------------------------------------

def compute_elevator_physics(inputs: ElevatorInputs) -> ElevatorPhysicsResult:
    """
    Compute all physics decisions for a cascade elevator.
    Pure function: no I/O, no side effects. Results drive MCP calls directly.
    """
    stroke = inputs.target_stroke_in
    load   = inputs.carriage_load_lb

    # Stage count
    stage_count = 2 if stroke >= _STROKE_2STAGE_THRESHOLD_IN else 1

    # Tube length per stage: stroke / stage_count + bearing block overhead
    tube_length_in = (stroke / stage_count) + BEARING_BLOCK_HEIGHT_IN

    # Round tube length up to nearest available stock length
    tube_length_in_rounded = _nearest_tube_length(tube_length_in)
    stage_part_key = _TUBE_KEY_BY_LENGTH.get(
        tube_length_in_rounded, "stage_rail_2x1_36in"
    )

    # Carriage plate thickness
    carriage_plate_thickness_in = 0.125 if load < 8.0 else 0.250
    carriage_part_key = (
        "carriage_plate_0125" if carriage_plate_thickness_in == 0.125
        else "carriage_plate_0250"
    )

    # Gear ratio: light < 5 lb → 5:1, medium 5–10 lb → 7:1, heavy > 10 lb → 10:1
    if load < 5.0:
        gear_ratio = 5
    elif load <= 10.0:
        gear_ratio = 7
    else:
        gear_ratio = 10

    # Motor type passthrough
    motor_type = inputs.motor_pref if inputs.motor_pref in ("kraken_x60", "neo") \
        else "kraken_x60"

    # Spring force: carriage_load rounded DOWN to nearest WCP stock rating
    spring_force_lb = _spring_for_load(load)
    spring_part_key = (
        "constant_force_spring_16lb_ttb" if spring_force_lb > 8
        else "constant_force_spring_4lb_wcp"
    )

    # Weight estimate
    tube_weight = tube_length_in_rounded * TUBE_WEIGHT_PER_IN_LB * 2 * stage_count
    motor_weight = MOTOR_DB[motor_type].weight_lb * MOTOR_COUNT
    carriage_weight = carriage_plate_thickness_in * 80 * 0.014  # 10x8in plate
    estimated_weight_lb = tube_weight + motor_weight + carriage_weight + 2.5  # misc

    # Layout positions (mm, world space)
    # Stage 1 left rail at origin; stage 2 offset 3" to the right on X
    tube_length_mm = tube_length_in_rounded * 25.4
    layout_mm = {
        "RAIL_S1_L": {"x": 0,   "y": 0,  "z": 0},
        "RAIL_S1_R": {"x": 254, "y": 0,  "z": 0},   # 10" rail spacing
        "RAIL_S2_L": {"x": 0,   "y": 0,  "z": 0},   # nested inside S1
        "RAIL_S2_R": {"x": 254, "y": 0,  "z": 0},
        "CARRIAGE":  {"x": 0,   "y": tube_length_mm * 0.5, "z": 0},
        "GEARBOX":   {"x": 127, "y": -76, "z": 0},   # 5" down from bottom
        "MOTOR_1":   {"x": 127, "y": -76, "z": 60},  # behind gearbox
        "MOTOR_2":   {"x": 127, "y": -76, "z": -60},
        "ENCODER":   {"x": 127, "y": -76, "z": 0},
    }

    return ElevatorPhysicsResult(
        stage_count              = stage_count,
        tube_length_in           = tube_length_in_rounded,
        tube_spec                = TUBE_SPEC,
        carriage_plate_thickness_in = carriage_plate_thickness_in,
        motor_count              = MOTOR_COUNT,
        motor_type               = motor_type,
        gear_ratio               = gear_ratio,
        belt_spec                = BELT_SPEC,
        pulley_teeth             = PULLEY_TEETH,
        spring_force_lb          = spring_force_lb,
        spring_part_key          = spring_part_key,
        stage_part_key           = stage_part_key,
        carriage_part_key        = carriage_part_key,
        layout_mm                = layout_mm,
        estimated_weight_lb      = estimated_weight_lb,
    )


def _nearest_tube_length(length_in: float) -> int:
    """Round up to the nearest available stock tube length in inches."""
    available = sorted(_TUBE_KEY_BY_LENGTH.keys())
    for stock in available:
        if length_in <= stock:
            return stock
    return available[-1]  # clamp to largest available


def _spring_for_load(load_lb: float) -> float:
    """Return nearest WCP spring rating at or below carriage load."""
    for rating in sorted(_WCP_SPRING_RATINGS, reverse=True):
        if rating <= load_lb:
            return float(rating)
    return float(_WCP_SPRING_RATINGS[0])  # minimum available


# ---------------------------------------------------------------------------
# MCP call sequence
# ---------------------------------------------------------------------------

def generate_elevator_assembly(
    oracle_json: dict,
    doc_id: Optional[str] = None,
    dry_run: bool = False,
    check_interference: bool = False,
    export_step: bool = False,
) -> AssemblyResult:
    """
    Top-level entry point. Orchestrates the full pipeline:
      parse → physics → MCP call sequence → AssemblyResult.

    Args:
        oracle_json: OracleOutput dict (from oracle.py or a fixture).
        doc_id:      Existing Onshape document ID to use. If None, attempts
                     create_document (fails on 5-doc-limit free accounts).
        dry_run:     If True, run parse + physics only; print JSON; no MCP writes.
        check_interference: If True, run interference check after assembly.
        export_step: If True, export STEP file after assembly.

    Returns:
        AssemblyResult with document_url, instance_count, slider_count.
    """
    inputs = parse_oracle_output(oracle_json)
    physics = compute_elevator_physics(inputs)

    if dry_run:
        result = asdict(physics)
        print(json.dumps(result, indent=2))
        return AssemblyResult(
            document_url="", document_id="", workspace_id="", element_id="",
            instance_count=0, slider_count=0, dry_run=True,
        )

    t0 = time.time()
    result = build_elevator_assembly(
        physics,
        doc_id=doc_id,
        check_interference=check_interference,
        export_step=export_step,
    )
    result.wall_time_sec = time.time() - t0
    return result


def build_elevator_assembly(
    physics: ElevatorPhysicsResult,
    doc_id: Optional[str] = None,
    check_interference: bool = False,
    export_step: bool = False,
) -> AssemblyResult:
    """
    Execute the full MCP call sequence (Phases A–F).
    Requires ONSHAPE_ACCESS_KEY env var or MCP server running.
    """
    missing_parts: list[str] = []

    # ── Phase A: Document + assembly shell ──────────────────────────────────
    doc_id, ws_id = _create_doc_and_assembly_prep(doc_id)
    asm_id = _create_assembly_element(doc_id, ws_id)

    # ── Phase B: Part Studios for geometry-created parts ────────────────────
    tube_elem_id = _create_tube_part_studio(
        doc_id, ws_id, physics.tube_length_in, physics.tube_spec
    )
    carriage_elem_id = _create_plate_part_studio(
        doc_id, ws_id, physics.carriage_plate_thickness_in
    )

    # ── Phase B: Insert instances ────────────────────────────────────────────
    instances = _insert_instances(
        doc_id, ws_id, asm_id,
        physics, tube_elem_id, carriage_elem_id,
        missing_parts,
    )

    # ── Phase C: Position instances ─────────────────────────────────────────
    _position_instances(doc_id, ws_id, asm_id, instances, physics)

    # ── Phase D: Get face IDs for mate creation ──────────────────────────────
    tube_faces = _get_tube_face_ids(doc_id, ws_id, tube_elem_id)
    carriage_faces = _get_plate_face_ids(doc_id, ws_id, carriage_elem_id)

    # ── Phase E: Add mates ──────────────────────────────────────────────────
    slider_count = _add_mates(
        doc_id, ws_id, asm_id,
        instances, physics, tube_faces, carriage_faces,
    )

    # ── Phase F: Optional validation ────────────────────────────────────────
    if check_interference:
        _run_interference_check(doc_id, ws_id, asm_id)
    if export_step:
        _export_assembly_step(doc_id, ws_id, asm_id)

    doc_url = f"https://cad.onshape.com/documents/{doc_id}"
    return AssemblyResult(
        document_url  = doc_url,
        document_id   = doc_id,
        workspace_id  = ws_id,
        element_id    = asm_id,
        instance_count= len(instances),
        slider_count  = slider_count,
        missing_parts = missing_parts,
    )


# ---------------------------------------------------------------------------
# Phase A helpers
# ---------------------------------------------------------------------------

def _create_doc_and_assembly_prep(doc_id: Optional[str]) -> tuple[str, str]:
    """
    Return (doc_id, workspace_id). Uses existing doc if doc_id provided,
    otherwise attempts create_document (409 on 5-doc-limit free accounts).
    """
    import importlib
    mcp = _get_mcp_module()

    if doc_id:
        summary = mcp.get_document_summary(doc_id)
        ws_id = summary["workspace_id"]
        print(f"[Phase A] Using existing document: {doc_id}, workspace: {ws_id}")
        return doc_id, ws_id

    # Try to create a new document
    from datetime import date
    doc_name = f"2950 Cascade Elevator — 2026_rebuilt {date.today().isoformat()}"
    result = mcp.create_document(name=doc_name)
    doc_id = result["documentId"]
    ws_id  = result["defaultWorkspaceId"]
    print(f"[Phase A] Created document: {doc_id}")
    return doc_id, ws_id


def _create_assembly_element(doc_id: str, ws_id: str) -> str:
    """Create the elevator Assembly element and return its element ID."""
    mcp = _get_mcp_module()
    result = mcp.create_assembly(
        documentId=doc_id, workspaceId=ws_id,
        name="Cascade Elevator Assembly"
    )
    asm_id = result["elementId"]
    print(f"[Phase A] Created assembly: {asm_id}")
    return asm_id


# ---------------------------------------------------------------------------
# Phase B helpers — geometry creation (tube + carriage)
# ---------------------------------------------------------------------------

def _create_tube_part_studio(
    doc_id: str, ws_id: str, length_in: float, tube_spec: str
) -> str:
    """Create a 2x1 tube Part Studio and return its element ID."""
    mcp = _get_mcp_module()
    ps_name = f"Rail Tube {tube_spec} {length_in:.0f}in"
    result = mcp.create_part_studio(
        documentId=doc_id, workspaceId=ws_id, name=ps_name
    )
    ps_id = result["elementId"]

    sketch = mcp.create_sketch_rectangle(
        documentId=doc_id, workspaceId=ws_id, elementId=ps_id,
        name="Tube Cross Section", plane="Front",
        corner1=[0, 0], corner2=[2.0, 1.0],
    )
    sketch_id = sketch["featureId"]

    mcp.create_extrude(
        documentId=doc_id, workspaceId=ws_id, elementId=ps_id,
        name="Tube Length", sketchFeatureId=sketch_id,
        depth=length_in,
    )
    print(f"[Phase B] Created tube Part Studio: {ps_id} ({length_in}in)")
    return ps_id


def _create_plate_part_studio(
    doc_id: str, ws_id: str, thickness_in: float
) -> str:
    """Create a carriage plate Part Studio and return its element ID."""
    mcp = _get_mcp_module()
    ps_name = f"Carriage Plate {thickness_in:.3f}in"
    result = mcp.create_part_studio(
        documentId=doc_id, workspaceId=ws_id, name=ps_name
    )
    ps_id = result["elementId"]

    sketch = mcp.create_sketch_rectangle(
        documentId=doc_id, workspaceId=ws_id, elementId=ps_id,
        name="Plate Footprint", plane="Front",
        corner1=[0, 0], corner2=[10.0, 8.0],
    )
    sketch_id = sketch["featureId"]

    mcp.create_extrude(
        documentId=doc_id, workspaceId=ws_id, elementId=ps_id,
        name="Plate Thickness", sketchFeatureId=sketch_id,
        depth=thickness_in,
    )
    print(f"[Phase B] Created carriage plate Part Studio: {ps_id} ({thickness_in}in)")
    return ps_id


# ---------------------------------------------------------------------------
# Phase B helpers — insert COTS instances
# ---------------------------------------------------------------------------

def _insert_instances(
    doc_id: str, ws_id: str, asm_id: str,
    physics: ElevatorPhysicsResult,
    tube_elem_id: str, carriage_elem_id: str,
    missing_parts: list[str],
) -> dict[str, str]:
    """
    Insert all part instances into the assembly.
    Returns dict mapping role name → instance ID.

    NOTE: add_assembly_instance returns instance_id="unknown" in its response.
    We always call get_assembly_positions after each batch to get real IDs.
    Strategy: insert one at a time, call get_assembly_positions, take the
    last (newest) instance ID each time.
    """
    mcp = _get_mcp_module()
    instances: dict[str, str] = {}

    def _add_and_capture(role: str, part_studio_id: str,
                         is_asm: bool = False, part_id: Optional[str] = None) -> str:
        """Insert instance and return its real ID via get_assembly_positions."""
        kwargs = dict(
            documentId=doc_id, workspaceId=ws_id, elementId=asm_id,
            partStudioElementId=part_studio_id, isAssembly=is_asm,
        )
        if part_id:
            kwargs["partId"] = part_id
        mcp.add_assembly_instance(**kwargs)
        positions = mcp.get_assembly_positions(
            documentId=doc_id, workspaceId=ws_id, elementId=asm_id
        )
        # Newest instance is last in list
        inst_id = positions["instances"][-1]["id"]
        instances[role] = inst_id
        print(f"[Phase B]   {role} → instance {inst_id}")
        return inst_id

    def _try_add_cots(role: str, part_key: str) -> Optional[str]:
        """Add a COTS part; on failure log to missing_parts and return None."""
        try:
            part = resolve(part_key)
            if part.get("is_asm") is None:
                missing_parts.append(
                    f"{role}: geometry-created part '{part_key}' — skipping COTS insert"
                )
                return None
            return _add_and_capture(
                role,
                part["elem"],
                is_asm=bool(part.get("is_asm")),
                part_id=part.get("part_id") or None,
            )
        except Exception as e:
            missing_parts.append(f"{role}: {e}")
            print(f"[Phase B]   WARNING: {role} failed — {e}")
            return None

    # Rail tubes (geometry-created — insert from our Part Studio)
    _add_and_capture("RAIL_S1_L", tube_elem_id, is_asm=False)
    _add_and_capture("RAIL_S1_R", tube_elem_id, is_asm=False)
    if physics.stage_count == 2:
        _add_and_capture("RAIL_S2_L", tube_elem_id, is_asm=False)
        _add_and_capture("RAIL_S2_R", tube_elem_id, is_asm=False)

    # Carriage plate (geometry-created)
    _add_and_capture("CARRIAGE", carriage_elem_id, is_asm=False)

    # Bearing blocks — 4 per moving stage
    bb_count = 4 * physics.stage_count
    bb_part = resolve("wcp_elevator_bearing_block_inline")
    for i in range(bb_count):
        try:
            _add_and_capture(
                f"BB_{i+1}", bb_part["elem"],
                is_asm=True, part_id=None,
            )
        except Exception as e:
            missing_parts.append(f"BB_{i+1}: {e}")
            print(f"[Phase B]   WARNING: BB_{i+1} failed — {e}")

    # Motors
    motor_part = resolve(physics.motor_type)
    if motor_part.get("is_asm") is None:
        missing_parts.append("MOTOR_*: geometry-only motor part")
    else:
        for mi in range(MOTOR_COUNT):
            try:
                _add_and_capture(
                    f"MOTOR_{mi+1}", motor_part["elem"],
                    is_asm=bool(motor_part.get("is_asm")),
                    part_id=motor_part.get("part_id") or None,
                )
            except Exception as e:
                missing_parts.append(f"MOTOR_{mi+1}: {e}")

    # Gearbox
    _try_add_cots("GEARBOX", "wcp_greyt_telescope_gearbox")

    # Encoder
    _try_add_cots("ENCODER", "through_bore_encoder")

    # Springs (2 springs)
    spring_key = physics.spring_part_key
    for si in range(2):
        _try_add_cots(f"SPRING_{si+1}", spring_key)

    return instances


# ---------------------------------------------------------------------------
# Phase C — position instances
# ---------------------------------------------------------------------------

def _position_instances(
    doc_id: str, ws_id: str, asm_id: str,
    instances: dict[str, str],
    physics: ElevatorPhysicsResult,
) -> None:
    """Move instances to their computed positions from layout_mm."""
    mcp = _get_mcp_module()
    MM_TO_IN = 1.0 / 25.4

    for role, inst_id in instances.items():
        pos = physics.layout_mm.get(role)
        if not pos:
            continue
        x_in = pos["x"] * MM_TO_IN
        y_in = pos["y"] * MM_TO_IN
        z_in = pos["z"] * MM_TO_IN
        if x_in == 0.0 and y_in == 0.0 and z_in == 0.0:
            continue  # already at origin
        try:
            mcp.transform_instance(
                documentId=doc_id, workspaceId=ws_id, elementId=asm_id,
                instanceId=inst_id,
                translateX=x_in, translateY=y_in, translateZ=z_in,
            )
            print(f"[Phase C]   {role} positioned to ({x_in:.2f}, {y_in:.2f}, {z_in:.2f}) in")
        except Exception as e:
            print(f"[Phase C]   WARNING: position {role} failed — {e}")


# ---------------------------------------------------------------------------
# Phase D — get face IDs
# ---------------------------------------------------------------------------

def _get_tube_face_ids(doc_id: str, ws_id: str, tube_elem_id: str) -> dict:
    """Get face IDs from the tube Part Studio."""
    mcp = _get_mcp_module()
    details = mcp.get_body_details(
        documentId=doc_id, workspaceId=ws_id, elementId=tube_elem_id
    )
    # Return the raw face dict indexed by normal direction
    faces: dict[str, str] = {}
    for body in details.get("bodies", [details]):
        for face in body.get("faces", []):
            normal = face.get("normal", {})
            nx, ny, nz = normal.get("x", 0), normal.get("y", 0), normal.get("z", 0)
            if ny > 0.5:
                faces["top_y"] = face["id"]   # +Y = top end of tube
            elif ny < -0.5:
                faces["bot_y"] = face["id"]   # -Y = bottom end of tube
    return faces


def _get_plate_face_ids(doc_id: str, ws_id: str, plate_elem_id: str) -> dict:
    """Get face IDs from the carriage plate Part Studio."""
    mcp = _get_mcp_module()
    details = mcp.get_body_details(
        documentId=doc_id, workspaceId=ws_id, elementId=plate_elem_id
    )
    faces: dict[str, str] = {}
    for body in details.get("bodies", [details]):
        for face in body.get("faces", []):
            normal = face.get("normal", {})
            nz = normal.get("z", 0)
            if nz < -0.5:
                faces["bot_z"] = face["id"]   # -Z = bottom of plate
    return faces


# ---------------------------------------------------------------------------
# Phase E — add mates
# ---------------------------------------------------------------------------

def _add_mates(
    doc_id: str, ws_id: str, asm_id: str,
    instances: dict[str, str],
    physics: ElevatorPhysicsResult,
    tube_faces: dict, carriage_faces: dict,
) -> int:
    """
    Add slider mates (one per moving stage) and fastened mates for rigid joints.
    Returns number of slider mates created successfully.

    Cascade coupling limitation: Phase 1 accepts 2 independent Slider DOFs.
    See module docstring for rationale.
    """
    mcp = _get_mcp_module()
    slider_count = 0

    # Fall back face IDs if geometry extraction failed
    top_face = tube_faces.get("top_y", "JHG")   # matches pre-flight scratch face
    bot_face = tube_faces.get("bot_y", "JHK")

    # ── Slider 1: Stage 2 slides on Stage 1 ────────────────────────────────
    if physics.stage_count == 2:
        s2l = instances.get("RAIL_S2_L")
        s1l = instances.get("RAIL_S1_L")
        if s2l and s1l:
            try:
                mcp.create_slider_mate(
                    documentId=doc_id, workspaceId=ws_id, elementId=asm_id,
                    name="Slider — Stage 2 on Stage 1",
                    firstInstanceId=s2l,  firstFaceId=bot_face,
                    secondInstanceId=s1l, secondFaceId=top_face,
                    minLimit=0.0,
                    maxLimit=float(physics.tube_length_in),
                )
                slider_count += 1
                print("[Phase E] Slider 1: Stage 2 on Stage 1 — OK")
            except Exception as e:
                print(f"[Phase E] WARNING: Slider 1 failed — {e}")

    # ── Slider 2: Carriage slides on top stage ──────────────────────────────
    carriage = instances.get("CARRIAGE")
    top_stage = instances.get(
        "RAIL_S2_L" if physics.stage_count == 2 else "RAIL_S1_L"
    )
    if carriage and top_stage:
        # Carriage plate uses its bottom-Z face; tube uses its top-Y face
        carriage_bot = carriage_faces.get("bot_z", bot_face)
        try:
            mcp.create_slider_mate(
                documentId=doc_id, workspaceId=ws_id, elementId=asm_id,
                name="Slider — Carriage on Stage",
                firstInstanceId=carriage,  firstFaceId=carriage_bot,
                secondInstanceId=top_stage, secondFaceId=top_face,
                minLimit=0.0,
                maxLimit=float(physics.tube_length_in),
            )
            slider_count += 1
            print("[Phase E] Slider 2: Carriage on Stage — OK")
        except Exception as e:
            print(f"[Phase E] WARNING: Slider 2 failed — {e}")

    # ── Fastened mates for rigid joints ─────────────────────────────────────
    # Gearbox to Stage 1 bottom (if both inserted successfully)
    gearbox = instances.get("GEARBOX")
    s1l = instances.get("RAIL_S1_L")
    if gearbox and s1l:
        try:
            mcp.create_fastened_mate(
                documentId=doc_id, workspaceId=ws_id, elementId=asm_id,
                name="Fastened — Gearbox to Rail S1",
                firstInstanceId=gearbox,  firstFaceId=top_face,
                secondInstanceId=s1l,     secondFaceId=bot_face,
                secondOffsetZ=-3.0,  # 3" below tube bottom
            )
            print("[Phase E] Fastened: Gearbox to Rail S1 — OK")
        except Exception as e:
            print(f"[Phase E] WARNING: Fastened gearbox failed — {e}")

    return slider_count


# ---------------------------------------------------------------------------
# Phase F — optional validation
# ---------------------------------------------------------------------------

def _run_interference_check(doc_id: str, ws_id: str, asm_id: str) -> None:
    mcp = _get_mcp_module()
    try:
        result = mcp.check_assembly_interference(
            documentId=doc_id, workspaceId=ws_id, elementId=asm_id
        )
        count = result.get("interference_count", "unknown")
        print(f"[Phase F] Interference check: {count} interferences")
    except Exception as e:
        print(f"[Phase F] WARNING: Interference check failed — {e}")


def _export_assembly_step(doc_id: str, ws_id: str, asm_id: str) -> None:
    mcp = _get_mcp_module()
    try:
        result = mcp.export_assembly(
            documentId=doc_id, workspaceId=ws_id, elementId=asm_id,
            format="STEP",
        )
        print(f"[Phase F] STEP export: {result.get('href', 'done')}")
    except Exception as e:
        print(f"[Phase F] WARNING: Export failed — {e}")


# ---------------------------------------------------------------------------
# MCP module wrapper
# ---------------------------------------------------------------------------

class _MCPModule:
    """
    Thin wrapper that exposes mcp__onshape__* calls as method calls.
    In production these delegate to the live MCP tool functions.
    In tests this object is replaced by a mock via dependency injection.

    The wrapper normalises the response format:
    - get_document_summary → {"workspace_id": ..., "element_ids": [...]}
    - create_document      → {"documentId": ..., "defaultWorkspaceId": ...}
    - create_assembly      → {"elementId": ...}
    - create_part_studio   → {"elementId": ...}
    - create_sketch_rectangle → {"featureId": ...}
    - create_extrude       → {"featureId": ...}
    - add_assembly_instance → (side effect; real ID via get_assembly_positions)
    - get_assembly_positions → {"instances": [{"id": ..., "name": ...}, ...]}
    - get_body_details     → {"bodies": [...face data...]}
    - transform_instance   → (side effect)
    - create_slider_mate   → {"featureId": ...}
    - create_fastened_mate → {"featureId": ...}
    - create_mate_connector → {"featureId": ...}
    - check_assembly_interference → {"interference_count": int}
    - export_assembly      → {"href": ...}
    """

    def get_document_summary(self, doc_id: str) -> dict:
        from mcp__onshape import get_document_summary as _f
        raw = _f(documentId=doc_id)
        # Extract first workspace
        ws = raw.get("workspaces", [{}])[0]
        return {"workspace_id": ws.get("id", ""), "raw": raw}

    def create_document(self, name: str) -> dict:
        from mcp__onshape import create_document as _f
        return _f(name=name)

    def create_assembly(self, **kw) -> dict:
        from mcp__onshape import create_assembly as _f
        return _f(**kw)

    def create_part_studio(self, **kw) -> dict:
        from mcp__onshape import create_part_studio as _f
        return _f(**kw)

    def create_sketch_rectangle(self, **kw) -> dict:
        from mcp__onshape import create_sketch_rectangle as _f
        return _f(**kw)

    def create_extrude(self, **kw) -> dict:
        from mcp__onshape import create_extrude as _f
        return _f(**kw)

    def add_assembly_instance(self, **kw) -> dict:
        from mcp__onshape import add_assembly_instance as _f
        return _f(**kw)

    def get_assembly_positions(self, **kw) -> dict:
        from mcp__onshape import get_assembly_positions as _f
        return _f(**kw)

    def get_body_details(self, **kw) -> dict:
        from mcp__onshape import get_body_details as _f
        return _f(**kw)

    def transform_instance(self, **kw) -> dict:
        from mcp__onshape import transform_instance as _f
        return _f(**kw)

    def create_slider_mate(self, **kw) -> dict:
        from mcp__onshape import create_slider_mate as _f
        return _f(**kw)

    def create_fastened_mate(self, **kw) -> dict:
        from mcp__onshape import create_fastened_mate as _f
        return _f(**kw)

    def create_mate_connector(self, **kw) -> dict:
        from mcp__onshape import create_mate_connector as _f
        return _f(**kw)

    def check_assembly_interference(self, **kw) -> dict:
        from mcp__onshape import check_assembly_interference as _f
        return _f(**kw)

    def export_assembly(self, **kw) -> dict:
        from mcp__onshape import export_assembly as _f
        return _f(**kw)


_MCP_INSTANCE: Optional[_MCPModule] = None


def _get_mcp_module() -> _MCPModule:
    global _MCP_INSTANCE
    if _MCP_INSTANCE is None:
        _MCP_INSTANCE = _MCPModule()
    return _MCP_INSTANCE


def set_mcp_module(mock_module) -> None:
    """Dependency-inject a mock MCP module for testing."""
    global _MCP_INSTANCE
    _MCP_INSTANCE = mock_module


# ---------------------------------------------------------------------------
# Sample oracle output for 2026_rebuilt game
# ---------------------------------------------------------------------------

ORACLE_2026_REBUILT = {
    "scorer": {
        "type": "elevator",
        "elevator_stages": 2,
        "target_height_in": 48.0,
        "game_piece_mass_lb": 1.5,
        "motor_preference": "kraken_x60",
        "rigging": "cascade",
    },
    "weight_budget": {
        "scorer_lb": 18.0,
    },
    "endgame": {
        "type": "none",
    },
}

ORACLE_BY_GAME: dict[str, dict] = {
    "2026_rebuilt": ORACLE_2026_REBUILT,
}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Team 2950 Cascade Elevator Generator — Rev 2 (MCP)"
    )
    parser.add_argument(
        "--game", default="2026_rebuilt",
        choices=list(ORACLE_BY_GAME.keys()),
        help="Game name (selects oracle output fixture)",
    )
    parser.add_argument(
        "--oracle-json", type=Path, default=None,
        help="Path to oracle JSON file (overrides --game fixture)",
    )
    parser.add_argument(
        "--doc-id", default=None,
        help="Existing Onshape document ID to use (required on free accounts)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Run physics only; print ElevatorPhysicsResult JSON; no MCP writes",
    )
    parser.add_argument(
        "--check-interference", action="store_true",
        help="Run interference check after assembly (slow)",
    )
    parser.add_argument(
        "--export-step", action="store_true",
        help="Export STEP file after assembly",
    )
    args = parser.parse_args()

    if args.oracle_json:
        oracle = json.loads(args.oracle_json.read_text())
    else:
        oracle = ORACLE_BY_GAME[args.game]

    result = generate_elevator_assembly(
        oracle_json=oracle,
        doc_id=args.doc_id,
        dry_run=args.dry_run,
        check_interference=args.check_interference,
        export_step=args.export_step,
    )

    print(result)

    if not args.dry_run:
        # Append wall-time measurement to spec doc as required by DoD
        _append_wall_time_note(result)


def _append_wall_time_note(result: AssemblyResult) -> None:
    """Append measured wall time to BLUEPRINT_REV2_COPY_PARAMETRIZE.md per DoD."""
    spec_path = (
        Path(__file__).parent.parent.parent
        / "design-intelligence"
        / "BLUEPRINT_REV2_COPY_PARAMETRIZE.md"
    )
    if not spec_path.exists():
        return
    note = (
        f"\n\n---\n*Phase 1 wall time measurement (auto-appended by elevator_rev2.py):*\n"
        f"Run date: {__import__('datetime').date.today().isoformat()}\n"
        f"Total wall time: {result.wall_time_sec:.1f}s\n"
        f"Instance count: {result.instance_count}\n"
        f"Slider mates: {result.slider_count}\n"
    )
    with open(spec_path, "a") as f:
        f.write(note)


if __name__ == "__main__":
    main()
