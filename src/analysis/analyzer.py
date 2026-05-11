"""
Load Test Analyzer - Core analysis logic with pass/fail criteria.

This module analyzes Locust test results and Grafana metrics against
defined thresholds to determine test success and generate recommendations.
"""

import yaml
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

from .locust_parser import LocustParser, LocustResults, RequestStats
from .grafana_client import GrafanaClient

logger = logging.getLogger(__name__)


class ThresholdLevel(Enum):
    """Threshold evaluation levels."""
    EXCELLENT = "excellent"
    GOOD = "good"
    ACCEPTABLE = "acceptable"
    POOR = "poor"
    CRITICAL = "critical"


@dataclass
class MetricEvaluation:
    """Evaluation result for a single metric."""
    metric_name: str
    value: float
    threshold_level: ThresholdLevel
    threshold_good: Optional[float] = None
    threshold_acceptable: Optional[float] = None
    passed: bool = True
    message: str = ""


@dataclass
class AnalysisResult:
    """Complete analysis result."""
    test_passed: bool
    overall_score: float  # 0-100
    locust_results: Optional[LocustResults] = None
    grafana_metrics: Dict[str, Any] = field(default_factory=dict)
    evaluations: List[MetricEvaluation] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    test_config: Dict[str, Any] = field(default_factory=dict)  # Test configuration (users, spawn_rate, etc.)
    
    @property
    def critical_issues(self) -> List[MetricEvaluation]:
        """Get critical issues (failed metrics)."""
        return [e for e in self.evaluations if not e.passed]
    
    @property
    def warnings(self) -> List[MetricEvaluation]:
        """Get warnings (poor but not failed metrics)."""
        return [
            e for e in self.evaluations 
            if e.passed and e.threshold_level == ThresholdLevel.POOR
        ]


