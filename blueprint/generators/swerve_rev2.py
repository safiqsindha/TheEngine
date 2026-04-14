#!/usr/bin/env python3
"""
blueprint/generators/swerve_rev2.py
Team 2950 — The Devastators

Phase 2 MCP swerve frame generator (B-MCP.3).
Implements: oracle → physics → MCP call sequence → Onshape assembly URL.

End-to-end path:
  oracle.py → SwerveInputs → compute_swerve_physics() → build_swerve_assembly()
            → ~35-45 mcp__onshape__* calls → cad.onshape.com URL

Usage:
  python3 blueprint/generators/swerve_rev2.py --dry-run
  python3 blueprint/generators/swerve_rev2.py --doc-id <existing_onshape_doc_id>
  python3 blueprint/generators/swerve_rev2.py \\
      --wheelbase 26.0 --trackwidth 26.0 --module-type sds_mk4i \\
      --doc-id <existing_onshape_doc_id>

Account limit note:
  Free Onshape accounts are limited to 5 documents. Provide --doc-id with an
  existing document ID to reuse rather than create. If --doc-id is omitted,
  create_document is attempted (fails with 409 on full accounts).

Scope (Phase 2):
  Structural frame only: perimeter rail tubes (long + short), 4 corner gussets,
  4 swerve module instances fastened at module-mount positions.
  No belly pan, no bumper mounts, no electrical layout — Phase 3.

Mate type note:
  Swerve frame is rigid. Only fastened mates are used (no Slider, no Revolute).
  Swerve module gearboxes are inside the module assembly — not separate instances.

Module coverage note:
  SDS MK4i is the canonical FRCDesignLib module (verified 2026-04-13).
  WCP Swerve X and REV MaxSwerve are not yet in FRCDesignLib; generator warns
  and falls back to SDS MK4i when these are requested.

Do NOT import or call: cad_builder, assembly_builder, insert_cots.
Do NOT modify: oracle.py, motor_model.py, bom_rollup.py, assembly_composer.py.
"""

from __future__ import annotations

import argparse
import json
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

