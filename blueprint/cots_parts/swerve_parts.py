"""
blueprint/cots_parts/swerve_parts.py
Team 2950 — The Devastators

COTS part-ID mapping for swerve drive frame components.
Format matches frcdesignlib_parts.json: doc/ver/elem/part_id/is_asm/elem_name.

WCP is primary vendor. SDS secondary. Part IDs verified via frcdesignlib_parts.json
on 2026-04-13.

NOTE on frame rails:
  Frame perimeter tubes are NOT in FRCDesignLib as insertable COTS parts.
  The generator creates them on-the-fly via create_part_studio + sketch + extrude.
  Entries with is_asm == None are geometry-created; the generator uses them for
  type checking only and never calls add_assembly_instance on them.

NOTE on module coverage:
  SDS MK4i is the canonical module in FRCDesignLib (verified 2026-04-13).
  WCP Swerve X and REV MaxSwerve are not yet in FRCDesignLib — generator falls
  back to SDS MK4i with a warning logged to missing_parts. Add in Phase 3 when
  their doc IDs are verified via search_documents.

NOTE on account limit:
  Free Onshape accounts are limited to 5 docs. Pass --doc-id to reuse an
  existing document. See swerve_rev2.py --doc-id flag.
"""

import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Import canonical parts from frcdesignlib_parts.json — do not duplicate doc IDs
# ---------------------------------------------------------------------------
_FRCDESIGN_JSON = Path(__file__).parent.parent / "frcdesignlib_parts.json"
_frcdesign = json.loads(_FRCDESIGN_JSON.read_text())

_MK4I_ENTRY   = _frcdesign.get("SDS MK4i Swerve Module", {})
_GUSSET_ENTRY = _frcdesign.get("WCP 90° Gusset (2x1 to 2x1)", {})

# ---------------------------------------------------------------------------
# SWERVE_PARTS — keyed by logical name used in swerve_rev2.py
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
SWERVE_PARTS: dict = {

    # ── Frame rail tubes ────────────────────────────────────────────────────
    # Created as Part Studio geometry; not in FRCDesignLib as COTS.
    # Two variants — long-side (wheelbase-length) and short-side (trackwidth-length).
    # Actual lengths are computed at runtime from wheelbase/trackwidth oracle inputs.
    "frame_rail_longside": {
        "is_asm": None,
        "elem_name": "Frame Rail Tube (long-side) 2x1x0.0625",
        "geometry_spec": {
            "width_in": 2.0, "height_in": 1.0, "wall_in": 0.0625,
            "note": "length_in set by physics layer from wheelbase_in",
        },
    },
    "frame_rail_shortside": {
        "is_asm": None,
        "elem_name": "Frame Rail Tube (short-side) 2x1x0.0625",
        "geometry_spec": {
            "width_in": 2.0, "height_in": 1.0, "wall_in": 0.0625,
            "note": "length_in set by physics layer from trackwidth_in",
        },
    },

    # ── Corner gussets (WCP 90° — primary, verified in frcdesignlib_parts.json)
    # WCP 90° Gusset 2x1→2x1, part_id JPD.
    "wcp_90deg_gusset_2x1": {
        "doc":      _GUSSET_ENTRY.get("doc",      "b0e317da377b0565c96fc265"),
        "ver":      _GUSSET_ENTRY.get("ver",      "cbe157a805604f06ccc5535d"),
        "elem":     _GUSSET_ENTRY.get("elem",     "d5d9651c0ee5e1170eaa7f5d"),
        "is_asm":   False,
        "part_id":  _GUSSET_ENTRY.get("part_id",  "JPD"),
        "elem_name": _GUSSET_ENTRY.get("elem_name", "Bracket/Gusset (WCP)"),
    },

    # ── Swerve modules ──────────────────────────────────────────────────────

    # SDS MK4i — canonical FRCDesignLib module (verified 2026-04-13)
    "sds_mk4i": {
        "doc":      _MK4I_ENTRY.get("doc",      "698e922b5304f1d6a2b06339"),
        "ver":      _MK4I_ENTRY.get("ver",      "2f9933801168ce166637b9c2"),
        "elem":     _MK4I_ENTRY.get("elem",     "0b77427a2fa7aa10301851ac"),
        "is_asm":   True,
        "part_id":  _MK4I_ENTRY.get("part_id",  ""),
        "elem_name": _MK4I_ENTRY.get("elem_name", "SDS MK4i"),
    },

    # WCP Swerve X — NOT yet in FRCDesignLib (2026-04-13).
    # Generator falls back to SDS MK4i with a warning.
    # Placeholder entry so resolve() gives a helpful error instead of KeyError.
    "wcp_swerve_x": {
        "is_asm": None,
        "elem_name": "WCP Swerve X (not yet in FRCDesignLib — fallback to SDS MK4i)",
        "geometry_spec": {
            "note": "Phase 2 deferred — search_documents for WCP Swerve X doc ID",
        },
    },

    # REV MaxSwerve — NOT yet in FRCDesignLib (2026-04-13).
    "rev_maxswerve": {
        "is_asm": None,
        "elem_name": "REV MaxSwerve (not yet in FRCDesignLib — fallback to SDS MK4i)",
        "geometry_spec": {
            "note": "Phase 2 deferred — search_documents for REV MaxSwerve doc ID",
        },
    },
}

