#!/usr/bin/env python3
"""Quick fix: upload FeatureScript to existing document."""

import json
import time
from pathlib import Path

BASE_DIR = Path(__file__).parent

from insert_cots import api_get, api_post, make_headers, BASE_URL
from cad_builder import generate_full_featurescript
import requests

# Load state
with open(BASE_DIR / "fresh_assembly_ids.json") as f:
    state = json.load(f)

doc_id = state["document_id"]
ws_id = state["workspace_id"]
ps_id = state["part_studio_id"]
asm_id = state["assembly_id"]

# Load spec and generate FeatureScript
with open(BASE_DIR / "2022_rapid_react_full_blueprint.json") as f:
    spec = json.load(f)

fs_code = generate_full_featurescript(spec)
print(f"FeatureScript: {len(fs_code)} chars")

# Step 1: Create Feature Studio
print("Creating Feature Studio...")
fs_resp = api_post(f"/api/v6/featurestudios/d/{doc_id}/w/{ws_id}", {
    "name": "2950 Robot Geometry",
})
fs_id = fs_resp.get("id", "")
print(f"Feature Studio ID: {fs_id}")

# Step 2: Get microversion from Feature Studio contents
time.sleep(1.0)
print("Getting microversion...")
fs_contents = api_get(f"/api/v6/featurestudios/d/{doc_id}/w/{ws_id}/e/{fs_id}")
mv = fs_contents.get("sourceMicroversion", "")
print(f"Microversion: {mv[:16]}...")

# Step 3: Upload FeatureScript code
print("Uploading FeatureScript...")
path = f"/api/v6/featurestudios/d/{doc_id}/w/{ws_id}/e/{fs_id}"
headers = make_headers("POST", path, "", "application/json")
resp = requests.post(BASE_URL + path, headers=headers, json={
    "contents": fs_code,
    "serializationVersion": "1.2.17",
    "sourceMicroversion": mv,
})
print(f"Upload status: {resp.status_code}")
if resp.status_code != 200:
    print(f"Response: {resp.text[:500]}")
else:
    print("FeatureScript uploaded OK!")

# Step 4: Apply custom feature to Part Studio
time.sleep(1.0)
print("\nApplying custom feature to Part Studio...")

# Re-read microversion after upload
fs_contents2 = api_get(f"/api/v6/featurestudios/d/{doc_id}/w/{ws_id}/e/{fs_id}")
mv2 = fs_contents2.get("sourceMicroversion", mv)

namespace = f"e{fs_id}::m{mv2}"
print(f"Namespace: {namespace[:40]}...")

feature_body = {
    "btType": "BTMFeature-134",
    "namespace": namespace,
    "featureType": "blueprintRobot",
    "name": "2950 Full Robot",
    "parameters": [],
}

features_path = f"/api/v6/partstudios/d/{doc_id}/w/{ws_id}/e/{ps_id}/features"
try:
    result = api_post(features_path, {"btType": "BTMFeature-134", "feature": feature_body})
    print(f"Feature applied! Result: {json.dumps(result)[:200]}")
except Exception as e:
    print(f"Feature apply attempt 1: {e}")
    # Try alternate format — direct feature body
    try:
        result = api_post(features_path, feature_body)
        print(f"Feature applied (alt format)! Result: {json.dumps(result)[:200]}")
    except Exception as e2:
        print(f"Feature apply attempt 2: {e2}")
        print("\nNote: Custom feature may need manual application in OnShape UI.")
        print("Open the Part Studio → Add Feature → select '2950 Robot Geometry'")

# Update state
state["feature_studio_id"] = fs_id
with open(BASE_DIR / "fresh_assembly_ids.json", "w") as f:
    json.dump(state, f, indent=2)

print(f"\nDocument: {BASE_URL}/documents/{doc_id}")
print("Done.")