class LoadTestAnalyzer:
    """Analyzer for load test results."""
    
    def __init__(self, thresholds_file: str = "config/analysis_thresholds.yaml"):
        """
        Initialize analyzer.
        
        Args:
            thresholds_file: Path to thresholds configuration file
        """
        self.thresholds_file = Path(thresholds_file)
        self.thresholds = self._load_thresholds()
    
    def _load_thresholds(self) -> Dict[str, Any]:
        """Load thresholds from YAML file."""
        if not self.thresholds_file.exists():
            logger.warning(f"Thresholds file not found: {self.thresholds_file}")
            return {}
        
        with open(self.thresholds_file, 'r') as f:
            return yaml.safe_load(f)
    
    def analyze(
        self,
        locust_stats_file: Optional[str] = None,
        grafana_client: Optional[GrafanaClient] = None,
        test_start_time: Optional[Any] = None,
        test_end_time: Optional[Any] = None
    ) -> AnalysisResult:
        """
        Analyze load test results.
        
        Args:
            locust_stats_file: Path to Locust statistics file
            grafana_client: GrafanaClient instance for fetching metrics
            test_start_time: Test start time for Grafana queries
            test_end_time: Test end time for Grafana queries
        
        Returns:
            AnalysisResult with complete analysis
        """
        result = AnalysisResult(test_passed=True, overall_score=100.0)
        
        # Parse Locust results
        if locust_stats_file:
            try:
                parser = LocustParser(locust_stats_file)
                result.locust_results = parser.parse()
                logger.info(f"Parsed Locust results: {result.locust_results.total_requests} requests")
            except Exception as e:
                logger.error(f"Failed to parse Locust results: {e}")
        
        # Fetch Grafana metrics
        if grafana_client:
            try:
                result.grafana_metrics = grafana_client.get_tfe_metrics(
                    test_start_time, test_end_time
                )
                logger.info(f"Fetched {len(result.grafana_metrics)} Grafana metrics")
            except Exception as e:
                logger.error(f"Failed to fetch Grafana metrics: {e}")
        
        # Evaluate metrics
        if result.locust_results:
            self._evaluate_locust_metrics(result)
        
        if result.grafana_metrics:
            self._evaluate_grafana_metrics(result)
        
        # Calculate overall score and pass/fail
        self._calculate_overall_score(result)
        
        # Generate recommendations
        self._generate_recommendations(result)
        
        # Create summary
        self._create_summary(result)
        
        return result
    
    def _evaluate_locust_metrics(self, result: AnalysisResult):
        """Evaluate Locust metrics against thresholds."""
        if not result.locust_results:
            return
        
        global_thresholds = self.thresholds.get('global', {})
        
        # Evaluate overall error rate
        error_rate = result.locust_results.overall_error_rate
        error_thresholds = global_thresholds.get('error_rate', {})
        
        eval_result = self._evaluate_metric(
            "Overall Error Rate",
            error_rate,
            error_thresholds.get('good', 1.0),
            error_thresholds.get('acceptable', 5.0),
            lower_is_better=True
        )
        result.evaluations.append(eval_result)
        
        # Evaluate aggregated response times
        if result.locust_results.aggregated_stats:
            stats = result.locust_results.aggregated_stats
            rt_thresholds = global_thresholds.get('response_time', {})
            
            # P50
            p50_thresholds = rt_thresholds.get('p50', {})
            eval_result = self._evaluate_metric(
                "Response Time (p50)",
                stats.percentile_50,
                p50_thresholds.get('good', 100),
                p50_thresholds.get('acceptable', 300),
                lower_is_better=True
            )
            result.evaluations.append(eval_result)
            
            # P95
            p95_thresholds = rt_thresholds.get('p95', {})
            eval_result = self._evaluate_metric(
                "Response Time (p95)",
                stats.percentile_95,
                p95_thresholds.get('good', 500),
                p95_thresholds.get('acceptable', 1000),
                lower_is_better=True
            )
            result.evaluations.append(eval_result)
            
            # P99
            p99_thresholds = rt_thresholds.get('p99', {})
            eval_result = self._evaluate_metric(
                "Response Time (p99)",
                stats.percentile_99,
                p99_thresholds.get('good', 1000),
                p99_thresholds.get('acceptable', 2000),
                lower_is_better=True
            )
            result.evaluations.append(eval_result)
            
            # Throughput - NOT evaluated for pass/fail (informational only)
            # throughput_thresholds = global_thresholds.get('throughput', {})
            # eval_result = self._evaluate_metric(
            #     "Throughput (req/s)",
            #     stats.requests_per_second,
            #     throughput_thresholds.get('good', 10),
            #     throughput_thresholds.get('acceptable', 5),
            #     lower_is_better=False
            # )
            # result.evaluations.append(eval_result)
        
        # Evaluate individual operations
        operation_thresholds = self.thresholds.get('operations', {})
        for stats in result.locust_results.request_stats:
            self._evaluate_operation(stats, operation_thresholds, result)
    
    def _evaluate_operation(
        self,
        stats: RequestStats,
        operation_thresholds: Dict[str, Any],
        result: AnalysisResult
    ):
        """Evaluate individual operation metrics."""
        # Try to match operation name to threshold config
        operation_key = self._match_operation_name(stats.name)
        if not operation_key or operation_key not in operation_thresholds:
            return
        
        thresholds = operation_thresholds[operation_key]
        
        # Evaluate error rate
        if 'error_rate' in thresholds:
            error_thresholds = thresholds['error_rate']
            eval_result = self._evaluate_metric(
                f"{stats.name} - Error Rate",
                stats.error_rate,
                error_thresholds.get('good', 1.0),
                error_thresholds.get('acceptable', 5.0),
                lower_is_better=True
            )
            result.evaluations.append(eval_result)
        
        # Evaluate response time (p95)
        if 'response_time' in thresholds:
            rt_thresholds = thresholds['response_time'].get('p95', {})
            eval_result = self._evaluate_metric(
                f"{stats.name} - Response Time (p95)",
                stats.percentile_95,
                rt_thresholds.get('good', 500),
                rt_thresholds.get('acceptable', 1000),
                lower_is_better=True
            )
            result.evaluations.append(eval_result)
    
    def _evaluate_grafana_metrics(self, result: AnalysisResult):
        """Evaluate Grafana metrics against thresholds."""
        tfe_thresholds = self.thresholds.get('tfe_metrics', {})
        
        # Run queue depth
        if 'run_queue_depth' in result.grafana_metrics:
            queue_thresholds = tfe_thresholds.get('run_queue_depth', {})
            eval_result = self._evaluate_metric(
                "Run Queue Depth",
                result.grafana_metrics['run_queue_depth'],
                queue_thresholds.get('good', 5),
                queue_thresholds.get('acceptable', 20),
                lower_is_better=True
            )
            result.evaluations.append(eval_result)
        
        # Database connections
        if 'db_connections' in result.grafana_metrics:
            db_thresholds = tfe_thresholds.get('database', {}).get('active_connections', {})
            eval_result = self._evaluate_metric(
                "Database Active Connections",
                result.grafana_metrics['db_connections'],
                db_thresholds.get('good', 50),
                db_thresholds.get('acceptable', 100),
                lower_is_better=True
            )
            result.evaluations.append(eval_result)
    
    def _evaluate_metric(
        self,
        metric_name: str,
        value: float,
        good_threshold: float,
        acceptable_threshold: float,
        lower_is_better: bool = True
    ) -> MetricEvaluation:
        """
        Evaluate a single metric against thresholds.
        
        Args:
            metric_name: Name of the metric
            value: Metric value
            good_threshold: Threshold for "good" level
            acceptable_threshold: Threshold for "acceptable" level
            lower_is_better: If True, lower values are better
        
        Returns:
            MetricEvaluation result
        """
        if lower_is_better:
            if value <= good_threshold:
                level = ThresholdLevel.GOOD
                passed = True
                message = f"✅ Excellent: {value:.2f} <= {good_threshold}"
            elif value <= acceptable_threshold:
                level = ThresholdLevel.ACCEPTABLE
                passed = True
                message = f"⚠️  Acceptable: {value:.2f} <= {acceptable_threshold}"
            else:
                level = ThresholdLevel.POOR
                passed = False
                message = f"❌ Poor: {value:.2f} > {acceptable_threshold}"
        else:
            if value >= good_threshold:
                level = ThresholdLevel.GOOD
                passed = True
                message = f"✅ Excellent: {value:.2f} >= {good_threshold}"
            elif value >= acceptable_threshold:
                level = ThresholdLevel.ACCEPTABLE
                passed = True
                message = f"⚠️  Acceptable: {value:.2f} >= {acceptable_threshold}"
            else:
                level = ThresholdLevel.POOR
                passed = False
                message = f"❌ Poor: {value:.2f} < {acceptable_threshold}"
        
        return MetricEvaluation(
            metric_name=metric_name,
            value=value,
            threshold_level=level,
            threshold_good=good_threshold,
            threshold_acceptable=acceptable_threshold,
            passed=passed,
            message=message
        )
    
    def _match_operation_name(self, operation_name: str) -> Optional[str]:
        """Match operation name to threshold configuration key."""
        operation_name_lower = operation_name.lower()
        
        # Simple keyword matching
        mappings = {
            'workspace': ['workspace_create', 'workspace_list', 'workspace_delete'],
            'create': ['workspace_create', 'run_create', 'state_upload'],
            'list': ['workspace_list', 'state_list'],
            'delete': ['workspace_delete'],
            'run': ['run_create', 'run_status'],
            'status': ['run_status'],
            'state': ['state_upload', 'state_download', 'state_list'],
            'upload': ['state_upload'],
            'download': ['state_download'],
        }
        
        for keyword, operations in mappings.items():
            if keyword in operation_name_lower:
                for op in operations:
                    if op.replace('_', ' ') in operation_name_lower:
                        return op
        
        return None
    
    def _calculate_overall_score(self, result: AnalysisResult):
        """Calculate overall test score and pass/fail status."""
        if not result.evaluations:
            result.overall_score = 0.0
            result.test_passed = False
            return
        
        # Calculate score based on threshold levels
        score_weights = {
            ThresholdLevel.GOOD: 100,
            ThresholdLevel.ACCEPTABLE: 70,
            ThresholdLevel.POOR: 30,
            ThresholdLevel.CRITICAL: 0
        }
        
        total_score = 0
        for eval_result in result.evaluations:
            total_score += score_weights.get(eval_result.threshold_level, 0)
        
        result.overall_score = total_score / len(result.evaluations)
        
        # Determine pass/fail
        critical_failures = [e for e in result.evaluations if not e.passed]
        result.test_passed = len(critical_failures) == 0
    
    def _generate_recommendations(self, result: AnalysisResult):
        """Generate recommendations based on analysis."""
        recommendations = []
        
        # Check for high error rates
        for eval_result in result.evaluations:
            if 'error rate' in eval_result.metric_name.lower():
                if eval_result.threshold_level == ThresholdLevel.POOR:
                    recommendations.append(
                        f"🔴 High error rate detected in {eval_result.metric_name}. "
                        "Investigate application logs and error responses."
                    )
        
        # Check for slow response times
        for eval_result in result.evaluations:
            if 'response time' in eval_result.metric_name.lower():
                if eval_result.threshold_level == ThresholdLevel.POOR:
                    recommendations.append(
                        f"🔴 Slow response times in {eval_result.metric_name}. "
                        "Consider scaling TFE resources or optimizing database queries."
                    )
        
        # Check for high queue depth
        for eval_result in result.evaluations:
            if 'queue depth' in eval_result.metric_name.lower():
                if eval_result.threshold_level == ThresholdLevel.POOR:
                    recommendations.append(
                        "🔴 High run queue depth. Consider increasing TFE worker capacity."
                    )
        
        # Check for high database connections
        for eval_result in result.evaluations:
            if 'database' in eval_result.metric_name.lower():
                if eval_result.threshold_level == ThresholdLevel.POOR:
                    recommendations.append(
                        "🔴 High database connection count. "
                        "Review connection pooling settings and database capacity."
                    )
        
        # General recommendations
        if result.overall_score < 70:
            recommendations.append(
                "⚠️  Overall performance is below acceptable levels. "
                "Consider reviewing TFE infrastructure capacity and configuration."
            )
        
        if not recommendations:
            recommendations.append(
                "✅ All metrics within acceptable thresholds. No immediate action required."
            )
        
        result.recommendations = recommendations
    
    def _create_summary(self, result: AnalysisResult):
        """Create summary statistics."""
        summary = {
            'test_passed': result.test_passed,
            'overall_score': result.overall_score,
            'total_evaluations': len(result.evaluations),
            'passed_evaluations': len([e for e in result.evaluations if e.passed]),
            'failed_evaluations': len([e for e in result.evaluations if not e.passed]),
            'warnings': len(result.warnings),
        }
        
        if result.locust_results:
            summary.update({
                'total_requests': result.locust_results.total_requests,
                'total_failures': result.locust_results.total_failures,
                'success_rate': result.locust_results.overall_success_rate,
                'error_rate': result.locust_results.overall_error_rate,
            })
            
            if result.locust_results.aggregated_stats:
                stats = result.locust_results.aggregated_stats
                summary.update({
                    'avg_response_time': stats.average_response_time,
                    'p95_response_time': stats.percentile_95,
                    'p99_response_time': stats.percentile_99,
                    'throughput': stats.requests_per_second,
                })
        
        result.summary = summary


def main():
    """Test analyzer."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python analyzer.py <locust_stats.csv>")
        sys.exit(1)
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create analyzer
    analyzer = LoadTestAnalyzer()
    
    # Analyze results
    result = analyzer.analyze(locust_stats_file=sys.argv[1])
    
    # Display results
    print(f"\n{'='*80}")
    print(f"📊 Load Test Analysis Results")
    print(f"{'='*80}")
    print(f"\nOverall Score: {result.overall_score:.1f}/100")
    print(f"Test Status: {'✅ PASSED' if result.test_passed else '❌ FAILED'}")
    
    print(f"\n📈 Summary")
    print(f"{'='*80}")
    for key, value in result.summary.items():
        if isinstance(value, float):
            print(f"{key}: {value:.2f}")
        else:
            print(f"{key}: {value}")
    
    print(f"\n🎯 Metric Evaluations")
    print(f"{'='*80}")
    for eval_result in result.evaluations:
        print(f"{eval_result.message} - {eval_result.metric_name}")
    
    print(f"\n💡 Recommendations")
    print(f"{'='*80}")
    for rec in result.recommendations:
        print(f"  {rec}")


if __name__ == '__main__':
    main()
