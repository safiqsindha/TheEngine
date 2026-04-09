#!/usr/bin/env python3
"""
The Blueprint — COTS Part Inserter
Team 2950 — The Devastators

Creates a real OnShape assembly with COTS parts from vendor CAD documents.
Resolves parts by version → inserts individual part bodies → positions them
at coordinates from the assembly planner.

Key lessons learned:
  - External document references MUST use versionId (not workspaceId)
  - Use partId + isWholePartStudio=false to avoid inserting 400+ sub-parts
  - Use isAssembly=true for complex parts (PDH) that are modeled as assemblies
  - OnShape insert API returns empty body on success — query assembly definition
    afterward to get instance IDs for positioning

Uses raw HMAC-SHA256 auth (the onshape_client library has urllib bugs).
"""

import base64
import hashlib
import hmac
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_DIR = Path(__file__).parent

# ── Load .env ──
_env_path = BASE_DIR / ".env"
if _env_path.exists():
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

ACCESS_KEY = os.environ["ONSHAPE_ACCESS_KEY"]
SECRET_KEY = os.environ["ONSHAPE_SECRET_KEY"]
BASE_URL = "https://cad.onshape.com"

# ═══════════════════════════════════════════════════════════════════
# COTS PART REGISTRY
# Each entry has the exact OnShape coordinates needed for insertion:
#   doc:      source document ID
#   ver:      version ID (required for cross-document references)
#   elem:     element ID within that version
#   is_asm:   True if the element is an Assembly (not Part Studio)
#   part_id:  specific partId within a Part Studio (avoids inserting
#             all sub-parts — screws, pins, etc.)
# ═══════════════════════════════════════════════════════════════════

