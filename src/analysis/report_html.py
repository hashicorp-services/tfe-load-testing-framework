# Copyright (c) 2026 IBM Corporation
# SPDX-License-Identifier: MPL-2.0

"""
HTML Report Generator for load test analysis.

This module generates comprehensive HTML reports with charts and styling
for displaying load test analysis results.
"""

from typing import Optional
from datetime import datetime
from pathlib import Path

from .analyzer import AnalysisResult, ThresholdLevel, MetricEvaluation


class HTMLReporter:
    """Generate HTML reports with charts and styling."""
    
    def __init__(self):
        """Initialize HTML reporter."""
        pass
    
    def generate_report(self, result: AnalysisResult, output_file: str):
        """
        Generate complete HTML report.
        
        Args:
            result: AnalysisResult to report
            output_file: Path to output HTML file
        """
        html = self._build_html(result)
        
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            f.write(html)
    
    def _build_html(self, result: AnalysisResult) -> str:
        """Build complete HTML document."""
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TFE Load Test Analysis Report</title>
    {self._get_styles()}
    {self._get_scripts()}
</head>
<body>
    <div class="container">
        {self._build_header(result)}
        {self._build_test_config(result)}
        {self._build_summary(result)}
        {self._build_metrics_section(result)}
        {self._build_grafana_section(result)}
        {self._build_recommendations(result)}
        {self._build_details(result)}
        {self._build_footer()}
    </div>
