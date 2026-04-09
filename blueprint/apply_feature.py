#!/usr/bin/env python3
"""Apply the custom feature to Part Studio — try multiple API formats."""

import json
import time
import uuid
from pathlib import Path

BASE_DIR = Path(__file__).parent
from insert_cots import api_get, api_post, make_headers, BASE_URL
import requests

with open(BASE_DIR / "fresh_assembly_ids.json") as f:
    state = json.load(f)

doc_id = state["document_id"]
ws_id = state["workspace_id"]
ps_id = state["part_studio_id"]
fs_id = state["feature_studio_id"]

# Get current microversion
fs_contents = api_get(f"/api/v6/featurestudios/d/{doc_id}/w/{ws_id}/e/{fs_id}")
mv = fs_contents.get("sourceMicroversion", "")
print(f"Feature Studio: {fs_id}")
print(f"Microversion: {mv}")
print(f"Part Studio: {ps_id}")

features_path = f"/api/v6/partstudios/d/{doc_id}/w/{ws_id}/e/{ps_id}/features"
fid = f"F{uuid.uuid4().hex[:16]}"

# Format 1: Wrapped in "feature" key with full details
bodies = [
    {
        "name": "Format 1: wrapped feature with featureId",
        "body": {
            "feature": {
                "btType": "BTMFeature-134",
                "featureType": "blueprintRobot",
                "name": "2950 Full Robot",
                "namespace": f"e{fs_id}::m{mv}",
                "parameters": [],
                "suppressed": False,
                "featureId": fid,
            },
            "btType": "BTFeatureDefinitionCall-1406",
        },
    },
    {
        "name": "Format 2: direct feature (no wrapper)",
        "body": {
            "btType": "BTMFeature-134",
            "featureType": "blueprintRobot",
            "name": "2950 Full Robot",
            "namespace": f"e{fs_id}::m{mv}",
            "parameters": [],
            "suppressed": False,
            "featureId": f"F{uuid.uuid4().hex[:16]}",
            "subFeatures": [],
            "returnAfterSubfeatures": False,
        },
    },
    {
        "name": "Format 3: BTFeatureDefinitionCall with serialization",
        "body": {
            "btType": "BTFeatureDefinitionCall-1406",
            "feature": {
                "btType": "BTMFeature-134",
                "featureType": "blueprintRobot",
                "name": "2950 Full Robot",
                "namespace": f"e{fs_id}::m{mv}",
                "parameters": [],
                "suppressed": False,
                "featureId": f"F{uuid.uuid4().hex[:16]}",
            },
            "serializationVersion": "1.2.17",
            "sourceMicroversion": mv,
            "libraryVersion": 2931,
            "rejectMicroversionSkew": False,
            "microversionSkew": False,
        },
    },
]

for attempt in bodies:
    print(f"\nTrying {attempt['name']}...")
    headers = make_headers("POST", features_path, "", "application/json")
    resp = requests.post(BASE_URL + features_path, headers=headers, json=attempt["body"])
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 200:
        print(f"  SUCCESS!")
        print(f"  Response: {resp.text[:300]}")
        break
    else:
        print(f"  Error: {resp.text[:300]}")

print(f"\nDocument: {BASE_URL}/documents/{doc_id}")
