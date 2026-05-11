# TFE Load Testing Framework

A comprehensive, open-source load testing framework specifically designed for **Terraform Enterprise (TFE)** using [Locust.io](https://locust.io/). This framework helps customers evaluate and optimize their TFE deployments under various load conditions.

> **🚀 New to the framework?** Start with the [Quick Start Guide](docs/QUICKSTART.md) for a 5-minute setup!



## 🎯 Purpose

This framework provides:
- Realistic TFE workload simulation
- Performance bottleneck identification
- Infrastructure capacity validation
- Performance baselines and benchmarks

## 🚀 Quick Start

### Prerequisites

- Python 3.11 or higher
- TFE instance (local or remote)
- TFE API token
- TFE organization

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd tfe-load-testing-framework
   ```

2. **Create virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your TFE credentials
   ```

### Running Your First Load Test

**Option 1: Run all tests sequentially (recommended)**
```bash
# Run all test scenarios with analysis
./run_all_tests.sh

# Custom configuration
./run_all_tests.sh --users 50 --spawn-rate 5 --run-time 10m

# With Grafana metrics
./run_all_tests.sh --with-grafana --grafana-url http://localhost:3000
```

See [docs/RUN_ALL_TESTS.md](docs/RUN_ALL_TESTS.md) for complete documentation.

**Option 2: Run individual tests**
```bash
# Headless mode (automated run)
./examples/run_workspace_test.sh

# Web UI mode (interactive)
./examples/run_workspace_test.sh web
```

**Option 2: Direct Locust command**
```bash
# Set environment variables
export TFE_HOSTNAME=tfe.localdemo.me
export TFE_TOKEN=your-token-here
export TFE_ORGANIZATION=your-org

# Run test
locust -f src/locustfiles/workspace_operations.py \
    --host https://tfe.localdemo.me \
    --users 10 \
    --spawn-rate 2 \
    --run-time 5m \
    --headless \
    --html reports/report.html
```

## 📁 Project Structure

```
tfe-load-testing-framework/
├── src/
│   ├── locustfiles/          # Locust test scenarios
│   │   ├── workspace_operations.py  # Workspace lifecycle tests
│   │   ├── run_operations.py        # Run lifecycle and queue tests
│   │   └── state_operations.py      # State management tests
│   ├── utils/                # Utility modules
│   │   └── tfe_client.py    # TFE API client wrapper
│   └── config/               # Configuration management
├── config/
│   └── tfe_config.yaml.example  # Configuration template
├── examples/
│   ├── .env.example                # Environment variables template
│   ├── run_workspace_test.sh       # Workspace test runner
│   ├── run_run_operations_test.sh  # Run operations test runner
│   └── run_state_operations_test.sh # State operations test runner
├── platform/
│   └── tfe/                 # Local TFE development environment
│       └── monitoring/      # Prometheus, Grafana, exporters
├── tests/                   # Unit and integration tests
├── reports/                 # Generated test reports
├── docs/                    # Documentation
└── requirements.txt         # Python dependencies
```

## 🧪 Available Test Scenarios

### 1. Workspace Operations (✅ Implemented)

Tests basic workspace lifecycle operations:
- **Create workspaces** - Simulates rapid workspace creation
- **List workspaces** - Tests pagination and filtering
- **Get workspace details** - Validates individual workspace retrieval
- **Delete workspaces** - Tests cleanup operations

**Configuration:**
```bash
# Environment variables
TFE_HOSTNAME=tfe.localdemo.me
TFE_TOKEN=your-token
TFE_ORGANIZATION=your-org
CLEANUP_WORKSPACES=true

# Locust parameters
LOCUST_USERS=10
LOCUST_SPAWN_RATE=2
LOCUST_RUN_TIME=5m
```

**Task Weights:**
- Create workspace: 10 (most frequent)
- List workspaces: 5
- Get workspace details: 3
- Delete workspace: 2

### 2. Run Operations (✅ Implemented)

Tests Terraform run lifecycle and queue management:
- **Create and upload configuration versions** - Generates and uploads Terraform configs
- **Trigger runs** - Creates plan and apply runs
- **Monitor run status** - Polls run progress
- **Queue multiple runs** - Tests queue depth handling
- **Cancel runs** - Tests run cancellation

**Run the test:**
```bash
./examples/run_run_operations_test.sh
```

**Task Weights:**
- Create and trigger run: 10 (most frequent)
- Monitor run status: 8
- Queue multiple runs: 3
- Cancel run: 2

### 3. State Operations (✅ Implemented)

Tests state management and file handling:
- **Upload state files** - Creates and uploads state versions
- **Download current state** - Retrieves latest state
- **List state versions** - Views state history
- **Download specific versions** - Retrieves historical state
- **Handle large state files** - Tests performance with large files

**Run the test:**
```bash
./examples/run_state_operations_test.sh
```

**Task Weights:**
- Upload state: 10 (most frequent)
- Download current state: 8
- List state versions: 5
- Download specific version: 3
- Upload large state: 2

## 🔧 Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# TFE Instance
TFE_HOSTNAME=tfe.localdemo.me
TFE_TOKEN=your-tfe-api-token
TFE_ORGANIZATION=your-org-name
TFE_VERIFY_SSL=false  # Set to true for production

# Test Configuration
CLEANUP_WORKSPACES=true

# Locust Settings
LOCUST_USERS=10
LOCUST_SPAWN_RATE=2
LOCUST_RUN_TIME=5m
```

### YAML Configuration (Advanced)

For more advanced configuration, copy and edit `config/tfe_config.yaml.example`:

```bash
cp config/tfe_config.yaml.example config/tfe_config.yaml
# Edit config/tfe_config.yaml
```

## 📊 Monitoring and Reporting

### Load Test Analysis Tool

The framework includes a comprehensive analysis tool that evaluates test results against configurable thresholds:

```bash
# Analyze test results with terminal report
./analyze_results.py --locust-stats reports/test_stats.csv --no-grafana

# Generate HTML report with Grafana metrics
./analyze_results.py \
    --locust-stats reports/test_stats.csv \
    --grafana-url http://localhost:3000 \
    --html-report reports/analysis.html

# CI/CD mode (exit code 1 if test fails)
./analyze_results.py \
    --locust-stats reports/test_stats.csv \
    --no-grafana \
    --ci-mode
```

**Features:**
- ✅ Automatic pass/fail evaluation against thresholds
- 📊 Grafana metrics integration (TFE infrastructure metrics)
- 🖥️ Colored terminal reports
- 📄 Beautiful HTML reports with charts
- 🤖 CI/CD ready with exit codes

See [docs/ANALYSIS_TOOL.md](docs/ANALYSIS_TOOL.md) for complete documentation.

### Built-in Reports

Locust generates HTML reports automatically:
```bash
reports/workspace_operations_YYYYMMDD_HHMMSS.html
```

### Metrics Tracked

- **Request metrics**: Response times (p50, p95, p99), failure rates
- **TFE-specific**: Workspace creation time, API error rates
- **System metrics**: Concurrent users, requests per second

### Integration with TFE Monitoring Stack

The framework integrates with the TFE monitoring stack (Prometheus + Grafana):

1. Start the TFE stack with monitoring:
   ```bash
   task tfe:up
   ```

2. Access dashboards:
   - Grafana: http://localhost:3000
   - Prometheus: http://localhost:9090

3. View TFE metrics during load tests:
   - Workspace counts
   - Run queue depth
   - API request latency
   - Database performance

## 🏃 Running Tests

### Headless Mode (Automated)

Best for CI/CD and automated testing:

```bash
locust -f src/locustfiles/workspace_operations.py \
    --host https://tfe.localdemo.me \
    --users 50 \
    --spawn-rate 5 \
    --run-time 10m \
    --headless \
    --html reports/report.html
```

### Web UI Mode (Interactive)

Best for development and experimentation:

```bash
locust -f src/locustfiles/workspace_operations.py \
    --host https://tfe.localdemo.me \
    --web-host 0.0.0.0 \
    --web-port 8089
```

Then open http://localhost:8089 in your browser.

### Custom Load Profiles

Adjust users and spawn rate for different scenarios:

**Light Load:**
```bash
--users 10 --spawn-rate 1 --run-time 5m
```

**Medium Load:**
```bash
--users 50 --spawn-rate 5 --run-time 15m
```

**Heavy Load:**
```bash
--users 200 --spawn-rate 10 --run-time 30m
```

## 🧰 Development

### Local TFE Setup

For local development and testing, use the included TFE stack:

```bash
# Check prerequisites
task check-prereqs

# Configure environment
cp platform/tfe/.env.example platform/tfe/.env
# Edit platform/tfe/.env with your TFE license

# Generate certificates
task generate-certs

# Start TFE
task tfe:up

# Check health
task tfe:health
```

See [AGENTS.md](AGENTS.md) for detailed setup instructions.

### Running Tests

```bash
# Unit tests
pytest tests/

# With coverage
pytest --cov=src tests/
```

### Code Quality

```bash
# Format code
black src/ tests/

# Lint
flake8 src/ tests/

# Type checking
mypy src/
```

## 📖 Documentation

- [AGENTS.md](AGENTS.md) - Detailed project documentation and development guide
- [docs/tfe-load-testing-scenarios.md](docs/tfe-load-testing-scenarios.md) - Comprehensive scenario documentation
- [Locust Documentation](https://docs.locust.io/) - Official Locust.io documentation
- [TFE API Documentation](https://developer.hashicorp.com/terraform/cloud-docs/api-docs) - TFE API reference

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📝 License

[License information to be added]

## 🆘 Troubleshooting

### Common Issues

**"TFE_TOKEN not configured"**
- Ensure `.env` file exists and contains `TFE_TOKEN`
- Verify token is valid in TFE

**"Connection refused"**
- Check TFE instance is running: `task tfe:health`
- Verify `TFE_HOSTNAME` is correct
- For local TFE, ensure using `tfe.localdemo.me`

**"SSL certificate verification failed"**
- For local development, set `TFE_VERIFY_SSL=false`
- For production, ensure valid SSL certificates

**"Rate limit exceeded"**
- Reduce `--users` or `--spawn-rate`
- Add delays between requests
- Use multiple API tokens

**"State download 401 errors (local dev only)"**
- Symptom: State uploads work, but downloads fail with 401 Unauthorized
- Root cause: Local MinIO presigned URLs have networking/signature limitations
- Impact: State download operations in load tests will show failures (~20-30% failure rate)
- Workaround: Test against production TFE instance for full functionality
- Note: This is a known limitation of the local dev environment, not a code issue
- All other operations (uploads, listing, API calls) work correctly at 100% success rate

### Getting Help

- Check [AGENTS.md](AGENTS.md) for detailed documentation
- Review [docs/tfe-load-testing-scenarios.md](docs/tfe-load-testing-scenarios.md)
- Open an issue on GitHub

## 🎯 Roadmap

- [x] Basic workspace operations scenario
- [x] Run operations scenario
- [x] State management scenario
- [x] Enhanced monitoring with system metrics (node-exporter)
- [ ] VCS integration scenario
- [ ] Variable management scenario
- [ ] Team and permissions scenario
- [ ] Custom metrics and dashboards
- [ ] Performance baseline reports
- [ ] CI/CD integration examples

---

**Status**: Production ready with documented limitations  
**Last Updated**: 2026-05-11