</body>
</html>"""
    
    def _get_styles(self) -> str:
        """Get embedded CSS styles."""
        return """<style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
            padding: 20px;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }
        
        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
        }
        
        .header .timestamp {
            opacity: 0.9;
            font-size: 0.9em;
        }
        
        .status-badge {
            display: inline-block;
            padding: 10px 30px;
            border-radius: 25px;
            font-weight: bold;
            font-size: 1.2em;
            margin-top: 20px;
        }
        
        .status-passed {
            background: #10b981;
            color: white;
        }
        
        .status-failed {
            background: #ef4444;
            color: white;
        }
        
        .section {
            padding: 30px 40px;
            border-bottom: 1px solid #e5e7eb;
        }
        
        .section:last-child {
            border-bottom: none;
        }
        
        .section-title {
            font-size: 1.8em;
            margin-bottom: 20px;
            color: #1f2937;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .score-container {
            display: flex;
            justify-content: center;
            align-items: center;
            margin: 30px 0;
        }
        
        .score-circle {
            width: 200px;
            height: 200px;
            border-radius: 50%;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            font-size: 3em;
            font-weight: bold;
            color: white;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        
        .score-label {
            font-size: 0.3em;
            margin-top: 5px;
            opacity: 0.9;
        }
        
        .score-excellent { background: linear-gradient(135deg, #10b981, #059669); }
        .score-good { background: linear-gradient(135deg, #3b82f6, #2563eb); }
        .score-acceptable { background: linear-gradient(135deg, #f59e0b, #d97706); }
        .score-poor { background: linear-gradient(135deg, #ef4444, #dc2626); }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }
        
        .stat-card {
            background: #f9fafb;
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }
        
        .stat-label {
            font-size: 0.9em;
            color: #6b7280;
            margin-bottom: 5px;
        }
        
        .stat-value {
            font-size: 1.8em;
            font-weight: bold;
            color: #1f2937;
            word-break: break-all;
            overflow-wrap: break-word;
        }
        
        .metrics-table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }
        
        .metrics-table th {
            background: #f3f4f6;
            padding: 12px;
            text-align: left;
            font-weight: 600;
            color: #374151;
            border-bottom: 2px solid #e5e7eb;
        }
        
        .metrics-table td {
            padding: 12px;
            border-bottom: 1px solid #e5e7eb;
        }
        
        .metrics-table tr:hover {
            background: #f9fafb;
        }
        
        .metric-status {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.85em;
            font-weight: 600;
        }
        
        .status-good {
            background: #d1fae5;
            color: #065f46;
        }
        
        .status-acceptable {
            background: #fef3c7;
            color: #92400e;
        }
        
        .status-poor {
            background: #fee2e2;
            color: #991b1b;
        }
        
        .recommendations {
            list-style: none;
        }
        
        .recommendation {
            padding: 15px;
            margin: 10px 0;
            border-radius: 8px;
            display: flex;
            align-items: flex-start;
            gap: 10px;
        }
        
        .recommendation-critical {
            background: #fee2e2;
            border-left: 4px solid #ef4444;
        }
        
        .recommendation-warning {
            background: #fef3c7;
            border-left: 4px solid #f59e0b;
        }
        
        .recommendation-success {
            background: #d1fae5;
            border-left: 4px solid #10b981;
        }
        
        .recommendation-icon {
            font-size: 1.5em;
            flex-shrink: 0;
        }
        
        .footer {
            background: #f9fafb;
            padding: 20px 40px;
            text-align: center;
            color: #6b7280;
            font-size: 0.9em;
        }
        
        .chart-container {
            margin: 20px 0;
            padding: 20px;
            background: #f9fafb;
            border-radius: 8px;
        }
        
        .progress-bar {
            width: 100%;
            height: 8px;
            background: #e5e7eb;
            border-radius: 4px;
            overflow: hidden;
            margin-top: 5px;
        }
        
        .progress-fill {
            height: 100%;
            transition: width 0.3s ease;
        }
        
        .progress-excellent { background: #10b981; }
        .progress-good { background: #3b82f6; }
        .progress-acceptable { background: #f59e0b; }
        .progress-poor { background: #ef4444; }
        
        @media print {
            body {
                background: white;
                padding: 0;
            }
            
            .container {
                box-shadow: none;
            }
        }
    </style>"""
    
    def _get_scripts(self) -> str:
        """Get embedded JavaScript."""
        return """<script>
        // Add any interactive features here
        document.addEventListener('DOMContentLoaded', function() {
            // Animate progress bars
            const progressBars = document.querySelectorAll('.progress-fill');
            progressBars.forEach(bar => {
                const width = bar.style.width;
                bar.style.width = '0';
                setTimeout(() => {
                    bar.style.width = width;
                }, 100);
            });
        });
    </script>"""
    
    def _build_header(self, result: AnalysisResult) -> str:
        """Build header section."""
        status_class = "status-passed" if result.test_passed else "status-failed"
        status_text = "✅ PASSED" if result.test_passed else "❌ FAILED"
        
        return f"""<div class="header">
        <h1>📊 TFE Load Test Analysis</h1>
        <div class="timestamp">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
        <div class="status-badge {status_class}">{status_text}</div>
    </div>"""
    
    def _build_test_config(self, result: AnalysisResult) -> str:
        """Build test configuration section."""
        if not result.test_config:
            return ""
        
        config = result.test_config
        config_items = []
        
        if 'users' in config:
            config_items.append(("👥 Concurrent Users", str(config['users'])))
        
        if 'spawn_rate' in config:
            config_items.append(("🚀 Spawn Rate", f"{config['spawn_rate']}/s"))
        
        if 'run_time' in config:
            config_items.append(("⏱️ Run Time", config['run_time']))
        
        if 'host' in config:
            config_items.append(("🌐 Target Host", config['host']))
        
        if not config_items:
            return ""
        
        stats_html = '<div class="stats-grid">'
        for label, value in config_items:
            stats_html += f"""
            <div class="stat-card">
                <div class="stat-label">{label}</div>
                <div class="stat-value">{value}</div>
            </div>"""
        stats_html += '</div>'
        
        return f"""<div class="section">
        <h2 class="section-title">⚙️ Test Configuration</h2>
        {stats_html}
    </div>"""
    
    def _build_summary(self, result: AnalysisResult) -> str:
        """Build summary section."""
        score = result.overall_score
        score_class = (
            "score-excellent" if score >= 90 else
            "score-good" if score >= 80 else
            "score-acceptable" if score >= 60 else
            "score-poor"
        )
        
        summary = result.summary
        
        stats_html = ""
        if summary:
            stats = [
                ("Total Requests", summary.get('total_requests', 0)),
                ("Success Rate", f"{summary.get('success_rate', 0):.2f}%"),
                ("Error Rate", f"{summary.get('error_rate', 0):.2f}%"),
                ("Avg Response Time", f"{summary.get('avg_response_time', 0):.0f}ms"),
                ("P95 Response Time", f"{summary.get('p95_response_time', 0):.0f}ms"),
                ("P99 Response Time", f"{summary.get('p99_response_time', 0):.0f}ms"),
                ("Throughput", f"{summary.get('throughput', 0):.2f} req/s"),
                ("Failed Metrics", len(result.critical_issues)),
            ]
            
            stats_html = '<div class="stats-grid">'
            for label, value in stats:
                stats_html += f"""
                <div class="stat-card">
                    <div class="stat-label">{label}</div>
                    <div class="stat-value">{value}</div>
                </div>"""
            stats_html += '</div>'
        
        return f"""<div class="section">
        <h2 class="section-title">📈 Summary</h2>
        <div class="score-container">
            <div class="score-circle {score_class}">
                {score:.0f}
                <div class="score-label">Overall Score</div>
            </div>
        </div>
        {stats_html}
    </div>"""
    
    def _build_metrics_section(self, result: AnalysisResult) -> str:
        """Build metrics evaluation section."""
        if not result.evaluations:
            return ""
        
        # Group metrics
        failed = [e for e in result.evaluations if not e.passed]
        warnings = [e for e in result.evaluations if e.passed and e.threshold_level == ThresholdLevel.POOR]
        passed = [e for e in result.evaluations if e.passed and e.threshold_level != ThresholdLevel.POOR]
        
        html = '<div class="section"><h2 class="section-title">🎯 Metric Evaluations</h2>'
        
        # Failed metrics
        if failed:
            html += '<h3 style="color: #ef4444; margin: 20px 0 10px 0;">❌ Failed Metrics</h3>'
            html += self._build_metrics_table(failed)
        
        # Warnings
        if warnings:
            html += '<h3 style="color: #f59e0b; margin: 20px 0 10px 0;">⚠️ Warnings</h3>'
            html += self._build_metrics_table(warnings)
        
        # Passed metrics
        if passed:
            html += f'<h3 style="color: #10b981; margin: 20px 0 10px 0;">✅ Passed Metrics ({len(passed)})</h3>'
            html += self._build_metrics_table(passed[:10])  # Show first 10
            if len(passed) > 10:
                html += f'<p style="color: #6b7280; margin-top: 10px;">... and {len(passed) - 10} more passed metrics</p>'
        
        html += '</div>'
        return html
    
    def _build_metrics_table(self, evaluations: list) -> str:
        """Build metrics table."""
        html = '<table class="metrics-table"><thead><tr>'
        html += '<th>Metric</th><th>Value</th><th>Status</th><th>Thresholds</th>'
        html += '</tr></thead><tbody>'
        
        for eval_result in evaluations:
            status_class = self._get_status_class(eval_result.threshold_level)
            status_text = eval_result.threshold_level.value.upper()
            
            value_str = f"{eval_result.value:.2f}" if eval_result.value < 10 else f"{eval_result.value:.0f}"
            
            threshold_text = ""
            if eval_result.threshold_good is not None:
                threshold_text = f"Good: {eval_result.threshold_good}, Acceptable: {eval_result.threshold_acceptable}"
            
            html += f"""<tr>
                <td>{eval_result.metric_name}</td>
                <td><strong>{value_str}</strong></td>
                <td><span class="metric-status {status_class}">{status_text}</span></td>
                <td style="color: #6b7280; font-size: 0.9em;">{threshold_text}</td>
            </tr>"""
        
        html += '</tbody></table>'
        return html
    
    def _build_grafana_section(self, result: AnalysisResult) -> str:
        """Build Grafana metrics section."""
        if not result.grafana_metrics:
            return ""
        
        html = '<div class="section"><h2 class="section-title">📊 TFE Infrastructure Metrics</h2>'
        html += '<div class="stats-grid">'
        
        metrics = [
            ("Workspaces Total", result.grafana_metrics.get('workspaces_total')),
            ("Workspaces Locked", result.grafana_metrics.get('workspaces_locked')),
            ("Run Queue Depth", result.grafana_metrics.get('run_queue_depth')),
            ("DB Connections", result.grafana_metrics.get('db_connections')),
            ("API Request Duration (p95)", result.grafana_metrics.get('api_request_duration_p95_current')),
            ("API Error Rate", result.grafana_metrics.get('api_error_rate_current')),
        ]
        
        for label, value in metrics:
            if value is not None:
                value_str = f"{value:.2f}" if isinstance(value, float) else str(value)
                html += f"""
                <div class="stat-card">
                    <div class="stat-label">{label}</div>
                    <div class="stat-value">{value_str}</div>
                </div>"""
        
        html += '</div></div>'
        return html
    
    def _build_recommendations(self, result: AnalysisResult) -> str:
        """Build recommendations section."""
        if not result.recommendations:
            return ""
        
        html = '<div class="section"><h2 class="section-title">💡 Recommendations</h2>'
        html += '<ul class="recommendations">'
        
        for rec in result.recommendations:
            rec_class = "recommendation-success"
            icon = "✅"
            rec_text = rec
            
            if rec.startswith("🔴"):
                rec_class = "recommendation-critical"
                icon = "🔴"
                rec_text = rec[2:].strip()  # Remove emoji and space
            elif rec.startswith("⚠️"):
                rec_class = "recommendation-warning"
                icon = "⚠️"
                rec_text = rec[3:].strip()  # Remove emoji and space (⚠️ is 2 chars + space)
            elif rec.startswith("✅"):
                rec_text = rec[2:].strip()  # Remove emoji and space
            
            html += f"""<li class="recommendation {rec_class}">
                <span class="recommendation-icon">{icon}</span>
                <span>{rec_text}</span>
            </li>"""
        
        html += '</ul></div>'
        return html
    
    def _build_details(self, result: AnalysisResult) -> str:
        """Build detailed results section."""
        if not result.locust_results:
            return ""
        
        html = '<div class="section"><h2 class="section-title">📋 Detailed Results</h2>'
        
        # Request breakdown
        if result.locust_results.request_stats:
            html += '<h3 style="margin: 20px 0 10px 0;">Request Breakdown</h3>'
            html += '<table class="metrics-table"><thead><tr>'
            html += '<th>Operation</th><th>Requests</th><th>Failures</th><th>Success Rate</th><th>P95 (ms)</th>'
            html += '</tr></thead><tbody>'
            
            for stats in result.locust_results.request_stats:
                html += f"""<tr>
                    <td>{stats.method} {stats.name}</td>
                    <td>{stats.num_requests}</td>
                    <td>{stats.num_failures}</td>
                    <td>{stats.success_rate:.2f}%</td>
                    <td>{stats.percentile_95:.0f}</td>
                </tr>"""
            
            html += '</tbody></table>'
        
        html += '</div>'
        return html
    
    def _build_footer(self) -> str:
        """Build footer section."""
        return f"""<div class="footer">
        <p>Generated by TFE Load Testing Framework</p>
        <p>Report generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>"""
    
    def _get_status_class(self, level: ThresholdLevel) -> str:
        """Get CSS class for threshold level."""
        if level == ThresholdLevel.GOOD:
            return "status-good"
        elif level == ThresholdLevel.ACCEPTABLE:
            return "status-acceptable"
        return "status-poor"


def main():
    """Test HTML reporter."""
    import sys
    from .analyzer import LoadTestAnalyzer
    
    if len(sys.argv) < 2:
        print("Usage: python report_html.py <locust_stats.csv> [output.html]")
        sys.exit(1)
    
    output_file = sys.argv[2] if len(sys.argv) > 2 else "report.html"
    
    # Analyze results
    analyzer = LoadTestAnalyzer()
    result = analyzer.analyze(locust_stats_file=sys.argv[1])
    
    # Generate HTML report
    reporter = HTMLReporter()
    reporter.generate_report(result, output_file)
    
    print(f"✅ HTML report generated: {output_file}")


if __name__ == '__main__':
    main()
