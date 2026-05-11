"""
TFE Load Test Analysis Package

This package provides tools for analyzing TFE load test results,
including Locust statistics parsing, Grafana metrics fetching,
threshold evaluation, and report generation.
"""

from .analyzer import LoadTestAnalyzer, AnalysisResult, ThresholdLevel, MetricEvaluation
from .locust_parser import LocustParser, LocustResults, RequestStats
from .grafana_client import GrafanaClient
from .report_terminal import TerminalReporter
from .report_html import HTMLReporter

__all__ = [
    'LoadTestAnalyzer',
    'AnalysisResult',
    'ThresholdLevel',
    'MetricEvaluation',
    'LocustParser',
    'LocustResults',
    'RequestStats',
    'GrafanaClient',
    'TerminalReporter',
    'HTMLReporter',
]

__version__ = '1.0.0'
