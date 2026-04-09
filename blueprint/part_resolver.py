#!/usr/bin/env python3
"""
The Blueprint — Part Resolver (CAD Evolution P0a)
Team 2950 — The Devastators

Resolves COTS catalog part names to OnShape document/element/part IDs.
Uses the OnShape search API to find FRCDesignLib parts, then caches
results locally so we don't re-search every build.

Usage:
  from part_resolver import PartResolver
  resolver = PartResolver()
  ids = resolver.resolve("SDS MK4i Swerve Module")
  # → {"document_id": "abc...", "element_id": "def...", "part_id": "ghi...", ...}
"""

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).parent
CACHE_PATH = BASE_DIR / "part_cache.json"


@dataclass
class ResolvedPart:
    """A COTS part resolved to OnShape document coordinates."""
    catalog_name: str = ""
    search_term: str = ""
    document_id: str = ""
    document_name: str = ""
    element_id: str = ""
    element_type: str = ""       # "PARTSTUDIO" or "ASSEMBLY"
    part_id: str = ""            # specific part within element (empty = whole part studio)
    configuration: str = ""      # OnShape configuration string
    microversion: str = ""       # for cache invalidation
    resolved_at: str = ""        # ISO timestamp
    source: str = ""             # "api_search", "manual", "frcdesignlib"

    @property
    def is_valid(self) -> bool:
        return bool(self.document_id and self.element_id)


class PartResolver:
    """
    Resolves COTS catalog names to OnShape document/element/part IDs.

    Resolution strategy:
      1. Check local cache (part_cache.json)
      2. Search OnShape public documents for the part
      3. Cache the result for future use

    The cache stores resolved IDs keyed by catalog name. Parts in
    FRCDesignLib don't change often, so cache hits are common.
    """

    def __init__(self, cache_path: Path = CACHE_PATH):
        self.cache_path = cache_path
        self.cache: dict[str, ResolvedPart] = {}
        self.catalog = self._load_catalog()
        self._load_cache()

    # ── Catalog ──

    def _load_catalog(self) -> dict:
        catalog_path = BASE_DIR / "cots_catalog.json"
        with open(catalog_path) as f:
            data = json.load(f)
        data.pop("_meta", None)
        return data

    def get_search_term(self, catalog_name: str) -> str:
        """Get the OnShape search term for a catalog part."""
        entry = self.catalog.get(catalog_name, {})
        onshape = entry.get("onshape", {})
        return onshape.get("search", catalog_name)

    # ── Cache ──

    def _load_cache(self):
        if self.cache_path.exists():
            with open(self.cache_path) as f:
                data = json.load(f)
            for name, entry in data.items():
                self.cache[name] = ResolvedPart(**entry)

    def _save_cache(self):
        data = {name: asdict(part) for name, part in self.cache.items()}
        with open(self.cache_path, "w") as f:
            json.dump(data, f, indent=2)

    def get_cached(self, catalog_name: str) -> Optional[ResolvedPart]:
        """Get a cached resolution, or None."""
        part = self.cache.get(catalog_name)
        if part and part.is_valid:
            return part
        return None

    def cache_manual(self, catalog_name: str, document_id: str, element_id: str,
                     part_id: str = "", configuration: str = "",
                     element_type: str = "PARTSTUDIO", document_name: str = ""):
        """Manually cache a part resolution (for known IDs)."""
        part = ResolvedPart(
            catalog_name=catalog_name,
            search_term=self.get_search_term(catalog_name),
            document_id=document_id,
            document_name=document_name,
            element_id=element_id,
            element_type=element_type,
            part_id=part_id,
            configuration=configuration,
            resolved_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            source="manual",
        )
        self.cache[catalog_name] = part
        self._save_cache()
        return part

    # ── Resolution ──

    def resolve(self, catalog_name: str, force: bool = False) -> Optional[ResolvedPart]:
        """
        Resolve a COTS catalog name to OnShape IDs.

        1. Check cache (unless force=True)
        2. Search OnShape API for the part
        3. Cache and return result

        Returns None if the part cannot be found.
        """
        # Check cache first
        if not force:
            cached = self.get_cached(catalog_name)
            if cached:
                return cached

        # Search OnShape
        search_term = self.get_search_term(catalog_name)
        result = self._search_onshape(catalog_name, search_term)

        if result and result.is_valid:
            self.cache[catalog_name] = result
            self._save_cache()

        return result

    def resolve_all(self, force: bool = False) -> dict[str, Optional[ResolvedPart]]:
        """Resolve all parts in the COTS catalog."""
        results = {}
        for name in self.catalog:
            results[name] = self.resolve(name, force=force)
        return results

    def _search_onshape(self, catalog_name: str, search_term: str) -> Optional[ResolvedPart]:
        """Search OnShape for a part by name."""
        try:
            from onshape_api import get_client
            client = get_client()
        except Exception:
            return None

        # Strategy 1: Search for FRCDesignLib documents containing the part
        search_queries = [
            f"FRCDesignLib {search_term}",
            f"FRC Design Library {search_term}",
            search_term,
        ]

        for query in search_queries:
            try:
                response = client.documents_api.search({
                    "raw_query": query,
                    "document_filter": 2,  # public documents
                    "limit": 5,
                })

                items = []
                if hasattr(response, 'items'):
                    items = response.items
                elif isinstance(response, dict):
                    items = response.get('items', [])

                for doc in items:
                    doc_id = doc.id if hasattr(doc, 'id') else doc.get('id', '')
                    doc_name = doc.name if hasattr(doc, 'name') else doc.get('name', '')

                    if not doc_id:
                        continue

                    # Check if this looks like a FRCDesignLib document
                    name_lower = doc_name.lower()
                    if any(kw in name_lower for kw in ['frcdesign', 'frc design', 'ftc', search_term.lower()]):
                        # Get elements in this document
                        try:
                            workspace_id = (doc.default_workspace.id
                                          if hasattr(doc, 'default_workspace')
                                          else doc.get('defaultWorkspace', {}).get('id', ''))
                            if not workspace_id:
                                continue

                            elements = client.documents_api.get_elements_in_document(
                                doc_id, "w", workspace_id
                            )

                            # Find a Part Studio or Assembly element
                            for elem in elements:
                                elem_type = (elem.element_type
                                           if hasattr(elem, 'element_type')
                                           else elem.get('elementType', ''))
                                elem_id = elem.id if hasattr(elem, 'id') else elem.get('id', '')

                                if elem_type in ("PARTSTUDIO", "ASSEMBLY"):
                                    return ResolvedPart(
                                        catalog_name=catalog_name,
                                        search_term=search_term,
                                        document_id=doc_id,
                                        document_name=doc_name,
                                        element_id=elem_id,
                                        element_type=elem_type,
                                        resolved_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                        source="api_search",
                                    )
                        except Exception:
                            continue

            except Exception:
                continue

        return None

    # ── Batch Operations ──

    def resolve_for_mechanism(self, mechanism_type: str) -> list[ResolvedPart]:
        """Resolve all COTS parts needed for a mechanism type."""
        mechanism_parts = MECHANISM_COTS_MAP.get(mechanism_type, [])
        resolved = []
        for part_name in mechanism_parts:
            result = self.resolve(part_name)
            if result:
                resolved.append(result)
        return resolved

    def get_resolution_status(self) -> dict:
        """Get status of all catalog resolutions."""
        total = len(self.catalog)
        cached = sum(1 for name in self.catalog if self.get_cached(name))
        return {
            "total_parts": total,
            "resolved": cached,
            "unresolved": total - cached,
            "resolution_rate": round(cached / total * 100, 1) if total > 0 else 0,
            "unresolved_parts": [name for name in self.catalog if not self.get_cached(name)],
        }


