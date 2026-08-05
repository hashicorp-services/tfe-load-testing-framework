# Copyright (c) 2026 IBM Corporation
# SPDX-License-Identifier: MPL-2.0

"""
TFE Sentinel Policy Evaluation Load Test

This load test scenario focuses on Terraform Enterprise Sentinel policy evaluation:
- Creating workspaces with policy sets attached
- Triggering runs that undergo policy checks
- Testing different policy enforcement levels (advisory, soft-mandatory, hard-mandatory)
- Testing policy pass/fail scenarios
- Testing policy override workflows
- Monitoring policy-stage wall time, best-effort engine duration, and outcomes

Prerequisites:
    - OPTIONAL: Create a custom policy set in TFE if you want to test specific policies
    - If TFE_POLICY_SET_NAME is not set, the synthetic-heavy default policy set
      'loadtest-policies-synthetic-heavy' will be automatically created/reused
    - Use '--policy-profile standard --policy-set loadtest-policies' for the lighter
      sample policies
    - If you specify a custom policy set name, it must exist in TFE before running the test

Environment Variables:
    TFE_HOSTNAME: TFE instance hostname (e.g., app.terraform.io or tfe.localdemo.me)
    TFE_TOKEN: TFE API token (must have permissions to manage policies)
    TFE_ORGANIZATION: TFE organization name
    TFE_POLICY_SET_NAME: Name of the policy set to use for testing (default: loadtest-policies-synthetic-heavy)
                         - Default policy set names: Auto-created/reused if needed
                         - If custom name: Must exist in TFE (for benchmarking your own policies)
    TFE_SENTINEL_POLICY_PROFILE: Policy profile to auto-create (default: synthetic-heavy; options: standard, synthetic-heavy)
    TFE_SENTINEL_SYNTHETIC_RESOURCE_COUNT: Resource count for synthetic-heavy profile (default: 150)
    TFE_SENTINEL_HEAVY_POLICY_SCAN_COUNT: Repeated plan scans for synthetic-heavy profile (default: 80)
    TFE_VERIFY_SSL: Whether to verify SSL certificates (default: true, set to false for local dev)
    LOCUST_USERS: Number of concurrent users (default: 5)
    LOCUST_SPAWN_RATE: User spawn rate per second (default: 1)
    LOCUST_RUN_TIME: Test duration (default: 10m)
"""

import os
import time
import tarfile
import io
import random
import uuid
import threading
from datetime import datetime, timezone
from gevent.lock import Semaphore
from locust import HttpUser, task, between, events
from src.utils.tfe_client import TFEClient

# Suppress SSL warnings for local development
import urllib3
if os.getenv('TFE_VERIFY_SSL', 'true').lower() == 'false':
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Global statistics tracking (thread-safe)
global_policy_stats = {
    'total_evaluated': 0,
    'total_passed': 0,
    'total_failed': 0,
    'soft_failed': 0,
    'hard_failed': 0,
    'advisory_failed': 0,
    'overrides_performed': 0,
    'total_duration_ms': 0,
    'engine_duration_count': 0,
    'min_duration_ms': float('inf'),
    'max_duration_ms': 0,
    'policy_stage_wall_time_count': 0,
    'total_policy_stage_wall_time_ms': 0,
    'min_policy_stage_wall_time_ms': float('inf'),
    'max_policy_stage_wall_time_ms': 0
}
stats_lock = threading.Lock()
policy_set_lock = Semaphore()
policy_set_cache = {}

POLICY_TERMINAL_TIMESTAMP_KEYS = {
    'passed': ('passed-at', 'passed_at'),
    'soft_failed': ('soft-failed-at', 'soft_failed_at'),
    'hard_failed': ('hard-failed-at', 'hard_failed_at'),
    'overridden': ('overridden-at', 'overridden_at'),
    'errored': ('errored-at', 'errored_at')
}

TERMINAL_POLICY_CHECK_STATUSES = set(POLICY_TERMINAL_TIMESTAMP_KEYS)


