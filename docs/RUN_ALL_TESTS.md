# Run All Tests Script

Automated script to run all TFE load test scenarios sequentially with comprehensive analysis and reporting.

## Overview

The `run_all_tests.sh` script provides a convenient way to:
- Run all load test scenarios in sequence
- Automatically analyze each test with threshold evaluation
- Generate comprehensive reports (Locust + Analysis)
- Create an index page for easy navigation
- Support CI/CD integration with exit codes

## Quick Start

```bash
# Basic usage (default settings)
./run_all_tests.sh

# Custom configuration
./run_all_tests.sh \
    --users 50 \
    --spawn-rate 5 \
    --run-time 10m \
    --host https://tfe.example.com

# With Grafana metrics
./run_all_tests.sh \
    --users 50 \
    --with-grafana \
    --grafana-url http://localhost:3000

# CI/CD mode (fail fast)
./run_all_tests.sh --ci-mode
```

## Command-Line Options

### Load Test Configuration

- `--users NUM` - Number of concurrent users (default: 10)
- `--spawn-rate NUM` - User spawn rate per second (default: 2)
- `--run-time TIME` - Test duration (e.g., 5m, 30s, 1h) (default: 5m)
- `--host URL` - TFE hostname (default: https://tfe.localdemo.me)

### Analysis Configuration

- `--with-grafana` - Include Grafana metrics in analysis
- `--grafana-url URL` - Grafana URL (default: http://localhost:3000)

### Test Selection

- `--skip-workspace` - Skip workspace operations test
- `--skip-run` - Skip run operations test
- `--skip-state` - Skip state operations test

### Behavior

- `--ci-mode` - CI/CD mode: fail fast on first failure, exit with code 1 if any test fails
- `--help` - Show help message

## Output Structure

All reports are organized in timestamped directories:

```
reports/
└── run_20260507_153000/
    ├── index.html                          # Navigation page
    ├── workspace_operations_stats.csv      # Locust CSV stats
    ├── workspace_operations_locust.html    # Locust HTML report
    ├── workspace_operations_analysis.html  # Analysis report
    ├── run_operations_stats.csv
    ├── run_operations_locust.html
    ├── run_operations_analysis.html
    ├── state_operations_stats.csv
    ├── state_operations_locust.html
    └── state_operations_analysis.html
```

## Examples

### Example 1: Quick Local Test

```bash
# Run all tests with default settings
./run_all_tests.sh

# Output:
# =================================
# TFE Load Testing Framework
# =================================
# 
# 📋 Test Configuration
#   Users: 10
#   Spawn Rate: 2/s
#   Run Time: 5m
#   Host: https://tfe.localdemo.me
#   Grafana: false
#   Report Directory: reports/run_20260507_153000
# 
# Running tests...
```

### Example 2: Production Load Test

```bash
# Heavy load test against production TFE
./run_all_tests.sh \
    --users 100 \
    --spawn-rate 10 \
    --run-time 30m \
    --host https://tfe.production.example.com \
    --with-grafana \
    --grafana-url https://grafana.example.com
```

### Example 3: Selective Testing

```bash
# Run only workspace and run tests (skip state)
./run_all_tests.sh \
    --users 50 \
    --skip-state
```

### Example 4: CI/CD Pipeline

```bash
#!/bin/bash
# CI/CD pipeline script

# Run tests in CI mode (fail fast)
./run_all_tests.sh \
    --users 50 \
    --spawn-rate 5 \
    --run-time 10m \
    --host $TFE_URL \
    --ci-mode

# Exit code will be 1 if any test fails
```

## Understanding the Output

### Terminal Output

The script provides real-time feedback:

```
=================================
Running: Workspace Operations Test
=================================
🚀 Starting load test...
✅ Load test completed

📊 Analyzing results...
✅ Analysis passed

Reports generated:
  - Locust HTML: reports/run_20260507_153000/workspace_operations_locust.html
  - Analysis HTML: reports/run_20260507_153000/workspace_operations_analysis.html
  - CSV Stats: reports/run_20260507_153000/workspace_operations_stats.csv
```

### Summary Report

At the end, you'll see a summary:

```
=================================
Test Run Summary
=================================

📊 Results
  Tests Run: 3
  Tests Passed: 2
  Tests Failed: 1
  Duration: 450s

❌ Failed Tests:
  - State Operations Test (analysis)

📁 All Reports Location
  reports/run_20260507_153000/
```

### Index Page

The script automatically creates an `index.html` page with:
- Summary statistics
- Links to all reports
- Easy navigation between tests

## CI/CD Integration

### GitHub Actions

```yaml
name: Load Tests

on:
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM
  workflow_dispatch:

jobs:
  load-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          python -m venv venv
          source venv/bin/activate
          pip install -r requirements.txt
      
      - name: Run load tests
        run: |
          source venv/bin/activate
          ./run_all_tests.sh \
            --users 50 \
            --spawn-rate 5 \
            --run-time 10m \
            --host ${{ secrets.TFE_URL }} \
            --ci-mode
      
      - name: Upload reports
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: load-test-reports
          path: reports/run_*/
```

### GitLab CI

```yaml
load_tests:
  stage: test
  script:
    - python -m venv venv
    - source venv/bin/activate
    - pip install -r requirements.txt
    - |
      ./run_all_tests.sh \
        --users 50 \
        --spawn-rate 5 \
        --run-time 10m \
        --host $TFE_URL \
        --ci-mode
  artifacts:
    when: always
    paths:
      - reports/run_*/
    expire_in: 30 days
  only:
    - schedules
    - web
```

### Jenkins

```groovy
pipeline {
    agent any
    
    triggers {
        cron('H 2 * * *')  // Daily at 2 AM
    }
    
    stages {
        stage('Setup') {
            steps {
                sh '''
                    python3 -m venv venv
                    . venv/bin/activate
                    pip install -r requirements.txt
                '''
            }
        }
        
        stage('Load Tests') {
            steps {
                sh '''
                    . venv/bin/activate
                    ./run_all_tests.sh \
                        --users 50 \
                        --spawn-rate 5 \
                        --run-time 10m \
                        --host ${TFE_URL} \
                        --ci-mode
                '''
            }
        }
    }
    
    post {
        always {
            publishHTML([
                reportDir: 'reports',
                reportFiles: 'run_*/index.html',
                reportName: 'Load Test Reports'
            ])
        }
    }
}
```

## Troubleshooting

### "Virtual environment not activated"

The script will automatically activate the virtual environment if it exists:

```bash
# If you see this warning, the script handles it automatically
⚠️  Virtual environment not activated. Activating...
```

If the venv doesn't exist:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Tests Failing in CI Mode

CI mode stops on the first failure. To see all results:

```bash
# Run without CI mode to see all test results
./run_all_tests.sh --users 50
```

### Grafana Connection Issues

If Grafana metrics fail:

```bash
# Test Grafana connection
curl http://localhost:3000/api/health

# Run without Grafana
./run_all_tests.sh --users 50  # (--with-grafana not specified)
```

### Long Test Duration

For quick validation:

```bash
# Short test run
./run_all_tests.sh \
    --users 5 \
    --run-time 1m
```

## Best Practices

1. **Start Small**: Begin with low user counts and short durations
   ```bash
   ./run_all_tests.sh --users 5 --run-time 2m
   ```

2. **Gradual Increase**: Incrementally increase load
   ```bash
   ./run_all_tests.sh --users 10 --run-time 5m
   ./run_all_tests.sh --users 25 --run-time 10m
   ./run_all_tests.sh --users 50 --run-time 15m
   ```

3. **Monitor Resources**: Watch TFE resources during tests
   - Check Grafana dashboards
   - Monitor database connections
   - Watch run queue depth

4. **Regular Testing**: Schedule regular load tests
   - Daily smoke tests (low load)
   - Weekly comprehensive tests (medium load)
   - Monthly stress tests (high load)

5. **Archive Reports**: Keep historical reports for trend analysis
   ```bash
   # Archive old reports
   tar -czf reports_archive_$(date +%Y%m).tar.gz reports/run_*
   ```

6. **Review Failures**: Always investigate failed tests
   - Check analysis reports for threshold violations
   - Review Locust reports for error patterns
   - Examine TFE logs for issues

## Advanced Usage

### Custom Test Sequence

Create a custom script for specific scenarios:

```bash
#!/bin/bash
# custom_test_sequence.sh

# Phase 1: Light load
./run_all_tests.sh --users 10 --run-time 5m

# Phase 2: Medium load
./run_all_tests.sh --users 50 --run-time 10m

# Phase 3: Heavy load
./run_all_tests.sh --users 100 --run-time 15m

# Phase 4: Stress test
./run_all_tests.sh --users 200 --run-time 20m
```

### Parallel Testing

Run different scenarios in parallel (use with caution):

```bash
# Terminal 1
./run_all_tests.sh --skip-run --skip-state --users 50 &

# Terminal 2
./run_all_tests.sh --skip-workspace --skip-state --users 50 &

# Terminal 3
./run_all_tests.sh --skip-workspace --skip-run --users 50 &

wait
```

## Related Documentation

- [Analysis Tool Documentation](ANALYSIS_TOOL.md)
- [Test Scenarios](tfe-load-testing-scenarios.md)
- [Main README](../README.md)
- [Known Limitations](KNOWN_LIMITATIONS.md)

---

**Last Updated**: 2026-05-07  
**Version**: 1.0.0
