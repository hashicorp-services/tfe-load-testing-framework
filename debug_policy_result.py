#!/usr/bin/env python3
"""Debug script to inspect TFE policy check result structure."""

import os
import sys
import json
import requests
import urllib3

# Disable SSL warnings for local dev
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Get credentials
token = os.environ.get('TFE_TOKEN')
hostname = os.environ.get('TFE_HOSTNAME', 'tfe.localdemo.me')
org = os.environ.get('TFE_ORGANIZATION')

if not token or not org:
    print("Error: TFE_TOKEN and TFE_ORGANIZATION must be set")
    sys.exit(1)

headers = {"Authorization": f"Bearer {token}"}
base_url = f"https://{hostname}/api/v2"

# Get recent runs to find policy checks
print("Fetching recent runs...")
response = requests.get(
    f"{base_url}/organizations/{org}/workspaces",
    headers=headers,
    params={"page[size]": 10},
    verify=False
)

if response.status_code != 200:
    print(f"Failed to list workspaces: {response.status_code}")
    sys.exit(1)

workspaces = response.json()
if not workspaces.get('data'):
    print("No workspaces found")
    sys.exit(1)

# Get runs from first workspace
ws_id = workspaces['data'][0]['id']
print(f"Fetching runs from workspace {ws_id}...")

runs_response = requests.get(
    f"{base_url}/workspaces/{ws_id}/runs",
    headers=headers,
    params={"page[size]": 10},
    verify=False
)

if runs_response.status_code != 200:
    print(f"Failed to list runs: {runs_response.status_code}")
    sys.exit(1)

runs = runs_response.json()
if not runs.get('data'):
    print("No runs found")
    sys.exit(1)

# Find a run with completed policy check
pc_id = None
for run in runs['data']:
    run_status = run['attributes']['status']
    # Look for runs that have completed policy checks
    if run_status in ['policy_checked', 'policy_override', 'applied', 'errored']:
        relationships = run.get('relationships', {})
        if 'policy-checks' in relationships:
            pc_data = relationships['policy-checks'].get('data', [])
            if pc_data:
                # Check if policy check is complete
                test_pc_id = pc_data[0]['id']
                test_response = requests.get(
                    f"{base_url}/policy-checks/{test_pc_id}",
                    headers=headers,
                    verify=False
                )
                if test_response.status_code == 200:
                    test_detail = test_response.json()
                    test_status = test_detail['data']['attributes']['status']
                    if test_status in ['passed', 'soft_failed', 'hard_failed', 'overridden']:
                        pc_id = test_pc_id
                        print(f"Found completed policy check with status: {test_status}")
                        break

if not pc_id:
    print("No completed policy checks found in recent runs")
    sys.exit(1)
print(f"\nFetching policy check {pc_id}...")

detail_response = requests.get(
    f"{base_url}/policy-checks/{pc_id}",
    headers=headers,
    verify=False
)

if detail_response.status_code != 200:
    print(f"Failed to get policy check: {detail_response.status_code}")
    sys.exit(1)

detail = detail_response.json()
attributes = detail['data']['attributes']
result = attributes.get('result')

print("\n" + "="*80)
print("FULL POLICY CHECK ATTRIBUTES:")
print("="*80)
print(json.dumps(attributes, indent=2))
print("="*80)

# Check for duration fields
print("\nDuration field analysis:")
print(f"  Status: {attributes.get('status')}")
print(f"  Result is null: {result is None}")

if result:
    if 'duration-ms' in result:
        print(f"  ✓ Found 'duration-ms': {result['duration-ms']}")
    if 'duration' in result:
        print(f"  ✓ Found 'duration': {result['duration']}")
    if 'sentinel' in result:
        print(f"  ✓ Found 'sentinel' object")
        sentinel_data = result.get('sentinel', {}).get('data', {})
        for ws_name, ws_data in sentinel_data.items():
            print(f"    Workspace: {ws_name}")
            for policy in ws_data.get('policies', []):
                if 'duration' in policy:
                    print(f"      Policy duration: {policy['duration']} (likely nanoseconds)")
else:
    print("  ⚠ Result is null - policy check may not be complete yet")
    print("  Try finding a completed policy check (status: 'passed' or 'failed')")
