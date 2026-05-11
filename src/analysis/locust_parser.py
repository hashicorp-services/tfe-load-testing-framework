"""
Locust Results Parser for load test analysis.

This module parses Locust statistics files (CSV, JSON) and extracts
metrics for analysis and reporting.
"""

import csv
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class RequestStats:
    """Statistics for a single request type."""
    name: str
    method: str
    num_requests: int
    num_failures: int
    median_response_time: float
    average_response_time: float
    min_response_time: float
    max_response_time: float
    average_content_size: float
    requests_per_second: float
    failures_per_second: float
    percentile_50: float
    percentile_66: float
    percentile_75: float
    percentile_80: float
    percentile_90: float
    percentile_95: float
    percentile_98: float
    percentile_99: float
    percentile_99_9: float
    percentile_99_99: float
    percentile_100: float
    
    @property
    def error_rate(self) -> float:
        """Calculate error rate as percentage."""
        if self.num_requests == 0:
            return 0.0
        return (self.num_failures / self.num_requests) * 100
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        return 100.0 - self.error_rate


@dataclass
class LocustResults:
    """Complete Locust test results."""
    request_stats: List[RequestStats] = field(default_factory=list)
    aggregated_stats: Optional[RequestStats] = None
    failures: List[Dict[str, Any]] = field(default_factory=list)
    exceptions: List[Dict[str, Any]] = field(default_factory=list)
    
    @property
    def total_requests(self) -> int:
        """Total number of requests across all types."""
        return sum(stat.num_requests for stat in self.request_stats)
    
    @property
    def total_failures(self) -> int:
        """Total number of failures across all types."""
        return sum(stat.num_failures for stat in self.request_stats)
    
    @property
    def overall_error_rate(self) -> float:
        """Overall error rate as percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.total_failures / self.total_requests) * 100
    
    @property
    def overall_success_rate(self) -> float:
        """Overall success rate as percentage."""
        return 100.0 - self.overall_error_rate


class LocustParser:
    """Parser for Locust statistics files."""
    
    def __init__(self, stats_file: str):
        """
        Initialize parser.
        
        Args:
            stats_file: Path to Locust statistics file (CSV or JSON)
        """
        self.stats_file = Path(stats_file)
        if not self.stats_file.exists():
            raise FileNotFoundError(f"Stats file not found: {stats_file}")
    
    def parse(self) -> LocustResults:
        """
        Parse Locust statistics file.
        
        Returns:
            LocustResults object with parsed data
        """
        if self.stats_file.suffix == '.csv':
            return self._parse_csv()
        elif self.stats_file.suffix == '.json':
            return self._parse_json()
        else:
            raise ValueError(f"Unsupported file format: {self.stats_file.suffix}")
    
    def _parse_csv(self) -> LocustResults:
        """
        Parse Locust CSV statistics file.
        
        Returns:
            LocustResults object
        """
        results = LocustResults()
        
        with open(self.stats_file, 'r') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                # Skip empty rows
                if not row.get('Name'):
                    continue
                
                # Parse request stats
                try:
                    stats = RequestStats(
                        name=row['Name'],
                        method=row['Type'],
                        num_requests=int(row['Request Count']),
                        num_failures=int(row['Failure Count']),
                        median_response_time=float(row['Median Response Time']),
                        average_response_time=float(row['Average Response Time']),
                        min_response_time=float(row['Min Response Time']),
                        max_response_time=float(row['Max Response Time']),
                        average_content_size=float(row['Average Content Size']),
                        requests_per_second=float(row['Requests/s']),
                        failures_per_second=float(row.get('Failures/s', 0)),
                        percentile_50=float(row['50%']),
                        percentile_66=float(row['66%']),
                        percentile_75=float(row['75%']),
                        percentile_80=float(row['80%']),
                        percentile_90=float(row['90%']),
                        percentile_95=float(row['95%']),
                        percentile_98=float(row['98%']),
                        percentile_99=float(row['99%']),
                        percentile_99_9=float(row['99.9%']),
                        percentile_99_99=float(row['99.99%']),
                        percentile_100=float(row['100%'])
                    )
                    
                    # Check if this is aggregated stats
                    if stats.name == 'Aggregated':
                        results.aggregated_stats = stats
                    else:
                        results.request_stats.append(stats)
                
                except (KeyError, ValueError) as e:
                    logger.warning(f"Failed to parse row: {e}")
                    continue
        
        return results
    
    def _parse_json(self) -> LocustResults:
        """
        Parse Locust JSON statistics file.
        
        Returns:
            LocustResults object
        """
        results = LocustResults()
        
        with open(self.stats_file, 'r') as f:
            data = json.load(f)
        
        # Parse request stats
        for stat_data in data.get('stats', []):
            try:
                stats = RequestStats(
                    name=stat_data['name'],
                    method=stat_data['method'],
                    num_requests=stat_data['num_requests'],
                    num_failures=stat_data['num_failures'],
                    median_response_time=stat_data['median_response_time'],
                    average_response_time=stat_data['avg_response_time'],
                    min_response_time=stat_data['min_response_time'],
                    max_response_time=stat_data['max_response_time'],
                    average_content_size=stat_data['avg_content_length'],
                    requests_per_second=stat_data.get('current_rps', 0),
                    failures_per_second=stat_data.get('current_fail_per_sec', 0),
                    percentile_50=stat_data.get('response_times', {}).get('50', 0),
                    percentile_66=stat_data.get('response_times', {}).get('66', 0),
                    percentile_75=stat_data.get('response_times', {}).get('75', 0),
                    percentile_80=stat_data.get('response_times', {}).get('80', 0),
                    percentile_90=stat_data.get('response_times', {}).get('90', 0),
                    percentile_95=stat_data.get('response_times', {}).get('95', 0),
                    percentile_98=stat_data.get('response_times', {}).get('98', 0),
                    percentile_99=stat_data.get('response_times', {}).get('99', 0),
                    percentile_99_9=stat_data.get('response_times', {}).get('99.9', 0),
                    percentile_99_99=stat_data.get('response_times', {}).get('99.99', 0),
                    percentile_100=stat_data.get('response_times', {}).get('100', 0)
                )
                
                if stats.name == 'Aggregated':
                    results.aggregated_stats = stats
                else:
                    results.request_stats.append(stats)
            
            except (KeyError, ValueError) as e:
                logger.warning(f"Failed to parse stat: {e}")
                continue
        
        # Parse failures
        results.failures = data.get('failures', [])
        
        # Parse exceptions
        results.exceptions = data.get('exceptions', [])
        
        return results
    
    def get_operation_stats(self, operation_name: str) -> Optional[RequestStats]:
        """
        Get statistics for a specific operation.
        
        Args:
            operation_name: Name of the operation (e.g., "workspace_create")
        
        Returns:
            RequestStats for the operation, or None if not found
        """
        results = self.parse()
        
        for stats in results.request_stats:
            if operation_name.lower() in stats.name.lower():
                return stats
        
        return None


def main():
    """Test Locust parser."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python locust_parser.py <stats_file.csv>")
        sys.exit(1)
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Parse file
    parser = LocustParser(sys.argv[1])
    results = parser.parse()
    
    # Display results
    print(f"\n📊 Locust Test Results")
    print(f"{'='*80}")
    print(f"Total Requests: {results.total_requests}")
    print(f"Total Failures: {results.total_failures}")
    print(f"Success Rate: {results.overall_success_rate:.2f}%")
    print(f"Error Rate: {results.overall_error_rate:.2f}%")
    
    if results.aggregated_stats:
        print(f"\n📈 Aggregated Statistics")
        print(f"{'='*80}")
        stats = results.aggregated_stats
        print(f"Median Response Time: {stats.median_response_time:.0f}ms")
        print(f"Average Response Time: {stats.average_response_time:.0f}ms")
        print(f"95th Percentile: {stats.percentile_95:.0f}ms")
        print(f"99th Percentile: {stats.percentile_99:.0f}ms")
        print(f"Requests/sec: {stats.requests_per_second:.2f}")
    
    print(f"\n📋 Request Breakdown")
    print(f"{'='*80}")
    for stats in results.request_stats:
        print(f"\n{stats.method} {stats.name}")
        print(f"  Requests: {stats.num_requests}")
        print(f"  Failures: {stats.num_failures} ({stats.error_rate:.2f}%)")
        print(f"  Response Time (p95): {stats.percentile_95:.0f}ms")
        print(f"  Requests/sec: {stats.requests_per_second:.2f}")


if __name__ == '__main__':
    main()
