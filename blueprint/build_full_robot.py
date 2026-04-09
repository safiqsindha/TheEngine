#!/usr/bin/env python3
"""
The Engine — Full Robot Assembly Builder
Team 2950 — The Devastators

Creates a complete OnShape assembly with:
  1. Frame geometry via FeatureScript (perimeter tubes, cross members, bellypan,
     swerve module housings, mechanism shapes)
  2. Real COTS parts from FRCDesignLib + vendor docs (53 parts for 2022)
  3. All parts positioned at planned coordinates

Usage:
  python3 build_full_robot.py                          # 2022 Rapid React (default)
  python3 build_full_robot.py <blueprint_spec.json>    # Any blueprint spec
"""

import json
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).parent

# Import from our pipeline modules
from insert_cots import (
    api_get, api_post, make_headers,
    COTS_REGISTRY, BASE_URL,
    create_document, insert_part, get_instance_ids, position_instances,
)
from assembly_builder import plan_assembly
from cad_builder import generate_full_featurescript

import requests


def build_full_robot(spec_path: str = None):
    """Full pipeline: frame FeatureScript + COTS parts → OnShape assembly."""

    # ── Load spec ──
    if not spec_path:
        spec_path = str(BASE_DIR / "2022_rapid_react_full_blueprint.json")
    with open(spec_path) as f:
        spec = json.load(f)

    game = spec.get("game", "Robot")
    year = spec.get("year", 2025)

    print(f"\n{'═' * 65}")
    print(f"  THE ENGINE — FULL ROBOT ASSEMBLY BUILDER")
    print(f"  {year} {game}")
    print(f"{'═' * 65}\n")

    # ── Plan assembly ──
    all_parts = plan_assembly(spec)
    insertable = [p for p in all_parts if p.catalog_name in COTS_REGISTRY]

    print(f"  Assembly plan: {len(all_parts)} total, {len(insertable)} COTS parts")
    cots_names = set(p.catalog_name for p in insertable)
    for cn in sorted(cots_names):
        count = sum(1 for p in insertable if p.catalog_name == cn)
        print(f"    {cn:40s}  x{count}")

    # ── Generate FeatureScript ──
    print(f"\n  [1/7] Generating FeatureScript...")
    fs_code = generate_full_featurescript(spec)
    print(f"         {len(fs_code)} chars, frame + mechanisms")

    # Save FeatureScript for reference
    fs_path = BASE_DIR / f"{year}_{game.lower().replace(' ', '_')}_full_robot.fs"
    with open(fs_path, "w") as f:
        f.write(fs_code)
    print(f"         Saved: {fs_path.name}")

    # ── Create OnShape document ──
    print(f"\n  [2/7] Creating OnShape document...")
    doc_id, ws_id, asm_id = create_document(f"2950 {game} {year} — Full Robot")
    url = f"{BASE_URL}/documents/{doc_id}"
    print(f"         {url}")

    # Find the Part Studio element
    elements = api_get(f"/api/v6/documents/d/{doc_id}/w/{ws_id}/elements")
    ps_id = ""
    for e in elements:
        if e.get("elementType") == "PARTSTUDIO":
            ps_id = e["id"]
            break
    print(f"         Part Studio: {ps_id[:16]}...")

    # ── Create Feature Studio and upload FeatureScript ──
    print(f"\n  [3/7] Uploading FeatureScript to Feature Studio...")
    try:
        fs_resp = api_post(f"/api/v6/featurestudios/d/{doc_id}/w/{ws_id}", {
            "name": "2950 Robot Geometry",
        })
        fs_id = fs_resp.get("id", "")
        print(f"         Feature Studio: {fs_id[:16]}...")

        # Get microversion from the Feature Studio contents
        time.sleep(1.0)
        fs_contents = api_get(f"/api/v6/featurestudios/d/{doc_id}/w/{ws_id}/e/{fs_id}")
        mv = fs_contents.get("sourceMicroversion", "")

        # Upload FeatureScript code
        path = f"/api/v6/featurestudios/d/{doc_id}/w/{ws_id}/e/{fs_id}"
        headers = make_headers("POST", path, "", "application/json")
        resp = requests.post(BASE_URL + path, headers=headers, json={
            "contents": fs_code,
            "serializationVersion": "1.2.17",
            "sourceMicroversion": mv,
        })
        resp.raise_for_status()
        print(f"         FeatureScript uploaded OK")
    except Exception as e:
        print(f"         FeatureScript upload failed: {e}")
        fs_id = ""

    # ── Apply custom feature to Part Studio ──
    print(f"\n  [4/7] Applying feature to Part Studio...")
    if fs_id and ps_id:
        try:
            time.sleep(1.0)
            # Get the namespace from the Feature Studio
            fs_contents = api_get(f"/api/v6/featurestudios/d/{doc_id}/w/{ws_id}/e/{fs_id}")
            mv = fs_contents.get("sourceMicroversion", mv)

            import uuid
            fid = f"F{uuid.uuid4().hex[:16]}"
            namespace = f"e{fs_id}::m{mv}"

            feature_body = {
                "feature": {
                    "btType": "BTMFeature-134",
                    "namespace": namespace,
                    "featureType": "blueprintRobot",
                    "name": "2950 Full Robot",
                    "parameters": [],
                    "suppressed": False,
                    "featureId": fid,
                },
                "btType": "BTFeatureDefinitionCall-1406",
            }

            path = f"/api/v6/partstudios/d/{doc_id}/w/{ws_id}/e/{ps_id}/features"
            headers = make_headers("POST", path, "", "application/json")
            resp = requests.post(BASE_URL + path, headers=headers, json=feature_body)
            resp.raise_for_status()
            print(f"         Custom feature applied OK")
        except Exception as e:
            print(f"         Feature apply note: {e}")

    # ── Insert Part Studio into Assembly ──
    print(f"\n  [5/7] Inserting frame into assembly...")
    if ps_id and asm_id:
        try:
            time.sleep(0.5)
            asm_path = f"/api/v6/assemblies/d/{doc_id}/w/{ws_id}/e/{asm_id}/instances"
            api_post(asm_path, {
                "documentId": doc_id,
                "elementId": ps_id,
                "isWholePartStudio": True,
            })
            print(f"         Frame Part Studio inserted")
        except Exception as e:
            print(f"         Frame insert note: {e}")

    # ── Insert COTS parts ──
    print(f"\n  [6/7] Inserting {len(insertable)} COTS parts...")
    inserted = 0
    for part in insertable:
        cots = COTS_REGISTRY[part.catalog_name]
        try:
            insert_part(doc_id, ws_id, asm_id, cots)
            inserted += 1
            print(f"    [OK] {part.name:35s} → {part.catalog_name}")
        except Exception as e:
            print(f"    [FAIL] {part.name}: {e}")
        time.sleep(0.3)

    print(f"  Inserted {inserted}/{len(insertable)}")

    # ── Position all parts ──
    print(f"\n  [7/7] Positioning parts...")
    time.sleep(1)
    instances = get_instance_ids(doc_id, ws_id, asm_id)
    print(f"  Found {len(instances)} instances in assembly")

    # Skip first instance (frame Part Studio) for positioning — it stays at origin
    # COTS instances start after the frame
    cots_instances = instances[1:] if len(instances) > len(insertable) else instances
    count = min(len(cots_instances), len(insertable))

    if count > 0:
        positioned = position_instances(doc_id, ws_id, asm_id,
                                        cots_instances[:count], insertable[:count])
    else:
        positioned = 0

    # ── Summary ──
    print(f"\n{'═' * 65}")
    print(f"  FULL ROBOT ASSEMBLY COMPLETE — {year} {game}")
    print(f"  Frame geometry:   42 fCuboid shapes (FeatureScript)")
    print(f"  COTS inserted:    {inserted}/{len(insertable)}")
    print(f"  Parts positioned: {positioned}")
    print(f"  COTS registry:    {len(COTS_REGISTRY)} unique parts")
    print(f"\n  OPEN: {url}")
    print(f"{'═' * 65}\n")

    # Save state
    state = {
        "document_id": doc_id,
        "workspace_id": ws_id,
        "assembly_id": asm_id,
        "part_studio_id": ps_id,
        "feature_studio_id": fs_id,
        "url": url,
        "inserted": inserted,
        "positioned": positioned,
        "game": game,
        "year": year,
    }
    with open(BASE_DIR / "fresh_assembly_ids.json", "w") as f:
        json.dump(state, f, indent=2)

    return state


if __name__ == "__main__":
    spec = sys.argv[1] if len(sys.argv) > 1 else None
    build_full_robot(spec)
