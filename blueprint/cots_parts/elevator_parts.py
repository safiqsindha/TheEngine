"""
blueprint/cots_parts/elevator_parts.py
Team 2950 — The Devastators

COTS part-ID mapping for cascade elevator components.
Format matches frcdesignlib_parts.json: doc/ver/elem/part_id/is_asm/elem_name.

WCP is primary vendor. REV/TTB secondary. Part IDs verified via MCP search on
2026-04-13 against the FRCDesignLib "Linear Mechanism Components" document and
the Sensor Parts document.

NOTE on rail tubes and carriage plates:
  These are NOT in FRCDesignLib as insertable COTS parts — FRCDesign creates
  them as custom Part Studio geometry. The generator creates them on-the-fly
  via create_part_studio + create_sketch_rectangle + create_extrude.
  The TUBE_* and CARRIAGE_* entries below are geometry specs only (no doc/elem);
  the generator checks is_asm == None to identify geometry-created parts.

NOTE on account limit:
  Free Onshape accounts are limited to 5 documents. create_document returns 409
  when the limit is reached. The generator uses an EXISTING document (passed via
  --doc-id) rather than creating a new one. See elevator_rev2.py --doc-id flag.
"""

import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Import Kraken X60 from frcdesignlib_parts.json — do not duplicate doc ID
# ---------------------------------------------------------------------------
_FRCDESIGN_JSON = Path(__file__).parent.parent / "frcdesignlib_parts.json"
_frcdesign = json.loads(_FRCDESIGN_JSON.read_text())

_KRAKEN_X60_ENTRY = _frcdesign.get("WCP Kraken X60", {})

# ---------------------------------------------------------------------------
# Linear Mechanism Components document (verified 2026-04-13)
# doc: f984b6b78196881d9906e72e  workspace: c2d92b345eb5fac5003034dd
# ---------------------------------------------------------------------------
_LMC_DOC = "f984b6b78196881d9906e72e"
_LMC_VER = None  # workspace (in-progress)
_LMC_WS  = "c2d92b345eb5fac5003034dd"

# Sensor Parts document (verified 2026-04-13)
# doc: fa27cf827e5efa781853e0fb  workspace: a5e301397855a3ee362f1945
_SENSOR_DOC = "fa27cf827e5efa781853e0fb"
_SENSOR_VER = None
_SENSOR_WS  = "a5e301397855a3ee362f1945"

# REV NEO from resolved_cots_v2.json (verified pre-existing)
_NEO_DOC  = "24dc4b87ad8f60ed432cf84e"
_NEO_VER  = "a020b03ec155974b72e0dad5"
_NEO_ELEM = "a9b91ad14dcc8f6168a39803"

