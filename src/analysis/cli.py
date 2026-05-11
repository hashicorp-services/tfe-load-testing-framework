#!/usr/bin/env python3
"""
TFE Load Test Analysis CLI

Command-line interface for analyzing TFE load test results.
"""

import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

from .analyzer import LoadTestAnalyzer
from .grafana_client import GrafanaClient
from .report_terminal import TerminalReporter
from .report_html import HTMLReporter


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description='Analyze TFE load test results',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze Locust results only
  %(prog)s --locust-stats results.csv
  
  # Analyze with Grafana metrics
  %(prog)s --locust-stats results.csv --grafana-url http://localhost:3000
  
  # Generate HTML report
  %(prog)s --locust-stats results.csv --html-report report.html
  
  # Custom thresholds
  %(prog)s --locust-stats results.csv --thresholds custom_thresholds.yaml
  
  # CI/CD mode (exit code 1 if test fails)
  %(prog)s --locust-stats results.csv --ci-mode
        """
    )
    
    # Input options
    input_group = parser.add_argument_group('Input Options')
    input_group.add_argument(
        '--locust-stats',
        type=str,
        required=True,
        help='Path to Locust statistics file (CSV or JSON)'
    )
    input_group.add_argument(
        '--thresholds',
        type=str,
        default='config/analysis_thresholds.yaml',
        help='Path to thresholds configuration file (default: config/analysis_thresholds.yaml)'
    )
    
    # Test configuration options
    test_config_group = parser.add_argument_group('Test Configuration')
    test_config_group.add_argument(
        '--users',
        type=int,
        help='Number of concurrent users during the test'
    )
    test_config_group.add_argument(
        '--spawn-rate',
        type=float,
        help='User spawn rate per second'
    )
    test_config_group.add_argument(
        '--run-time',
        type=str,
        help='Test run time (e.g., 5m, 1h)'
    )
    test_config_group.add_argument(
        '--host',
        type=str,
        help='Target host URL'
    )
    
    # Grafana options
    grafana_group = parser.add_argument_group('Grafana Options')
    grafana_group.add_argument(
        '--grafana-url',
        type=str,
        help='Grafana URL (default: http://localhost:3000)'
    )
    grafana_group.add_argument(
        '--grafana-api-key',
        type=str,
        help='Grafana API key (or set GRAFANA_API_KEY env var)'
    )
    grafana_group.add_argument(
        '--test-duration',
        type=int,
        default=5,
        help='Test duration in minutes for Grafana queries (default: 5)'
    )
    grafana_group.add_argument(
        '--no-grafana',
        action='store_true',
        help='Skip Grafana metrics fetching'
    )
    
    # Output options
    output_group = parser.add_argument_group('Output Options')
    output_group.add_argument(
        '--html-report',
        type=str,
        help='Generate HTML report at specified path'
    )
    output_group.add_argument(
        '--no-terminal',
        action='store_true',
        help='Skip terminal report output'
    )
    output_group.add_argument(
        '--summary-only',
        action='store_true',
        help='Show only summary (for CI/CD)'
    )
    output_group.add_argument(
        '--no-colors',
        action='store_true',
        help='Disable colored output'
    )
    
    # Behavior options
    behavior_group = parser.add_argument_group('Behavior Options')
    behavior_group.add_argument(
        '--ci-mode',
        action='store_true',
        help='CI/CD mode: exit with code 1 if test fails'
    )
    behavior_group.add_argument(
        '--verbose',
        '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    return parser.parse_args()


def main():
    """Main CLI entry point."""
    args = parse_args()
    
    # Setup logging
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)
    
    try:
        # Validate input file
        if not Path(args.locust_stats).exists():
            logger.error(f"Locust stats file not found: {args.locust_stats}")
            return 1
        
        # Create analyzer
        logger.info("Initializing analyzer...")
        analyzer = LoadTestAnalyzer(thresholds_file=args.thresholds)
        
        # Setup Grafana client if needed
        grafana_client = None
        if not args.no_grafana:
            grafana_url = args.grafana_url or "http://localhost:3000"
            logger.info(f"Connecting to Grafana at {grafana_url}...")
            
            grafana_client = GrafanaClient(
                url=grafana_url,
                api_key=args.grafana_api_key,
                verify_ssl=False
            )
            
            if not grafana_client.test_connection():
                logger.warning("Failed to connect to Grafana. Continuing without Grafana metrics.")
                grafana_client = None
        
        # Calculate time range for Grafana queries
        test_end_time = datetime.utcnow()
        test_start_time = test_end_time - timedelta(minutes=args.test_duration)
        
        # Collect test configuration
        test_config = {}
        if args.users:
            test_config['users'] = args.users
        if args.spawn_rate:
            test_config['spawn_rate'] = args.spawn_rate
        if args.run_time:
            test_config['run_time'] = args.run_time
        if args.host:
            test_config['host'] = args.host
        
        # Analyze results
        logger.info("Analyzing test results...")
        result = analyzer.analyze(
            locust_stats_file=args.locust_stats,
            grafana_client=grafana_client,
            test_start_time=test_start_time,
            test_end_time=test_end_time
        )
        
        # Add test configuration to result
        result.test_config = test_config
        
        # Generate terminal report
        if not args.no_terminal:
            reporter = TerminalReporter(use_colors=not args.no_colors)
            
            if args.summary_only:
                print(reporter.generate_summary(result))
            else:
                reporter.print_report(result)
        
        # Generate HTML report
        if args.html_report:
            logger.info(f"Generating HTML report: {args.html_report}")
            html_reporter = HTMLReporter()
            html_reporter.generate_report(result, args.html_report)
            print(f"\n✅ HTML report generated: {args.html_report}")
        
        # Exit with appropriate code in CI mode
        if args.ci_mode:
            if result.test_passed:
                logger.info("Test PASSED")
                return 0
            else:
                logger.error("Test FAILED")
                return 1
        
        return 0
    
    except KeyboardInterrupt:
        logger.info("Analysis interrupted by user")
        return 130
    
    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=args.verbose)
        return 1


if __name__ == '__main__':
    sys.exit(main())
