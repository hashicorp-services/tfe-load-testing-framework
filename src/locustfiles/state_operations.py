# Copyright (c) 2026 IBM Corporation
# SPDX-License-Identifier: IPL-1.0

"""
TFE State Management Load Test

This load test scenario focuses on Terraform Enterprise state operations:
- Uploading state files
- Downloading state files
- Listing state versions
- State locking operations
- Handling large state files

Environment Variables:
    TFE_HOSTNAME: TFE instance hostname (e.g., app.terraform.io or tfe.localdemo.me)
    TFE_TOKEN: TFE API token
    TFE_ORGANIZATION: TFE organization name
    TFE_VERIFY_SSL: Whether to verify SSL certificates (default: true, set to false for local dev)
    LOCUST_USERS: Number of concurrent users (default: 10)
    LOCUST_SPAWN_RATE: User spawn rate per second (default: 1)
    LOCUST_RUN_TIME: Test duration (default: 5m)
"""

import os
import json
import time
import random
import uuid
from locust import HttpUser, task, between, events
from src.utils.tfe_client import TFEClient

# Suppress SSL warnings for local development
import urllib3
if os.getenv('TFE_VERIFY_SSL', 'true').lower() == 'false':
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class TFEStateUser(HttpUser):
    """
    Simulates a user performing state management operations in TFE.
    
    Task weights determine the frequency of each operation:
    - upload_state: 10 (most common - uploading new state)
    - download_current_state: 8 (frequently downloading current state)
    - list_state_versions: 5 (checking state history)
    - download_specific_version: 3 (occasionally downloading old versions)
    - upload_large_state: 2 (testing large file handling)
    """
    
    wait_time = between(1, 3)  # Wait 1-3 seconds between tasks
    
    def on_start(self):
        """Initialize TFE client and create test workspace on user start."""
        # Initialize attributes first (before any exceptions can be raised)
        self.state_versions = []
        self.state_counter = 0
        self.workspace_locked = False
        self.workspace_id = None
        self.workspace_name = None
        
        self.tfe = TFEClient(
            hostname=os.getenv('TFE_HOSTNAME', 'app.terraform.io'),
            token=os.getenv('TFE_TOKEN'),
            organization=os.getenv('TFE_ORGANIZATION'),
            verify_ssl=os.getenv('TFE_VERIFY_SSL', 'true').lower() == 'true'
        )
        
        # Create a unique workspace for this user
        workspace_name = f"loadtest-state-{uuid.uuid4().hex[:8]}"
        self.workspace = self.tfe.create_workspace(
            name=workspace_name
        )
        self.workspace_id = self.workspace['data']['id']
        self.workspace_name = workspace_name
        
        print(f"User started with workspace: {workspace_name}")
    
    def on_stop(self):
        """Clean up test workspace on user stop."""
        try:
            if hasattr(self, 'workspace_id'):
                # Unlock workspace if it's locked before deletion
                if hasattr(self, 'workspace_locked') and self.workspace_locked:
                    try:
                        self.tfe.unlock_workspace(self.workspace_id)
                    except:
                        # Try force unlock if regular unlock fails
                        try:
                            self.tfe.force_unlock_workspace(self.workspace_id)
                        except:
                            pass
                
                self.tfe.delete_workspace(self.workspace_id)
                print(f"Cleaned up workspace: {self.workspace_name}")
        except Exception as e:
            print(f"Error during cleanup: {e}")
    
    def _generate_state_file(self, resource_count=10, size_multiplier=1):
        """
        Generate a realistic Terraform state file.
        
        Args:
            resource_count: Number of resources in the state
            size_multiplier: Multiplier for state file size (for testing large files)
            
        Returns:
            dict: Terraform state file structure
        """
        resources = []
        
        for i in range(resource_count):
            # Create various resource types
            resource_types = [
                "null_resource",
                "random_string",
                "random_id",
                "random_password",
                "local_file"
            ]
            
            resource_type = random.choice(resource_types)
            
            resource = {
                "mode": "managed",
                "type": resource_type,
                "name": f"test_{i}",
                "provider": f"provider[\"registry.terraform.io/hashicorp/{resource_type.split('_')[0]}\"]",
                "instances": [
                    {
                        "schema_version": 0,
                        "attributes": {
                            "id": f"test-{i}-{random.randint(1000, 9999)}",
                            "triggers": {
                                "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
                                "random": str(random.randint(1000, 9999))
                            }
                        }
                    }
                ]
            }
            
            # Add padding for size testing
            if size_multiplier > 1:
                resource["instances"][0]["attributes"]["padding"] = "x" * (1000 * size_multiplier)
            
            resources.append(resource)
        
        state = {
            "version": 4,
            "terraform_version": "1.5.0",
            "serial": self.state_counter,
            "lineage": f"loadtest-{self.workspace_name}",
            "outputs": {
                "resource_count": {
                    "value": resource_count,
                    "type": "number"
                },
                "timestamp": {
                    "value": time.strftime('%Y-%m-%d %H:%M:%S'),
                    "type": "string"
                }
            },
            "resources": resources
        }
        
        self.state_counter += 1
        return state
    
    @task(10)
    def upload_state(self):
        """
        Upload a new state file to the workspace.
        This is the most common state operation.
        """
        try:
            # Lock workspace before uploading state
            if not self.workspace_locked:
                self.tfe.lock_workspace(self.workspace_id, reason="Load test state upload")
                self.workspace_locked = True
            
            # Generate state file
            state_data = self._generate_state_file(
                resource_count=random.randint(5, 20)
            )
            state_json = json.dumps(state_data)
            
            # Prepare payload
            import hashlib
            import base64
            
            serial = state_data.get('serial', 0)
            lineage = state_data.get('lineage')
            md5 = hashlib.md5(state_json.encode('utf-8')).hexdigest()
            state_b64 = base64.b64encode(state_json.encode('utf-8')).decode('utf-8')
            
            payload = {
                "data": {
                    "type": "state-versions",
                    "attributes": {
                        "serial": serial,
                        "md5": md5,
                        "state": state_b64
                    }
                }
            }
            
            if lineage:
                payload["data"]["attributes"]["lineage"] = lineage
            
            # Create state version using Locust's client for metrics
            with self.client.post(
                f"/api/v2/workspaces/{self.workspace_id}/state-versions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.tfe.token}",
                    "Content-Type": "application/vnd.api+json"
                },
                verify=self.tfe.verify_ssl,
                catch_response=True,
                name="/api/v2/workspaces/:id/state-versions [CREATE]"
            ) as response:
                if response.status_code == 201:
                    state_version = response.json()
                    version_id = state_version['data']['id']
                    self.state_versions.append(version_id)
                    response.success()
                    print(f"Uploaded state version {version_id} to {self.workspace_name} "
                          f"(serial: {self.state_counter - 1}, size: {len(state_json)} bytes)")
                else:
                    response.failure(f"Failed to create state version: {response.status_code}")
            
            # Unlock workspace after successful upload
            self.tfe.unlock_workspace(self.workspace_id)
            self.workspace_locked = False
            
        except Exception as e:
            print(f"Error uploading state: {e}")
            # Try to unlock on error
            if self.workspace_locked:
                try:
                    self.tfe.unlock_workspace(self.workspace_id)
                    self.workspace_locked = False
                except:
                    pass
    
    @task(8)
    def download_current_state(self):
        """
        Download the current state file from the workspace.
        Simulates users pulling the latest state.
        """
        try:
            # Get current state version using Locust's client
            with self.client.get(
                f"/api/v2/workspaces/{self.workspace_id}/current-state-version",
                headers={
                    "Authorization": f"Bearer {self.tfe.token}",
                    "Content-Type": "application/vnd.api+json"
                },
                verify=self.tfe.verify_ssl,
                catch_response=True,
                name="/api/v2/workspaces/:id/current-state-version [GET]"
            ) as response:
                if response.status_code == 404:
                    # No state yet - this is normal for new workspaces
                    response.success()
                    return
                elif response.status_code != 200:
                    response.failure(f"Failed to get current state: {response.status_code}")
                    return
                
                current_state = response.json()
                response.success()
            
            if not current_state.get('data'):
                return
            
            # Download the state file (presigned URL - explicitly remove auth header)
            download_url = current_state['data']['attributes']['hosted-state-download-url']
            
            # Create a new session without auth headers for presigned URL
            import requests
            session = requests.Session()
            
            start_time = time.time()
            try:
                response = session.get(
                    download_url,
                    verify=self.tfe.verify_ssl
                )
                total_time = int((time.time() - start_time) * 1000)
                
                if response.status_code == 200:
                    state_data = response.json()
                    resource_count = len(state_data.get('resources', []))
                    self.environment.events.request.fire(
                        request_type="GET",
                        name="/state-versions/:id/hosted_state [DOWNLOAD]",
                        response_time=total_time,
                        response_length=len(response.content),
                        exception=None,
                        context={}
                    )
                    print(f"Downloaded current state from {self.workspace_name} "
                          f"({resource_count} resources, {len(response.content)} bytes)")
                else:
                    self.environment.events.request.fire(
                        request_type="GET",
                        name="/state-versions/:id/hosted_state [DOWNLOAD]",
                        response_time=total_time,
                        response_length=0,
                        exception=Exception(f"Failed to download state: {response.status_code}"),
                        context={}
                    )
            except Exception as e:
                total_time = int((time.time() - start_time) * 1000)
                self.environment.events.request.fire(
                    request_type="GET",
                    name="/state-versions/:id/hosted_state [DOWNLOAD]",
                    response_time=total_time,
                    response_length=0,
                    exception=e,
                    context={}
                )
            
        except Exception as e:
            print(f"Error downloading current state: {e}")
    
    @task(5)
    def list_state_versions(self):
        """
        List all state versions for the workspace.
        Simulates users checking state history.
        """
        try:
            # Get workspace details first
            workspace = self.tfe.get_workspace(self.workspace_id)
            workspace_name = workspace['data']['attributes']['name']
            
            # List state versions using Locust's client
            with self.client.get(
                "/api/v2/state-versions",
                params={
                    "filter[workspace][name]": workspace_name,
                    "filter[organization][name]": self.tfe.organization,
                    "page[size]": 20,
                    "page[number]": 1
                },
                headers={
                    "Authorization": f"Bearer {self.tfe.token}",
                    "Content-Type": "application/vnd.api+json"
                },
                verify=self.tfe.verify_ssl,
                catch_response=True,
                name="/api/v2/state-versions [LIST]"
            ) as response:
                if response.status_code == 404:
                    # No state versions yet - normal for new workspaces
                    response.success()
                    return
                elif response.status_code == 200:
                    state_versions = response.json()
                    version_count = len(state_versions.get('data', []))
                    response.success()
                    print(f"Listed {version_count} state versions for {self.workspace_name}")
                    
                    # Store version IDs for potential download
                    if state_versions.get('data'):
                        self.state_versions = [v['id'] for v in state_versions['data']]
                else:
                    response.failure(f"Failed to list state versions: {response.status_code}")
            
        except Exception as e:
            print(f"Error listing state versions: {e}")
    
    @task(3)
    def download_specific_version(self):
        """
        Download a specific historical state version.
        Simulates users retrieving old state for comparison or rollback.
        """
        if not self.state_versions:
            return
        
        try:
            # Pick a random state version
            version_id = random.choice(self.state_versions)
            
            # Get state version details using Locust's client
            with self.client.get(
                f"/api/v2/state-versions/{version_id}",
                headers={
                    "Authorization": f"Bearer {self.tfe.token}",
                    "Content-Type": "application/vnd.api+json"
                },
                verify=self.tfe.verify_ssl,
                catch_response=True,
                name="/api/v2/state-versions/:id [GET]"
            ) as response:
                if response.status_code != 200:
                    response.failure(f"Failed to get state version: {response.status_code}")
                    return
                
                state_version = response.json()
                response.success()
            
            # Download the state file (presigned URL - explicitly remove auth header)
            download_url = state_version['data']['attributes']['hosted-state-download-url']
            
            # Create a new session without auth headers for presigned URL
            import requests
            session = requests.Session()
            
            start_time = time.time()
            try:
                response = session.get(
                    download_url,
                    verify=self.tfe.verify_ssl
                )
                total_time = int((time.time() - start_time) * 1000)
                
                if response.status_code == 200:
                    state_data = response.json()
                    serial = state_data.get('serial', 'unknown')
                    self.environment.events.request.fire(
                        request_type="GET",
                        name="/state-versions/:id/hosted_state [DOWNLOAD SPECIFIC]",
                        response_time=total_time,
                        response_length=len(response.content),
                        exception=None,
                        context={}
                    )
                    print(f"Downloaded state version {version_id} from {self.workspace_name} "
                          f"(serial: {serial}, {len(response.content)} bytes)")
                else:
                    self.environment.events.request.fire(
                        request_type="GET",
                        name="/state-versions/:id/hosted_state [DOWNLOAD SPECIFIC]",
                        response_time=total_time,
                        response_length=0,
                        exception=Exception(f"Failed to download state: {response.status_code}"),
                        context={}
                    )
            except Exception as e:
                total_time = int((time.time() - start_time) * 1000)
                self.environment.events.request.fire(
                    request_type="GET",
                    name="/state-versions/:id/hosted_state [DOWNLOAD SPECIFIC]",
                    response_time=total_time,
                    response_length=0,
                    exception=e,
                    context={}
                )
            
        except Exception as e:
            print(f"Error downloading specific state version: {e}")
    
    @task(2)
    def upload_large_state(self):
        """
        Upload a large state file to test performance with bigger files.
        Simulates workspaces with many resources.
        """
        try:
            # Lock workspace before uploading state
            if not self.workspace_locked:
                self.tfe.lock_workspace(self.workspace_id, reason="Load test large state upload")
                self.workspace_locked = True
            
            # Generate a larger state file (50-100 resources with padding)
            state_data = self._generate_state_file(
                resource_count=random.randint(50, 100),
                size_multiplier=random.randint(5, 10)
            )
            state_json = json.dumps(state_data)
            
            print(f"Uploading large state to {self.workspace_name} "
                  f"({len(state_json)} bytes, ~{len(state_json) / 1024:.1f} KB)")
            
            # Prepare payload
            import hashlib
            import base64
            
            serial = state_data.get('serial', 0)
            lineage = state_data.get('lineage')
            md5 = hashlib.md5(state_json.encode('utf-8')).hexdigest()
            state_b64 = base64.b64encode(state_json.encode('utf-8')).decode('utf-8')
            
            payload = {
                "data": {
                    "type": "state-versions",
                    "attributes": {
                        "serial": serial,
                        "md5": md5,
                        "state": state_b64
                    }
                }
            }
            
            if lineage:
                payload["data"]["attributes"]["lineage"] = lineage
            
            # Create state version using Locust's client for metrics
            with self.client.post(
                f"/api/v2/workspaces/{self.workspace_id}/state-versions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.tfe.token}",
                    "Content-Type": "application/vnd.api+json"
                },
                verify=self.tfe.verify_ssl,
                catch_response=True,
                name="/api/v2/workspaces/:id/state-versions [CREATE LARGE]"
            ) as response:
                if response.status_code == 201:
                    state_version = response.json()
                    version_id = state_version['data']['id']
                    self.state_versions.append(version_id)
                    response.success()
                    print(f"Successfully uploaded large state version {version_id}")
                else:
                    response.failure(f"Failed to create large state version: {response.status_code}")
            
            # Unlock workspace after successful upload
            self.tfe.unlock_workspace(self.workspace_id)
            self.workspace_locked = False
            
        except Exception as e:
            print(f"Error uploading large state: {e}")
            # Try to unlock on error
            if self.workspace_locked:
                try:
                    self.tfe.unlock_workspace(self.workspace_id)
                    self.workspace_locked = False
                except:
                    pass


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Print test configuration when test starts."""
    print("\n" + "="*80)
    print("TFE State Management Load Test Starting")
    print("="*80)
    print(f"TFE Hostname: {os.getenv('TFE_HOSTNAME', 'app.terraform.io')}")
    print(f"Organization: {os.getenv('TFE_ORGANIZATION', 'NOT SET')}")
    print(f"SSL Verification: {os.getenv('TFE_VERIFY_SSL', 'true')}")
    print(f"Users: {os.getenv('LOCUST_USERS', '10')}")
    print(f"Spawn Rate: {os.getenv('LOCUST_SPAWN_RATE', '1')}/s")
    print(f"Run Time: {os.getenv('LOCUST_RUN_TIME', '5m')}")
    print("="*80 + "\n")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Print test summary when test stops."""
    print("\n" + "="*80)
    print("TFE State Management Load Test Completed")
    print("="*80)
    print("Check Grafana dashboard for detailed metrics:")
    print("  - State upload/download performance")
    print("  - API request latency for state operations")
    print("  - Large file handling performance")
    print("  - State version management overhead")
    print("="*80 + "\n")
