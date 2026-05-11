#!/usr/bin/env python3
"""
TFE Metrics Exporter for Prometheus

Exports metrics from Terraform Enterprise API for monitoring during load tests.
"""

import os
import time
import logging
from typing import Dict, List
import requests
from prometheus_client import start_http_server, Gauge, Counter, Histogram
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration from environment
TFE_HOSTNAME = os.getenv('TFE_HOSTNAME', 'tfe.localdemo.me')
TFE_INTERNAL_HOSTNAME = os.getenv('TFE_INTERNAL_HOSTNAME', 'tfe')
TFE_INTERNAL_PORT = os.getenv('TFE_INTERNAL_PORT', '8443')
TFE_TOKEN = os.getenv('TFE_TOKEN', '')
TFE_ORGANIZATION = os.getenv('TFE_ORGANIZATION', '')
EXPORTER_PORT = int(os.getenv('EXPORTER_PORT', '9101'))
SCRAPE_INTERVAL = int(os.getenv('SCRAPE_INTERVAL', '15'))

# TFE API base URL - use internal hostname when running in container network
TFE_API_BASE = f'https://{TFE_INTERNAL_HOSTNAME}:{TFE_INTERNAL_PORT}/api/v2'

# Prometheus metrics
# Workspace metrics
workspace_count = Gauge('tfe_workspaces_total', 'Total number of workspaces', ['organization'])
workspace_locked = Gauge('tfe_workspaces_locked', 'Number of locked workspaces', ['organization'])

# Run metrics
run_count = Gauge('tfe_runs_total', 'Total number of runs', ['organization', 'status'])
run_queue_depth = Gauge('tfe_run_queue_depth', 'Number of runs in queue', ['organization'])
run_duration = Histogram('tfe_run_duration_seconds', 'Run duration in seconds', ['organization', 'status'])

# API metrics
api_request_duration = Histogram('tfe_api_request_duration_seconds', 'API request duration', ['endpoint', 'method'])
api_request_total = Counter('tfe_api_requests_total', 'Total API requests', ['endpoint', 'method', 'status'])
api_errors_total = Counter('tfe_api_errors_total', 'Total API errors', ['endpoint', 'error_type'])

# State version metrics
state_version_count = Gauge('tfe_state_versions_total', 'Total state versions', ['organization'])

# Organization metrics
org_user_count = Gauge('tfe_organization_users', 'Number of users in organization', ['organization'])
org_team_count = Gauge('tfe_organization_teams', 'Number of teams in organization', ['organization'])


class TFEClient:
    """Client for interacting with TFE API"""
    
    def __init__(self, hostname: str, token: str, port: str = '443'):
        self.hostname = hostname
        self.port = port
        self.base_url = f'https://{hostname}:{port}/api/v2'
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/vnd.api+json',
            'Host': TFE_HOSTNAME  # Use external hostname in Host header to avoid redirects
        })
        
        # Configure retries
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount('https://', adapter)
        self.session.verify = False  # For local dev with self-signed certs
        
        # Suppress SSL warnings for local dev
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict:
        """Make API request with metrics tracking"""
        url = f'{self.base_url}/{endpoint}'
        
        start_time = time.time()
        try:
            # Disable redirects to prevent TFE from redirecting to external hostname
            response = self.session.request(method, url, allow_redirects=False, **kwargs)
            duration = time.time() - start_time
            
            # Log response details for debugging
            logger.info(f"Response status: {response.status_code}, URL: {url}")
            
            # Record metrics
            api_request_duration.labels(endpoint=endpoint, method=method).observe(duration)
            api_request_total.labels(endpoint=endpoint, method=method, status=response.status_code).inc()
            
            # Handle redirects manually - TFE API shouldn't redirect, but if it does, log it
            if 300 <= response.status_code < 400:
                redirect_url = response.headers.get('Location', 'unknown')
                logger.warning(f"TFE API returned redirect {response.status_code} to {redirect_url}. This is unexpected for API calls.")
                # Don't follow the redirect, return empty dict
                return {}
            
            response.raise_for_status()
            
            # Check if response has content before parsing JSON
            if not response.content:
                logger.warning(f"Empty response from {url}, status: {response.status_code}")
                return {}
            
            return response.json()
        except requests.exceptions.RequestException as e:
            duration = time.time() - start_time
            api_request_duration.labels(endpoint=endpoint, method=method).observe(duration)
            api_errors_total.labels(endpoint=endpoint, error_type=type(e).__name__).inc()
            logger.error(f"API request failed: {endpoint} - {e}")
            raise
    
    def get_workspaces(self, organization: str) -> List[Dict]:
        """Get all workspaces for an organization"""
        workspaces = []
        page = 1
        
        while True:
            data = self._make_request(
                'GET',
                f'organizations/{organization}/workspaces',
                params={'page[number]': page, 'page[size]': 100}
            )
            workspaces.extend(data.get('data', []))
            
            # Check if there are more pages
            if not data.get('data') or len(data.get('data', [])) < 100:
                break
            page += 1
        
        return workspaces
    
    def get_runs(self, organization: str) -> List[Dict]:
        """Get recent runs for an organization"""
        try:
            data = self._make_request(
                'GET',
                f'organizations/{organization}/runs',
                params={'page[size]': 100}
            )
            return data.get('data', [])
        except Exception as e:
            logger.warning(f"Failed to get runs: {e}")
            return []
    
    def get_organization(self, organization: str) -> Dict:
        """Get organization details"""
        data = self._make_request('GET', f'organizations/{organization}')
        return data.get('data', {})


