#!/usr/bin/env python3
"""
The Blueprint — Assembly Builder (CAD Evolution P0b)
Team 2950 — The Devastators

Creates real OnShape assemblies with COTS parts from FRCDesignLib.
Takes a Blueprint spec → resolves COTS parts → creates assembly document →
inserts + positions all parts → returns assembly URL.

Two modes:
  1. Full API mode: creates real OnShape document with inserted parts
  2. Manifest mode: outputs a JSON manifest of what WOULD be inserted
     (for testing without API calls)

Usage:
  python3 assembly_builder.py manifest <blueprint_spec.json>
  python3 assembly_builder.py build <blueprint_spec.json>
"""

import json
import math
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from assembly_composer import compose_robot, MechanismPlacement, RobotLayout
from part_resolver import (
    PartResolver, ResolvedPart,
    MODULE_PARTS_MAP, MOTOR_PARTS_MAP, MECHANISM_COTS_MAP,
)

BASE_DIR = Path(__file__).parent


# ═══════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════

@dataclass
class PartInstance:
    """A single part to insert into the assembly."""
    name: str = ""                    # human-readable instance name
    catalog_name: str = ""            # key into cots_catalog.json
    resolved: Optional[ResolvedPart] = None
    position_mm: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotation_deg: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    quantity: int = 1
    subassembly: str = ""             # group name (e.g. "drivetrain", "intake")
    source: str = "cots"              # "cots", "generated", "manual"
    instance_id: str = ""             # filled after insertion

    @property
    def transform_matrix(self) -> list:
        """4x4 transform matrix for OnShape positioning."""
        tx, ty, tz = self.position_mm
        rx = math.radians(self.rotation_deg[0])
        ry = math.radians(self.rotation_deg[1])
        rz = math.radians(self.rotation_deg[2])

        # Rotation matrices (Rz * Ry * Rx)
        cx, sx = math.cos(rx), math.sin(rx)
        cy, sy = math.cos(ry), math.sin(ry)
        cz, sz = math.cos(rz), math.sin(rz)

        return [
            cy*cz,  sx*sy*cz - cx*sz,  cx*sy*cz + sx*sz,  tx,
            cy*sz,  sx*sy*sz + cx*cz,  cx*sy*sz - sx*cz,  ty,
            -sy,    sx*cy,              cx*cy,              tz,
            0,      0,                  0,                  1,
        ]


@dataclass
class AssemblyManifest:
    """Complete manifest of what goes into the assembly."""
    game: str = ""
    year: int = 0
    frame_length_in: float = 27.0
    frame_width_in: float = 27.0
    parts: list = field(default_factory=list)          # list of PartInstance dicts
    subassemblies: list = field(default_factory=list)   # group names
    generated_parts: list = field(default_factory=list)  # FeatureScript-generated
    total_cots_parts: int = 0
    total_generated_parts: int = 0
    total_instances: int = 0
    resolution_status: dict = field(default_factory=dict)
    assembly_url: str = ""
    created_at: str = ""


# ═══════════════════════════════════════════════════════════════════
# ASSEMBLY PLANNER
# ═══════════════════════════════════════════════════════════════════

def _mm(inches: float) -> float:
    return round(inches * 25.4, 2)