# ═══════════════════════════════════════════════════════════════════
# MECHANISM → COTS PART MAPPINGS
# ═══════════════════════════════════════════════════════════════════

MECHANISM_COTS_MAP = {
    "swerve_drivetrain": [
        "SDS MK4i Swerve Module",
        "WCP Kraken X60",          # drive motors
        "REV NEO 550",             # steer motors (or Kraken for some modules)
    ],
    "swerve_drivetrain_thrifty": [
        "Thrifty Swerve Module",
        "REV NEO Motor",
        "REV NEO 550",
    ],
    "swerve_drivetrain_rev": [
        "REV MAXSwerve",
        "REV NEO Vortex",
        "REV NEO 550",
    ],
    "intake": [
        "REV NEO Motor",
        "REV MAXPlanetary Gearbox",
        "1/2in Hex Shaft",
        "Flanged Bearing 1/2in Hex",
    ],
    "flywheel": [
        "REV NEO Vortex",
        "1/2in Hex Shaft",
        "Flanged Bearing 1/2in Hex",
    ],
    "elevator": [
        "WCP Kraken X60",
        "2x1 Aluminum Box Tube",
        "1x1 Aluminum Box Tube",
        "Thrifty Elevator Bearing Block",
        "1/2in Hex Shaft",
    ],
    "arm": [
        "REV NEO Motor",
        "REV MAXPlanetary Gearbox",
        "Flanged Bearing 1/2in Hex",
    ],
    "climber": [
        "REV NEO Motor",
        "REV MAXPlanetary Gearbox",
        "1/2in Hex Shaft",
    ],
    "electronics": [
        "Power Distribution Hub",
        "RoboRIO 2",
        "FRC Battery (MK ES17-12)",
        "OpenMesh Radio (OM5P-AC)",
        "Main Breaker (120A)",
        "REV Spark MAX",
        "CTRE Pigeon 2.0 IMU",
    ],
    "frame_structure": [
        "2x1 Aluminum Box Tube",
        "1x1 Aluminum Box Tube",
    ],
}

