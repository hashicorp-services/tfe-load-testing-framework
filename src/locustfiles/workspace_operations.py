"""
Workspace Operations Load Test

This Locust test simulates basic workspace lifecycle operations:
- Creating workspaces
- Listing workspaces
- Deleting workspaces

This is a foundational scenario for testing TFE's ability to handle
workspace management under load.
"""

import os
import uuid
import logging
import warnings
from typing import Optional

from locust import HttpUser, task, between, events
from locust.exception import StopUser
from urllib3.exceptions import InsecureRequestWarning

# Add parent directory to path for imports
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.tfe_client import TFEClient

logger = logging.getLogger(__name__)


class TFEWorkspaceUser(HttpUser):
    """
    Simulates a user performing workspace operations on TFE.
    
    This user will:
    1. Create workspaces with unique names
    2. List workspaces periodically
    3. Delete workspaces after a certain time
    
    Configuration via environment variables:
    - TFE_HOSTNAME: TFE instance hostname (default: tfe.localdemo.me)
    - TFE_TOKEN: TFE API token (required)
    - TFE_ORGANIZATION: Organization name (required)
    - TFE_VERIFY_SSL: Verify SSL certificates (default: true)
    - CLEANUP_WORKSPACES: Delete workspaces after creation (default: true)
    """
    
    # Wait time between tasks (simulates user think time)
    wait_time = between(2, 5)
    
    # Track created workspaces for cleanup
    created_workspaces = []
    
    def on_start(self):
        """
        Initialize TFE client when user starts.
        Called once per user when they start.
        """
        # Initialize attributes first (before any exceptions can be raised)
        self.cleanup_enabled = os.getenv("CLEANUP_WORKSPACES", "true").lower() == "true"
        self.created_workspaces = []
        self.test_id = uuid.uuid4().hex[:8]
        
        # Get configuration from environment
        hostname = os.getenv("TFE_HOSTNAME", "tfe.localdemo.me")
        token = os.getenv("TFE_TOKEN")
        organization = os.getenv("TFE_ORGANIZATION")
        verify_ssl = os.getenv("TFE_VERIFY_SSL", "true").lower() == "true"
        
        if not token:
            logger.error("TFE_TOKEN environment variable is required")
            raise StopUser("TFE_TOKEN not configured")
        
        if not organization:
            logger.error("TFE_ORGANIZATION environment variable is required")
            raise StopUser("TFE_ORGANIZATION not configured")
        
        # Initialize TFE client
        self.tfe_client = TFEClient(
            hostname=hostname,
            token=token,
            organization=organization,
            verify_ssl=verify_ssl
        )
        
        # Store configuration
        self.organization = organization
        
        # Suppress SSL warnings if SSL verification is disabled
        if not verify_ssl:
            warnings.filterwarnings('ignore', category=InsecureRequestWarning)
        
        logger.info(f"User {self.test_id} started - Organization: {organization}")
    
    def on_stop(self):
        """
        Cleanup when user stops.
        Called once per user when they stop.
        """
        if self.cleanup_enabled and self.created_workspaces:
            logger.info(f"User {self.test_id} cleaning up {len(self.created_workspaces)} workspaces")
            for workspace_id in self.created_workspaces:
                try:
                    self.tfe_client.delete_workspace(workspace_id)
                    logger.debug(f"Cleaned up workspace {workspace_id}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup workspace {workspace_id}: {e}")
    
    @task(10)
    def create_workspace(self):
        """
        Create a new workspace with a unique name.
        
        Weight: 10 (most common operation in this scenario)
        """
        workspace_name = f"loadtest-{self.test_id}-{uuid.uuid4().hex[:6]}"
        
        try:
            # Use Locust's client for automatic metrics tracking
            with self.client.post(
                f"/api/v2/organizations/{self.organization}/workspaces",
                json={
                    "data": {
                        "type": "workspaces",
                        "attributes": {
                            "name": workspace_name,
                            "auto-apply": False,
                            "queue-all-runs": True,
                            "description": f"Load test workspace created by user {self.test_id}"
                        }
                    }
                },
                headers={
                    "Authorization": f"Bearer {self.tfe_client.token}",
                    "Content-Type": "application/vnd.api+json"
                },
                verify=self.tfe_client.verify_ssl,
                catch_response=True,
                name="/api/v2/organizations/:org/workspaces [CREATE]"
            ) as response:
                if response.status_code == 201:
                    workspace_data = response.json()
                    workspace_id = workspace_data["data"]["id"]
                    self.created_workspaces.append(workspace_id)
                    response.success()
                    logger.debug(f"Created workspace: {workspace_name} (ID: {workspace_id})")
                elif response.status_code == 422:
                    # Workspace name conflict - not a failure for load testing
                    response.success()
                    logger.debug(f"Workspace name conflict: {workspace_name}")
                else:
                    response.failure(f"Failed to create workspace: {response.status_code}")
                    logger.error(f"Failed to create workspace {workspace_name}: {response.text}")
        
        except Exception as e:
            logger.error(f"Exception creating workspace: {e}")
            # Let Locust handle the exception for metrics
            raise
    
    @task(5)
    def list_workspaces(self):
        """
        List workspaces in the organization.
        
        Weight: 5 (moderate frequency)
        """
        try:
            with self.client.get(
                f"/api/v2/organizations/{self.organization}/workspaces",
                params={"page[size]": 20, "page[number]": 1},
                headers={
                    "Authorization": f"Bearer {self.tfe_client.token}",
                    "Content-Type": "application/vnd.api+json"
                },
                verify=self.tfe_client.verify_ssl,
                catch_response=True,
                name="/api/v2/organizations/:org/workspaces [LIST]"
            ) as response:
                if response.status_code == 200:
                    data = response.json()
                    workspace_count = len(data.get("data", []))
                    response.success()
                    logger.debug(f"Listed {workspace_count} workspaces")
                else:
                    response.failure(f"Failed to list workspaces: {response.status_code}")
                    logger.error(f"Failed to list workspaces: {response.text}")
        
        except Exception as e:
            logger.error(f"Exception listing workspaces: {e}")
            raise
    
    @task(3)
    def get_workspace_details(self):
        """
        Get details of a previously created workspace.
        
        Weight: 3 (lower frequency)
        """
        if not self.created_workspaces:
            # Skip if no workspaces created yet
            return
        
        # Get a random workspace from our created list
        workspace_id = self.created_workspaces[0]
        
        try:
            with self.client.get(
                f"/api/v2/workspaces/{workspace_id}",
                headers={
                    "Authorization": f"Bearer {self.tfe_client.token}",
                    "Content-Type": "application/vnd.api+json"
                },
                verify=self.tfe_client.verify_ssl,
                catch_response=True,
                name="/api/v2/workspaces/:id [GET]"
            ) as response:
                if response.status_code == 200:
                    response.success()
                    logger.debug(f"Retrieved workspace details: {workspace_id}")
                elif response.status_code == 404:
                    # Workspace might have been deleted - not a failure
                    response.success()
                    self.created_workspaces.remove(workspace_id)
                    logger.debug(f"Workspace not found (deleted?): {workspace_id}")
                else:
                    response.failure(f"Failed to get workspace: {response.status_code}")
                    logger.error(f"Failed to get workspace {workspace_id}: {response.text}")
        
        except Exception as e:
            logger.error(f"Exception getting workspace details: {e}")
            raise
    
    @task(2)
    def delete_workspace(self):
        """
        Delete a previously created workspace.
        
        Weight: 2 (lower frequency - cleanup operation)
        """
        if not self.created_workspaces:
            # Skip if no workspaces to delete
            return
        
        # Delete the oldest workspace
        workspace_id = self.created_workspaces.pop(0)
        
        try:
            with self.client.delete(
                f"/api/v2/workspaces/{workspace_id}",
                headers={
                    "Authorization": f"Bearer {self.tfe_client.token}",
                    "Content-Type": "application/vnd.api+json"
                },
                verify=self.tfe_client.verify_ssl,
                catch_response=True,
                name="/api/v2/workspaces/:id [DELETE]"
            ) as response:
                if response.status_code == 204:
                    response.success()
                    logger.debug(f"Deleted workspace: {workspace_id}")
                elif response.status_code == 404:
                    # Already deleted - not a failure
                    response.success()
                    logger.debug(f"Workspace already deleted: {workspace_id}")
                else:
                    response.failure(f"Failed to delete workspace: {response.status_code}")
                    logger.error(f"Failed to delete workspace {workspace_id}: {response.text}")
        
        except Exception as e:
            logger.error(f"Exception deleting workspace: {e}")
            raise


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """
    Event handler called when the test starts.
    """
    logger.info("=" * 80)
    logger.info("TFE Workspace Operations Load Test Starting")
    logger.info("=" * 80)
    logger.info(f"Target: {os.getenv('TFE_HOSTNAME', 'tfe.localdemo.me')}")
    logger.info(f"Organization: {os.getenv('TFE_ORGANIZATION', 'NOT SET')}")
    logger.info(f"Cleanup Enabled: {os.getenv('CLEANUP_WORKSPACES', 'true')}")
    logger.info("=" * 80)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """
    Event handler called when the test stops.
    """
    logger.info("=" * 80)
    logger.info("TFE Workspace Operations Load Test Completed")
    logger.info("=" * 80)


# For running directly with locust CLI
if __name__ == "__main__":
    import subprocess
    import sys
    
    # Run with locust
    cmd = [
        "locust",
        "-f", __file__,
        "--host", f"https://{os.getenv('TFE_HOSTNAME', 'tfe.localdemo.me')}",
        "--users", "10",
        "--spawn-rate", "2",
        "--run-time", "5m",
        "--html", "workspace_operations_report.html"
    ]
    
    print("Running Locust with command:")
    print(" ".join(cmd))
    print("\nPress Ctrl+C to stop the test")
    print("=" * 80)
    
    subprocess.run(cmd)
