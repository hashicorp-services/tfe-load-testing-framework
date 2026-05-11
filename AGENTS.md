# AGENTS.md

This file provides guidance to agents when working with code in this repository.

## Project Overview

**TFE Load Testing Framework** is a load testing tool/suite designed specifically for **Terraform Enterprise (TFE)** to help customers evaluate and optimize their TFE deployments under various load conditions.

### Project Purpose
This framework provides customers with a comprehensive, open-source solution to:
- Simulate realistic TFE workloads and usage patterns
- Identify performance bottlenecks in TFE deployments
- Validate infrastructure capacity and scaling requirements
- Establish performance baselines and benchmarks

### Key Requirements
- **Customer-Shareable**: Designed from the ground up to be distributed to customers
- **Open Source Only**: Uses only OSS tooling to ensure transparency and accessibility
- **TFE-Specific**: Focuses on the most relevant Terraform Enterprise operations and workflows

### Technology Stack
- **Load Testing Framework**: [Locust.io](https://locust.io/) - Python-based, open-source load testing tool
- **Language**: Python 3.x
- **Target Platform**: Terraform Enterprise (TFE)
- **Configuration**: YAML/JSON for test scenarios and TFE connection parameters

## Project Structure

```
tfe-load-testing-framework/
├── platform/
│   └── tfe/               # Local TFE development environment
│       ├── certs/         # TLS certificates
│       ├── .env           # Environment configuration (not in git)
│       ├── .env.example   # Environment template
│       └── podman-compose.yml  # TFE stack definition
├── scripts/               # Setup and utility scripts
│   ├── check-prereqs.sh   # Verify prerequisites
│   └── generate-dev-certs.sh  # Generate TLS certificates
├── src/
│   ├── locustfiles/       # Locust test definitions
│   ├── scenarios/         # TFE-specific test scenarios
│   ├── utils/             # Helper functions and utilities
│   └── config/            # Configuration management
├── tests/                 # Unit and integration tests
├── examples/              # Example configurations and usage
├── docs/                  # Documentation
│   ├── setup.md          # Setup and installation guide
│   ├── scenarios.md      # Available test scenarios
│   └── customization.md  # How to customize tests
├── config/
│   ├── tfe_config.yaml   # TFE connection configuration
│   └── scenarios.yaml    # Test scenario definitions
├── requirements.txt       # Python dependencies
├── Makefile               # Build and management tasks
├── Taskfile.yml           # Task runner configuration
├── README.md             # Project overview and quick start
└── LICENSE               # Open source license
```

## Monitoring Stack

The framework includes a complete monitoring solution integrated into the TFE stack:

### Components

1. **Prometheus** - Metrics collection and storage
   - Scrapes metrics every 15 seconds
   - Stores time-series data for analysis
   - Available at: http://localhost:9090

2. **Grafana** - Visualization and dashboards
   - Pre-configured TFE Load Testing Overview dashboard
   - Default credentials: admin/admin (configurable via .env)
   - Available at: http://localhost:3000

3. **TFE Exporter** - Custom Python exporter for TFE metrics
   - Workspace counts and status
   - Run queue depth and status distribution
   - API request latency (p50, p95)
   - API error rates
   - Requires TFE_TOKEN and TFE_ORGANIZATION
   - Metrics endpoint: http://localhost:9101/metrics

4. **PostgreSQL Exporter** - Database performance metrics
   - Active connections
   - Transaction rates (commits/rollbacks)
   - Query performance
   - Metrics endpoint: http://localhost:9187/metrics

### Monitored Metrics

**TFE Metrics:**
- `tfe_workspaces_total` - Total number of workspaces
- `tfe_workspaces_locked` - Number of locked workspaces
- `tfe_runs_total{status}` - Total runs by status
- `tfe_run_queue_depth` - Number of runs in queue
- `tfe_api_request_duration_seconds` - API request latency histogram
- `tfe_api_requests_total` - Total API requests by endpoint
- `tfe_api_errors_total` - API errors by type

**Database Metrics:**
- `pg_stat_database_numbackends` - Active database connections
- `pg_stat_database_xact_commit` - Transaction commit rate
- `pg_stat_database_xact_rollback` - Transaction rollback rate

### Configuration

Update `platform/tfe/.env` with monitoring credentials:

```bash
# Monitoring Configuration
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=admin
TFE_TOKEN=<your-tfe-api-token>
TFE_ORGANIZATION=<your-org-name>
```

**Important:** The TFE exporter requires a valid TFE API token and organization name to collect metrics. Create these in TFE after initial setup.

### Accessing Dashboards

After starting the stack with `task tfe:up`:

1. **Grafana Dashboard:**
   - URL: http://localhost:3000
   - Login: admin/admin (or configured credentials)
   - Navigate to: Dashboards → TFE Load Testing Overview

2. **Prometheus UI:**
   - URL: http://localhost:9090
   - Explore metrics and run PromQL queries

3. **Raw Metrics:**
   - TFE Exporter: http://localhost:9101/metrics
   - PostgreSQL Exporter: http://localhost:9187/metrics

## TFE Test Scenarios

The framework should define tests for the most relevant TFE operations:

### Core TFE Operations to Test
1. **Workspace Operations**
   - Create/update/delete workspaces
   - List workspaces with pagination
   - Workspace variable management

2. **Run Operations**
   - Trigger runs (plan/apply)
   - Queue multiple runs
   - Monitor run status
   - Handle run cancellations

3. **State Management**
   - State file uploads/downloads
   - State version listing
   - State locking operations

4. **VCS Integration**
   - Webhook processing
   - Repository connection operations
   - Commit-triggered runs

5. **API Operations**
   - Authentication and token management
   - Rate limiting behavior
   - Concurrent API requests

6. **Configuration Version Operations**
   - Upload configuration files
   - Create configuration versions
   - Handle large configuration uploads

## Local Development Setup

### Running TFE Locally with Docker Compose

For local development and testing, you can spin up a complete TFE environment using Docker Compose. This setup includes:
- **PostgreSQL**: Database backend for TFE
- **MinIO**: S3-compatible object storage
- **TFE**: Terraform Enterprise container in external operational mode

### Prerequisites

- **Podman** and **podman-compose** installed (recommended)
- Alternatively: Docker and Docker Compose
- TFE license file
- At least 4GB RAM available for containers
- **Task** (optional, for task runner) - Install via: `brew install go-task/tap/go-task`

#### Quick Setup

```bash
# 1. Check prerequisites
task check-prereqs

# 2. Copy and configure environment
cp platform/tfe/.env.example platform/tfe/.env
# Edit platform/tfe/.env with your TFE license and configuration

# 3. Generate TLS certificates
task generate-certs

# 4. Detect correct host alias IP
task detect-host-alias-ip
# Update TFE_HOST_ALIAS_IP in platform/tfe/.env with detected value

# 5. Verify configuration
task check-tfe-env

# 6. Start TFE
task tfe:up

# 7. Monitor startup
task tfe:logs

# 8. Check health
task tfe:health
```

#### Environment Configuration

The `platform/tfe/.env` file contains all TFE configuration. Key variables:

```bash
# TFE Configuration
TFE_IMAGE=images.releases.hashicorp.com/hashicorp/terraform-enterprise:1.0.3
TFE_LICENSE=<your-tfe-license-content>
TFE_HOSTNAME=tfe.localdemo.me
TFE_HTTPS_PORT=443
TFE_ENCRYPTION_PASSWORD=<generate-strong-password>
TFE_IACT_SUBNETS=10.88.0.0/16,127.0.0.1/32

# IMPORTANT: Host alias for CLI-driven runs
# macOS Podman: 192.168.127.254
# Linux Podman: 10.88.0.1
TFE_HOST_ALIAS_IP=192.168.127.254

# Podman Socket
# macOS: /run/podman/podman.sock (rootful)
# Linux: /tmp/podman.sock
PODMAN_SOCKET=/run/podman/podman.sock

# Database Configuration
TFE_DATABASE_NAME=tfe
TFE_DATABASE_USER=postgres
TFE_DATABASE_PASSWORD=<generate-strong-password>
TFE_DATABASE_PARAMETERS=sslmode=disable

# Object Storage (MinIO)
MINIO_ROOT_USER=minio
MINIO_ROOT_PASSWORD=<generate-strong-password>
TFE_OBJECT_STORAGE_S3_REGION=us-east-1
TFE_OBJECT_STORAGE_S3_BUCKET=tfe-state
```

#### TLS Certificates

Certificates are automatically generated using the provided script:

```bash
# Generate certificates for tfe.localdemo.me
task generate-certs

# Or manually with custom hostname
./scripts/generate-dev-certs.sh custom.hostname.local
```

Certificates are stored in `platform/tfe/certs/`:
- `cert.pem` - Server certificate
- `key.pem` - Private key
- `bundle.pem` - Certificate bundle
- `ca.pem` - CA certificate (for trusting)

#### Host Configuration

The hostname `tfe.localdemo.me` resolves to 127.0.0.1 via public DNS, so no `/etc/hosts` modification is needed.

If using a custom hostname, add it to `/etc/hosts`:

```bash
echo "127.0.0.1 custom.hostname.local" | sudo tee -a /etc/hosts
```

#### Initial TFE Setup

1. Access the admin console: `https://terraform.local:8800`
2. Complete the initial setup wizard
3. Create an organization and user account
4. Generate an API token for load testing

#### Stopping and Cleaning Up

```bash
# Stop services
task tfe:down

# Stop and remove volumes (clean slate)
podman-compose --env-file platform/tfe/.env -f platform/tfe/podman-compose.yml down -v

# Regenerate certificates if needed
task generate-certs
```

#### Troubleshooting Local Setup

**TFE container fails to start:**
- Check logs: `task tfe:logs`
- Verify license is valid in `platform/tfe/.env`
- Run health check: `task tfe:health`
- Verify environment: `task check-tfe-env`

**Cannot access TFE web interface:**
- URL: `https://tfe.localdemo.me` (resolves via public DNS)
- Admin console: `https://tfe.localdemo.me:8800`
- Accept self-signed certificate in browser
- Or trust CA: `platform/tfe/certs/ca.pem`

**Podman socket errors:**
- Get correct socket: `task podman-socket`
- Update `PODMAN_SOCKET` in `platform/tfe/.env`
- Ensure using rootful Podman (not rootless)
- macOS: Switch to rootful connection if needed

**Port 443 blocked (macOS Podman machine):**
- Run: `task podman-machine-allow-443`
- Or use alternative: Set `TFE_HTTPS_PORT=8443` in `platform/tfe/.env`

**Host alias errors (CLI-driven runs fail):**
- Symptom: Archivist callbacks fail with connection errors
- Detect correct IP: `task detect-host-alias-ip`
- Update `TFE_HOST_ALIAS_IP` in `platform/tfe/.env`
- macOS typical: `192.168.127.254`
- Linux typical: `10.88.0.1`

**Database connection errors:**
- Ensure PostgreSQL is healthy: Check logs with `task tfe:logs`
- Verify credentials in `platform/tfe/.env` match

**Object storage errors:**
- Check MinIO status in logs: `task tfe:logs`
- Verify MinIO bucket creation completed successfully

**State download 401 errors (presigned URLs):**
- Symptom: State uploads work, but downloads fail with 401 Unauthorized
- Root cause: Local MinIO presigned URLs have networking/signature limitations
- Impact: State download operations in load tests will show failures
- Workaround: Test against production TFE instance for full functionality
- Note: This is a known limitation of the local dev environment, not a code issue
- All other operations (uploads, listing, API calls) work correctly

## Development Guidelines

### Getting Started

```bash
# Install dependencies
pip install -r requirements.txt

# Configure TFE connection
cp config/tfe_config.yaml.example config/tfe_config.yaml
# Edit config/tfe_config.yaml with your TFE instance details

# Run a basic load test
locust -f src/locustfiles/basic_tfe_test.py --host=https://your-tfe-instance.com

# Run with web UI
locust -f src/locustfiles/basic_tfe_test.py --host=https://your-tfe-instance.com --web-host=0.0.0.0
```

### Locust.io Best Practices

1. **Task Organization**
   - Group related TFE operations into task sets
   - Use appropriate wait times between tasks to simulate realistic user behavior
   - Implement proper error handling for API failures

2. **Authentication**
   - Securely manage TFE API tokens
   - Support both user tokens and team tokens
   - Never commit credentials to the repository

3. **Test Data Management**
   - Generate unique workspace names to avoid conflicts
   - Clean up test resources after runs (optional cleanup mode)
   - Use realistic data sizes for configuration uploads

4. **Metrics and Reporting**
   - Track TFE-specific metrics (run duration, queue times, etc.)
   - Monitor API rate limits
   - Generate customer-friendly reports

### Code Quality Standards

1. **Python Style**
   - Follow PEP 8 style guidelines
   - Use type hints for function signatures
   - Write docstrings for all public functions and classes

2. **Testing**
   - Unit tests for utility functions
   - Integration tests for TFE API interactions
   - Mock TFE responses for offline testing

3. **Documentation**
   - Clear README with quick start guide
   - Document all configuration options
   - Provide example scenarios for common use cases
   - Include troubleshooting section

4. **Security**
   - Never log or expose API tokens
   - Validate all configuration inputs
   - Use environment variables for sensitive data
   - Include security best practices in documentation

### Customer-Facing Considerations

Since this tool will be shared with customers:

- **Clear Documentation**: Assume users may not be familiar with Locust.io
- **Easy Setup**: Minimize configuration complexity
- **Helpful Examples**: Provide ready-to-use test scenarios
- **Error Messages**: Make error messages clear and actionable
- **Support**: Include troubleshooting guide and FAQ
- **Licensing**: Ensure all dependencies are OSS-compatible

## Configuration Management

### TFE Connection Configuration
```yaml
# config/tfe_config.yaml
tfe:
  hostname: "app.terraform.io"  # or your TFE instance
  organization: "your-org"
  token: "${TFE_TOKEN}"  # Use environment variable
  
load_test:
  users: 10
  spawn_rate: 1
  run_time: "5m"
```

### Test Scenario Configuration
```yaml
# config/scenarios.yaml
scenarios:
  - name: "workspace_operations"
    weight: 30
    tasks:
      - create_workspace
      - update_variables
      - trigger_run
      
  - name: "state_operations"
    weight: 20
    tasks:
      - upload_state
      - download_state
```

## Implementation Status

### ✅ Completed

1. **Initial Setup**
   - [x] Set up Python project structure
   - [x] Create requirements.txt with Locust.io and dependencies
   - [x] Implement TFE API client wrapper (`src/utils/tfe_client.py`)
   - [x] Create basic Locust task for workspace creation

2. **Core Scenarios**
   - [x] Implement workspace lifecycle tests (`src/locustfiles/workspace_operations.py`)
   - [x] Implement run operations tests (`src/locustfiles/run_operations.py`)
   - [x] Implement state management tests (`src/locustfiles/state_operations.py`)
   - [x] Full Locust metrics tracking for all operations

3. **Documentation**
   - [x] Write comprehensive README
   - [x] Create setup guide for customers
   - [x] Document available test scenarios (`docs/tfe-load-testing-scenarios.md`)
   - [x] Add troubleshooting guide (README.md + AGENTS.md)
   - [x] Document known limitations (`docs/KNOWN_LIMITATIONS.md`)

4. **Testing & Validation**
   - [x] Test against local TFE instance
   - [x] Validate with different load profiles
   - [x] Identify and document local dev environment limitations

5. **Monitoring & Observability**
   - [x] Prometheus integration
   - [x] Grafana dashboards
   - [x] Custom TFE exporter
   - [x] PostgreSQL exporter
   - [x] Node exporter


6. **Analysis & Reporting**
   - [x] Load test analysis tool with threshold evaluation
   - [x] Terminal and HTML report generation
   - [x] Grafana metrics integration
   - [x] CI/CD mode with exit codes
   - [x] run_all_tests.sh orchestration script


### 🚧 Future Enhancements

- [ ] VCS integration tests
- [ ] Variable management scenario
- [ ] Team and permissions scenario
- [ ] Custom metrics and dashboards
- [ ] Performance baseline reports
- [ ] CI/CD integration examples
- [ ] Get customer feedback
- [ ] Refine based on real-world usage

## Resources

### Locust.io Documentation
- [Locust.io Official Docs](https://docs.locust.io/)
- [Writing Locustfiles](https://docs.locust.io/en/stable/writing-a-locustfile.html)
- [Locust API Reference](https://docs.locust.io/en/stable/api.html)

### Terraform Enterprise
- [TFE API Documentation](https://developer.hashicorp.com/terraform/cloud-docs/api-docs)
- [TFE Architecture](https://developer.hashicorp.com/terraform/enterprise/architecture)
- [TFE Performance Considerations](https://developer.hashicorp.com/terraform/enterprise/admin/infrastructure/monitoring)

### Load Testing Best Practices
- Gradual ramp-up to identify breaking points
- Realistic user behavior simulation
- Comprehensive metrics collection
- Clear reporting and visualization

---

**Last Updated**: 2026-05-11  
**Status**: Production ready with documented limitations