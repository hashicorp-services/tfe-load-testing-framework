# TFE Load Test Analysis Tool

Comprehensive analysis tool for TFE load test results with automatic threshold evaluation, Grafana metrics integration, and beautiful reports.

## Features

- 📊 **Automatic Analysis**: Parse Locust statistics and evaluate against configurable thresholds
- 🎯 **Pass/Fail Criteria**: Automatic test pass/fail determination based on performance metrics
- 📈 **Grafana Integration**: Fetch TFE infrastructure metrics from Grafana/Prometheus
- 🖥️ **Terminal Reports**: Colored, formatted terminal output with detailed metrics
- 📄 **HTML Reports**: Beautiful HTML reports with charts and styling
- ⚙️ **Configurable Thresholds**: Customize performance thresholds via YAML configuration
- 🤖 **CI/CD Ready**: Exit codes and summary mode for automation

## Quick Start

### Basic Usage

```bash
# Analyze Locust results (terminal report only)
./analyze_results.py --locust-stats reports/test_stats.csv --no-grafana

# Generate HTML report
./analyze_results.py --locust-stats reports/test_stats.csv \
    --no-grafana \
    --html-report reports/analysis.html

# With Grafana metrics
./analyze_results.py --locust-stats reports/test_stats.csv \
    --grafana-url http://localhost:3000

# CI/CD mode (exit code 1 if test fails)
./analyze_results.py --locust-stats reports/test_stats.csv \
    --no-grafana \
    --ci-mode
```

### Complete Workflow

```bash
# 1. Run load test with CSV output
locust -f src/locustfiles/workspace_operations.py \
    --headless \
    --users 50 \
    --spawn-rate 5 \
    --run-time 5m \
    --host https://tfe.example.com \
    --csv reports/loadtest

# 2. Analyze results
./analyze_results.py \
    --locust-stats reports/loadtest_stats.csv \
    --grafana-url http://localhost:3000 \
    --html-report reports/analysis.html

# 3. View HTML report
open reports/analysis.html
```

## Installation

The analysis tool is included in the main project. Ensure dependencies are installed:

```bash
# Install dependencies
pip install -r requirements.txt

# Make script executable (if needed)
chmod +x analyze_results.py
```

## Configuration

### Thresholds Configuration

Edit `config/analysis_thresholds.yaml` to customize performance thresholds:

```yaml
# Global thresholds
global:
  response_time:
    p95:
      good: 500      # < 500ms is excellent
      acceptable: 1000 # 500-1000ms is acceptable
  
  error_rate:
    good: 1.0        # < 1% is excellent
    acceptable: 5.0  # 1-5% is acceptable

# Operation-specific thresholds
operations:
  workspace_create:
    response_time:
      p95:
        good: 1000
        acceptable: 2000
    error_rate:
      good: 0.5
      acceptable: 2.0
```

### Grafana Configuration

Set up Grafana access:

```bash
# Option 1: Environment variable
export GRAFANA_API_KEY=your-api-key-here

# Option 2: Command-line argument
./analyze_results.py --grafana-api-key your-api-key-here ...
```

**Creating a Grafana API Key:**

1. Open Grafana: http://localhost:3000
2. Go to Configuration → API Keys
3. Click "Add API key"
4. Name: "TFE Load Test Analyzer"
5. Role: Viewer
6. Copy the generated key

## Command-Line Options

### Input Options

- `--locust-stats PATH` (required): Path to Locust statistics CSV file
- `--thresholds PATH`: Custom thresholds YAML file (default: `config/analysis_thresholds.yaml`)

### Grafana Options

