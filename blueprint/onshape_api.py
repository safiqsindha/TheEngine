"""
The Blueprint — OnShape API Wrapper (B.1)
Parametric CAD Pipeline for THE ENGINE
Team 2950 — The Devastators

Wraps the OnShape REST API for:
- Document/assembly creation
- COTS part insertion from FRCDesignLib
- Mate creation between parts
- BOM extraction
- STEP/PDF export
"""

import os
import json
from pathlib import Path
from onshape_client.client import Client

# ── Load .env ─────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
_env_path = BASE_DIR / ".env"
if _env_path.exists():
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

ONSHAPE_ACCESS_KEY = os.environ.get("ONSHAPE_ACCESS_KEY", "")
ONSHAPE_SECRET_KEY = os.environ.get("ONSHAPE_SECRET_KEY", "")
ONSHAPE_BASE_URL = os.environ.get("ONSHAPE_BASE_URL", "https://cad.onshape.com")


def get_client() -> Client:
    """Create and return an authenticated OnShape API client."""
    if not ONSHAPE_ACCESS_KEY or not ONSHAPE_SECRET_KEY:
        raise ValueError(
            "OnShape API keys not configured. "
            "Set ONSHAPE_ACCESS_KEY and ONSHAPE_SECRET_KEY in blueprint/.env\n"
            "Get keys from: https://dev-portal.onshape.com/keys"
        )

    client = Client(configuration={
        "base_url": ONSHAPE_BASE_URL,
        "access_key": ONSHAPE_ACCESS_KEY,
        "secret_key": ONSHAPE_SECRET_KEY,
    })
    return client


# ═══════════════════════════════════════════════════════════════════
# DOCUMENT OPERATIONS
# ═══════════════════════════════════════════════════════════════════

def create_document(name: str, description: str = "") -> dict:
    """Create a new OnShape document. Returns {document_id, workspace_id, url}."""
    client = get_client()
    response = client.documents_api.create_document({
        "name": name,
        "description": description,
        "isPublic": False,
    })
    doc_id = response.id
    workspace_id = response.default_workspace.id
    return {
        "document_id": doc_id,
        "workspace_id": workspace_id,
        "url": f"{ONSHAPE_BASE_URL}/documents/{doc_id}",
    }


def list_documents(query: str = "Engine", limit: int = 10) -> list[dict]:
    """Search for documents by name."""
    client = get_client()
    response = client.documents_api.search({
        "raw_query": query,
        "document_filter": 0,  # My documents
        "limit": limit,
    })
    results = []
    for item in response.items:
        results.append({
            "document_id": item.id,
            "name": item.name,
            "url": f"{ONSHAPE_BASE_URL}/documents/{item.id}",
            "modified": str(item.modified_at),
        })
    return results


def get_document_elements(document_id: str, workspace_id: str) -> list[dict]:
    """List all elements (part studios, assemblies) in a document."""
    client = get_client()
    response = client.documents_api.get_elements_in_document(
        document_id, "w", workspace_id
    )
    elements = []
    for elem in response:
        elements.append({
            "element_id": elem.id,
            "name": elem.name,
            "type": elem.element_type,  # "PARTSTUDIO", "ASSEMBLY", etc.
        })
    return elements


# ═══════════════════════════════════════════════════════════════════
# PART OPERATIONS (COTS from FRCDesignLib)
# ═══════════════════════════════════════════════════════════════════

def load_cots_catalog() -> dict:
    """Load the COTS parts catalog from JSON."""
    catalog_path = BASE_DIR / "cots_catalog.json"
    if not catalog_path.exists():
        return {}
    with open(catalog_path) as f:
        return json.load(f)


def lookup_part(part_name: str) -> dict:
    """Look up a COTS part by name. Returns OnShape element reference."""
    catalog = load_cots_catalog()
    # Exact match first
    if part_name in catalog:
        return catalog[part_name]
    # Case-insensitive search
    name_lower = part_name.lower()
    for key, value in catalog.items():
        if key.lower() == name_lower:
            return value
    # Partial match
    matches = {k: v for k, v in catalog.items() if name_lower in k.lower()}
    if len(matches) == 1:
        return list(matches.values())[0]
    if matches:
        raise ValueError(
            f"Multiple matches for '{part_name}': {list(matches.keys())}"
        )
    raise KeyError(f"Part '{part_name}' not found in COTS catalog")


# ═══════════════════════════════════════════════════════════════════
# ASSEMBLY OPERATIONS
# ═══════════════════════════════════════════════════════════════════

def insert_part_into_assembly(
    document_id: str,
    workspace_id: str,
    assembly_element_id: str,
    part_document_id: str,
    part_element_id: str,
    part_id: str = "",
    configuration: str = "",
) -> dict:
    """Insert a part or sub-assembly into an assembly."""
    client = get_client()
    body = {
        "documentId": part_document_id,
        "elementId": part_element_id,
        "isWholePartStudio": not part_id,
    }
    if part_id:
        body["partId"] = part_id
    if configuration:
        body["configuration"] = configuration

    response = client.assemblies_api.create_instance(
        document_id, "w", workspace_id, assembly_element_id,
        body=body,
    )
    return {"instance_id": response.id if hasattr(response, 'id') else str(response)}


# ═══════════════════════════════════════════════════════════════════
# BOM OPERATIONS
# ═══════════════════════════════════════════════════════════════════

def get_assembly_bom(
    document_id: str,
    workspace_id: str,
    element_id: str,
) -> list[dict]:
    """Extract Bill of Materials from an assembly."""
    client = get_client()
    response = client.assemblies_api.get_bill_of_materials(
        document_id, "w", workspace_id, element_id,
    )
    items = []
    if hasattr(response, 'rows'):
        for row in response.rows:
            items.append({
                "name": row.get("headerName", ""),
                "quantity": row.get("quantity", 1),
                "part_number": row.get("partNumber", ""),
            })
    return items


# ═══════════════════════════════════════════════════════════════════
# HEALTH CHECK
# ═══════════════════════════════════════════════════════════════════

def test_connection() -> dict:
    """Test the OnShape API connection. Returns user info on success."""
    client = get_client()
    try:
        user = client.users_api.session_info()
        return {
            "connected": True,
            "user": user.name,
            "email": user.email,
            "message": f"Connected to OnShape as {user.name} ({user.email})",
        }
    except Exception as e:
        return {
            "connected": False,
            "error": str(e),
            "message": f"Connection failed: {e}",
        }


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 onshape_api.py test          Test API connection")
        print("  python3 onshape_api.py docs [query]   List documents")
        print("  python3 onshape_api.py lookup <part>  Look up COTS part")
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "test":
        result = test_connection()
        print(result["message"])
        sys.exit(0 if result["connected"] else 1)

    elif cmd == "docs":
        query = sys.argv[2] if len(sys.argv) > 2 else "Engine"
        docs = list_documents(query)
        if not docs:
            print(f"No documents found for '{query}'")
        for doc in docs:
            print(f"  {doc['name']} — {doc['url']}")

    elif cmd == "lookup":
        if len(sys.argv) < 3:
            print("Usage: python3 onshape_api.py lookup <part_name>")
            sys.exit(1)
        part_name = " ".join(sys.argv[2:])
        try:
            part = lookup_part(part_name)
            print(f"Found: {part_name}")
            print(json.dumps(part, indent=2))
        except (KeyError, ValueError) as e:
            print(f"Error: {e}")
            sys.exit(1)