from cots_parts.swerve_parts import (  # noqa: E402
    SWERVE_PARTS,
    resolve,
    resolve_module,
    validate_all as validate_swerve_parts,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
RAIL_SPEC:             str   = "2x1x0.0625"
TUBE_WEIGHT_PER_IN_LB: float = 0.035   # 2x1x0.0625 linear density (lb/in)
MODULE_WEIGHT_LB:      float = 4.2     # SDS MK4i spec weight per module
MODULE_COUNT:          int   = 4
GUSSET_COUNT:          int   = 4
GUSSET_WEIGHT_LB:      float = 1.5     # WCP 90° gusset approx weight × 4 (total)

# Default oracle values for standalone CLI use
DEFAULT_WHEELBASE_IN:  float = 26.0
DEFAULT_TRACKWIDTH_IN: float = 26.0
DEFAULT_MODULE_TYPE:   str   = "sds_mk4i"

# Canonical module corner labels
_MODULE_CORNERS = ("MOD_FL", "MOD_FR", "MOD_RL", "MOD_RR")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class SwerveInputs:
    """Oracle-derived inputs to the physics layer."""
    wheelbase_in:   float           # front-to-back wheel centre distance
    trackwidth_in:  float           # left-to-right wheel centre distance
    module_type:    str = "sds_mk4i"
    module_count:   int = 4
    weight_budget_lb: float = 30.0


@dataclass
class SwervePhysicsResult:
    """Fully-resolved physics decisions. No side effects, no I/O."""
    wheelbase_in:       float
    trackwidth_in:      float
    rail_spec:          str
    rail_longside_in:   float   # length of front/rear perimeter rails
    rail_shortside_in:  float   # length of left/right perimeter rails
    module_part_key:    str     # key into SWERVE_PARTS (resolved, fallback applied)
    module_type_orig:   str     # original oracle module_type before fallback
    gusset_count:       int
    module_count:       int
    estimated_weight_lb: float
    layout_mm:          dict    # computed positions keyed by instance role


@dataclass
class AssemblyResult:
    """Result returned by generate_swerve_assembly()."""
    document_url:   str
    document_id:    str
    workspace_id:   str
    element_id:     str
    instance_count: int
    fastened_count: int
    missing_parts:  list[str] = field(default_factory=list)
    wall_time_sec:  float = 0.0
    dry_run:        bool  = False

    def __str__(self) -> str:
        if self.dry_run:
            return "[DRY RUN] No Onshape document created."
        return (
            f"Assembly URL: {self.document_url}\n"
            f"  Instances     : {self.instance_count}\n"
            f"  Fastened mates: {self.fastened_count}\n"
            f"  Wall time     : {self.wall_time_sec:.1f}s"
        )


# ---------------------------------------------------------------------------
# Public interface — parse oracle output
# ---------------------------------------------------------------------------

def parse_oracle_output(oracle_json: dict) -> SwerveInputs:
    """
    Extract SwerveInputs from oracle.py's OracleOutput dict.
    Raises ValueError if required keys are missing or scorer != 'swerve'.
    """
    scorer = oracle_json.get("scorer", {})
    if scorer.get("type") != "swerve":
        raise ValueError(
            f"parse_oracle_output: scorer type is '{scorer.get('type')}', "
            "expected 'swerve'. Run oracle.py for a game that produces a "
            "swerve scorer (e.g., any FRC game from 2023+)."
        )

    module_count = int(scorer.get("module_count", MODULE_COUNT))
    if module_count != 4:
        raise ValueError(
            f"parse_oracle_output: module_count={module_count}. "
            "Phase 2 generator supports 4-module canonical configuration only."
        )

    return SwerveInputs(
        wheelbase_in    = float(scorer.get("wheelbase_in", DEFAULT_WHEELBASE_IN)),
        trackwidth_in   = float(scorer.get("trackwidth_in", DEFAULT_TRACKWIDTH_IN)),
        module_type     = scorer.get("module_type", DEFAULT_MODULE_TYPE),
        module_count    = module_count,
        weight_budget_lb= float(
            oracle_json.get("weight_budget", {}).get("scorer_lb", 30.0)
        ),
    )


# ---------------------------------------------------------------------------
# Physics layer — pure function
# ---------------------------------------------------------------------------

def compute_swerve_physics(inputs: SwerveInputs) -> SwervePhysicsResult:
    """
    Compute all physics decisions for a swerve drive frame.
    Pure function: no I/O, no side effects. Results drive MCP calls directly.

    Frame geometry:
      - Long-side (front/rear) rails span the trackwidth of the frame.
        Each rail runs the full trackwidth dimension.
      - Short-side (left/right) rails span the wheelbase of the frame.
        Length = wheelbase_in (front rail outer face to rear rail outer face).
      - All rails are 2x1x0.0625 aluminium tube (standard FRC perimeter).

    Module corner offsets (world XY, millimetres, frame-centre origin):
      FL: (-trackwidth/2,  wheelbase/2)
      FR: ( trackwidth/2,  wheelbase/2)
      RL: (-trackwidth/2, -wheelbase/2)
      RR: ( trackwidth/2, -wheelbase/2)
    """
    wb_in = inputs.wheelbase_in
    tw_in = inputs.trackwidth_in

    # Rail lengths
    rail_longside_in  = tw_in   # trackwidth-spanning perimeter rails (front + rear)
    rail_shortside_in = wb_in   # wheelbase-spanning perimeter rails (left + right)

    # Module part resolution (with fallback)
    _module_part, module_part_key = resolve_module(inputs.module_type)

    # Weight estimate
    perimeter_in = 2 * rail_longside_in + 2 * rail_shortside_in
    frame_weight_lb = perimeter_in * TUBE_WEIGHT_PER_IN_LB
    module_weight_lb = inputs.module_count * MODULE_WEIGHT_LB
    estimated_weight_lb = frame_weight_lb + module_weight_lb + GUSSET_WEIGHT_LB

    # Layout positions (mm, world-space, frame-centre origin)
    IN_TO_MM = 25.4
    wb_mm = wb_in * IN_TO_MM
    tw_mm = tw_in * IN_TO_MM
    hs_mm = rail_shortside_in * IN_TO_MM   # half span for short-side rails
    hl_mm = rail_longside_in  * IN_TO_MM   # half span for long-side rails

    layout_mm: dict = {
        # Long-side perimeter rails (front and rear, running trackwidth direction)
        "RAIL_LS_1": {"x": -tw_mm / 2, "y":  wb_mm / 2, "z": 0},   # Front Left
        "RAIL_LS_2": {"x":  tw_mm / 2, "y":  wb_mm / 2, "z": 0},   # Front Right
        "RAIL_LS_3": {"x": -tw_mm / 2, "y": -wb_mm / 2, "z": 0},   # Rear Left
        "RAIL_LS_4": {"x":  tw_mm / 2, "y": -wb_mm / 2, "z": 0},   # Rear Right

        # Short-side cross-member rails (left and right sides, running wheelbase direction)
        "RAIL_SS_1": {"x": -tw_mm / 2, "y": 0, "z": 0},            # Left side
        "RAIL_SS_2": {"x":  tw_mm / 2, "y": 0, "z": 0},            # Right side

        # Corner gussets — at four frame corners
        "GUSSET_1": {"x": -tw_mm / 2, "y":  wb_mm / 2, "z": 10},   # Front Left
        "GUSSET_2": {"x":  tw_mm / 2, "y":  wb_mm / 2, "z": 10},   # Front Right
        "GUSSET_3": {"x": -tw_mm / 2, "y": -wb_mm / 2, "z": 10},   # Rear Left
        "GUSSET_4": {"x":  tw_mm / 2, "y": -wb_mm / 2, "z": 10},   # Rear Right

        # Swerve modules — at corner offsets
        "MOD_FL": {"x": -tw_mm / 2, "y":  wb_mm / 2, "z": -25.4},  # front-left  (1in below frame)
        "MOD_FR": {"x":  tw_mm / 2, "y":  wb_mm / 2, "z": -25.4},  # front-right
        "MOD_RL": {"x": -tw_mm / 2, "y": -wb_mm / 2, "z": -25.4},  # rear-left
        "MOD_RR": {"x":  tw_mm / 2, "y": -wb_mm / 2, "z": -25.4},  # rear-right
    }

    return SwervePhysicsResult(
        wheelbase_in        = wb_in,
        trackwidth_in       = tw_in,
        rail_spec           = RAIL_SPEC,
        rail_longside_in    = rail_longside_in,
        rail_shortside_in   = rail_shortside_in,
        module_part_key     = module_part_key,
        module_type_orig    = inputs.module_type,
        gusset_count        = GUSSET_COUNT,
        module_count        = inputs.module_count,
        estimated_weight_lb = estimated_weight_lb,
        layout_mm           = layout_mm,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_swerve_assembly(
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
        AssemblyResult with document_url, instance_count, fastened_count.
    """
    inputs  = parse_oracle_output(oracle_json)
    physics = compute_swerve_physics(inputs)

    if dry_run:
        result = asdict(physics)
        print(json.dumps(result, indent=2))
        return AssemblyResult(
            document_url="", document_id="", workspace_id="", element_id="",
            instance_count=0, fastened_count=0, dry_run=True,
        )

    t0 = time.time()
    result = build_swerve_assembly(
        physics,
        doc_id=doc_id,
        check_interference=check_interference,
        export_step=export_step,
    )
    result.wall_time_sec = time.time() - t0
    return result


def build_swerve_assembly(
    physics: SwervePhysicsResult,
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

    # ── Phase B: Part Studios for geometry-created tubes ────────────────────
    longside_elem_id  = _create_tube_part_studio(
        doc_id, ws_id, physics.rail_longside_in, physics.rail_spec, "Long-side"
    )
    shortside_elem_id = _create_tube_part_studio(
        doc_id, ws_id, physics.rail_shortside_in, physics.rail_spec, "Short-side"
    )

    # ── Phase B: Insert instances ────────────────────────────────────────────
    instances = _insert_instances(
        doc_id, ws_id, asm_id,
        physics, longside_elem_id, shortside_elem_id,
        missing_parts,
    )

    # ── Phase C: Position instances ─────────────────────────────────────────
    _position_instances(doc_id, ws_id, asm_id, instances, physics)

    # ── Phase D: Get face IDs for mate creation ──────────────────────────────
    tube_faces = _get_tube_face_ids(doc_id, ws_id, longside_elem_id)

    # ── Phase E: Add mates ──────────────────────────────────────────────────
    fastened_count = _add_mates(
        doc_id, ws_id, asm_id,
        instances, physics, tube_faces,
    )

    # ── Phase F: Optional validation ────────────────────────────────────────
    if check_interference:
        _run_interference_check(doc_id, ws_id, asm_id)
    if export_step:
        _export_assembly_step(doc_id, ws_id, asm_id)

    doc_url = f"https://cad.onshape.com/documents/{doc_id}"
    return AssemblyResult(
        document_url   = doc_url,
        document_id    = doc_id,
        workspace_id   = ws_id,
        element_id     = asm_id,
        instance_count = len(instances),
        fastened_count = fastened_count,
        missing_parts  = missing_parts,
    )


# ---------------------------------------------------------------------------
# Phase A helpers
# ---------------------------------------------------------------------------

def _create_doc_and_assembly_prep(doc_id: Optional[str]) -> tuple[str, str]:
    """
    Return (doc_id, workspace_id). Uses existing doc if doc_id provided,
    otherwise attempts create_document (409 on 5-doc-limit free accounts).
    """
    mcp = _get_mcp_module()

    if doc_id:
        summary = mcp.get_document_summary(doc_id)
        ws_id = summary["workspace_id"]
        print(f"[Phase A] Using existing document: {doc_id}, workspace: {ws_id}")
        return doc_id, ws_id

    from datetime import date
    doc_name = f"2950 Swerve Drive Frame — {date.today().isoformat()}"
    result = mcp.create_document(name=doc_name)
    doc_id = result["documentId"]
    ws_id  = result["defaultWorkspaceId"]
    print(f"[Phase A] Created document: {doc_id}")
    return doc_id, ws_id


def _create_assembly_element(doc_id: str, ws_id: str) -> str:
    """Create the swerve Assembly element and return its element ID."""
    mcp = _get_mcp_module()
    result = mcp.create_assembly(
        documentId=doc_id, workspaceId=ws_id,
        name="Swerve Drive Frame Assembly"
    )
    asm_id = result["elementId"]
    print(f"[Phase A] Created assembly: {asm_id}")
    return asm_id


# ---------------------------------------------------------------------------
# Phase B helpers — geometry creation (frame rail tubes)
# ---------------------------------------------------------------------------

def _create_tube_part_studio(
    doc_id: str, ws_id: str, length_in: float, tube_spec: str, label: str
) -> str:
    """Create a 2x1 frame rail tube Part Studio and return its element ID."""
    mcp = _get_mcp_module()
    ps_name = f"Frame Rail Tube {tube_spec} {label} {length_in:.1f}in"
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
    print(f"[Phase B] Created tube Part Studio: {ps_id} ({label}, {length_in:.1f}in)")
    return ps_id


# ---------------------------------------------------------------------------
# Phase B helpers — insert instances
# ---------------------------------------------------------------------------

def _insert_instances(
    doc_id: str, ws_id: str, asm_id: str,
    physics: SwervePhysicsResult,
    longside_elem_id: str, shortside_elem_id: str,
    missing_parts: list[str],
) -> dict[str, str]:
    """
    Insert all part instances into the assembly.
    Returns dict mapping role name → instance ID.

    NOTE: add_assembly_instance returns instance_id="unknown" in its response.
    We always call get_assembly_positions after each insert and take the last
    (newest) instance ID each time. Same pattern as elevator_rev2.py.
    """
    mcp = _get_mcp_module()
    instances: dict[str, str] = {}

    def _add_and_capture(
        role: str, part_studio_id: str,
        is_asm: bool = False, part_id: Optional[str] = None,
    ) -> str:
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
                    f"{role}: geometry/deferred part '{part_key}' — skipping COTS insert"
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

    # ── Long-side rails (trackwidth-spanning, 4 rails for perimeter) ─────────
    for i in range(1, 5):
        _add_and_capture(f"RAIL_LS_{i}", longside_elem_id, is_asm=False)

    # ── Short-side cross-member rails (wheelbase-spanning, left + right) ─────
    for i in range(1, 3):
        _add_and_capture(f"RAIL_SS_{i}", shortside_elem_id, is_asm=False)

    # ── Corner gussets (4 corners) ───────────────────────────────────────────
    gusset_part = resolve("wcp_90deg_gusset_2x1")
    for i in range(1, GUSSET_COUNT + 1):
        try:
            _add_and_capture(
                f"GUSSET_{i}", gusset_part["elem"],
                is_asm=bool(gusset_part.get("is_asm")),
                part_id=gusset_part.get("part_id") or None,
            )
        except Exception as e:
            missing_parts.append(f"GUSSET_{i}: {e}")
            print(f"[Phase B]   WARNING: GUSSET_{i} failed — {e}")

    # ── Swerve modules (4 corners) ───────────────────────────────────────────
    module_part, effective_key = resolve_module(physics.module_type_orig)
    if effective_key != physics.module_part_key:
        missing_parts.append(
            f"MODULE: requested '{physics.module_type_orig}' not in FRCDesignLib; "
            f"using '{effective_key}' fallback"
        )
    for corner in _MODULE_CORNERS:
        try:
            _add_and_capture(
                corner, module_part["elem"],
                is_asm=bool(module_part.get("is_asm")),
                part_id=module_part.get("part_id") or None,
            )
        except Exception as e:
            missing_parts.append(f"{corner}: {e}")
            print(f"[Phase B]   WARNING: {corner} failed — {e}")

    return instances


# ---------------------------------------------------------------------------
# Phase C — position instances
# ---------------------------------------------------------------------------

def _position_instances(
    doc_id: str, ws_id: str, asm_id: str,
    instances: dict[str, str],
    physics: SwervePhysicsResult,
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
            print(
                f"[Phase C]   {role} positioned to "
                f"({x_in:.2f}, {y_in:.2f}, {z_in:.2f}) in"
            )
        except Exception as e:
            print(f"[Phase C]   WARNING: position {role} failed — {e}")


# ---------------------------------------------------------------------------
# Phase D — get face IDs
# ---------------------------------------------------------------------------

def _get_tube_face_ids(doc_id: str, ws_id: str, tube_elem_id: str) -> dict:
    """Get face IDs from a tube Part Studio."""
    mcp = _get_mcp_module()
    try:
        details = mcp.get_body_details(
            documentId=doc_id, workspaceId=ws_id, elementId=tube_elem_id
        )
        faces: dict[str, str] = {}
        for body in details.get("bodies", [details]):
            for face in body.get("faces", []):
                normal = face.get("normal", {})
                ny = normal.get("y", 0)
                nz = normal.get("z", 0)
                if ny > 0.5:
                    faces["top_y"] = face["id"]
                elif ny < -0.5:
                    faces["bot_y"] = face["id"]
                elif nz > 0.5:
                    faces["top_z"] = face["id"]
                elif nz < -0.5:
                    faces["bot_z"] = face["id"]
        return faces
    except Exception as e:
        print(f"[Phase D] WARNING: get_body_details failed — {e}")
        return {}


# ---------------------------------------------------------------------------
# Phase E — add mates
# ---------------------------------------------------------------------------

def _add_mates(
    doc_id: str, ws_id: str, asm_id: str,
    instances: dict[str, str],
    physics: SwervePhysicsResult,
    tube_faces: dict,
) -> int:
    """
    Add fastened mates for swerve frame rigid joints.
    Returns number of fastened mates created successfully.

    Mate targets:
    - 4 corner gusset → adjacent rail (gusset fastened at each corner)
    - 4 module → frame (module fastened at module-mount position below frame)
    """
    mcp = _get_mcp_module()
    fastened_count = 0

    # Fall-back face IDs if geometry extraction failed
    top_face = tube_faces.get("top_y", "JHG")
    bot_face = tube_faces.get("bot_y", "JHK")

    # ── Gussets fastened to front/rear perimeter rails ───────────────────────
    # Pair each gusset with its adjacent long-side rail
    gusset_rail_pairs = [
        ("GUSSET_1", "RAIL_LS_1"),   # Front Left gusset → Front Left rail
        ("GUSSET_2", "RAIL_LS_2"),   # Front Right gusset → Front Right rail
        ("GUSSET_3", "RAIL_LS_3"),   # Rear Left gusset → Rear Left rail
        ("GUSSET_4", "RAIL_LS_4"),   # Rear Right gusset → Rear Right rail
    ]
    for gusset_role, rail_role in gusset_rail_pairs:
        gusset_id = instances.get(gusset_role)
        rail_id   = instances.get(rail_role)
        if gusset_id and rail_id:
            try:
                mcp.create_fastened_mate(
                    documentId=doc_id, workspaceId=ws_id, elementId=asm_id,
                    name=f"Fastened — {gusset_role} to {rail_role}",
                    firstInstanceId=gusset_id,  firstFaceId=bot_face,
                    secondInstanceId=rail_id,   secondFaceId=top_face,
                )
                fastened_count += 1
                print(f"[Phase E] Fastened: {gusset_role} → {rail_role} — OK")
            except Exception as e:
                print(f"[Phase E] WARNING: Fastened {gusset_role} failed — {e}")

    # ── Modules fastened to frame (below frame floor) ────────────────────────
    # Each module mates to the nearest long-side rail (front modules → RAIL_LS_1/2,
    # rear modules → RAIL_LS_3/4)
    module_rail_pairs = [
        ("MOD_FL", "RAIL_LS_1"),
        ("MOD_FR", "RAIL_LS_2"),
        ("MOD_RL", "RAIL_LS_3"),
        ("MOD_RR", "RAIL_LS_4"),
    ]
    for mod_role, rail_role in module_rail_pairs:
        mod_id  = instances.get(mod_role)
        rail_id = instances.get(rail_role)
        if mod_id and rail_id:
            try:
                mcp.create_fastened_mate(
                    documentId=doc_id, workspaceId=ws_id, elementId=asm_id,
                    name=f"Fastened — {mod_role} to frame",
                    firstInstanceId=mod_id,   firstFaceId=top_face,
                    secondInstanceId=rail_id, secondFaceId=bot_face,
                    secondOffsetZ=-1.0,   # 1 in below rail bottom (module sits under frame)
                )
                fastened_count += 1
                print(f"[Phase E] Fastened: {mod_role} → {rail_role} — OK")
            except Exception as e:
                print(f"[Phase E] WARNING: Fastened {mod_role} failed — {e}")

    return fastened_count


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
    In tests this object is replaced by a mock via set_mcp_module().

    Same pattern as elevator_rev2._MCPModule.
    Phase 3 refactor: extract to blueprint/mcp_helpers.py and import from both.
    """

    def get_document_summary(self, doc_id: str) -> dict:
        from mcp__onshape import get_document_summary as _f
        raw = _f(documentId=doc_id)
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

    def create_fastened_mate(self, **kw) -> dict:
        from mcp__onshape import create_fastened_mate as _f
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
# Sample oracle output fixtures
# ---------------------------------------------------------------------------

ORACLE_SWERVE_26x26 = {
    "scorer": {
        "type": "swerve",
        "wheelbase_in": 26.0,
        "trackwidth_in": 26.0,
        "module_type": "sds_mk4i",
        "module_count": 4,
    },
    "weight_budget": {"scorer_lb": 35.0},
    "endgame": {"type": "none"},
}

ORACLE_SWERVE_28x28 = {
    "scorer": {
        "type": "swerve",
        "wheelbase_in": 28.0,
        "trackwidth_in": 28.0,
        "module_type": "sds_mk4i",
        "module_count": 4,
    },
    "weight_budget": {"scorer_lb": 35.0},
    "endgame": {"type": "none"},
}

ORACLE_BY_GAME: dict[str, dict] = {
    "swerve_26x26": ORACLE_SWERVE_26x26,
    "swerve_28x28": ORACLE_SWERVE_28x28,
}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Team 2950 Swerve Drive Frame Generator — Rev 2 (MCP)"
    )
    parser.add_argument(
        "--game", default=None,
        choices=list(ORACLE_BY_GAME.keys()),
        help="Preset oracle fixture (overrides --wheelbase / --trackwidth)",
    )
    parser.add_argument(
        "--wheelbase", type=float, default=DEFAULT_WHEELBASE_IN,
        help=f"Wheelbase (front-to-back wheel centre, inches). Default: {DEFAULT_WHEELBASE_IN}",
    )
    parser.add_argument(
        "--trackwidth", type=float, default=DEFAULT_TRACKWIDTH_IN,
        help=f"Trackwidth (left-to-right wheel centre, inches). Default: {DEFAULT_TRACKWIDTH_IN}",
    )
    parser.add_argument(
        "--module-type", default=DEFAULT_MODULE_TYPE,
        choices=list({"sds_mk4i", "wcp_swerve_x", "rev_maxswerve"}),
        help="Swerve module type. Default: sds_mk4i (WCP Swerve X / REV MaxSwerve fall back to MK4i)",
    )
    parser.add_argument(
        "--doc-id", default=None,
        help=(
            "Existing Onshape document ID to use. REQUIRED on free accounts "
            "(5-doc limit). If omitted, create_document is attempted."
        ),
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Run parse + physics only; print JSON; skip MCP writes.")
    parser.add_argument("--check-interference", action="store_true",
                        help="Run interference check after assembly (slow).")
    parser.add_argument("--export-step", action="store_true",
                        help="Export STEP file after assembly.")
    args = parser.parse_args()

    if args.game:
        oracle_json = ORACLE_BY_GAME[args.game]
    else:
        oracle_json = {
            "scorer": {
                "type": "swerve",
                "wheelbase_in": args.wheelbase,
                "trackwidth_in": args.trackwidth,
                "module_type": args.module_type,
                "module_count": 4,
            },
            "weight_budget": {"scorer_lb": 35.0},
            "endgame": {"type": "none"},
        }

    result = generate_swerve_assembly(
        oracle_json=oracle_json,
        doc_id=args.doc_id,
        dry_run=args.dry_run,
        check_interference=args.check_interference,
        export_step=args.export_step,
    )
    print(result)


if __name__ == "__main__":
    main()