# ---------------------------------------------------------------------------
# MODULE_TYPE_MAP — oracle string → SWERVE_PARTS key
# ---------------------------------------------------------------------------
MODULE_TYPE_MAP: dict[str, str] = {
    "sds_mk4i":      "sds_mk4i",
    "wcp_swerve_x":  "wcp_swerve_x",   # will warn + fallback at runtime
    "rev_maxswerve": "rev_maxswerve",  # will warn + fallback at runtime
}

# Canonical fallback when module type is unavailable
MODULE_FALLBACK_KEY = "sds_mk4i"

# ---------------------------------------------------------------------------
# Required fields for validation
# ---------------------------------------------------------------------------
_REQUIRED_FIELDS_INSERTABLE = {"doc", "elem", "is_asm", "elem_name"}
_REQUIRED_FIELDS_GEOMETRY   = {"is_asm", "elem_name", "geometry_spec"}


def resolve(key: str) -> dict:
    """
    Return part dict for the given logical key.
    Raises KeyError with a helpful message if the key is unknown.

    For is_asm == None (geometry-created) parts the caller must build geometry
    via Part Studio rather than calling add_assembly_instance directly.
    """
    if key not in SWERVE_PARTS:
        available = ", ".join(sorted(SWERVE_PARTS))
        raise KeyError(
            f"swerve_parts: unknown key '{key}'. "
            f"Available keys: {available}"
        )
    return SWERVE_PARTS[key]


def resolve_module(module_type: str) -> tuple[dict, str]:
    """
    Resolve oracle module_type string to a (part_dict, effective_key) tuple.
    Falls back to SDS MK4i with a note when the requested module is geometry-only
    (not yet in FRCDesignLib).

    Returns:
        (part_dict, effective_key) — effective_key may differ from module_type
        when fallback is applied.
    """
    key = MODULE_TYPE_MAP.get(module_type, MODULE_FALLBACK_KEY)
    part = resolve(key)
    if part.get("is_asm") is None:
        # Not yet insertable — fall back to canonical module
        return resolve(MODULE_FALLBACK_KEY), MODULE_FALLBACK_KEY
    return part, key


def validate_all() -> list[str]:
    """
    Validate every entry in SWERVE_PARTS has required fields.
    Returns list of error strings (empty = all OK).
    """
    errors = []
    for key, entry in SWERVE_PARTS.items():
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
        print("SWERVE_PARTS validation FAILED:")
        for e in errors:
            print(e)
        sys.exit(1)
    print(f"SWERVE_PARTS OK — {len(SWERVE_PARTS)} entries validated.")
    for key in sorted(SWERVE_PARTS):
        e = SWERVE_PARTS[key]
        vendor_note = "(geometry/deferred)" if e["is_asm"] is None else "(insertable)"
        print(f"  {key}: {e['elem_name']}  {vendor_note}")