# Module-type specific part mapping
MODULE_PARTS_MAP = {
    "sds_mk4i": "SDS MK4i Swerve Module",
    "sds_mk4n": "SDS MK4n Swerve Module",
    "thrifty": "Thrifty Swerve Module",
    "rev_maxswerve": "REV MAXSwerve",
}

# Motor-type specific part mapping
MOTOR_PARTS_MAP = {
    "neo": "REV NEO Motor",
    "neo_vortex": "REV NEO Vortex",
    "neo_550": "REV NEO 550",
    "kraken_x60": "WCP Kraken X60",
    "falcon_500": "VEXpro Falcon 500",
}


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

def main():
    import sys

    resolver = PartResolver()

    if len(sys.argv) < 2:
        print("Part Resolver — COTS catalog → OnShape IDs")
        print()
        print("Commands:")
        print("  python3 part_resolver.py status          Show resolution status")
        print("  python3 part_resolver.py resolve <name>  Resolve a specific part")
        print("  python3 part_resolver.py resolve-all     Resolve all catalog parts")
        print("  python3 part_resolver.py cache           Show cached resolutions")
        print("  python3 part_resolver.py mechanism <type> Show COTS parts for mechanism")
        return

    cmd = sys.argv[1]

    if cmd == "status":
        status = resolver.get_resolution_status()
        print(f"\nPart Resolution Status:")
        print(f"  Total parts:  {status['total_parts']}")
        print(f"  Resolved:     {status['resolved']}")
        print(f"  Unresolved:   {status['unresolved']}")
        print(f"  Rate:         {status['resolution_rate']}%")
        if status['unresolved_parts']:
            print(f"\n  Unresolved parts:")
            for name in status['unresolved_parts']:
                search = resolver.get_search_term(name)
                print(f"    - {name} (search: \"{search}\")")

    elif cmd == "cache":
        print(f"\nCached Part Resolutions ({len(resolver.cache)} entries):")
        for name, part in sorted(resolver.cache.items()):
            status = "valid" if part.is_valid else "invalid"
            print(f"  [{status}] {name}")
            if part.is_valid:
                print(f"         doc: {part.document_id[:12]}... ({part.document_name})")
                print(f"         elem: {part.element_id[:12]}... ({part.element_type})")
                print(f"         resolved: {part.resolved_at} via {part.source}")

    elif cmd == "resolve":
        if len(sys.argv) < 3:
            print("Usage: python3 part_resolver.py resolve <part_name>")
            return
        name = " ".join(sys.argv[2:])
        print(f"Resolving: {name}...")
        result = resolver.resolve(name, force=True)
        if result and result.is_valid:
            print(f"  Found: {result.document_name}")
            print(f"  Document: {result.document_id}")
            print(f"  Element:  {result.element_id} ({result.element_type})")
            print(f"  Source:   {result.source}")
        else:
            print(f"  Not found via API search.")
            print(f"  Search term was: \"{resolver.get_search_term(name)}\"")
            print(f"  You can manually cache with resolver.cache_manual(...)")

    elif cmd == "resolve-all":
        print("Resolving all catalog parts...")
        results = resolver.resolve_all(force="--force" in sys.argv)
        found = sum(1 for r in results.values() if r and r.is_valid)
        print(f"\nResolved {found}/{len(results)} parts")
        for name, result in results.items():
            status = "OK" if result and result.is_valid else "MISS"
            print(f"  [{status}] {name}")

    elif cmd == "mechanism":
        if len(sys.argv) < 3:
            print("Available mechanism types:")
            for mtype in MECHANISM_COTS_MAP:
                print(f"  {mtype} ({len(MECHANISM_COTS_MAP[mtype])} parts)")
            return
        mtype = sys.argv[2]
        parts = MECHANISM_COTS_MAP.get(mtype, [])
        if not parts:
            print(f"Unknown mechanism type: {mtype}")
            return
        print(f"\nCOTS parts for {mtype}:")
        for part_name in parts:
            cached = resolver.get_cached(part_name)
            status = "cached" if cached else "unresolved"
            print(f"  [{status}] {part_name}")

    else:
        print(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main()