- `--grafana-url URL`: Grafana URL (default: http://localhost:3000)
- `--grafana-api-key KEY`: Grafana API key (or use `GRAFANA_API_KEY` env var)
- `--test-duration MINUTES`: Test duration for Grafana queries (default: 5)
- `--no-grafana`: Skip Grafana metrics fetching

### Output Options

- `--html-report PATH`: Generate HTML report at specified path
- `--no-terminal`: Skip terminal report output
- `--summary-only`: Show only summary (for CI/CD)
- `--no-colors`: Disable colored terminal output

### Behavior Options

- `--ci-mode`: CI/CD mode - exit with code 1 if test fails
- `--verbose`, `-v`: Enable verbose logging

## Understanding the Reports

### Terminal Report

The terminal report includes:

1. **Overall Status**: Pass/fail and overall score (0-100)
2. **Summary Statistics**: Key metrics from the load test
3. **Metric Evaluations**: Detailed breakdown of each metric vs thresholds
4. **Grafana Metrics**: TFE infrastructure metrics (if enabled)
5. **Recommendations**: Actionable suggestions based on results

**Status Indicators:**
- ✅ **GOOD**: Metric within excellent threshold
- ⚠️ **ACCEPTABLE**: Metric within acceptable threshold
- ❌ **POOR**: Metric exceeded acceptable threshold (test fails)

### HTML Report

The HTML report provides:

- **Visual Score Display**: Large circular score indicator
- **Statistics Grid**: Key metrics in card format
- **Detailed Tables**: All metrics with color-coded status
- **Grafana Metrics**: Infrastructure metrics visualization
- **Recommendations**: Highlighted action items
- **Request Breakdown**: Per-operation statistics

**Opening HTML Reports:**

```bash
# macOS
open reports/analysis.html

# Linux
xdg-open reports/analysis.html

# Windows
start reports/analysis.html
```

## Metrics Evaluated

### Locust Metrics

- **Error Rate**: Percentage of failed requests
- **Response Times**: p50, p95, p99 percentiles
- **Throughput**: Requests per second
- **Per-Operation Metrics**: Individual operation performance

### Grafana Metrics (TFE Infrastructure)

- **Workspace Count**: Total and locked workspaces
- **Run Queue Depth**: Number of runs waiting in queue
- **Database Connections**: Active PostgreSQL connections
- **API Request Duration**: TFE API response times
- **API Error Rate**: TFE API error frequency
- **Transaction Rate**: Database transaction throughput

## Threshold Levels

Metrics are evaluated against three levels:

1. **Good** (✅): Excellent performance, no action needed
2. **Acceptable** (⚠️): Adequate performance, monitor
3. **Poor** (❌): Unacceptable performance, test fails

## Pass/Fail Criteria

A test **passes** if:
- Overall error rate ≤ acceptable threshold
- P95 response time ≤ acceptable threshold
- No individual metrics in "poor" state

A test **fails** if:
- Any metric exceeds acceptable threshold
- Error rate > 10% (automatic fail)
- P99 response time > 5000ms (automatic fail)

## CI/CD Integration

### GitHub Actions Example

```yaml
- name: Run Load Test
  run: |
    locust -f src/locustfiles/workspace_operations.py \
      --headless --users 50 --spawn-rate 5 --run-time 5m \
      --host ${{ secrets.TFE_URL }} \
      --csv reports/loadtest

- name: Analyze Results
  run: |
    ./analyze_results.py \
      --locust-stats reports/loadtest_stats.csv \
      --no-grafana \
      --html-report reports/analysis.html \
      --ci-mode

- name: Upload Report
  if: always()
  uses: actions/upload-artifact@v3
  with:
    name: load-test-report
    path: reports/analysis.html
```

### GitLab CI Example

```yaml
load_test:
  script:
    - locust -f src/locustfiles/workspace_operations.py --headless --users 50 --spawn-rate 5 --run-time 5m --host $TFE_URL --csv reports/loadtest
    - ./analyze_results.py --locust-stats reports/loadtest_stats.csv --no-grafana --html-report reports/analysis.html --ci-mode
  artifacts:
    when: always
    paths:
      - reports/analysis.html
    reports:
      junit: reports/analysis.xml
```

## Customization

### Custom Thresholds

Create a custom thresholds file:

```bash
cp config/analysis_thresholds.yaml config/custom_thresholds.yaml
# Edit config/custom_thresholds.yaml

# Use custom thresholds
./analyze_results.py \
    --locust-stats reports/test_stats.csv \
    --thresholds config/custom_thresholds.yaml
```

### Environment-Specific Thresholds

```bash
# Development environment (relaxed thresholds)
./analyze_results.py \
    --locust-stats reports/test_stats.csv \
    --thresholds config/thresholds_dev.yaml

# Production environment (strict thresholds)
./analyze_results.py \
    --locust-stats reports/test_stats.csv \
    --thresholds config/thresholds_prod.yaml
```

## Troubleshooting

### "Locust stats file not found"

Ensure you're using the correct path and that Locust generated the CSV file:

```bash
# Check if file exists
ls -la reports/loadtest_stats.csv

# Verify Locust command includes --csv flag
locust ... --csv reports/loadtest
```

### "Failed to connect to Grafana"

1. Verify Grafana is running: `curl http://localhost:3000/api/health`
2. Check API key is valid
3. Use `--no-grafana` to skip Grafana metrics

### "YAML parsing error"

Check your thresholds YAML file for syntax errors:

```bash
# Validate YAML syntax
python3 -c "import yaml; yaml.safe_load(open('config/analysis_thresholds.yaml'))"
```

### Low Throughput Causing Test Failure

If throughput is consistently low:

1. Increase `--users` in load test
2. Adjust throughput thresholds in config
3. Check if TFE instance is resource-constrained

## Examples

### Example 1: Quick Analysis

```bash
./analyze_results.py \
    --locust-stats reports/test_stats.csv \
    --no-grafana \
    --summary-only
```

Output:
```
Test Status: PASSED
Overall Score: 85.0/100
Total Requests: 1250
Error Rate: 0.80%
P95 Response Time: 450ms
Failed Metrics: 0
Warnings: 1
```

### Example 2: Full Analysis with Grafana

```bash
export GRAFANA_API_KEY=your-key-here

./analyze_results.py \
    --locust-stats reports/test_stats.csv \
    --grafana-url http://localhost:3000 \
    --test-duration 10 \
    --html-report reports/full_analysis.html
```

### Example 3: CI/CD Pipeline

```bash
#!/bin/bash
set -e

# Run load test
locust -f src/locustfiles/workspace_operations.py \
    --headless --users 100 --spawn-rate 10 --run-time 10m \
    --host https://tfe.example.com \
    --csv reports/loadtest

# Analyze with strict mode
./analyze_results.py \
    --locust-stats reports/loadtest_stats.csv \
    --thresholds config/thresholds_prod.yaml \
    --html-report reports/analysis.html \
    --ci-mode

echo "✅ Load test passed!"
```

## Best Practices

1. **Baseline First**: Run tests to establish baseline performance before setting thresholds
2. **Environment-Specific**: Use different thresholds for dev/staging/prod
3. **Regular Testing**: Run load tests regularly to catch performance regressions
4. **Monitor Trends**: Compare reports over time to identify trends
5. **Grafana Integration**: Always use Grafana metrics for production analysis
6. **Archive Reports**: Keep HTML reports for historical comparison

## Advanced Usage

### Programmatic Usage

```python
from src.analysis import LoadTestAnalyzer, GrafanaClient, HTMLReporter

# Create analyzer
analyzer = LoadTestAnalyzer(thresholds_file='config/analysis_thresholds.yaml')

# Optional: Setup Grafana
grafana = GrafanaClient(url='http://localhost:3000')

# Analyze
result = analyzer.analyze(
    locust_stats_file='reports/test_stats.csv',
    grafana_client=grafana
)

# Generate reports
if result.test_passed:
    print("✅ Test passed!")
else:
    print("❌ Test failed!")
    for issue in result.critical_issues:
        print(f"  - {issue.metric_name}: {issue.message}")

# Generate HTML report
reporter = HTMLReporter()
reporter.generate_report(result, 'reports/analysis.html')
```

## Support

For issues or questions:

1. Check this documentation
2. Review `config/analysis_thresholds.yaml` for threshold configuration
3. Run with `--verbose` for detailed logging
4. Check the main project README and AGENTS.md

---

**Last Updated**: 2026-05-11  
**Version**: 1.0.0
