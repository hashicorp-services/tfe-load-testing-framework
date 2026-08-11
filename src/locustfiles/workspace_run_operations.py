# Copyright (c) 2026 IBM Corporation
# SPDX-License-Identifier: MPL-2.0

"""
TFE Workspace + Run Scaling Load Test

Focused scenario for concurrent-run capacity testing:
- Each Locust user creates one workspace in on_start
- A single task repeatedly uploads config and triggers a run
- N users ⇒ N workspaces ⇒ up to N concurrent runs (one active run per workspace)

Unlike run_operations.py, this scenario does not include monitor, cancel,
or queue-multiple tasks.

Environment Variables:
    TFE_HOSTNAME: TFE instance hostname (e.g., app.terraform.io or tfe.localdemo.me)
    TFE_TOKEN: TFE API token
    TFE_ORGANIZATION: TFE organization name
    TFE_VERIFY_SSL: Whether to verify SSL certificates (default: true, set to false for local dev)
    LOCUST_USERS: Number of concurrent users (default: 10)
    LOCUST_SPAWN_RATE: User spawn rate per second (default: 1)
    LOCUST_RUN_TIME: Test duration (default: 5m)
    MAX_CONCURRENT_RUNS: Target concurrent runs; drives user/spawn auto-calc in the runner
"""

import os
import time
import tarfile
import io
import random
import uuid
from locust import HttpUser, task, between, events
from locust.exception import RescheduleTask
from src.utils.tfe_client import TFEClient