COTS_REGISTRY = {
    # ═══════════════════════════════════════════════════════════
    # Sources:
    #   REV vendor docs  — official REV Robotics OnShape documents
    #   FRCDesignLib     — community library (juliaschatz/onshape-library-window)
    # ═══════════════════════════════════════════════════════════

    # ── Motors ──
    "REV NEO Motor": {
        "doc": "24dc4b87ad8f60ed432cf84e",  # REV vendor
        "ver": "a020b03ec155974b72e0dad5",
        "elem": "a9b91ad14dcc8f6168a39803",
        "is_asm": False,
        "part_id": "JFD",
    },
    "REV NEO 550": {
        "doc": "94cd842681559b5225d6a65d",  # REV vendor
        "ver": "7058453d3c7a214bf9e7d458",
        "elem": "33552f0d44478b8c67625afe",
        "is_asm": False,
        "part_id": "JFD",
    },
    "REV NEO Vortex": {
        "doc": "8245bcd193e0740b7ff84002",  # REV vendor
        "ver": "362b83aa1fe35ad013c5f8c6",
        "elem": "1fb9f91d190a6343346d13a7",
        "is_asm": True,
        "part_id": "",
    },
    "WCP Kraken X60": {
        "doc": "1e490f667f2060acc06d66b0",  # FRCDesignLib Motors
        "ver": "53f9ad47189f3b4de77e81ba",
        "elem": "f000b0eb12c83199847430dc",
        "is_asm": True,
        "part_id": "",
    },

    # ── Motor Controllers ──
    "REV Spark MAX": {
        "doc": "24a3618a96cde81470cc7619",  # REV vendor
        "ver": "b6ce8926d4dc44a656754cbb",
        "elem": "8fe83c196785dee57a9f655e",
        "is_asm": True,
        "part_id": "",
    },
    "REV Spark Flex": {
        "doc": "8245bcd193e0740b7ff84002",  # REV vendor (shared with Vortex)
        "ver": "362b83aa1fe35ad013c5f8c6",
        "elem": "75f3719629b91766ef3f8bb3",
        "is_asm": True,
        "part_id": "",
    },

    # ── Swerve ──
    "SDS MK4i Swerve Module": {
        "doc": "698e922b5304f1d6a2b06339",  # FRCDesignLib Swerve
        "ver": "2f9933801168ce166637b9c2",
        "elem": "0b77427a2fa7aa10301851ac",
        "is_asm": True,
        "part_id": "",
    },

    # ── Electronics ──
    "Power Distribution Hub": {
        "doc": "7abd9d1f0938c06f65ca7ce7",  # REV vendor
        "ver": "924ee07e3e508ccafd20d0a7",
        "elem": "aafdae5cadd3ed0a45f9bdd5",
        "is_asm": True,
        "part_id": "",
    },
    "RoboRIO 2": {
        "doc": "913294293c53429a987b0e72",  # FRCDesignLib Electronics
        "ver": "d80f477ae17bfb450cdeb992",
        "elem": "9ab551bdb91ea59eeb4479be",
        "is_asm": False,
        "part_id": "RkBD",
    },
    "FRC Battery (MK ES17-12)": {
        "doc": "913294293c53429a987b0e72",  # FRCDesignLib Electronics
        "ver": "d80f477ae17bfb450cdeb992",
        "elem": "d4fb95979d4ad65e959318a5",
        "is_asm": False,
        "part_id": "JHD",
    },
    "Main Breaker (120A)": {
        "doc": "913294293c53429a987b0e72",  # FRCDesignLib Electronics
        "ver": "d80f477ae17bfb450cdeb992",
        "elem": "36a27db0718a30acff00a6b0",
        "is_asm": False,
        "part_id": "JRD",
    },
    "OpenMesh Radio (OM5P-AC)": {
        "doc": "913294293c53429a987b0e72",  # FRCDesignLib Electronics
        "ver": "d80f477ae17bfb450cdeb992",
        "elem": "30e4be275853cea93b1378f7",
        "is_asm": False,
        "part_id": "RdBD",
    },

    # ── Gearboxes ──
    "REV MAXPlanetary Gearbox": {
        "doc": "116670a318148214a3504b49",  # REV vendor
        "ver": "19010f58968e2590c1fdd64f",
        "elem": "0fbf6f21d691fa15a20f96f1",
        "is_asm": False,
        "part_id": "JFD",
    },

    # ── Sensors ──
    "REV Through Bore Encoder": {
        "doc": "ed3723cf08a2a96a39a7132d",  # REV vendor
        "ver": "a6f6721c70ae8b7af660ab0b",
        "elem": "117aba981cefb6c100d995c6",
        "is_asm": True,
        "part_id": "",
    },
    "CTRE Pigeon 2.0 IMU": {
        "doc": "990a1de0f0e5dded8f3cec1b",  # FRCDesignLib Sensors
        "ver": "50195c55d3747c32e80c3c83",
        "elem": "c66c89d2f1fea1f4b1621f12",
        "is_asm": False,
        "part_id": "JtD",
    },

    # ── Structure ──
    "WCP 90\u00b0 Gusset (2x1 to 2x1)": {
        "doc": "b0e317da377b0565c96fc265",  # FRCDesignLib Gussets
        "ver": "cbe157a805604f06ccc5535d",
        "elem": "d5d9651c0ee5e1170eaa7f5d",
        "is_asm": False,
        "part_id": "JPD",
    },
    "Flanged Bearing 1/2in Hex": {
        "doc": "836cd26e60025118646fa104",  # FRCDesignLib Bearings
        "ver": "f80305b5989c0356c206b4b4",
        "elem": "cfbd251bf34e4159e9b98da2",
        "is_asm": False,
        "part_id": "JTD",
    },
    "1/2in Hex Shaft": {
        "doc": "360f7941a43b138116bd29b6",  # FRCDesignLib Extrusions
        "ver": "db0e96c3c7c6287fbbe1fef8",
        "elem": "9f4aace5c3f38ced43b69179",
        "is_asm": False,
        "part_id": "JHD",
    },
}


# ═══════════════════════════════════════════════════════════════════
# HMAC AUTH
# ═══════════════════════════════════════════════════════════════════

def make_headers(method: str, path: str, query: str = "",
                 content_type: str = "application/json") -> dict:
    date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
    nonce = base64.b64encode(os.urandom(25)).decode()
    hmac_str = (
        method + "\n" + nonce + "\n" + date + "\n" +
        content_type + "\n" + path + "\n" + query + "\n"
    ).lower()
    signature = base64.b64encode(
        hmac.new(SECRET_KEY.encode(), hmac_str.encode(), hashlib.sha256).digest()
    ).decode()
    return {
        "Content-Type": content_type,
        "Accept": "application/json",
        "Date": date,
        "On-Nonce": nonce,
        "Authorization": f"On {ACCESS_KEY}:HmacSHA256:{signature}",
    }


def api_get(path: str, query: str = ""):
    headers = make_headers("GET", path, query)
    url = BASE_URL + path + ("?" + query if query else "")
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    return resp.json()


def api_post(path: str, body: dict, query: str = ""):
    headers = make_headers("POST", path, query, "application/json")
    url = BASE_URL + path + ("?" + query if query else "")
    resp = requests.post(url, headers=headers, json=body)
    resp.raise_for_status()
    text = resp.text.strip()
    return resp.json() if text else {}