def _parse_tfe_timestamp(value):
    """Parse a TFE timestamp into an aware datetime."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None


def _timestamp_from_keys(status_timestamps, keys):
    """Return the first timestamp found for either JSON or hstore-style keys."""
    if not status_timestamps:
        return None
    for key in keys:
        parsed = _parse_tfe_timestamp(status_timestamps.get(key))
        if parsed:
            return parsed
    return None


class TFESentinelPolicyUser(HttpUser):
    """
    Simulates a user performing operations that trigger Sentinel policy evaluations.
    
    Task weights determine the frequency of each operation:
    - trigger_run_with_policy_pass: 10 (most common - runs that pass policies)
    - trigger_run_with_policy_fail: 5 (runs that fail policies)
    - monitor_policy_check_status: 15 (checking policy evaluation status)
    - override_soft_mandatory_policy: 3 (testing override workflow)
    """
    
    wait_time = between(1, 3)  # Wait 1-3 seconds between tasks (aggressive polling to unlock stuck runs)
    
    def on_start(self):
        """Initialize TFE client and create test workspace with policy set on user start."""
        # Initialize attributes first
        self.created_runs = []
        self.workspace_id = None
        self.workspace_name = None
        self.policy_set_id = None
        self.run_policy_timing = {}
        self.recorded_policy_checks = set()
        
        self.tfe = TFEClient(
            hostname=os.getenv('TFE_HOSTNAME', 'app.terraform.io'),
            token=os.getenv('TFE_TOKEN'),
            organization=os.getenv('TFE_ORGANIZATION'),
            verify_ssl=os.getenv('TFE_VERIFY_SSL', 'true').lower() == 'true'
        )
        
        # Get or create policy set
        policy_profile = os.getenv('TFE_SENTINEL_POLICY_PROFILE', 'synthetic-heavy').lower()
        policy_set_name = os.getenv('TFE_POLICY_SET_NAME')
        if not policy_set_name:
            policy_set_name = 'loadtest-policies-synthetic-heavy' if policy_profile == 'synthetic-heavy' else 'loadtest-policies'
        is_default_policy_set = policy_set_name == 'loadtest-policies'
        is_default_policy_set = is_default_policy_set or policy_set_name == 'loadtest-policies-synthetic-heavy'
        
        try:
            cache_key = (self.tfe.organization, policy_set_name, policy_profile)
            with policy_set_lock:
                policy_set = policy_set_cache.get(cache_key)
                if not policy_set:
                    policy_set = self._get_policy_set(policy_set_name)
                    if policy_set:
                        print(f"Using existing policy set: {policy_set_name} (ID: {policy_set['id']})")
                    elif is_default_policy_set:
                        print(f"Default policy set '{policy_set_name}' not found. Creating it...")
                        policy_set = self._create_default_policy_set(policy_set_name)
                    else:
                        print(f"WARNING: Custom policy set '{policy_set_name}' not found. Policy checks will not run.")
                        print(f"         Create the policy set in TFE or use the default by not setting TFE_POLICY_SET_NAME.")

                if policy_set and is_default_policy_set:
                    self._ensure_default_policies(policy_set, policy_profile)

                if policy_set:
                    policy_set_cache[cache_key] = policy_set

            if policy_set:
                self.policy_set_id = policy_set['id']
            elif is_default_policy_set:
                print(f"WARNING: Failed to create default policy set. Policy checks will not run.")
        except Exception as e:
            print(f"WARNING: Could not retrieve/create policy set: {e}")
        
        # Create a unique workspace for this user
        workspace_name = f"loadtest-sentinel-{uuid.uuid4().hex[:8]}"
        self.workspace = self.tfe.create_workspace(
            name=workspace_name,
            auto_apply=True  # Enable auto-apply so runs proceed automatically after policy check
        )
        self.workspace_id = self.workspace['id']
        self.workspace_name = workspace_name
        
        # Attach policy set to workspace if available
        if self.policy_set_id:
            try:
                self._attach_policy_set_to_workspace()
                print(f"Attached policy set to workspace: {workspace_name}")
            except Exception as e:
                print(f"WARNING: Could not attach policy set to workspace: {e}")
        
        print(f"User started with workspace: {workspace_name}")
    
    def on_stop(self):
        """Clean up test workspace on user stop."""
        try:
            # Cancel any pending runs
            for run_id in self.created_runs:
                try:
                    self.tfe.cancel_run(run_id)
                except Exception:
                    pass
            
            time.sleep(2)
            
            # Delete the workspace
            if hasattr(self, 'workspace_id') and self.workspace_id:
                try:
                    self.tfe.delete_workspace(self.workspace_id)
                    print(f"Cleaned up workspace: {self.workspace_name}")
                except Exception as e:
                    print(f"Warning: Could not delete workspace {self.workspace_name}: {e}")
        except Exception as e:
            print(f"Warning during cleanup: {e}")
    
    def _get_policy_set(self, policy_set_name):
        """Get policy set by name."""
        with self.client.get(
            f"/api/v2/organizations/{self.tfe.organization}/policy-sets",
            headers={
                "Authorization": f"Bearer {self.tfe.token}",
                "Content-Type": "application/vnd.api+json"
            },
            verify=self.tfe.verify_ssl,
            catch_response=True,
            name="/api/v2/organizations/:org/policy-sets [LIST]"
        ) as response:
            if response.status_code != 200:
                response.failure(f"Failed to list policy sets: {response.status_code}")
                return None
            
            data = response.json()
            response.success()
            
            for policy_set in data.get('data', []):
                if policy_set['attributes']['name'] == policy_set_name:
                    return policy_set
            
            return None

    def _get_policy(self, policy_name):
        """Get an organization policy by name."""
        with self.client.get(
            f"/api/v2/organizations/{self.tfe.organization}/policies",
            headers={
                "Authorization": f"Bearer {self.tfe.token}",
                "Content-Type": "application/vnd.api+json"
            },
            params={"page[size]": 100},
            verify=self.tfe.verify_ssl,
            catch_response=True,
            name="/api/v2/organizations/:org/policies [LIST]"
        ) as response:
            if response.status_code != 200:
                response.failure(f"Failed to list policies: {response.status_code}")
                return None

            data = response.json()
            response.success()

            for policy in data.get('data', []):
                if policy['attributes']['name'] == policy_name:
                    return policy

            return None
    
    def _create_default_policy_set(self, policy_set_name):
        """
        Create a default policy set with sample Sentinel policies for load testing.
        
        This creates:
        - Advisory policy: Always passes, just logs
        - Soft-mandatory policy: Checks for required tags (can be overridden)
        - Hard-mandatory policy: Strict validation (cannot be overridden)
        - Optional synthetic-heavy policy: Repeated plan scans to produce measurable
          local engine duration for calibration.
        """
        # Create the policy set
        with self.client.post(
            f"/api/v2/organizations/{self.tfe.organization}/policy-sets",
            json={
                "data": {
                    "type": "policy-sets",
                    "attributes": {
                        "name": policy_set_name,
                        "description": "Default policy set for load testing - auto-created",
                        "global": False,
                        "policies-path": "",
                        "vcs-repo": None
                    }
                }
            },
            headers={
                "Authorization": f"Bearer {self.tfe.token}",
                "Content-Type": "application/vnd.api+json"
            },
            verify=self.tfe.verify_ssl,
            catch_response=True,
            name="/api/v2/organizations/:org/policy-sets [CREATE]"
        ) as response:
            if response.status_code != 201:
                # Another user/process may have created it between list and create.
                existing_policy_set = self._get_policy_set(policy_set_name)
                if existing_policy_set:
                    response.success()
                    return existing_policy_set

                response.failure(f"Failed to create policy set: {response.status_code}")
                return None
            
            policy_set = response.json()
            response.success()

        return policy_set['data']

    def _default_policy_configs(self, policy_profile):
        """Return the default policy configs for the requested profile."""
        policies = [
            {
                "name": "advisory-logging",
                "description": "Advisory policy that always passes - for testing",
                "enforcement-level": "advisory",
                "policy": "main = rule { true }"
            },
            {
                "name": "soft-mandatory-tags",
                "description": "Soft-mandatory policy checking for required tags",
                "enforcement-level": "soft-mandatory",
                "policy": """import "tfplan/v2" as tfplan