# ---------------------------------------------------------------------------
# ELEVATOR_PARTS — keyed by logical name used in elevator_rev2.py
# ---------------------------------------------------------------------------
#
# is_asm = True  → add_assembly_instance with isAssembly=True
# is_asm = False → add_assembly_instance with isAssembly=False (part studio)
# is_asm = None  → geometry-created part (no Onshape insert; generator builds it)
#
# geometry_spec is only present for is_asm == None parts.
# Required fields for insertable parts: doc, elem, is_asm, elem_name
# Optional: ver (None = current workspace), part_id (empty string if asm)
#
ELEVATOR_PARTS: dict = {

    # ── Rail tubes ─────────────────────────────────────────────────────────
    # Created as Part Studio geometry; not in FRCDesignLib as COTS.
    # tube_spec: "WxHxWALL" in inches; length_in set by physics layer.
    "stage_rail_2x1_24in": {
        "is_asm": None,
        "elem_name": "Stage Rail Tube 2x1x0.0625 — 24in",
        "geometry_spec": {
            "width_in": 2.0, "height_in": 1.0, "wall_in": 0.0625,
            "length_in": 24.0,
        },
    },
    "stage_rail_2x1_28in": {
        "is_asm": None,
        "elem_name": "Stage Rail Tube 2x1x0.0625 — 28in",
        "geometry_spec": {
            "width_in": 2.0, "height_in": 1.0, "wall_in": 0.0625,
            "length_in": 28.0,
        },
    },
    "stage_rail_2x1_30in": {
        "is_asm": None,
        "elem_name": "Stage Rail Tube 2x1x0.0625 — 30in",
        "geometry_spec": {
            "width_in": 2.0, "height_in": 1.0, "wall_in": 0.0625,
            "length_in": 30.0,
        },
    },
    "stage_rail_2x1_36in": {
        "is_asm": None,
        "elem_name": "Stage Rail Tube 2x1x0.0625 — 36in",
        "geometry_spec": {
            "width_in": 2.0, "height_in": 1.0, "wall_in": 0.0625,
            "length_in": 36.0,
        },
    },

    # ── Carriage plate ──────────────────────────────────────────────────────
    # Created as Part Studio geometry; thickness selected by physics layer.
    "carriage_plate_0125": {
        "is_asm": None,
        "elem_name": "Carriage Plate — 0.125in 6061 Al",
        "geometry_spec": {
            "width_in": 10.0, "height_in": 8.0, "thickness_in": 0.125,
        },
    },
    "carriage_plate_0250": {
        "is_asm": None,
        "elem_name": "Carriage Plate — 0.250in 6061 Al",
        "geometry_spec": {
            "width_in": 10.0, "height_in": 8.0, "thickness_in": 0.250,
        },
    },

    # ── Bearing blocks (WCP inline — primary, verified in LMC doc) ─────────
    "wcp_elevator_bearing_block_inline": {
        "doc": _LMC_DOC, "ver": _LMC_VER, "elem": "39267273a3250eac7230838e",
        "is_asm": True, "part_id": "",
        "elem_name": "Elevator Bearing Block - Inline (WCP)",
    },
    "wcp_elevator_bearing_block_clamping": {
        "doc": _LMC_DOC, "ver": _LMC_VER, "elem": "1c3cfb14706c85e3f62d57ae",
        "is_asm": True, "part_id": "",
        "elem_name": "Elevator Bearing Block - Clamping (WCP)",
    },
    # TTB bearing block — secondary vendor
    "ttb_elevator_bearing_block": {
        "doc": _LMC_DOC, "ver": _LMC_VER, "elem": "f406f2bc26f9f428ea3dd70a",
        "is_asm": True, "part_id": "",
        "elem_name": "Elevator Bearing Block (TTB)",
    },

    # ── Greyt Telescope Gearbox (WCP) — primary gearbox ────────────────────
    # One assembly covers all ratios via configuration in Onshape.
    # Phase 1: single assembly insert; ratio is documented in BOM note only.
    "wcp_greyt_telescope_gearbox": {
        "doc": _LMC_DOC, "ver": _LMC_VER, "elem": "1822be61eb996a68afd54913",
        "is_asm": True, "part_id": "",
        "elem_name": "Greyt Telescope Gearbox (WCP)",
    },

    # ── Motors ─────────────────────────────────────────────────────────────
    "kraken_x60": {
        "doc":  _KRAKEN_X60_ENTRY.get("doc", "1e490f667f2060acc06d66b0"),
        "ver":  _KRAKEN_X60_ENTRY.get("ver", "53f9ad47189f3b4de77e81ba"),
        "elem": _KRAKEN_X60_ENTRY.get("elem", "f000b0eb12c83199847430dc"),
        "is_asm": True,
        "part_id": _KRAKEN_X60_ENTRY.get("part_id", ""),
        "elem_name": _KRAKEN_X60_ENTRY.get("elem_name", "Kraken X60 Brushless Motor"),
    },
    "neo_brushless": {
        "doc": _NEO_DOC, "ver": _NEO_VER, "elem": _NEO_ELEM,
        "is_asm": False, "part_id": "",
        "elem_name": "NEO Brushless Motor (REV-21-1650)",
    },

    # ── Encoder ─────────────────────────────────────────────────────────────
    "through_bore_encoder": {
        "doc": _SENSOR_DOC, "ver": _SENSOR_VER,
        "elem": "7c218d56a5f862bd63d78a7b",
        "is_asm": False, "part_id": "JnD",
        "elem_name": "REV Through Bore Encoder",
    },

    # ── Constant force springs (WCP primary, TTB secondary) ─────────────────
    # WCP spring: 4 lb × 40" travel (part_id JHD)
    "constant_force_spring_4lb_wcp": {
        "doc": _LMC_DOC, "ver": _LMC_VER, "elem": "bb9fb27621f03eed62f2c709",
        "is_asm": False, "part_id": "JHD",
        "elem_name": "Constant Force Spring (4 lbs, 40in Travel) WCP",
    },
    # TTB spring: 16.5 lb × 50" travel (part_id JID)
    "constant_force_spring_16lb_ttb": {
        "doc": _LMC_DOC, "ver": _LMC_VER, "elem": "163bdf09ed341654005e0a06",
        "is_asm": False, "part_id": "JID",
        "elem_name": "Constant Force Spring (16.5 lbs, 50in Travel) TTB",
    },

    # ── Belt kit (geometry only — no FRCDesignLib belt part) ────────────────
    # Phase 1: documented in BOM notes only; no 3D instance added.
    "belt_9mm_htd3_kit": {
        "is_asm": None,
        "elem_name": "9mm HTD3 Belt + 18T Pulleys Kit",
        "geometry_spec": {
            "note": "belt-in-tube; no 3D instance in Phase 1 assembly",
        },
    },
}