# ═══════════════════════════════════════════════════════════════════
# ASSEMBLY OPERATIONS
# ═══════════════════════════════════════════════════════════════════

def create_document(name: str) -> tuple[str, str, str]:
    """Create document, return (doc_id, workspace_id, assembly_element_id)."""
    resp = api_post("/api/v6/documents", {
        "name": name,
        "description": "Generated by The Engine — Real COTS Assembly Pipeline",
        "isPublic": True,
    })
    doc_id = resp["id"]
    ws_id = resp["defaultWorkspace"]["id"]

    # Find the default Assembly tab
    elements = api_get(f"/api/v6/documents/d/{doc_id}/w/{ws_id}/elements")
    asm_id = ""
    for e in elements:
        if e.get("elementType") == "ASSEMBLY":
            asm_id = e["id"]
            break

    return doc_id, ws_id, asm_id


def insert_part(doc_id: str, ws_id: str, asm_id: str, cots: dict):
    """Insert one COTS part into the assembly."""
    path = f"/api/v6/assemblies/d/{doc_id}/w/{ws_id}/e/{asm_id}/instances"
    body = {
        "documentId": cots["doc"],
        "versionId": cots["ver"],
        "elementId": cots["elem"],
    }
    if cots["is_asm"]:
        body["isAssembly"] = True
        body["isWholePartStudio"] = False
    else:
        body["isWholePartStudio"] = False
        body["partId"] = cots["part_id"]

    api_post(path, body)


def get_instance_ids(doc_id: str, ws_id: str, asm_id: str) -> list[dict]:
    """Query assembly definition to get instance IDs for positioning."""
    path = f"/api/v6/assemblies/d/{doc_id}/w/{ws_id}/e/{asm_id}"
    data = api_get(path)
    return data.get("rootAssembly", {}).get("instances", [])


def position_instances(doc_id: str, ws_id: str, asm_id: str,
                       instances: list[dict], plan: list):
    """Apply transforms to position instances at planned coordinates."""
    path = f"/api/v6/assemblies/d/{doc_id}/w/{ws_id}/e/{asm_id}/occurrencetransforms"
    positioned = 0

    for inst, part in zip(instances, plan):
        iid = inst["id"]
        # Convert mm → meters (OnShape units)
        tx = part.position_mm[0] / 1000.0
        ty = part.position_mm[1] / 1000.0
        tz = part.position_mm[2] / 1000.0

        transform = [
            1, 0, 0, tx,
            0, 1, 0, ty,
            0, 0, 1, tz,
            0, 0, 0, 1,
        ]

        body = {
            "occurrences": [{"path": [iid]}],
            "transform": transform,
            "isRelative": False,
        }
        try:
            api_post(path, body)
            positioned += 1
            pos_str = f"({tx:.3f}, {ty:.3f}, {tz:.3f})m"
            print(f"    [OK] {part.name:35s} at {pos_str}")
        except Exception as e:
            print(f"    [FAIL] {part.name}: {e}")
        time.sleep(0.3)

    return positioned


# ═══════════════════════════════════════════════════════════════════
# FULL PIPELINE
# ═══════════════════════════════════════════════════════════════════