def plan_assembly(spec: dict) -> list[PartInstance]:
    """
    Plan all part instances needed for the robot assembly.
    Returns a list of PartInstance objects with positions.
    """
    layout = compose_robot(spec)
    frame = spec.get("frame", {})
    L = _mm(layout.frame_length_in)
    W = _mm(layout.frame_width_in)

    parts = []

    # ── Swerve Modules ──
    module_type = frame.get("module_type", "sds_mk4i")
    module_catalog = MODULE_PARTS_MAP.get(module_type, "SDS MK4i Swerve Module")

    for mod in layout.swerve_modules:
        pos = mod.get("position_in", [0, 0])
        name = mod.get("name", "module")
        # Convert center-origin → corner-origin (FeatureScript frame starts at 0,0)
        parts.append(PartInstance(
            name=f"swerve_{name}",
            catalog_name=module_catalog,
            position_mm=[_mm(pos[0]) + L/2, _mm(pos[1]) + W/2, 0],
            subassembly="drivetrain",
        ))

    # ── Drive + Steer Motors (per module) ──
    drive_motor = _select_drive_motor(module_type)
    steer_motor = _select_steer_motor(module_type)

    for mod in layout.swerve_modules:
        pos = mod.get("position_in", [0, 0])
        name = mod.get("name", "module")
        # Convert center-origin → corner-origin
        mx = _mm(pos[0]) + L/2
        my = _mm(pos[1]) + W/2
        # Drive motor sits on top of module
        parts.append(PartInstance(
            name=f"drive_motor_{name}",
            catalog_name=drive_motor,
            position_mm=[mx, my, 76.2],  # above frame
            subassembly="drivetrain",
        ))
        # Steer motor offset from module center
        parts.append(PartInstance(
            name=f"steer_motor_{name}",
            catalog_name=steer_motor,
            position_mm=[mx + 30, my, 76.2],
            subassembly="drivetrain",
        ))

    # ── Frame Gussets ──
    # 4 corner gussets + cross member junctions
    gusset_positions = _compute_gusset_positions(layout)
    for i, gpos in enumerate(gusset_positions):
        parts.append(PartInstance(
            name=f"gusset_{i}",
            catalog_name="WCP 90° Gusset (2x1 to 2x1)",
            position_mm=gpos,
            subassembly="frame",
        ))

    # ── Electronics ──
    electronics_parts = _plan_electronics(layout, L, W)
    parts.extend(electronics_parts)

    # ── Mechanisms ──
    for placement in layout.placements:
        mech_parts = _plan_mechanism_parts(placement, spec, L, W)
        parts.extend(mech_parts)

    return parts


def _select_drive_motor(module_type: str) -> str:
    """Select drive motor based on swerve module type."""
    drive_motors = {
        "sds_mk4i": "WCP Kraken X60",
        "sds_mk4n": "WCP Kraken X60",
        "thrifty": "REV NEO Motor",
        "rev_maxswerve": "REV NEO Vortex",
    }
    return drive_motors.get(module_type, "WCP Kraken X60")


def _select_steer_motor(module_type: str) -> str:
    """Select steer motor based on swerve module type."""
    steer_motors = {
        "sds_mk4i": "REV NEO 550",
        "sds_mk4n": "REV NEO 550",
        "thrifty": "REV NEO 550",
        "rev_maxswerve": "REV NEO 550",
    }
    return steer_motors.get(module_type, "REV NEO 550")


def _compute_gusset_positions(layout: RobotLayout) -> list[list[float]]:
    """Compute positions for frame gussets at rail junctions."""
    L = _mm(layout.frame_length_in)
    W = _mm(layout.frame_width_in)
    th = 25.4  # frame height 1"

    # 4 corner gussets (inside corners of perimeter)
    inset = 50.8  # 2" from corner
    positions = [
        [inset, inset, th],                 # front-left
        [L - inset, inset, th],             # front-right
        [inset, W - inset, th],             # back-left
        [L - inset, W - inset, th],         # back-right
    ]

    # Cross member junctions (left and right side of each cross)
    cross_y_vals = [W * 0.25, W * 0.50, W * 0.75]
    for cy in cross_y_vals:
        positions.append([50.8, cy, th])        # left side
        positions.append([L - 50.8, cy, th])    # right side

    return positions


def _plan_electronics(layout: RobotLayout, L: float, W: float) -> list[PartInstance]:
    """Plan electronics part instances."""
    parts = []

    # Default electronics positions (on bellypan, center-origin)
    electronics_map = [
        ("battery", "FRC Battery (MK ES17-12)", [0, -50, 0]),
        ("pdh", "Power Distribution Hub", [80, 0, 0]),
        ("roborio", "RoboRIO 2", [-80, 0, 0]),
        ("radio", "OpenMesh Radio (OM5P-AC)", [0, 80, 0]),
        ("breaker", "Main Breaker (120A)", [-80, -50, 0]),
        ("imu", "CTRE Pigeon 2.0 IMU", [0, 0, 0]),
    ]

    for name, catalog_name, pos in electronics_map:
        parts.append(PartInstance(
            name=f"elec_{name}",
            catalog_name=catalog_name,
            position_mm=[L/2 + pos[0], W/2 + pos[1], pos[2]],
            subassembly="electronics",
        ))

    return parts


