# Copyright (c) 2026 IBM Corporation
# SPDX-License-Identifier: IPL-1.0

"""
Terminal Report Generator for load test analysis.

This module generates formatted terminal reports with colors and tables
for displaying load test analysis results.
"""

import sys
from typing import Optional
from datetime import datetime

from .analyzer import AnalysisResult, ThresholdLevel, MetricEvaluation


class TerminalReporter:
    """Generate formatted terminal reports."""
    
    # ANSI color codes
    RESET = '\033[0m'
    BOLD = '\033[1m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    
    def __init__(self, use_colors: bool = True):
        """
        Initialize reporter.
        
        Args:
            use_colors: Whether to use ANSI colors (disable for CI/CD)
        """
        self.use_colors = use_colors and sys.stdout.isatty()
    
    def _color(self, text: str, color: str) -> str:
        """Apply color to text if colors are enabled."""
        if not self.use_colors:
            return text
        return f"{color}{text}{self.RESET}"
    
    def _bold(self, text: str) -> str:
        """Make text bold if colors are enabled."""
        if not self.use_colors:
            return text
        return f"{self.BOLD}{text}{self.RESET}"
    
    def _status_icon(self, passed: bool) -> str:
        """Get status icon."""
        if passed:
            return self._color("✅", self.GREEN)
        return self._color("❌", self.RED)
    
    def _level_color(self, level: ThresholdLevel) -> str:
        """Get color for threshold level."""
        if level == ThresholdLevel.GOOD:
            return self.GREEN
        elif level == ThresholdLevel.ACCEPTABLE:
            return self.YELLOW
        elif level == ThresholdLevel.POOR:
            return self.RED
        return self.RESET
    
    def generate_report(self, result: AnalysisResult) -> str:
        """
        Generate complete terminal report.
        
        Args:
            result: AnalysisResult to report
        
        Returns:
            Formatted report string
        """
        lines = []
        
        # Header
        lines.append("")
        lines.append(self._color("=" * 80, self.CYAN))
        lines.append(self._bold(self._color("📊 TFE Load Test Analysis Report", self.CYAN)))
        lines.append(self._color("=" * 80, self.CYAN))
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        
        # Overall Status
        lines.append(self._bold("🎯 Overall Status"))
        lines.append("-" * 80)
        
        status_text = "PASSED" if result.test_passed else "FAILED"
        status_color = self.GREEN if result.test_passed else self.RED
        lines.append(f"Test Result: {self._color(self._bold(status_text), status_color)}")
        
        score_color = self.GREEN if result.overall_score >= 80 else (
            self.YELLOW if result.overall_score >= 60 else self.RED
        )
        lines.append(f"Overall Score: {self._color(f'{result.overall_score:.1f}/100', score_color)}")
        lines.append("")
        
        # Summary Statistics
        if result.summary:
            lines.append(self._bold("📈 Summary Statistics"))
            lines.append("-" * 80)
            
            summary_items = [
                ("Total Requests", result.summary.get('total_requests')),
                ("Total Failures", result.summary.get('total_failures')),
                ("Success Rate", f"{result.summary.get('success_rate', 0):.2f}%"),
                ("Error Rate", f"{result.summary.get('error_rate', 0):.2f}%"),
                ("Avg Response Time", f"{result.summary.get('avg_response_time', 0):.0f}ms"),
                ("P95 Response Time", f"{result.summary.get('p95_response_time', 0):.0f}ms"),
                ("P99 Response Time", f"{result.summary.get('p99_response_time', 0):.0f}ms"),
                ("Throughput", f"{result.summary.get('throughput', 0):.2f} req/s"),
            ]
            
            for label, value in summary_items:
                if value is not None:
                    lines.append(f"  {label:.<30} {value}")
            lines.append("")
        
        # Metric Evaluations
        if result.evaluations:
            lines.append(self._bold("🎯 Metric Evaluations"))
            lines.append("-" * 80)
            
            # Group by status
            passed = [e for e in result.evaluations if e.passed]
            failed = [e for e in result.evaluations if not e.passed]
            
            if failed:
                lines.append(self._color(self._bold("❌ Failed Metrics:"), self.RED))
                for eval_result in failed:
                    lines.append(f"  {self._format_evaluation(eval_result)}")
                lines.append("")
            
            if passed:
                # Show warnings (poor but passed)
                warnings = [e for e in passed if e.threshold_level == ThresholdLevel.POOR]
                if warnings:
                    lines.append(self._color(self._bold("⚠️  Warnings:"), self.YELLOW))
                    for eval_result in warnings:
                        lines.append(f"  {self._format_evaluation(eval_result)}")
                    lines.append("")
                
                # Show good metrics (collapsed)
                good = [e for e in passed if e.threshold_level != ThresholdLevel.POOR]
                if good:
                    lines.append(self._color(self._bold(f"✅ Passed Metrics ({len(good)}):"), self.GREEN))
                    for eval_result in good[:5]:  # Show first 5
                        lines.append(f"  {self._format_evaluation(eval_result)}")
                    if len(good) > 5:
                        lines.append(f"  ... and {len(good) - 5} more")
                    lines.append("")
        
        # Grafana Metrics
        if result.grafana_metrics:
            lines.append(self._bold("📊 TFE Infrastructure Metrics (Grafana)"))
            lines.append("-" * 80)
            
            metrics_to_show = [
                ("Workspaces Total", result.grafana_metrics.get('workspaces_total')),
                ("Workspaces Locked", result.grafana_metrics.get('workspaces_locked')),
                ("Run Queue Depth", result.grafana_metrics.get('run_queue_depth')),
                ("DB Connections", result.grafana_metrics.get('db_connections')),
                ("API Request Duration (p95)", result.grafana_metrics.get('api_request_duration_p95_current')),
                ("API Error Rate", result.grafana_metrics.get('api_error_rate_current')),
            ]
            
            for label, value in metrics_to_show:
                if value is not None:
                    if isinstance(value, float):
                        lines.append(f"  {label:.<40} {value:.2f}")
                    else:
                        lines.append(f"  {label:.<40} {value}")
            lines.append("")
        
        # Recommendations
        if result.recommendations:
            lines.append(self._bold("💡 Recommendations"))
            lines.append("-" * 80)
            for rec in result.recommendations:
                # Color code recommendations
                if rec.startswith("🔴"):
                    lines.append(self._color(f"  {rec}", self.RED))
                elif rec.startswith("⚠️"):
                    lines.append(self._color(f"  {rec}", self.YELLOW))
                elif rec.startswith("✅"):
                    lines.append(self._color(f"  {rec}", self.GREEN))
                else:
                    lines.append(f"  {rec}")
            lines.append("")
        
        # Footer
        lines.append(self._color("=" * 80, self.CYAN))
        
        if result.test_passed:
            lines.append(self._color(self._bold("✅ Test PASSED - All metrics within acceptable thresholds"), self.GREEN))
        else:
            lines.append(self._color(self._bold("❌ Test FAILED - Some metrics exceeded thresholds"), self.RED))
        
        lines.append(self._color("=" * 80, self.CYAN))
        lines.append("")
        
        return "\n".join(lines)
    
    def _format_evaluation(self, eval_result: MetricEvaluation) -> str:
        """Format a single metric evaluation."""
        level_color = self._level_color(eval_result.threshold_level)
        
        # Format value
        if eval_result.value < 1:
            value_str = f"{eval_result.value:.3f}"
        elif eval_result.value < 10:
            value_str = f"{eval_result.value:.2f}"
        else:
            value_str = f"{eval_result.value:.0f}"
        
        # Format thresholds
        threshold_info = ""
        if eval_result.threshold_good is not None and eval_result.threshold_acceptable is not None:
            threshold_info = f" (good: {eval_result.threshold_good}, acceptable: {eval_result.threshold_acceptable})"
        
        status = "✅" if eval_result.passed else "❌"
        level_text = eval_result.threshold_level.value.upper()
        
        return (
            f"{status} {self._color(level_text, level_color):20} "
            f"{eval_result.metric_name:40} = {value_str}{threshold_info}"
        )
    
    def print_report(self, result: AnalysisResult):
        """Print report to stdout."""
        print(self.generate_report(result))
    
    def generate_summary(self, result: AnalysisResult) -> str:
        """
        Generate brief summary (for CI/CD).
        
        Args:
            result: AnalysisResult to summarize
        
        Returns:
            Brief summary string
        """
        lines = []
        
        status = "PASSED" if result.test_passed else "FAILED"
        lines.append(f"Test Status: {status}")
        lines.append(f"Overall Score: {result.overall_score:.1f}/100")
        
        if result.summary:
            lines.append(f"Total Requests: {result.summary.get('total_requests', 0)}")
            lines.append(f"Error Rate: {result.summary.get('error_rate', 0):.2f}%")
            lines.append(f"P95 Response Time: {result.summary.get('p95_response_time', 0):.0f}ms")
        
        lines.append(f"Failed Metrics: {len(result.critical_issues)}")
        lines.append(f"Warnings: {len(result.warnings)}")
        
        return "\n".join(lines)


def main():
    """Test terminal reporter."""
    import sys
    from .analyzer import LoadTestAnalyzer
    
    if len(sys.argv) < 2:
        print("Usage: python report_terminal.py <locust_stats.csv>")
        sys.exit(1)
    
    # Analyze results
    analyzer = LoadTestAnalyzer()
    result = analyzer.analyze(locust_stats_file=sys.argv[1])
    
    # Generate and print report
    reporter = TerminalReporter()
    reporter.print_report(result)


if __name__ == '__main__':
    main()