def collect_metrics(client: TFEClient, organization: str):
    """Collect metrics from TFE"""
    try:
        logger.info(f"Collecting metrics for organization: {organization}")
        
        # Get workspaces
        workspaces = client.get_workspaces(organization)
        workspace_count.labels(organization=organization).set(len(workspaces))
        
        locked_count = sum(1 for ws in workspaces if ws.get('attributes', {}).get('locked', False))
        workspace_locked.labels(organization=organization).set(locked_count)
        
        logger.info(f"Workspaces: {len(workspaces)} total, {locked_count} locked")
        
        # Get runs
        runs = client.get_runs(organization)
        
        # Count runs by status
        status_counts = {}
        queued_count = 0
        
        for run in runs:
            status = run.get('attributes', {}).get('status', 'unknown')
            status_counts[status] = status_counts.get(status, 0) + 1
            
            if status in ['pending', 'plan_queued', 'apply_queued']:
                queued_count += 1
        
        # Update run metrics
        for status, count in status_counts.items():
            run_count.labels(organization=organization, status=status).set(count)
        
        run_queue_depth.labels(organization=organization).set(queued_count)
        
        logger.info(f"Runs: {len(runs)} total, {queued_count} queued")
        logger.info(f"Run status breakdown: {status_counts}")
        
        # Get organization details
        try:
            org_data = client.get_organization(organization)
            # Note: User and team counts may require additional API calls
            # This is a placeholder - adjust based on actual TFE API capabilities
        except Exception as e:
            logger.warning(f"Failed to get organization details: {e}")
        
    except Exception as e:
        logger.error(f"Error collecting metrics: {e}", exc_info=True)


def main():
    """Main exporter loop"""
    logger.info(f"Starting TFE Exporter on port {EXPORTER_PORT}")
    logger.info(f"TFE Hostname (external): {TFE_HOSTNAME}")
    logger.info(f"TFE Hostname (internal): {TFE_INTERNAL_HOSTNAME}:{TFE_INTERNAL_PORT}")
    logger.info(f"Organization: {TFE_ORGANIZATION}")
    logger.info(f"Scrape interval: {SCRAPE_INTERVAL}s")
    
    if not TFE_TOKEN:
        logger.error("TFE_TOKEN environment variable is required")
        return
    
    if not TFE_ORGANIZATION:
        logger.warning("TFE_ORGANIZATION not set, some metrics may not be available")
    
    # Start Prometheus HTTP server
    start_http_server(EXPORTER_PORT)
    logger.info(f"Metrics available at http://localhost:{EXPORTER_PORT}/metrics")
    
    # Initialize TFE client with internal hostname and port
    logger.info(f"Connecting to TFE at https://{TFE_INTERNAL_HOSTNAME}:{TFE_INTERNAL_PORT}/api/v2")
    client = TFEClient(TFE_INTERNAL_HOSTNAME, TFE_TOKEN, TFE_INTERNAL_PORT)
    
    # Main collection loop
    while True:
        try:
            if TFE_ORGANIZATION:
                collect_metrics(client, TFE_ORGANIZATION)
            time.sleep(SCRAPE_INTERVAL)
        except KeyboardInterrupt:
            logger.info("Shutting down exporter")
            break
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}", exc_info=True)
            time.sleep(SCRAPE_INTERVAL)


if __name__ == '__main__':
    main()