# ---------------------------------------------------------------------------
# Required fields for validation
# ---------------------------------------------------------------------------
_REQUIRED_FIELDS_INSERTABLE = {"doc", "elem", "is_asm", "elem_name"}
_REQUIRED_FIELDS_GEOMETRY   = {"is_asm", "elem_name", "geometry_spec"}


def resolve(key: str) -> dict:
    """
    Return part dict for the given logical key.
    Raises KeyError with a helpful message if the key is unknown.

    For is_asm == None (geometry-created) parts the caller must use
    _create_tube_part_studio() / _create_plate_part_studio() in elevator_rev2.py
    rather than calling add_assembly_instance directly.
    """
    if key not in ELEVATOR_PARTS:
        available = ", ".join(sorted(ELEVATOR_PARTS))
        raise KeyError(
            f"elevator_parts: unknown key '{key}'. "
            f"Available keys: {available}"
        )
    return ELEVATOR_PARTS[key]


def resolve_spring_for_load(load_lb: float) -> dict:
    """
    Return the appropriate spring key given carriage load.
    WCP 4 lb spring for load <= 8 lb (use 2 springs in parallel).
    TTB 16.5 lb spring for load > 8 lb.
    """
    if load_lb <= 8.0:
        return resolve("constant_force_spring_4lb_wcp")
    return resolve("constant_force_spring_16lb_ttb")


def resolve_bearing_block(vendor: str = "wcp") -> dict:
    """Return the primary bearing block for the given vendor."""
    key_map = {
        "wcp":  "wcp_elevator_bearing_block_inline",
        "ttb":  "ttb_elevator_bearing_block",
        "rev":  "wcp_elevator_bearing_block_inline",  # fallback to WCP
    }
    return resolve(key_map.get(vendor.lower(), "wcp_elevator_bearing_block_inline"))


def validate_all() -> list[str]:
    """
    Validate every entry in ELEVATOR_PARTS has required fields.
    Returns list of error strings (empty = all OK).
    """
    errors = []
    for key, entry in ELEVATOR_PARTS.items():
        if entry.get("is_asm") is None:
            required = _REQUIRED_FIELDS_GEOMETRY
        else:
            required = _REQUIRED_FIELDS_INSERTABLE
        missing = required - set(entry.keys())
        if missing:
            errors.append(f"  {key}: missing fields {missing}")
    return errors


if __name__ == "__main__":
    errors = validate_all()
    if errors:
        print("ELEVATOR_PARTS validation FAILED:")
        for e in errors:
            print(e)
        sys.exit(1)
    print(f"ELEVATOR_PARTS OK — {len(ELEVATOR_PARTS)} entries validated.")
    for key in sorted(ELEVATOR_PARTS):
        e = ELEVATOR_PARTS[key]
        vendor_note = "(geometry)" if e["is_asm"] is None else "(insertable)"
        print(f"  {key}: {e['elem_name']}  {vendor_note}")
