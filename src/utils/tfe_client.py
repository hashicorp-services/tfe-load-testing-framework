"""
TFE API Client Wrapper

Provides a simplified interface for interacting with Terraform Enterprise API
for load testing purposes.
"""

import os
import time
import logging
from typing import Optional, Dict, Any, List
from urllib.parse import urljoin
import warnings

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib3.exceptions import InsecureRequestWarning

logger = logging.getLogger(__name__)


class TFEClient:
    """
    Terraform Enterprise API client wrapper.
    
    Handles authentication, request formatting, and common API operations
    for load testing scenarios.
    """
    
    def __init__(
        self,
        hostname: str,
        token: str,
        organization: str,
        verify_ssl: bool = True,
        timeout: int = 30,
        max_retries: int = 3
    ):
        """
        Initialize TFE client.
        
        Args:
            hostname: TFE hostname (e.g., 'app.terraform.io' or 'tfe.example.com')
            token: TFE API token
            organization: Default organization name
            verify_ssl: Whether to verify SSL certificates
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for failed requests
        """
        self.hostname = hostname.rstrip('/')
        self.token = token
        self.organization = organization
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        
        # Suppress SSL warnings when verify_ssl is False
        if not verify_ssl:
            warnings.filterwarnings('ignore', category=InsecureRequestWarning)
        
        # Build base URL
        if not self.hostname.startswith(('http://', 'https://')):
            self.base_url = f"https://{self.hostname}"
        else:
            self.base_url = self.hostname
        
        self.api_url = urljoin(self.base_url, '/api/v2/')
        
        # Configure session with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST", "PUT", "PATCH"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set default headers
        self.session.headers.update({
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/vnd.api+json",
            "Accept": "application/vnd.api+json"
        })
    
    def _make_request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> requests.Response:
        """
        Make an API request.
        
        Args:
            method: HTTP method (GET, POST, PATCH, DELETE)
            endpoint: API endpoint (relative to /api/v2/)
            json_data: JSON payload for request body
            params: Query parameters
            **kwargs: Additional arguments passed to requests
        
        Returns:
            Response object
        """
        url = urljoin(self.api_url, endpoint.lstrip('/'))
        
        response = self.session.request(
            method=method,
            url=url,
            json=json_data,
            params=params,
            verify=self.verify_ssl,
            timeout=self.timeout,
            **kwargs
        )
        
        # Log rate limit information if present
        if 'X-RateLimit-Remaining' in response.headers:
            remaining = response.headers['X-RateLimit-Remaining']
            logger.debug(f"Rate limit remaining: {remaining}")
        
        return response
    
    # Organization Operations
    
    def create_organization(self, name: str, email: str) -> Dict[str, Any]:
        """
        Create a new organization.
        
        Args:
            name: Organization name
            email: Admin email address
        
        Returns:
            Organization data
        """
        payload = {
            "data": {
                "type": "organizations",
                "attributes": {
                    "name": name,
                    "email": email
                }
            }
        }
        
        response = self._make_request("POST", "organizations", json_data=payload)
        response.raise_for_status()
        return response.json()
    
    def get_organization(self, name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get organization details.
        
        Args:
            name: Organization name (defaults to client's organization)
        
        Returns:
            Organization data
        """
        org_name = name or self.organization
        response = self._make_request("GET", f"organizations/{org_name}")
        response.raise_for_status()
        return response.json()
    
    def delete_organization(self, name: Optional[str] = None) -> None:
        """
        Delete an organization.
        
        Args:
            name: Organization name (defaults to client's organization)
        """
        org_name = name or self.organization
        response = self._make_request("DELETE", f"organizations/{org_name}")
        response.raise_for_status()
    
    # Workspace Operations
    
    def create_workspace(
        self,
        name: str,
        auto_apply: bool = False,
        queue_all_runs: bool = True,
        terraform_version: Optional[str] = None,
        working_directory: Optional[str] = None,
        organization: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new workspace.
        
        Args:
            name: Workspace name
            auto_apply: Whether to automatically apply successful plans
            queue_all_runs: Whether to queue all runs
            terraform_version: Terraform version to use
            working_directory: Working directory for Terraform operations
            organization: Organization name (defaults to client's organization)
        
        Returns:
            Workspace data
        """
        org_name = organization or self.organization
        
        attributes = {
            "name": name,
            "auto-apply": auto_apply,
            "queue-all-runs": queue_all_runs
        }
        
        if terraform_version:
            attributes["terraform-version"] = terraform_version
        if working_directory:
            attributes["working-directory"] = working_directory
        
        payload = {
            "data": {
                "type": "workspaces",
                "attributes": attributes
            }
        }
        
        response = self._make_request(
            "POST",
            f"organizations/{org_name}/workspaces",
            json_data=payload
        )
        response.raise_for_status()
        return response.json()
    
    def get_workspace(self, workspace_id: str) -> Dict[str, Any]:
        """
        Get workspace details.
        
        Args:
            workspace_id: Workspace ID
        
        Returns:
            Workspace data
        """
        response = self._make_request("GET", f"workspaces/{workspace_id}")
        response.raise_for_status()
        return response.json()
    
    def list_workspaces(
        self,
        organization: Optional[str] = None,
        page_size: int = 20,
        page_number: int = 1
    ) -> Dict[str, Any]:
        """
        List workspaces in an organization.
        
        Args:
            organization: Organization name (defaults to client's organization)
            page_size: Number of workspaces per page
            page_number: Page number to retrieve
        
        Returns:
            Paginated workspace list
        """
        org_name = organization or self.organization
        params = {
            "page[size]": page_size,
            "page[number]": page_number
        }
        
        response = self._make_request(
            "GET",
            f"organizations/{org_name}/workspaces",
            params=params
        )
        response.raise_for_status()
        return response.json()
    
    def delete_workspace(self, workspace_id: str) -> None:
        """
        Delete a workspace.
        
        Args:
            workspace_id: Workspace ID
        """
        response = self._make_request("DELETE", f"workspaces/{workspace_id}")
        response.raise_for_status()
    
    def update_workspace(
        self,
        workspace_id: str,
        **attributes
    ) -> Dict[str, Any]:
        """
        Update workspace attributes.
        
        Args:
            workspace_id: Workspace ID
            **attributes: Workspace attributes to update
        
        Returns:
            Updated workspace data
        """
        payload = {
            "data": {
                "type": "workspaces",
                "attributes": attributes
            }
        }
        
        response = self._make_request(
            "PATCH",
            f"workspaces/{workspace_id}",
            json_data=payload
        )
        response.raise_for_status()
        return response.json()
    
    def lock_workspace(
        self,
        workspace_id: str,
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Lock a workspace to prevent concurrent state modifications.
        
        Args:
            workspace_id: Workspace ID
            reason: Optional reason for locking
        
        Returns:
            Updated workspace data
        """
        payload = {
            "reason": reason or "Load testing state operations"
        }
        
        response = self._make_request(
            "POST",
            f"workspaces/{workspace_id}/actions/lock",
            json_data=payload
        )
        response.raise_for_status()
        return response.json()
    
    def unlock_workspace(
        self,
        workspace_id: str
    ) -> Dict[str, Any]:
        """
        Unlock a workspace to allow state modifications.
        
        Args:
            workspace_id: Workspace ID
        
        Returns:
            Updated workspace data
        """
        response = self._make_request(
            "POST",
            f"workspaces/{workspace_id}/actions/unlock"
        )
        response.raise_for_status()
        return response.json()
    
    def force_unlock_workspace(
        self,
        workspace_id: str
    ) -> Dict[str, Any]:
        """
        Force unlock a workspace (admin operation).
        
        Args:
            workspace_id: Workspace ID
        
        Returns:
            Updated workspace data
        """
        response = self._make_request(
            "POST",
            f"workspaces/{workspace_id}/actions/force-unlock"
        )
        response.raise_for_status()
        return response.json()
    
    # Configuration Version Operations
    
    def create_configuration_version(
        self,
        workspace_id: str,
        auto_queue_runs: bool = True,
        speculative: bool = False
    ) -> Dict[str, Any]:
        """
        Create a configuration version.
        
        Args:
            workspace_id: Workspace ID
            auto_queue_runs: Whether to automatically queue runs
            speculative: Whether this is a speculative plan
        
        Returns:
            Configuration version data with upload URL
        """
        payload = {
            "data": {
                "type": "configuration-versions",
                "attributes": {
                    "auto-queue-runs": auto_queue_runs,
                    "speculative": speculative
                }
            }
        }
        
        response = self._make_request(
            "POST",
            f"workspaces/{workspace_id}/configuration-versions",
            json_data=payload
        )
        response.raise_for_status()
        return response.json()
    
    def upload_configuration(
        self,
        upload_url: str,
        config_data
    ) -> None:
        """
        Upload configuration tarball to presigned URL.
        
        Args:
            upload_url: Presigned upload URL from configuration version
            config_data: Either path to configuration tarball (.tar.gz) or bytes data
        """
        if isinstance(config_data, (str, bytes, bytearray)):
            if isinstance(config_data, str):
                # File path provided
                with open(config_data, 'rb') as f:
                    data = f.read()
            else:
                # Bytes data provided
                data = config_data
            
            response = requests.put(
                upload_url,
                data=data,
                headers={"Content-Type": "application/octet-stream"},
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            response.raise_for_status()
        else:
            raise TypeError(f"config_data must be str (file path) or bytes, got {type(config_data)}")
    
    def get_configuration_version(self, cv_id: str) -> Dict[str, Any]:
        """
        Get configuration version details.
        
        Args:
            cv_id: Configuration version ID
        
        Returns:
            Configuration version data
        """
        response = self._make_request("GET", f"configuration-versions/{cv_id}")
        response.raise_for_status()
        return response.json()
    
    # Run Operations
    
    def create_run(
        self,
        workspace_id: str,
        message: Optional[str] = None,
        auto_apply: Optional[bool] = None,
        is_destroy: bool = False
    ) -> Dict[str, Any]:
        """
        Create a new run.
        
        Args:
            workspace_id: Workspace ID
            message: Optional message for the run
            auto_apply: Override workspace auto-apply setting
            is_destroy: Whether this is a destroy run
        
        Returns:
            Run data
        """
        attributes = {"is-destroy": is_destroy}
        
        if message:
            attributes["message"] = message
        if auto_apply is not None:
            attributes["auto-apply"] = auto_apply
        
        payload = {
            "data": {
                "type": "runs",
                "attributes": attributes,
                "relationships": {
                    "workspace": {
                        "data": {
                            "type": "workspaces",
                            "id": workspace_id
                        }
                    }
                }
            }
        }
        
        response = self._make_request("POST", "runs", json_data=payload)
        response.raise_for_status()
        return response.json()
    
    def get_run(self, run_id: str) -> Dict[str, Any]:
        """
        Get run details.
        
        Args:
            run_id: Run ID
        
        Returns:
            Run data
        """
        response = self._make_request("GET", f"runs/{run_id}")
        response.raise_for_status()
        return response.json()
    
    def cancel_run(self, run_id: str, comment: Optional[str] = None) -> None:
        """
        Cancel a run.
        
        Args:
            run_id: Run ID
            comment: Optional cancellation comment
        """
        payload = {}
        if comment:
            payload["comment"] = comment
        
        response = self._make_request(
            "POST",
            f"runs/{run_id}/actions/cancel",
            json_data=payload
        )
        response.raise_for_status()
    
    def poll_run_until_completion(
        self,
        run_id: str,
        timeout: int = 300,
        poll_interval: int = 10,
        terminal_states: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Poll run status until it reaches a terminal state.
        
        Args:
            run_id: Run ID
            timeout: Maximum time to wait in seconds
            poll_interval: Time between polls in seconds
            terminal_states: List of terminal states (defaults to standard terminal states)
        
        Returns:
            Final run data
        
        Raises:
            TimeoutError: If run doesn't complete within timeout
        """
        if terminal_states is None:
            terminal_states = [
                "applied",
                "planned_and_finished",
                "errored",
                "canceled",
                "discarded",
                "force_canceled"
            ]
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            run_data = self.get_run(run_id)
            status = run_data["data"]["attributes"]["status"]
            
            logger.debug(f"Run {run_id} status: {status}")
            
            if status in terminal_states:
                return run_data
            
            time.sleep(poll_interval)
        
        raise TimeoutError(f"Run {run_id} did not complete within {timeout} seconds")
    
    # Variable Operations
    
    def create_variable(
        self,
        workspace_id: str,
        key: str,
        value: str,
        category: str = "terraform",
        sensitive: bool = False,
        hcl: bool = False,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a workspace variable.
        
        Args:
            workspace_id: Workspace ID
            key: Variable key
            value: Variable value
            category: Variable category ('terraform' or 'env')
            sensitive: Whether the variable is sensitive
            hcl: Whether the value is HCL
            description: Optional variable description
        
        Returns:
            Variable data
        """
        attributes = {
            "key": key,
            "value": value,
            "category": category,
            "sensitive": sensitive,
            "hcl": hcl
        }
        
        if description:
            attributes["description"] = description
        
        payload = {
            "data": {
                "type": "vars",
                "attributes": attributes,
                "relationships": {
                    "workspace": {
                        "data": {
                            "type": "workspaces",
                            "id": workspace_id
                        }
                    }
                }
            }
        }
        
        response = self._make_request("POST", "vars", json_data=payload)
        response.raise_for_status()
        return response.json()
    
    def list_variables(self, workspace_id: str) -> Dict[str, Any]:
        """
        List workspace variables.
        
        Args:
            workspace_id: Workspace ID
        
        Returns:
            Variable list
        """
        response = self._make_request(
            "GET",
            f"workspaces/{workspace_id}/vars"
        )
        response.raise_for_status()
        return response.json()
    
    def delete_variable(self, variable_id: str) -> None:
        """
        Delete a variable.
        
        Args:
            variable_id: Variable ID
        """
        response = self._make_request("DELETE", f"vars/{variable_id}")
        response.raise_for_status()
    
    # State Version Operations
    
    def create_state_version(
        self,
        workspace_id: str,
        state: str,
        md5: Optional[str] = None,
        serial: Optional[int] = None,
        lineage: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new state version by uploading state data.
        
        Args:
            workspace_id: Workspace ID
            state: JSON-encoded state file content
            md5: Optional MD5 hash of the state file
            serial: Optional state serial number (extracted from state if not provided)
            lineage: Optional state lineage (extracted from state if not provided)
        
        Returns:
            State version data
        """
        import hashlib
        import base64
        import json as json_module
        
        # Parse state to extract serial and lineage if not provided
        try:
            state_data = json_module.loads(state)
            if serial is None:
                serial = state_data.get('serial', 0)
            if lineage is None:
                lineage = state_data.get('lineage')
        except (json_module.JSONDecodeError, KeyError):
            # If parsing fails, use defaults
            if serial is None:
                serial = 0
        
        # Calculate MD5 of the raw state (before base64 encoding) if not provided
        # TFE expects MD5 in hexadecimal format, not base64
        if md5 is None:
            md5 = hashlib.md5(state.encode('utf-8')).hexdigest()
        
        # Base64 encode the state for transmission
        state_b64 = base64.b64encode(state.encode('utf-8')).decode('utf-8')
        
        # Build payload with required serial field
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
        
        # Add optional lineage if available
        if lineage is not None:
            payload["data"]["attributes"]["lineage"] = lineage
        
        response = self._make_request(
            "POST",
            f"workspaces/{workspace_id}/state-versions",
            json_data=payload
        )
        response.raise_for_status()
        return response.json()
    
    def list_state_versions(
        self,
        workspace_id: str,
        page_size: int = 20,
        page_number: int = 1
    ) -> Dict[str, Any]:
        """
        List state versions for a workspace.
        
        Args:
            workspace_id: Workspace ID
            page_size: Number of state versions per page
            page_number: Page number to retrieve
        
        Returns:
            Paginated state version list
        """
        # Get workspace details to extract name and organization
        workspace = self.get_workspace(workspace_id)
        workspace_name = workspace['data']['attributes']['name']
        
        # Use the organization from the workspace or fall back to client's organization
        org_name = self.organization
        
        params = {
            "filter[workspace][name]": workspace_name,
            "filter[organization][name]": org_name,
            "page[size]": page_size,
            "page[number]": page_number
        }
        
        response = self._make_request(
            "GET",
            "state-versions",
            params=params
        )
        response.raise_for_status()
        return response.json()
    
    def get_state_version(self, state_version_id: str) -> Dict[str, Any]:
        """
        Get details of a specific state version.
        
        Args:
            state_version_id: State version ID
        
        Returns:
            State version data
        """
        response = self._make_request(
            "GET",
            f"state-versions/{state_version_id}"
        )
        response.raise_for_status()
        return response.json()
    
    def get_current_state_version(self, workspace_id: str) -> Dict[str, Any]:
        """
        Get current state version for a workspace.
        
        Args:
            workspace_id: Workspace ID
        
        Returns:
            State version data
        """
        response = self._make_request(
            "GET",
            f"workspaces/{workspace_id}/current-state-version"
        )
        response.raise_for_status()
        return response.json()
    
    def download_state(self, download_url: str) -> bytes:
        """
        Download state file from presigned URL.
        
        Args:
            download_url: Presigned download URL
        
        Returns:
            State file content
        """
        response = requests.get(
            download_url,
            verify=self.verify_ssl,
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.content