has_required_tags = rule {
    all tfplan.resource_changes as _, rc {
        ((rc.mode else "") != "managed") or
        not ((rc.change.actions else []) contains "create") or
        all ["environment", "cost_center"] as tag {
            (rc.change.after.triggers else {}) contains tag
        }
    }
}

main = rule {
    has_required_tags
}"""
            },
            {
                "name": "hard-mandatory-validation",
                "description": "Hard-mandatory policy for strict validation",
                "enforcement-level": "hard-mandatory",
                "policy": "main = rule { true }"
            }
        ]

        if policy_profile == 'synthetic-heavy':
            policies.append({
                "name": "synthetic-heavy-plan-scan",
                "description": "Synthetic advisory policy that repeatedly scans plan changes to calibrate local duration metrics",
                "enforcement-level": "advisory",
                "policy": self._create_synthetic_heavy_policy()
            })

        return policies

    def _ensure_default_policies(self, policy_set, policy_profile):
        """Create or reuse default policies and attach them to the policy set."""
        policy_set_id = policy_set['id']
        policies = self._default_policy_configs(policy_profile)

        # Create each policy
        for policy_config in policies:
            policy = self._create_or_get_policy(policy_config)
            if not policy:
                continue

            policy_id = policy['id']
            self._upload_policy_code(policy_id, policy_config["policy"])
            self._attach_policy_to_policy_set(policy_set_id, policy_id)

    def _create_or_get_policy(self, policy_config):
        """Create a policy, or reuse an existing one with the same name."""
        policy_name = policy_config["name"]
        with self.client.post(
            f"/api/v2/organizations/{self.tfe.organization}/policies",
            json={
                "data": {
                    "type": "policies",
                    "attributes": {
                        "name": policy_name,
                        "description": policy_config["description"],
                        "enforce": [
                            {
                                "path": f"{policy_name}.sentinel",
                                "mode": policy_config["enforcement-level"]
                            }
                        ]
                    }
                }
            },
            headers={
                "Authorization": f"Bearer {self.tfe.token}",
                "Content-Type": "application/vnd.api+json"
            },
            verify=self.tfe.verify_ssl,
            catch_response=True,
            name="/api/v2/organizations/:org/policies [CREATE]"
        ) as response:
            if response.status_code == 201:
                policy = response.json()
                response.success()
                return policy['data']

            if response.status_code == 422:
                existing_policy = self._get_policy(policy_name)
                if existing_policy:
                    response.success()
                    print(f"Reusing existing policy: {policy_name} (ID: {existing_policy['id']})")
                    return existing_policy

                response.failure(f"Policy {policy_name} already exists but could not be retrieved")
                return None
            else:
                response.failure(f"Failed to create policy {policy_name}: {response.status_code}")
                return None

    def _upload_policy_code(self, policy_id, policy_code):
        """Upload policy code to a policy."""
        with self.client.put(
            f"/api/v2/policies/{policy_id}/upload",
            data=policy_code.encode('utf-8'),
            headers={
                "Authorization": f"Bearer {self.tfe.token}",
                "Content-Type": "application/octet-stream"
            },
            verify=self.tfe.verify_ssl,
            catch_response=True,
            name="/api/v2/policies/:id/upload [PUT]"
        ) as response:
            if response.status_code != 200:
                response.failure(f"Failed to upload policy code: {response.status_code}")
            else:
                response.success()

    def _attach_policy_to_policy_set(self, policy_set_id, policy_id):
        """Attach a policy to a policy set, treating existing relationships as success."""
        with self.client.post(
            f"/api/v2/policy-sets/{policy_set_id}/relationships/policies",
            json={
                "data": [
                    {"type": "policies", "id": policy_id}
                ]
            },
            headers={
                "Authorization": f"Bearer {self.tfe.token}",
                "Content-Type": "application/vnd.api+json"
            },
            verify=self.tfe.verify_ssl,
            catch_response=True,
            name="/api/v2/policy-sets/:id/relationships/policies [ATTACH]"
        ) as response:
            if response.status_code in [200, 204, 409, 422]:
                response.success()
            else:
                response.failure(f"Failed to attach policy to set: {response.status_code}")

    def _create_synthetic_heavy_policy(self):
        """
        Create an intentionally repetitive policy for local timing calibration.

        Real customer benchmarking should use real customer policies. This policy is
        useful when the tiny default policies complete below TFE's integer-ms
        duration reporting floor.
        """
        scan_count = int(os.getenv('TFE_SENTINEL_HEAVY_POLICY_SCAN_COUNT', '80'))
        scan_count = max(1, min(scan_count, 250))
        rules = []
        rule_names = []
        for index in range(1, scan_count + 1):
            rule_name = f"scan_{index:03d}"
            rule_names.append(rule_name)
            rules.append(f"""{rule_name} = rule {{
    all tfplan.resource_changes as _, rc {{
        ((rc.mode else "") == "managed") and ((rc.change.actions else []) contains "create")
    }}
}}""")

        return """import "tfplan/v2" as tfplan