def _plan_mechanism_parts(placement: MechanismPlacement, spec: dict,
                          L: float, W: float) -> list[PartInstance]:
    """Plan COTS parts for a mechanism based on its placement."""
    parts = []
    name = placement.name
    px, py, pz = placement.position_mm

    # Convert from center-origin to corner-origin
    px += L / 2
    py += W / 2

    mech_spec = spec.get(name, {})
    motor_type = mech_spec.get("motor_type", mech_spec.get("roller_motor_type", "neo"))
    motor_count = mech_spec.get("motor_count", mech_spec.get("roller_motor_count", 1))
    motor_catalog = MOTOR_PARTS_MAP.get(motor_type, "REV NEO Motor")

    # Motors for this mechanism
    for i in range(motor_count):
        offset_x = i * 60  # space motors 60mm apart
        parts.append(PartInstance(
            name=f"{name}_motor_{i}",
            catalog_name=motor_catalog,
            position_mm=[px + offset_x, py, pz],
            subassembly=name,
        ))

    # Gearbox (if mechanism uses one)
    if name in ("intake", "arm", "climber"):
        gearbox = "REV MAXPlanetary Gearbox"
        parts.append(PartInstance(
            name=f"{name}_gearbox",
            catalog_name=gearbox,
            position_mm=[px, py + 40, pz],
            subassembly=name,
        ))

    # Bearings (most mechanisms need 2-4)
    bearing_count = 2 if name in ("intake", "flywheel", "arm") else 0
    if name == "elevator":
        bearing_count = 4  # bearing blocks per stage
    for i in range(bearing_count):
        if name == "elevator":
            parts.append(PartInstance(
                name=f"{name}_bearing_block_{i}",
                catalog_name="Thrifty Elevator Bearing Block",
                position_mm=[px + (i % 2) * 100, py, pz + (i // 2) * 200],
                subassembly=name,
            ))
        else:
            parts.append(PartInstance(
                name=f"{name}_bearing_{i}",
                catalog_name="Flanged Bearing 1/2in Hex",
                position_mm=[px + i * 80, py, pz],
                subassembly=name,
            ))

    # Hex shaft (for intake, flywheel)
    if name in ("intake", "flywheel", "climber"):
        parts.append(PartInstance(
            name=f"{name}_shaft",
            catalog_name="1/2in Hex Shaft",
            position_mm=[px, py, pz],
            subassembly=name,
        ))

    # Flywheel/shooter wheels
    if name == "flywheel":
        wheel_count = mech_spec.get("wheel_count", 2)
        wheel_dia_in = mech_spec.get("wheel_diameter_in", 4.0)
        # Pick wheel based on diameter: 6" → Colson/Stealth, 4" → Stealth/Flex
        if wheel_dia_in >= 5.0:
            wheel_catalog = "Stealth Wheel Flywheel"
        else:
            wheel_catalog = "Stealth Wheel Flywheel"
        for i in range(wheel_count):
            parts.append(PartInstance(
                name=f"{name}_wheel_{i}",
                catalog_name=wheel_catalog,
                position_mm=[px + i * 50, py, pz + 40],
                subassembly=name,
            ))

    # Intake flex wheels (rollers)
    if name == "intake":
        roller_count = mech_spec.get("roller_count", 2)
        for i in range(roller_count):
            # Space rollers along the intake width
            roller_spacing = mech_spec.get("roller_spacing_in", 12.0)
            parts.append(PartInstance(
                name=f"{name}_roller_wheel_{i}",
                catalog_name="WCP Flex Wheel 4in",
                position_mm=[px, py + i * _mm(roller_spacing), pz + 30],
                subassembly=name,
            ))

    # Elevator-specific: tube stock
    if name == "elevator":
        parts.append(PartInstance(
            name=f"{name}_outer_tube",
            catalog_name="2x1 Aluminum Box Tube",
            position_mm=[px - 30, py, pz],
            subassembly=name,
        ))
        parts.append(PartInstance(
            name=f"{name}_inner_tube",
            catalog_name="1x1 Aluminum Box Tube",
            position_mm=[px, py, pz + 100],
            subassembly=name,
        ))

    # Motor controllers (one per motor)
    controller = "REV Spark MAX"
    if motor_type in ("kraken_x60", "falcon_500"):
        controller = "REV Spark Flex"  # integrated, but still track it
    for i in range(motor_count):
        parts.append(PartInstance(
            name=f"{name}_controller_{i}",
            catalog_name=controller,
            position_mm=[px + i * 40, py - 60, pz],
            subassembly="electronics",
        ))

    return parts


# ═══════════════════════════════════════════════════════════════════
# MANIFEST GENERATION
# ═══════════════════════════════════════════════════════════════════

def generate_manifest(spec: dict) -> AssemblyManifest:
    """
    Generate a complete assembly manifest from a Blueprint spec.
    No API calls — just plans what would be built.
    """
    layout = compose_robot(spec)
    parts = plan_assembly(spec)

    # Resolve parts (from cache only — no API calls in manifest mode)
    resolver = PartResolver()
    for part in parts:
        cached = resolver.get_cached(part.catalog_name)
        if cached:
            part.resolved = cached

    # Group by subassembly
    subassemblies = sorted(set(p.subassembly for p in parts if p.subassembly))

    # Count unique COTS parts
    cots_names = set(p.catalog_name for p in parts if p.source == "cots")

    manifest = AssemblyManifest(
        game=spec.get("game", ""),
        year=spec.get("year", 0),
        frame_length_in=layout.frame_length_in,
        frame_width_in=layout.frame_width_in,
        parts=[_part_to_dict(p) for p in parts],
        subassemblies=subassemblies,
        total_cots_parts=len(cots_names),
        total_instances=len(parts),
        resolution_status=resolver.get_resolution_status(),
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )

    return manifest


def _part_to_dict(part: PartInstance) -> dict:
    """Convert PartInstance to serializable dict."""
    d = {
        "name": part.name,
        "catalog_name": part.catalog_name,
        "position_mm": part.position_mm,
        "rotation_deg": part.rotation_deg,
        "subassembly": part.subassembly,
        "source": part.source,
    }
    if part.resolved and part.resolved.is_valid:
        d["resolved"] = True
        d["document_id"] = part.resolved.document_id
        d["element_id"] = part.resolved.element_id
    else:
        d["resolved"] = False
    return d


def display_manifest(manifest: AssemblyManifest):
    """Pretty-print an assembly manifest."""
    print(f"\n{'═' * 65}")
    print(f"  ASSEMBLY MANIFEST — {manifest.year} {manifest.game}")
    print(f"  Frame: {manifest.frame_length_in}\" x {manifest.frame_width_in}\"")
    print(f"{'═' * 65}")

    print(f"\n  SUBASSEMBLIES ({len(manifest.subassemblies)})")
    for sub in manifest.subassemblies:
        count = sum(1 for p in manifest.parts if p.get("subassembly") == sub)
        resolved = sum(1 for p in manifest.parts
                      if p.get("subassembly") == sub and p.get("resolved"))
        print(f"    {sub:20s}  {count:3d} instances  ({resolved} resolved)")

    print(f"\n  UNIQUE COTS PARTS ({manifest.total_cots_parts})")
    seen = set()
    for p in manifest.parts:
        cname = p.get("catalog_name", "")
        if cname not in seen:
            seen.add(cname)
            status = "OK" if p.get("resolved") else "--"
            print(f"    [{status}] {cname}")

    print(f"\n  TOTALS")
    print(f"    Total instances:   {manifest.total_instances}")
    print(f"    Unique COTS parts: {manifest.total_cots_parts}")
    print(f"    Resolution rate:   {manifest.resolution_status.get('resolution_rate', 0)}%")

    unresolved = manifest.resolution_status.get("unresolved_parts", [])
    if unresolved:
        print(f"\n  UNRESOLVED PARTS ({len(unresolved)})")
        for name in unresolved[:10]:
            print(f"    - {name}")

    print(f"\n{'═' * 65}\n")


# ═══════════════════════════════════════════════════════════════════
# ONSHAPE ASSEMBLY BUILD
# ═══════════════════════════════════════════════════════════════════

def build_assembly(spec: dict, name: str = "2950 Blueprint Robot") -> dict:
    """
    Create a real OnShape assembly with COTS parts.

    1. Create document
    2. Create Part Studio with frame FeatureScript
    3. Create Assembly
    4. Insert frame from Part Studio
    5. Resolve + insert each COTS part
    6. Position parts using transforms
    7. Return assembly URL
    """
    from onshape_api import get_client
    from cad_builder import generate_full_featurescript

    client = get_client()
    resolver = PartResolver()
    parts = plan_assembly(spec)

    print(f"\n{'═' * 65}")
    print(f"  BUILDING ONSHAPE ASSEMBLY")
    print(f"  {name}")
    print(f"  {len(parts)} part instances to place")
    print(f"{'═' * 65}\n")

    # Step 1: Create document
    print("  [1/6] Creating document...")
    doc_response = client.documents_api.create_document({
        "name": name,
        "description": "Generated by The Engine — Real COTS Assembly Pipeline",
        "isPublic": True,
    })
    doc_id = doc_response.id
    workspace_id = doc_response.default_workspace.id
    doc_url = f"https://cad.onshape.com/documents/{doc_id}"
    print(f"         {doc_url}")

    # Step 2: Get Part Studio, create FeatureScript for frame
    print("  [2/6] Generating frame geometry...")
    elements = client.documents_api.get_elements_in_document(doc_id, "w", workspace_id)
    part_studio_id = None
    for elem in elements:
        if elem.element_type == "PARTSTUDIO":
            part_studio_id = elem.id
            break

    # Upload frame FeatureScript
    fs_code = generate_full_featurescript(spec)

    # Create Feature Studio for the frame
    try:
        fs_response = client.api_client.call_api(
            f"/api/featurestudios/d/{doc_id}/w/{workspace_id}",
            "POST",
            body={"name": "2950 Frame Builder"},
            header_params={"Content-Type": "application/json", "Accept": "application/json"},
            response_type="object",
        )
        fs_id = fs_response.id if hasattr(fs_response, 'id') else fs_response.get("id", "")

        doc_info = client.documents_api.get_document(doc_id)
        mv = ""
        if hasattr(doc_info, 'default_workspace') and hasattr(doc_info.default_workspace, 'microversion'):
            mv = doc_info.default_workspace.microversion

        client.api_client.call_api(
            f"/api/featurestudios/d/{doc_id}/w/{workspace_id}/e/{fs_id}",
            "POST",
            body={"contents": fs_code, "serializationVersion": "1.2.17", "sourceMicroversion": mv},
            header_params={"Content-Type": "application/json", "Accept": "application/json"},
            response_type="object",
        )
        print(f"         Frame FeatureScript uploaded ({len(fs_code)} chars)")
    except Exception as e:
        print(f"         Frame FeatureScript upload note: {e}")

    # Step 3: Create Assembly
    print("  [3/6] Creating assembly...")
    try:
        asm_response = client.api_client.call_api(
            f"/api/assemblies/d/{doc_id}/w/{workspace_id}",
            "POST",
            body={"name": f"{name} — Assembly"},
            header_params={"Content-Type": "application/json", "Accept": "application/json"},
            response_type="object",
        )
        asm_id = asm_response.id if hasattr(asm_response, 'id') else asm_response.get("id", "")
        print(f"         Assembly ID: {asm_id}")
    except Exception as e:
        print(f"         Assembly creation note: {e}")
        # Fall back to finding existing assembly element
        elements = client.documents_api.get_elements_in_document(doc_id, "w", workspace_id)
        asm_id = None
        for elem in elements:
            if hasattr(elem, 'element_type') and elem.element_type == "ASSEMBLY":
                asm_id = elem.id
                break
        if not asm_id:
            print("         Could not create or find assembly element")
            return {"url": doc_url, "document_id": doc_id, "error": "no assembly"}

    # Step 4: Insert frame Part Studio into assembly
    print("  [4/6] Inserting frame into assembly...")
    if part_studio_id:
        try:
            from onshape_api import insert_part_into_assembly
            insert_part_into_assembly(
                doc_id, workspace_id, asm_id,
                part_document_id=doc_id,
                part_element_id=part_studio_id,
            )
            print(f"         Frame inserted")
        except Exception as e:
            print(f"         Frame insert note: {e}")

    # Step 5: Resolve + insert COTS parts
    print(f"  [5/6] Inserting {len(parts)} COTS parts...")
    inserted = 0
    failed = 0
    skipped = 0

    for part in parts:
        resolved = resolver.resolve(part.catalog_name)
        if not resolved or not resolved.is_valid:
            skipped += 1
            continue

        try:
            from onshape_api import insert_part_into_assembly
            result = insert_part_into_assembly(
                doc_id, workspace_id, asm_id,
                part_document_id=resolved.document_id,
                part_element_id=resolved.element_id,
                part_id=resolved.part_id,
                configuration=resolved.configuration,
            )
            part.instance_id = result.get("instance_id", "")
            inserted += 1
        except Exception as e:
            failed += 1

    print(f"         Inserted: {inserted}, Failed: {failed}, Skipped (unresolved): {skipped}")

    # Step 6: Position parts (apply transforms)
    print("  [6/6] Positioning parts...")
    positioned = 0
    for part in parts:
        if not part.instance_id:
            continue
        try:
            transform = part.transform_matrix
            client.assemblies_api.transform_occurrences(
                doc_id, "w", workspace_id, asm_id,
                body={
                    "occurrences": [{"path": [part.instance_id]}],
                    "transform": transform,
                    "isRelative": False,
                }
            )
            positioned += 1
        except Exception:
            pass

    print(f"         Positioned: {positioned}/{inserted}")

    # Save manifest
    manifest = generate_manifest(spec)
    manifest.assembly_url = doc_url
    manifest_path = BASE_DIR / f"{spec.get('year', 0)}_{spec.get('game', 'robot').lower().replace(' ', '_')}_assembly_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(asdict(manifest), f, indent=2)

    print(f"\n{'═' * 65}")
    print(f"  ASSEMBLY COMPLETE")
    print(f"  URL:       {doc_url}")
    print(f"  Parts:     {inserted} inserted, {positioned} positioned")
    print(f"  Manifest:  {manifest_path.name}")
    print(f"{'═' * 65}\n")

    return {
        "url": doc_url,
        "document_id": doc_id,
        "workspace_id": workspace_id,
        "assembly_id": asm_id,
        "parts_inserted": inserted,
        "parts_positioned": positioned,
        "parts_skipped": skipped,
        "manifest_path": str(manifest_path),
    }


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

def main():
    args = sys.argv[1:]
    if not args:
        print("Assembly Builder — Real COTS Assembly Pipeline")
        print()
        print("Commands:")
        print("  python3 assembly_builder.py manifest <blueprint_spec.json>")
        print("  python3 assembly_builder.py build <blueprint_spec.json>")
        print("  python3 assembly_builder.py plan <blueprint_spec.json>  (show part plan)")
        return

    cmd = args[0]
    spec_path = Path(args[1]) if len(args) > 1 else BASE_DIR / "2022_rapid_react_full_blueprint.json"

    if not spec_path.exists():
        print(f"Spec not found: {spec_path}")
        return

    with open(spec_path) as f:
        spec = json.load(f)

    if cmd == "manifest":
        manifest = generate_manifest(spec)
        display_manifest(manifest)

        out_path = spec_path.with_suffix(".assembly_manifest.json")
        with open(out_path, "w") as f:
            json.dump(asdict(manifest), f, indent=2)
        print(f"  Manifest saved: {out_path.name}")

    elif cmd == "plan":
        parts = plan_assembly(spec)
        print(f"\n  Assembly Plan — {len(parts)} part instances\n")

        by_sub = {}
        for p in parts:
            by_sub.setdefault(p.subassembly, []).append(p)

        for sub, sub_parts in sorted(by_sub.items()):
            print(f"  [{sub}] ({len(sub_parts)} parts)")
            for p in sub_parts:
                pos = [round(v, 1) for v in p.position_mm]
                print(f"    {p.name:30s}  {p.catalog_name:35s}  at {pos}")
            print()

    elif cmd == "build":
        game = spec.get("game", "Robot")
        year = spec.get("year", "2025")
        result = build_assembly(spec, name=f"2950 {game} {year} — COTS Assembly")
        print(f"\n  Open in browser: {result.get('url', 'N/A')}")

    else:
        print(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main()