def build_cots_assembly(spec_path: str = None):
    """Full pipeline: create doc → insert COTS → position."""
    # Load blueprint spec
    if not spec_path:
        spec_path = str(BASE_DIR / "2022_rapid_react_full_blueprint.json")
    with open(spec_path) as f:
        spec = json.load(f)

    game = spec.get("game", "Robot")
    year = spec.get("year", 2025)

    print(f"\n{'═' * 65}")
    print(f"  THE ENGINE — COTS ASSEMBLY BUILDER")
    print(f"  {year} {game}")
    print(f"{'═' * 65}\n")

    # Get assembly plan
    from assembly_builder import plan_assembly
    all_parts = plan_assembly(spec)
    insertable = [p for p in all_parts if p.catalog_name in COTS_REGISTRY]

    print(f"  Assembly plan: {len(all_parts)} total, {len(insertable)} have COTS CAD")
    cots_names = set(p.catalog_name for p in insertable)
    for cn in sorted(cots_names):
        count = sum(1 for p in insertable if p.catalog_name == cn)
        print(f"    {cn:40s}  x{count}")

    # Create fresh document
    print(f"\n  Creating OnShape document...")
    doc_id, ws_id, asm_id = create_document(f"2950 {game} {year} — COTS Assembly")
    url = f"{BASE_URL}/documents/{doc_id}"
    print(f"  Document: {url}")

    # Insert parts
    print(f"\n  Inserting {len(insertable)} COTS parts...")
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

    # Get instance IDs for positioning
    print(f"\n  Querying assembly for instance IDs...")
    instances = get_instance_ids(doc_id, ws_id, asm_id)
    print(f"  Found {len(instances)} instances")

    # Position — use min count if assembly merges some instances
    count = min(len(instances), len(insertable))
    if count > 0:
        print(f"\n  Positioning {count} parts...")
        positioned = position_instances(doc_id, ws_id, asm_id,
                                        instances[:count], insertable[:count])
    else:
        positioned = 0

    # Summary
    print(f"\n{'═' * 65}")
    print(f"  ASSEMBLY COMPLETE — {year} {game}")
    print(f"  Parts inserted:   {inserted}")
    print(f"  Parts positioned: {positioned}")
    print(f"  Parts unresolved: {len(all_parts) - len(insertable)}")
    print(f"\n  Open: {url}")
    print(f"{'═' * 65}\n")

    # Save state
    state = {
        "document_id": doc_id,
        "workspace_id": ws_id,
        "assembly_id": asm_id,
        "url": url,
        "inserted": inserted,
        "positioned": positioned,
        "game": game,
        "year": year,
    }
    with open(BASE_DIR / "fresh_assembly_ids.json", "w") as f:
        json.dump(state, f, indent=2)

    return state


def resolve_new_part(name: str, doc_id: str):
    """Resolve a new COTS part and add it to the registry.

    Usage: python3 insert_cots.py add-part "RoboRIO 2" abc123def456...
    """
    print(f"\n  Resolving: {name} (doc: {doc_id[:16]}...)")

    # Get latest version
    versions = api_get(f"/api/v6/documents/d/{doc_id}/versions")
    if not versions:
        print("  FAIL: no versions")
        return
    ver = versions[-1]
    ver_id = ver["id"]
    print(f"  Version: {ver.get('name', '')} ({ver_id[:16]}...)")

    # Get elements
    elements = api_get(f"/api/v6/documents/d/{doc_id}/v/{ver_id}/elements")
    print(f"  Elements ({len(elements)}):")

    for e in elements:
        etype = e.get("elementType", "")
        eid = e.get("id", "")
        ename = e.get("name", "")
        if etype in ("PARTSTUDIO", "ASSEMBLY"):
            print(f"    {etype:15s} {eid} \"{ename}\"")

            if etype == "PARTSTUDIO":
                # Check part count
                try:
                    parts = api_get(f"/api/v6/parts/d/{doc_id}/v/{ver_id}/e/{eid}")
                    print(f"      → {len(parts)} parts")
                    if len(parts) <= 3:
                        for p in parts:
                            print(f"        partId={p.get('partId','')} \"{p.get('name','')}\"")
                except Exception:
                    print(f"      → (could not list parts)")

    print(f"\n  Add to COTS_REGISTRY in insert_cots.py:")
    print(f"    \"{name}\": {{")
    print(f"        \"doc\": \"{doc_id}\",")
    print(f"        \"ver\": \"{ver_id}\",")
    print(f"        \"elem\": \"<element_id>\",")
    print(f"        \"is_asm\": False,  # True if Assembly")
    print(f"        \"part_id\": \"JFD\",  # or empty for assemblies")
    print(f"    }},")


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"

    if cmd == "build":
        spec = sys.argv[2] if len(sys.argv) > 2 else None
        build_cots_assembly(spec)

    elif cmd == "add-part":
        if len(sys.argv) < 4:
            print("Usage: python3 insert_cots.py add-part <name> <document_id>")
            return
        resolve_new_part(sys.argv[2], sys.argv[3])

    elif cmd == "registry":
        print(f"\nCOTS Registry ({len(COTS_REGISTRY)} parts):")
        for name, info in COTS_REGISTRY.items():
            asm = " [ASM]" if info["is_asm"] else ""
            print(f"  {name:40s} doc={info['doc'][:12]}...{asm}")

    else:
        print("COTS Part Inserter — Real OnShape Assembly Pipeline")
        print()
        print("Commands:")
        print("  python3 insert_cots.py build [spec.json]    Build full COTS assembly")
        print("  python3 insert_cots.py add-part <name> <doc_id>  Resolve new part")
        print("  python3 insert_cots.py registry              Show resolved parts")


if __name__ == "__main__":
    main()
