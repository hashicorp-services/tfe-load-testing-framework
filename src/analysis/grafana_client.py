"""
Grafana API Client for fetching metrics during load test analysis.

This module provides a client for interacting with Grafana's API to fetch
Prometheus metrics and dashboard data for load test analysis.
"""

import os
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class GrafanaClient:
    """Client for interacting with Grafana API."""
    
    def __init__(
        self,
        url: str = "http://localhost:3000",
        api_key: Optional[str] = None,
        verify_ssl: bool = True
    ):
        """
        Initialize Grafana client.
        
        Args:
            url: Grafana base URL (default: http://localhost:3000)
            api_key: Grafana API key (if None, reads from GRAFANA_API_KEY env var)
            verify_ssl: Whether to verify SSL certificates
        """
        self.url = url.rstrip('/')
        self.api_key = api_key or os.getenv('GRAFANA_API_KEY')
        self.verify_ssl = verify_ssl
        
        self.session = requests.Session()
        if self.api_key:
            self.session.headers.update({
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            })
        
        # Disable SSL warnings if verify_ssl is False
        if not verify_ssl:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    def test_connection(self) -> bool:
        """
        Test connection to Grafana.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            response = self.session.get(
                f"{self.url}/api/health",
                verify=self.verify_ssl,
                timeout=5
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to connect to Grafana: {e}")
            return False
    
    def query_prometheus(
        self,
        query: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        step: str = "15s"
    ) -> Dict[str, Any]:
        """
        Query Prometheus via Grafana's datasource proxy.
        
        Args:
            query: PromQL query string
            start_time: Start time for range query (default: 5 minutes ago)
            end_time: End time for range query (default: now)
            step: Query resolution step (default: 15s)
        
        Returns:
            Query result as dictionary
        """
        if end_time is None:
            end_time = datetime.utcnow()
        if start_time is None:
            start_time = end_time - timedelta(minutes=5)
        
        # Get Prometheus datasource UID
        datasource_uid = self._get_prometheus_datasource_uid()
        if not datasource_uid:
            logger.error("Could not find Prometheus datasource")
            return {}
        
        # Query Prometheus via Grafana proxy
        url = f"{self.url}/api/datasources/proxy/uid/{datasource_uid}/api/v1/query_range"
        
        params = {
            'query': query,
            'start': int(start_time.timestamp()),
            'end': int(end_time.timestamp()),
            'step': step
        }
        
        try:
            response = self.session.get(
                url,
                params=params,
                verify=self.verify_ssl,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to query Prometheus: {e}")
            return {}
    
    def query_prometheus_instant(self, query: str) -> Dict[str, Any]:
        """
        Execute instant Prometheus query (current value).
        
        Args:
            query: PromQL query string
        
        Returns:
            Query result as dictionary
        """
        datasource_uid = self._get_prometheus_datasource_uid()
        if not datasource_uid:
            logger.error("Could not find Prometheus datasource")
            return {}
        
        url = f"{self.url}/api/datasources/proxy/uid/{datasource_uid}/api/v1/query"
        
        params = {'query': query}
        
        try:
            response = self.session.get(
                url,
                params=params,
                verify=self.verify_ssl,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to query Prometheus: {e}")
            return {}
    
    def get_metric_value(self, query: str) -> Optional[float]:
        """
        Get single metric value from instant query.
        
        Args:
            query: PromQL query string
        
        Returns:
            Metric value as float, or None if query failed
        """
        result = self.query_prometheus_instant(query)
        
        if result.get('status') == 'success':
            data = result.get('data', {})
            results = data.get('result', [])
            
            if results and len(results) > 0:
                value = results[0].get('value', [])
                if len(value) > 1:
                    return float(value[1])
        
        return None
    
    def get_metric_range(
        self,
        query: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Get metric values over time range.
        
        Args:
            query: PromQL query string
            start_time: Start time (default: 5 minutes ago)
            end_time: End time (default: now)
        
        Returns:
            List of {timestamp, value} dictionaries
        """
        result = self.query_prometheus(query, start_time, end_time)
        
        if result.get('status') == 'success':
            data = result.get('data', {})
            results = data.get('result', [])
            
            if results and len(results) > 0:
                values = results[0].get('values', [])
                return [
                    {
                        'timestamp': datetime.fromtimestamp(v[0]),
                        'value': float(v[1])
                    }
                    for v in values
                ]
        
        return []
    
    def get_tfe_metrics(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Fetch common TFE metrics for analysis.
        
        Args:
            start_time: Start time for metrics (default: 5 minutes ago)
            end_time: End time for metrics (default: now)
        
        Returns:
            Dictionary of metric names to values/ranges
        """
        metrics = {}
        
        # Current values (instant queries)
        instant_queries = {
            'workspaces_total': 'tfe_workspaces_total',
            'workspaces_locked': 'tfe_workspaces_locked',
            'run_queue_depth': 'tfe_run_queue_depth',
            'db_connections': 'pg_stat_database_numbackends{datname="tfe"}',
        }
        
        for name, query in instant_queries.items():
            value = self.get_metric_value(query)
            if value is not None:
                metrics[name] = value
        
        # Range queries (over time)
        range_queries = {
            'api_request_duration_p95': 'histogram_quantile(0.95, rate(tfe_api_request_duration_seconds_bucket[1m]))',
            'api_request_duration_p50': 'histogram_quantile(0.50, rate(tfe_api_request_duration_seconds_bucket[1m]))',
            'api_error_rate': 'rate(tfe_api_errors_total[1m])',
            'db_transaction_rate': 'rate(pg_stat_database_xact_commit{datname="tfe"}[1m])',
        }
        
        for name, query in range_queries.items():
            values = self.get_metric_range(query, start_time, end_time)
            if values:
                # Calculate statistics
                value_list = [v['value'] for v in values]
                metrics[f"{name}_avg"] = sum(value_list) / len(value_list)
                metrics[f"{name}_max"] = max(value_list)
                metrics[f"{name}_min"] = min(value_list)
                metrics[f"{name}_current"] = value_list[-1] if value_list else None
        
        return metrics
    
    def _get_prometheus_datasource_uid(self) -> Optional[str]:
        """
        Get Prometheus datasource UID.
        
        Returns:
            Datasource UID or None if not found
        """
        try:
            response = self.session.get(
                f"{self.url}/api/datasources",
                verify=self.verify_ssl,
                timeout=10
            )
            response.raise_for_status()
            
            datasources = response.json()
            for ds in datasources:
                if ds.get('type') == 'prometheus':
                    return ds.get('uid')
            
            return None
        except Exception as e:
            logger.error(f"Failed to get datasources: {e}")
            return None
    
    def get_dashboard_info(self, dashboard_uid: str) -> Dict[str, Any]:
        """
        Get dashboard information.
        
        Args:
            dashboard_uid: Dashboard UID
        
        Returns:
            Dashboard information
        """
        try:
            response = self.session.get(
                f"{self.url}/api/dashboards/uid/{dashboard_uid}",
                verify=self.verify_ssl,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get dashboard info: {e}")
            return {}


def main():
    """Test Grafana client."""
    import sys
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create client
    client = GrafanaClient()
    
    # Test connection
    print("Testing Grafana connection...")
    if client.test_connection():
        print("✅ Connected to Grafana")
    else:
        print("❌ Failed to connect to Grafana")
        sys.exit(1)
    
    # Fetch TFE metrics
    print("\nFetching TFE metrics...")
    metrics = client.get_tfe_metrics()
    
    if metrics:
        print("\n📊 Current TFE Metrics:")
        for name, value in metrics.items():
            if isinstance(value, float):
                print(f"  {name}: {value:.2f}")
            else:
                print(f"  {name}: {value}")
    else:
        print("⚠️  No metrics available")


if __name__ == '__main__':
    main()