# Suppress SSL warnings for local development
import urllib3
if os.getenv('TFE_VERIFY_SSL', 'true').lower() == 'false':
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class TFEWorkspaceRunUser(HttpUser):
    """
    Simulates a user that owns one workspace and repeatedly triggers runs.

    Designed for concurrent-run scaling: each user holds a dedicated workspace
    so TFE can execute one active run per user concurrently.
    """

    wait_time = between(1, 3)  # Short wait to re-queue promptly for sustained concurrency

    def on_start(self):
        """Initialize TFE client and create one dedicated workspace for this user."""
        # Initialize attributes first (before any exceptions can be raised)
        self.created_runs = []
        self.workspace_id = None
        self.workspace_name = None

        self.tfe = TFEClient(
            hostname=os.getenv('TFE_HOSTNAME', 'app.terraform.io'),
            token=os.getenv('TFE_TOKEN'),
            organization=os.getenv('TFE_ORGANIZATION'),
            verify_ssl=os.getenv('TFE_VERIFY_SSL', 'true').lower() == 'true'
        )

        # Create a unique workspace for this user
        workspace_name = f"loadtest-ws-run-{uuid.uuid4().hex[:8]}"
        self.workspace = self.tfe.create_workspace(
            name=workspace_name,
            auto_apply=True  # Enable auto-apply for end-to-end testing
        )
        self.workspace_id = self.workspace['id']
        self.workspace_name = workspace_name

        print(f"User started with workspace: {workspace_name}")

    def on_stop(self):
        """Cancel tracked runs and delete the user's workspace."""
        try:
            # Cancel any pending runs
            for run_id in self.created_runs:
                try:
                    self.tfe.cancel_run(run_id)
                except Exception:
                    pass  # Run might already be completed or canceled

            # Wait a moment for cancellations to process
            time.sleep(2)

            # Delete the workspace
            if hasattr(self, 'workspace_id') and self.workspace_id:
                try:
                    self.tfe.delete_workspace(self.workspace_id)
                    print(f"Cleaned up workspace: {self.workspace_name}")
                except Exception as e:
                    # Workspace might be locked or have active runs
                    # This is acceptable during cleanup - don't fail the test
                    print(f"Warning: Could not delete workspace {self.workspace_name}: {e}")
        except Exception as e:
            # Don't let cleanup errors fail the test
            print(f"Warning during cleanup: {e}")

    def _create_terraform_config(self, resource_count=5):
        """
        Create a simple Terraform configuration as a tar.gz file.

        Args:
            resource_count: Number of null_resource instances to create

        Returns:
            bytes: Tar.gz file content
        """
        # Create a simple Terraform configuration
        main_tf = f"""
terraform {{
  required_version = ">= 1.0"
}}

# Generate random resources for testing
resource "null_resource" "test" {{
  count = {resource_count}
  
  triggers = {{
    timestamp = timestamp()
    random_id = uuid()
  }}
}}

output "resource_count" {{
  value = {resource_count}
}}

output "timestamp" {{
  value = timestamp()
}}
"""

        # Create tar.gz in memory
        tar_buffer = io.BytesIO()
        with tarfile.open(fileobj=tar_buffer, mode='w:gz') as tar:
            # Add main.tf
            main_tf_data = main_tf.encode('utf-8')
            tarinfo = tarfile.TarInfo(name='main.tf')
            tarinfo.size = len(main_tf_data)
            tarinfo.mtime = int(time.time())
            tarinfo.mode = 0o644
            tarinfo.type = tarfile.REGTYPE
            tar.addfile(tarinfo, io.BytesIO(main_tf_data))

        return tar_buffer.getvalue()

    @task
    def create_and_trigger_run(self):
        """
        Create a configuration version, upload config, and trigger a run.
        Single task for sustained concurrent-run pressure.
        """
        run_id = None
        try:
            # Create configuration version using Locust client for metrics
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
                name="/api/v2/workspaces/:id/configuration-versions [CREATE]"
            ) as response:
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 5))
                    print(f"Rate limited (429) creating config version, backing off {retry_after}s")
                    time.sleep(retry_after)
                    raise RescheduleTask()
                elif response.status_code != 201:
                    response.failure(f"Failed to create config version: {response.status_code}")
                    return

                config_version = response.json()
                upload_url = config_version['data']['attributes']['upload-url']
                response.success()

            # Generate and upload Terraform configuration
            config_data = self._create_terraform_config(resource_count=random.randint(3, 10))

            with self.client.put(
                upload_url,
                data=config_data,
                headers={"Content-Type": "application/octet-stream"},
                verify=self.tfe.verify_ssl,
                catch_response=True,
                name="/configuration-versions/:id/upload [PUT]"
            ) as response:
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 5))
                    print(f"Rate limited (429) uploading config, backing off {retry_after}s")
                    time.sleep(retry_after)
                    raise RescheduleTask()
                elif response.status_code != 200:
                    response.failure(f"Failed to upload config: {response.status_code}")
                    return
                response.success()

            # Wait for configuration version to be uploaded
            config_version_id = config_version['data']['id']
            max_retries = 20
            config_uploaded = False
            for i in range(max_retries):
                with self.client.get(
                    f"/api/v2/configuration-versions/{config_version_id}",
                    headers={
                        "Authorization": f"Bearer {self.tfe.token}",
                        "Content-Type": "application/vnd.api+json"
                    },
                    verify=self.tfe.verify_ssl,
                    catch_response=True,
                    name="/api/v2/configuration-versions/:id [STATUS-CHECK]"
                ) as cv_response:
                    if cv_response.status_code == 200:
                        cv_data = cv_response.json()
                        status = cv_data['data']['attributes']['status']
                        cv_response.success()
                        if status == 'uploaded':
                            config_uploaded = True
                            break
                        elif status == 'errored':
                            print(f"Config version {config_version_id} errored")
                            return
                    elif cv_response.status_code == 429:
                        retry_after = int(cv_response.headers.get("Retry-After", 5))
                        print(f"Rate limited (429) checking config version status, backing off {retry_after}s")
                        time.sleep(retry_after)
                        raise RescheduleTask()
                    else:
                        cv_response.failure(f"Failed to check config version status: {cv_response.status_code}")
                        return
                time.sleep(0.5)

            # Verify config version is uploaded before creating run
            if not config_uploaded:
                print(f"Config version {config_version_id} not uploaded after {max_retries} retries, skipping run creation")
                return

            # Check workspace status and current run before creating new run
            with self.client.get(
                f"/api/v2/workspaces/{self.workspace_id}",
                headers={
                    "Authorization": f"Bearer {self.tfe.token}",
                    "Content-Type": "application/vnd.api+json"
                },
                verify=self.tfe.verify_ssl,
                catch_response=True,
                name="/api/v2/workspaces/:id [LOCK-CHECK]"
            ) as ws_response:
                if ws_response.status_code == 200:
                    ws_data = ws_response.json()
                    is_locked = ws_data['data']['attributes']['locked']

                    # Check if there's a current run
                    current_run = ws_data['data']['relationships'].get('current-run', {}).get('data')
                    ws_response.success()

                    if is_locked:
                        print(f"Workspace {self.workspace_name} is locked, skipping run creation")
                        return

                    # If there's a current run, wait a bit before creating a new one
                    if current_run:
                        print(f"Workspace {self.workspace_name} has active run, waiting before creating new run")
                        time.sleep(2)
                elif ws_response.status_code == 429:
                    retry_after = int(ws_response.headers.get("Retry-After", 5))
                    print(f"Rate limited (429) checking workspace lock, backing off {retry_after}s")
                    time.sleep(retry_after)
                    raise RescheduleTask()
                else:
                    ws_response.failure(f"Failed to check workspace lock status: {ws_response.status_code}")
                    return

            # Create a run (plan) using Locust client
            with self.client.post(
                "/api/v2/runs",
                json={
                    "data": {
                        "type": "runs",
                        "attributes": {
                            "message": f"Load test run - {time.strftime('%Y-%m-%d %H:%M:%S')}"
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
                name="/api/v2/runs [CREATE]"
            ) as response:
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 5))
                    print(f"Rate limited (429) creating run, backing off {retry_after}s")
                    time.sleep(retry_after)
                    raise RescheduleTask()
                elif response.status_code != 201:
                    error_detail = ""
                    try:
                        error_data = response.json()
                        if 'errors' in error_data and len(error_data['errors']) > 0:
                            error_detail = error_data['errors'][0].get('detail', '')
                    except Exception:
                        pass
                    response.failure(f"Failed to create run: {response.status_code} - {error_detail}")
                    print(f"Run creation failed for workspace {self.workspace_name}: {response.status_code} - {error_detail}")
                    return

                run = response.json()
                run_id = run['data']['id']
                self.created_runs.append(run_id)
                response.success()
                print(f"Created run {run_id} in workspace {self.workspace_name}")

        except RescheduleTask:
            raise
        except Exception as e:
            print(f"Error creating and triggering run: {e}")


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Print test configuration when test starts."""
    print("\n" + "="*80)
    print("TFE Workspace + Run Scaling Load Test Starting")
    print("="*80)
    print(f"TFE Hostname: {os.getenv('TFE_HOSTNAME', 'app.terraform.io')}")
    print(f"Organization: {os.getenv('TFE_ORGANIZATION', 'NOT SET')}")
    print(f"SSL Verification: {os.getenv('TFE_VERIFY_SSL', 'true')}")
    print(f"Max Concurrent Runs: {os.getenv('MAX_CONCURRENT_RUNS', 'not set')}")
    print(f"Users: {os.getenv('LOCUST_USERS', '10')}")
    print(f"Spawn Rate: {os.getenv('LOCUST_SPAWN_RATE', '1')}/s")
    print(f"Run Time: {os.getenv('LOCUST_RUN_TIME', '5m')}")
    print("="*80 + "\n")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Print test summary when test stops."""
    print("\n" + "="*80)
    print("TFE Workspace + Run Scaling Load Test Completed")
    print("="*80)
    print("Check Grafana dashboard for detailed metrics:")
    print("  - Run queue depth over time")
    print("  - Run status distribution")
    print("  - API request latency")
    print("  - Concurrent run capacity vs TFE_CAPACITY_CONCURRENCY")
    print("="*80 + "\n")