""" + "\n\n".join(rules) + "\n\nmain = rule {\n    " + " and\n    ".join(rule_names) + "\n}\n"
    
    def _attach_policy_set_to_workspace(self):
        """Attach policy set to workspace."""
        with self.client.post(
            f"/api/v2/policy-sets/{self.policy_set_id}/relationships/workspaces",
            json={
                "data": [
                    {"type": "workspaces", "id": self.workspace_id}
                ]
            },
            headers={
                "Authorization": f"Bearer {self.tfe.token}",
                "Content-Type": "application/vnd.api+json"
            },
            verify=self.tfe.verify_ssl,
            catch_response=True,
            name="/api/v2/policy-sets/:id/relationships/workspaces [ATTACH]"
        ) as response:
            if response.status_code not in [200, 204]:
                response.failure(f"Failed to attach policy set: {response.status_code}")
                return
            response.success()
    
    def _create_terraform_config(self, policy_test_type="pass"):
        """
        Create a Terraform configuration designed to pass or fail policies.
        
        Args:
            policy_test_type: "pass" or "fail" - determines config characteristics
            
        Returns:
            bytes: Tar.gz file content
        """
        policy_profile = os.getenv('TFE_SENTINEL_POLICY_PROFILE', 'synthetic-heavy').lower()
        default_resource_count = '150' if policy_profile == 'synthetic-heavy' else '1'
        resource_count = int(os.getenv('TFE_SENTINEL_SYNTHETIC_RESOURCE_COUNT', default_resource_count))
        resource_count = max(1, min(resource_count, 500))

        # Create config that might trigger different policy outcomes
        if policy_test_type == "pass":
            # Standard compliant configuration
            main_tf = """
terraform {
  required_version = ">= 1.0"
}

# Compliant resource configuration
resource "null_resource" "compliant" {
  count = __RESOURCE_COUNT__

  triggers = {
    index = tostring(count.index)
    environment = "production"
    cost_center = "engineering"
  }
}

output "status" {
  value = "compliant"
}
"""
        else:  # fail
            # Configuration that might violate policies
            main_tf = """
terraform {
  required_version = ">= 1.0"
}

# Non-compliant resource (missing required tags, etc.)
resource "null_resource" "non_compliant" {
  count = __RESOURCE_COUNT__

  triggers = {
    index = tostring(count.index)
    # Missing required tags like environment, cost_center
  }
}

