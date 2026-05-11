# Quick Start Guide

Get up and running with the TFE Load Testing Framework in 5 minutes.

## Prerequisites

- Python 3.11 or higher
- TFE instance (local or cloud)
- TFE API token
- TFE organization

## Step 1: Clone and Setup

```bash
# Clone the repository (if not already done)
cd tfe-load-testing-framework

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Step 2: Configure Environment

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env with your values
nano .env  # or use your preferred editor
```

**Required variables:**
```bash
TFE_TOKEN=your-tfe-api-token-here
TFE_ORGANIZATION=your-organization-name
```

**Optional variables:**
```bash
TFE_HOSTNAME=tfe.localdemo.me  # or app.terraform.io for TFE Cloud
TFE_VERIFY_SSL=false           # true for production, false for local dev
```

## Step 3: Load Environment Variables

```bash
# Load the environment variables
source .env

# Verify they're set
echo $TFE_TOKEN
echo $TFE_ORGANIZATION
```

## Step 4: Run Your First Test

### Option A: Run All Tests (Recommended)

```bash
# Run all test scenarios with default settings
./run_all_tests.sh

# The script will:
# 1. Validate your environment
# 2. Run workspace operations test
# 3. Run run operations test
# 4. Run state operations test
# 5. Analyze each test
# 6. Generate reports in reports/run_TIMESTAMP/
```

### Option B: Run Individual Test

```bash
# Run just the workspace operations test
./examples/run_workspace_test.sh
```

## Step 5: View Results

After the tests complete, open the generated reports:

```bash
# The script will automatically open the index page
# Or manually open:
open reports/run_TIMESTAMP/index.html
```

## Common Issues

### Issue: "TFE_TOKEN environment variable is required"

**Solution:**
```bash
# Make sure you've loaded the .env file
source .env

# Verify the variable is set
echo $TFE_TOKEN
```

### Issue: "Virtual environment not found"

**Solution:**
```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Issue: SSL Certificate Errors

**Solution:**
```bash
# For local development with self-signed certificates
export TFE_VERIFY_SSL=false

# Or add to your .env file
echo "TFE_VERIFY_SSL=false" >> .env
source .env
```

### Issue: "Organization not found"

**Solution:**
```bash
# Verify your organization name is correct
# It should match exactly as shown in TFE
export TFE_ORGANIZATION=your-exact-org-name
```

## Next Steps

1. **Customize Test Parameters:**
   ```bash
   ./run_all_tests.sh --users 50 --spawn-rate 5 --run-time 10m
   ```

2. **Enable Grafana Metrics:**
   ```bash
   ./run_all_tests.sh --with-grafana --grafana-url http://localhost:3000
   ```

3. **Run in CI/CD:**
   ```bash
   ./run_all_tests.sh --ci-mode
   ```

4. **Read Full Documentation:**
   - [Run All Tests Guide](RUN_ALL_TESTS.md)
   - [Analysis Tool Guide](ANALYSIS_TOOL.md)
   - [Test Scenarios](tfe-load-testing-scenarios.md)

## Quick Reference

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TFE_TOKEN` | ✅ Yes | - | TFE API token |
| `TFE_ORGANIZATION` | ✅ Yes | - | TFE organization name |
| `TFE_HOSTNAME` | No | `tfe.localdemo.me` | TFE instance hostname |
| `TFE_VERIFY_SSL` | No | `true` | Verify SSL certificates |
| `CLEANUP_WORKSPACES` | No | `true` | Clean up test workspaces |

### Command-Line Options

```bash
./run_all_tests.sh [options]

Options:
  --users NUM          Number of concurrent users (default: 10)
  --spawn-rate NUM     User spawn rate per second (default: 2)
  --run-time TIME      Test duration (default: 5m)
  --host URL           TFE hostname (default: https://tfe.localdemo.me)
  --with-grafana       Include Grafana metrics
  --grafana-url URL    Grafana URL (default: http://localhost:3000)
  --skip-workspace     Skip workspace operations test
  --skip-run           Skip run operations test
  --skip-state         Skip state operations test
  --ci-mode            CI/CD mode (fail fast)
  --help               Show help message
```

## Support

For issues or questions:
1. Check the [Known Limitations](KNOWN_LIMITATIONS.md)
2. Review the [Troubleshooting Guide](RUN_ALL_TESTS.md#troubleshooting)
3. Check the main [README](../README.md)

---

**Last Updated**: 2026-05-11  
**Version**: 1.0.0