output "status" {
  value = "non_compliant"
}
"""

        main_tf = main_tf.replace('__RESOURCE_COUNT__', str(resource_count))
        
        # Create tar.gz in memory
        tar_buffer = io.BytesIO()
        with tarfile.open(fileobj=tar_buffer, mode='w:gz') as tar:
            main_tf_data = main_tf.encode('utf-8')
            tarinfo = tarfile.TarInfo(name='main.tf')
            tarinfo.size = len(main_tf_data)
            tarinfo.mtime = int(time.time())
            tarinfo.mode = 0o644
            tarinfo.type = tarfile.REGTYPE
            tar.addfile(tarinfo, io.BytesIO(main_tf_data))
        
        return tar_buffer.getvalue()
    
    def _create_and_upload_config(self, policy_test_type="pass"):
        """Create configuration version and upload config."""
        # Create configuration version
        with self.client.post(
            f"/api/v2/workspaces/{self.workspace_id}/configuration-versions",
            json={
                "data": {
                    "type": "configuration-versions",
                    "attributes": {"auto-queue-runs": False, "speculative": False}
                }
            },
            headers={
                "Authorization": f"Bearer {self.tfe.token}",
                "Content-Type": "application/vnd.api+json"
            },
            verify=self.tfe.verify_ssl,
            catch_response=True,
            name="/api/v2/workspaces/:id/configuration-versions [POLICY]"
        ) as response:
            if response.status_code != 201:
                response.failure(f"Failed to create config version: {response.status_code}")
                return None
            
            config_version = response.json()
            upload_url = config_version['data']['attributes']['upload-url']
            config_version_id = config_version['data']['id']
            response.success()
        
        # Upload config
        config_data = self._create_terraform_config(policy_test_type)
        with self.client.put(
            upload_url,
            data=config_data,
            headers={"Content-Type": "application/octet-stream"},
            verify=self.tfe.verify_ssl,
            catch_response=True,
            name="/configuration-versions/:id/upload [POLICY]"
        ) as response:
            if response.status_code != 200:
                response.failure(f"Failed to upload config: {response.status_code}")
                return None
            response.success()
        
        # Wait for upload
        max_retries = 20
        for _ in range(max_retries):
            with self.client.get(
                f"/api/v2/configuration-versions/{config_version_id}",
                headers={
                    "Authorization": f"Bearer {self.tfe.token}",
                    "Content-Type": "application/vnd.api+json"
                },
                verify=self.tfe.verify_ssl,
                catch_response=True,
                name="/api/v2/configuration-versions/:id [POLICY-STATUS]"
            ) as cv_response:
                if cv_response.status_code == 200:
                    cv_data = cv_response.json()
                    status = cv_data['data']['attributes']['status']
                    cv_response.success()
                    if status == 'uploaded':
                        return config_version_id
                    elif status == 'errored':
                        return None
                else:
                    cv_response.failure(f"Failed to check config status: {cv_response.status_code}")
                    return None
            time.sleep(0.5)
        
        return None

    def _extract_policy_engine_duration_ms(self, result):
        """Extract best-effort Sentinel engine duration from a policy check result."""
        if not result:
            return 0

        if 'duration-ms' in result:
            return result['duration-ms'] or 0

        if 'sentinel' in result:
            duration_ns = 0
            sentinel_data = result.get('sentinel', {}).get('data', {})
            for workspace_data in sentinel_data.values():
                workspace_duration = workspace_data.get('duration', 0) or 0
                if workspace_duration > 0:
                    duration_ns += workspace_duration
                    continue
                for policy in workspace_data.get('policies', []):
                    duration_ns += policy.get('duration', 0) or 0
            return duration_ns / 1_000_000 if duration_ns > 0 else 0

        if 'duration' in result:
            return (result['duration'] or 0) * 1000

        return 0

    def _policy_stage_wall_time_ms(self, run_id, policy_check_id, policy_check_attributes):
        """
        Compute policy_stage_wall_time_ms from TFE timestamps, with observed polling fallback.

        This metric intentionally captures policy-stage elapsed time, not only
        Sentinel engine execution. It is the primary local load-testing metric
        because TFE may persist 0 for the engine-only duration fields.
        """
        status = policy_check_attributes.get('status')
        status_timestamps = policy_check_attributes.get('status-timestamps', {})
        start_time = _timestamp_from_keys(status_timestamps, ('queued-at', 'queued_at'))
        end_time = _timestamp_from_keys(status_timestamps, POLICY_TERMINAL_TIMESTAMP_KEYS.get(status, ()))

        if start_time and end_time:
            return max((end_time - start_time).total_seconds() * 1000, 0)

        timing = self.run_policy_timing.setdefault(run_id, {})
        observed_start = timing.get('policy_checking_started_at') or timing.get('policy_check_first_seen_at')
        if observed_start:
            return max((time.monotonic() - observed_start) * 1000, 0)

        return None

    def _record_policy_metrics(self, run_id, policy_check_id, policy_check_attributes):
        """Record policy result counts and custom wall-time metric once per policy check."""
        if not policy_check_id or policy_check_id in self.recorded_policy_checks:
            return

        pc_status = policy_check_attributes.get('status')
        if pc_status not in TERMINAL_POLICY_CHECK_STATUSES:
            return

        result = policy_check_attributes.get('result') or {}
        if not result:
            return

        self.recorded_policy_checks.add(policy_check_id)

        # Debug: Print result structure once to understand format
        import json
        if global_policy_stats['total_evaluated'] == 0:
            print(f"\n[DEBUG] Policy check result structure sample:")
            print(json.dumps(result, indent=2)[:500])

        duration_ms = self._extract_policy_engine_duration_ms(result)
        wall_time_ms = self._policy_stage_wall_time_ms(run_id, policy_check_id, policy_check_attributes)

        if wall_time_ms is not None:
            self.environment.events.request.fire(
                request_type="METRIC",
                name="policy_stage_wall_time_ms",
                response_time=wall_time_ms,
                response_length=0,
                exception=None,
                context={
                    "run_id": run_id,
                    "policy_check_id": policy_check_id,
                    "policy_check_status": pc_status
                }
            )

        with stats_lock:
            global_policy_stats['total_evaluated'] += 1
            if result.get('result', False):
                global_policy_stats['total_passed'] += 1
            else:
                global_policy_stats['total_failed'] += 1

            global_policy_stats['soft_failed'] += result.get('soft-failed', 0)
            global_policy_stats['hard_failed'] += result.get('hard-failed', 0)
            global_policy_stats['advisory_failed'] += result.get('advisory-failed', 0)

            if duration_ms > 0:
                global_policy_stats['engine_duration_count'] += 1
                global_policy_stats['total_duration_ms'] += duration_ms
                global_policy_stats['min_duration_ms'] = min(global_policy_stats['min_duration_ms'], duration_ms)
                global_policy_stats['max_duration_ms'] = max(global_policy_stats['max_duration_ms'], duration_ms)

            if wall_time_ms is not None:
                global_policy_stats['policy_stage_wall_time_count'] += 1
                global_policy_stats['total_policy_stage_wall_time_ms'] += wall_time_ms
                global_policy_stats['min_policy_stage_wall_time_ms'] = min(
                    global_policy_stats['min_policy_stage_wall_time_ms'],
                    wall_time_ms
                )
                global_policy_stats['max_policy_stage_wall_time_ms'] = max(
                    global_policy_stats['max_policy_stage_wall_time_ms'],
                    wall_time_ms
                )
    
    @task(10)
    def trigger_run_with_policy_pass(self):
        """
        Trigger a run with configuration expected to pass policies.
        This is the most common scenario - compliant infrastructure.
        """
        if not self.policy_set_id:
            return  # Skip if no policy set configured
        
        try:
            # Create and upload config
            config_version_id = self._create_and_upload_config(policy_test_type="pass")
            if not config_version_id:
                return
            
            # Create run
            with self.client.post(
                "/api/v2/runs",
                json={
                    "data": {
                        "type": "runs",
                        "attributes": {
                            "message": f"Policy test (pass) - {time.strftime('%Y-%m-%d %H:%M:%S')}"
                        },
                        "relationships": {
                            "workspace": {"data": {"type": "workspaces", "id": self.workspace_id}},
                            "configuration-version": {"data": {"type": "configuration-versions", "id": config_version_id}}
                        }
                    }
                },
                headers={
                    "Authorization": f"Bearer {self.tfe.token}",
                    "Content-Type": "application/vnd.api+json"
                },
                verify=self.tfe.verify_ssl,
                catch_response=True,
                name="/api/v2/runs [POLICY-PASS]"
            ) as response:
                if response.status_code != 201:
                    response.failure(f"Failed to create run: {response.status_code}")
                    return
                
                run = response.json()
                run_id = run['data']['id']
                self.created_runs.append(run_id)
                response.success()
                print(f"Created run {run_id} (expected to pass policies)")
                
        except Exception as e:
            print(f"Error triggering run with policy pass: {e}")
    
    @task(5)
    def trigger_run_with_policy_fail(self):
        """
        Trigger a run with configuration expected to fail policies.
        Tests policy enforcement and failure handling.
        """
        if not self.policy_set_id:
            return
        
        try:
            # Create and upload config
            config_version_id = self._create_and_upload_config(policy_test_type="fail")
            if not config_version_id:
                return
            
            # Create run
            with self.client.post(
                "/api/v2/runs",
                json={
                    "data": {
                        "type": "runs",
                        "attributes": {
                            "message": f"Policy test (fail) - {time.strftime('%Y-%m-%d %H:%M:%S')}"
                        },
                        "relationships": {
                            "workspace": {"data": {"type": "workspaces", "id": self.workspace_id}},
                            "configuration-version": {"data": {"type": "configuration-versions", "id": config_version_id}}
                        }
                    }
                },
                headers={
                    "Authorization": f"Bearer {self.tfe.token}",
                    "Content-Type": "application/vnd.api+json"
                },
                verify=self.tfe.verify_ssl,
                catch_response=True,
                name="/api/v2/runs [POLICY-FAIL]"
            ) as response:
                if response.status_code != 201:
                    response.failure(f"Failed to create run: {response.status_code}")
                    return
                
                run = response.json()
                run_id = run['data']['id']
                self.created_runs.append(run_id)
                response.success()
                print(f"Created run {run_id} (expected to fail policies)")
                
        except Exception as e:
            print(f"Error triggering run with policy fail: {e}")
    
    @task(15)
    def monitor_policy_check_status(self):
        """
        Monitor policy check status for existing runs.
        Tracks policy evaluation duration and outcomes.
        INCREASED FREQUENCY to aggressively unlock stuck runs.
        Checks ALL runs to find and unlock stuck ones.
        """
        if not self.created_runs:
            return
        
        # Check ALL runs, not just one random run
        for run_id in list(self.created_runs):
            try:
                # Get run details
                with self.client.get(
                    f"/api/v2/runs/{run_id}",
                    headers={
                        "Authorization": f"Bearer {self.tfe.token}",
                        "Content-Type": "application/vnd.api+json"
                    },
                    verify=self.tfe.verify_ssl,
                    catch_response=True,
                    name="/api/v2/runs/:id [POLICY-STATUS]"
                ) as response:
                    if response.status_code != 200:
                        response.failure(f"Failed to get run: {response.status_code}")
                        continue
                    
                    run = response.json()
                    status = run['data']['attributes']['status']
                    response.success()

                    timing = self.run_policy_timing.setdefault(run_id, {})
                    if status == 'policy_checking' and 'policy_checking_started_at' not in timing:
                        timing['policy_checking_started_at'] = time.monotonic()
                    
                    # Get policy check results if available
                    policy_check_id = None
                    if 'relationships' in run['data'] and 'policy-checks' in run['data']['relationships']:
                        policy_checks = run['data']['relationships']['policy-checks'].get('data', [])
                        if policy_checks:
                            policy_check_id = policy_checks[0]['id']
                            if 'policy_check_first_seen_at' not in timing:
                                timing['policy_check_first_seen_at'] = time.monotonic()
                    
                    if policy_check_id:
                        with self.client.get(
                            f"/api/v2/policy-checks/{policy_check_id}",
                            headers={
                                "Authorization": f"Bearer {self.tfe.token}",
                                "Content-Type": "application/vnd.api+json"
                            },
                            verify=self.tfe.verify_ssl,
                            catch_response=True,
                            name="/api/v2/policy-checks/:id [GET]"
                        ) as pc_response:
                            if pc_response.status_code == 200:
                                policy_check = pc_response.json()
                                policy_check_attributes = policy_check['data']['attributes']
                                pc_response.success()
                                self._record_policy_metrics(run_id, policy_check_id, policy_check_attributes)
                            else:
                                pc_response.failure(f"Failed to get policy check: {pc_response.status_code}")
                    
                    # Auto-override soft-mandatory policy failures using policy-checks endpoint
                    if status == 'policy_override' and policy_check_id:
                        with self.client.post(
                            f"/api/v2/policy-checks/{policy_check_id}/actions/override",
                            headers={
                                "Authorization": f"Bearer {self.tfe.token}",
                                "Content-Type": "application/vnd.api+json"
                            },
                            verify=self.tfe.verify_ssl,
                            catch_response=True,
                            name="/api/v2/policy-checks/:id/actions/override [AUTO]"
                        ) as override_response:
                            if override_response.status_code in [200, 202]:
                                override_response.success()
                                with stats_lock:
                                    global_policy_stats['overrides_performed'] += 1
                                # Note: Auto-apply is enabled, so TFE will automatically proceed with apply
                            else:
                                override_response.failure(f"Failed to override policy: {override_response.status_code}")
                    
                    # Remove completed runs (auto-apply enabled, so runs proceed automatically)
                    if status in ['applied', 'errored', 'canceled', 'discarded', 'policy_soft_failed']:
                        self.created_runs.remove(run_id)
                        self.run_policy_timing.pop(run_id, None)
                        
            except Exception as e:
                print(f"Error monitoring policy check for run {run_id}: {e}")
                continue
    
    @task(3)
    def override_soft_mandatory_policy(self):
        """
        Test policy override workflow for soft-mandatory policies.
        Simulates scenarios where policy failures need to be overridden.
        """
        if not self.created_runs:
            return
        
        try:
            run_id = random.choice(self.created_runs)
            
            # Check if run has policy check that can be overridden
            with self.client.get(
                f"/api/v2/runs/{run_id}",
                headers={
                    "Authorization": f"Bearer {self.tfe.token}",
                    "Content-Type": "application/vnd.api+json"
                },
                verify=self.tfe.verify_ssl,
                catch_response=True,
                name="/api/v2/runs/:id [OVERRIDE-CHECK]"
            ) as response:
                if response.status_code != 200:
                    response.failure(f"Failed to get run: {response.status_code}")
                    return
                
                run = response.json()
                status = run['data']['attributes']['status']
                response.success()
                
                # Only override if in policy_override state
                if status == 'policy_override':
                    with self.client.post(
                        f"/api/v2/runs/{run_id}/actions/override-policy",
                        headers={
                            "Authorization": f"Bearer {self.tfe.token}",
                            "Content-Type": "application/vnd.api+json"
                        },
                        verify=self.tfe.verify_ssl,
                        catch_response=True,
                        name="/api/v2/runs/:id/actions/override-policy [POST]"
                    ) as override_response:
                        if override_response.status_code == 202:
                            override_response.success()
                            print(f"Overrode policy for run {run_id}")
                        else:
                            override_response.failure(f"Failed to override policy: {override_response.status_code}")
                            
        except Exception as e:
            print(f"Error overriding policy: {e}")


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Print test configuration when test starts."""
    print("\n" + "="*80)
    print("TFE Sentinel Policy Evaluation Load Test Starting")
    print("="*80)
    policy_profile = os.getenv('TFE_SENTINEL_POLICY_PROFILE', 'synthetic-heavy').lower()
    default_policy_set = 'loadtest-policies-synthetic-heavy' if policy_profile == 'synthetic-heavy' else 'loadtest-policies'
    print(f"TFE Hostname: {os.getenv('TFE_HOSTNAME', 'app.terraform.io')}")
    print(f"Organization: {os.getenv('TFE_ORGANIZATION', 'NOT SET')}")
    print(f"Policy Set: {os.getenv('TFE_POLICY_SET_NAME', default_policy_set)}")
    print(f"SSL Verification: {os.getenv('TFE_VERIFY_SSL', 'true')}")
    print(f"Users: {os.getenv('LOCUST_USERS', '5')}")
    print(f"Spawn Rate: {os.getenv('LOCUST_SPAWN_RATE', '1')}/s")
    print(f"Run Time: {os.getenv('LOCUST_RUN_TIME', '10m')}")
    print(f"Policy Profile: {policy_profile}")
    print("="*80)
    print("Default sample policy sets are auto-created; custom policy sets must exist in TFE.")
    print("="*80 + "\n")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Print test summary with policy statistics when test stops."""
    print("\n" + "="*80)
    print("TFE Sentinel Policy Evaluation Load Test Completed")
    print("="*80)
    
    # Display policy statistics
    with stats_lock:
        print("\nSENTINEL POLICY STATISTICS:")
        print(f"  Total Policy Evaluations:    {global_policy_stats['total_evaluated']}")
        print(f"    ✅ Passed:                  {global_policy_stats['total_passed']}")
        print(f"    ❌ Failed:                  {global_policy_stats['total_failed']}")
        print(f"\n  Failure Breakdown:")
        print(f"    Soft-Mandatory Failures:   {global_policy_stats['soft_failed']}")
        print(f"    Hard-Mandatory Failures:   {global_policy_stats['hard_failed']}")
        print(f"    Advisory Failures:         {global_policy_stats['advisory_failed']}")
        print(f"\n  Overrides Performed:         {global_policy_stats['overrides_performed']}")
        
        # Display performance metrics
        if global_policy_stats['total_evaluated'] > 0:
            wall_count = global_policy_stats['policy_stage_wall_time_count']
            if wall_count > 0:
                avg_wall_time = global_policy_stats['total_policy_stage_wall_time_ms'] / wall_count
                min_wall_time = global_policy_stats['min_policy_stage_wall_time_ms']
                max_wall_time = global_policy_stats['max_policy_stage_wall_time_ms']
            else:
                avg_wall_time = 0
                min_wall_time = 0
                max_wall_time = 0

            engine_count = global_policy_stats['engine_duration_count']
            
            print(f"\n  Policy Evaluation Performance:")
            print(f"    policy_stage_wall_time_ms Avg: {avg_wall_time:.2f}ms")
            print(f"    policy_stage_wall_time_ms Min: {min_wall_time:.2f}ms")
            print(f"    policy_stage_wall_time_ms Max: {max_wall_time:.2f}ms")

            if engine_count > 0:
                avg_duration = global_policy_stats['total_duration_ms'] / engine_count
                min_duration = global_policy_stats['min_duration_ms']
                max_duration = global_policy_stats['max_duration_ms']
                print(f"    Engine Duration Avg:       {avg_duration:.2f}ms")
                print(f"    Engine Duration Min:       {min_duration:.2f}ms")
                print(f"    Engine Duration Max:       {max_duration:.2f}ms")
            else:
                print(f"    Engine Duration:           unavailable (TFE returned 0 for all duration fields)")
    
    print("\nCheck Grafana dashboard for detailed metrics:")
    print("  - policy_stage_wall_time_ms")
    print("  - Policy engine duration when TFE reports it")
    print("  - Policy pass/fail rates")
    print("  - Policy override frequency")
    print("  - Run status distribution")
    print("="*80 + "\n")
