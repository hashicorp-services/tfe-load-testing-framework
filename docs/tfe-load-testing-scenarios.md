# TFE Load Testing Scenarios

**Document Purpose**: Research findings from TFE codebase analysis to identify realistic load testing scenarios for Locust-based framework.

**Last Updated**: 2026-05-06  
**Status**: Research Phase - Ready for Implementation

---

## Table of Contents

1. [Overview](#overview)
2. [TFE API Operations Identified](#tfe-api-operations-identified)
3. [Core Load Testing Scenarios](#core-load-testing-scenarios)
4. [Advanced Scenarios](#advanced-scenarios)
5. [Performance Bottleneck Areas](#performance-bottleneck-areas)
6. [Metrics to Monitor](#metrics-to-monitor)
7. [Implementation Recommendations](#implementation-recommendations)

---

## Overview

This document outlines load testing scenarios derived from analyzing the Terraform Enterprise (TFE) codebase, specifically the `release/shared/tfe` package which contains production-grade testing patterns used by HashiCorp for TFE validation.

### Key Findings

- **Primary API Endpoint**: `/api/v2/*` (JSON:API compliant)
- **Main Operations**: Workspaces, Runs, Organizations, State Versions, Configuration Versions
- **Concurrency Patterns**: TFE uses `errgroup` for concurrent operations with configurable limits
- **Rate Limiting**: Admin API has rate limiting middleware
- **Queue Management**: Redis-based queue for run management
- **Timeout Patterns**: Operations have configurable timeouts (typically 1-5 minutes)

---

## TFE API Operations Identified

### 1. Organization Operations

**Endpoints**:
- `POST /api/v2/organizations` - Create organization
- `GET /api/v2/organizations/:name` - Read organization
- `DELETE /api/v2/organizations/:name` - Delete organization
- `PATCH /api/v2/organizations/:name` - Update organization

**Characteristics**:
- Low frequency in production
- Foundation for all other operations
- Minimal resource impact

### 2. Workspace Operations

**Endpoints**:
- `POST /api/v2/organizations/:org/workspaces` - Create workspace
- `GET /api/v2/workspaces/:id` - Read workspace
- `GET /api/v2/organizations/:org/workspaces` - List workspaces (paginated)
- `PATCH /api/v2/workspaces/:id` - Update workspace
- `DELETE /api/v2/workspaces/:id` - Delete workspace

**Characteristics**:
- High frequency operation
- Supports pagination
- Can include related resources (current-run, current-state-version)
- Auto-apply and queue-all-runs settings affect behavior

**Code Reference**:
```go
// From release/shared/tfe/tfe.go
ws, createWsErr := client.c.Workspaces.Create(context.Background(), cmd.OrgName, cmd.Options)
```

### 3. Configuration Version Operations

**Endpoints**:
- `POST /api/v2/workspaces/:id/configuration-versions` - Create configuration version
- `PUT <upload-url>` - Upload configuration tarball
- `GET /api/v2/configuration-versions/:id` - Read configuration version

**Characteristics**:
- Two-phase operation: create + upload
- Upload uses presigned URL
- Polling required to confirm upload completion
- File size impacts upload time (typical: 1-50MB)

**Code Reference**:
```go
// From release/shared/tfe/tfe.go
cv, cvCreateErr := client.c.ConfigurationVersions.Create(ctx, cmd.Workspace.ID, cmd.Options)
if uploadErr := client.c.ConfigurationVersions.Upload(context.Background(), cv.UploadURL, cmd.SourceDir); uploadErr != nil {
    return nil, fmt.Errorf("error uploading configuration version data: %w", uploadErr)
}
```

### 4. Run Operations

**Endpoints**:
- `POST /api/v2/runs` - Create run
- `GET /api/v2/runs/:id` - Read run
- `GET /api/v2/workspaces/:id/runs` - List runs (paginated)
- `POST /api/v2/runs/:id/actions/cancel` - Cancel run
- `POST /api/v2/runs/:id/actions/force-cancel` - Force cancel run
- `POST /api/v2/runs/:id/actions/discard` - Discard run

**Run States**:
- `pending` → `plan_queued` → `planning` → `planned` → `cost_estimating` → `cost_estimated` → `policy_checking` → `policy_checked` → `apply_queued` → `applying` → `applied`
- Terminal states: `applied`, `canceled`, `discarded`, `errored`

**Characteristics**:
- Most resource-intensive operation
- Long-running (1-30+ minutes typical)
- Queue-based execution
- Polling required for status updates (10-second intervals typical)
- Auto-apply affects workflow

**Code Reference**:
```go
// From release/shared/tfe/tfe.go
run, runCreateErr := client.c.Runs.Create(ctx, options)

// Polling pattern
for finished := false; !finished; {
    select {
    case <-ctx.Done():
        return nil, fmt.Errorf("timed out polling run status")
    case <-time.After(10 * time.Second):
        polledRun, readRunErr = client.c.Runs.Read(ctx, runID)
        if slices.Contains(terminatedRunStates, polledRun.Status) {
            finished = true
        }
    }
}
```

### 5. State Version Operations

**Endpoints**:
- `GET /api/v2/workspaces/:id/current-state-version` - Read current state
- `GET /api/v2/state-versions/:id` - Read state version
- `GET <download-url>` - Download state file
- `POST /api/v2/workspaces/:id/state-versions` - Create state version (CLI-driven)

**Characteristics**:
- State files can be large (1MB-100MB+)
- Download uses presigned URL
- Encryption/decryption overhead
- Polling for finalization status

**Code Reference**:
```go
// From release/shared/tfe/smoke_tester.go
stateVersion, err := client.c.StateVersions.ReadCurrent(context.Background(), workspaceID)
stateVersionContent, err := client.c.StateVersions.Download(context.Background(), stateVersion.DownloadURL)
```

### 6. Apply Operations

**Endpoints**:
- `GET /api/v2/applies/:id` - Read apply
- `GET /api/v2/applies/:id/logs` - Stream apply logs

**Characteristics**:
- Part of run lifecycle
- Log streaming can be resource-intensive
- Long-running operation

### 7. Plan Operations

**Endpoints**:
- `GET /api/v2/plans/:id` - Read plan
- `GET /api/v2/plans/:id/logs` - Stream plan logs
- `GET /api/v2/plans/:id/json-output` - Get structured plan output

**Characteristics**:
- Part of run lifecycle
- Log streaming
- JSON output can be large

### 8. Variable Operations

**Endpoints**:
- `POST /api/v2/workspaces/:id/vars` - Create variable
- `GET /api/v2/workspaces/:id/vars` - List variables
- `PATCH /api/v2/vars/:id` - Update variable
- `DELETE /api/v2/vars/:id` - Delete variable

**Characteristics**:
- Moderate frequency
- Sensitive data handling (HCL, sensitive flag)
- Can trigger runs if auto-apply enabled

---

## Core Load Testing Scenarios

### Scenario 1: Workspace Creation Burst

**Objective**: Test TFE's ability to handle rapid workspace creation.

**Pattern**:
```python
# Locust task pattern
@task(weight=10)
def create_workspace(self):
    workspace_name = f"ws-{uuid.uuid4().hex[:8]}"
    response = self.client.post(
        f"/api/v2/organizations/{org_name}/workspaces",
        json={
            "data": {
                "type": "workspaces",
                "attributes": {
                    "name": workspace_name,
                    "auto-apply": True,
                    "queue-all-runs": True
                }
            }
        }
    )
```

**Load Profile**:
- Users: 10-50 concurrent
- Spawn rate: 5 users/second
- Duration: 5-10 minutes
- Expected: 100-500 workspaces created

**Success Criteria**:
- < 2 second response time (p95)
- < 1% error rate
- Database connection pool stable

### Scenario 2: Configuration Upload Storm

**Objective**: Test configuration version upload handling under load.

**Pattern**:
```python
@task(weight=15)
def upload_configuration(self):
    # Phase 1: Create configuration version
    cv_response = self.client.post(
        f"/api/v2/workspaces/{workspace_id}/configuration-versions",
        json={"data": {"type": "configuration-versions", "attributes": {"auto-queue-runs": False}}}
    )
    upload_url = cv_response.json()["data"]["attributes"]["upload-url"]
    
    # Phase 2: Upload tarball
    with open("config.tar.gz", "rb") as f:
        self.client.put(upload_url, data=f)
    
    # Phase 3: Poll for upload completion
    cv_id = cv_response.json()["data"]["id"]
    self.wait_for_upload(cv_id)
```

**Load Profile**:
- Users: 20-100 concurrent
- File sizes: 1MB, 10MB, 50MB (varied)
- Duration: 10-15 minutes

**Success Criteria**:
- Upload success rate > 99%
- Object storage (S3/MinIO) not saturated
- No upload URL expiration issues

### Scenario 3: Run Queue Saturation

**Objective**: Test run queue management and worker capacity.

**Pattern** (from TFE smoke test):
```python
@task(weight=20)
def trigger_run(self):
    # Create run
    run_response = self.client.post(
        "/api/v2/runs",
        json={
            "data": {
                "type": "runs",
                "relationships": {
                    "workspace": {"data": {"type": "workspaces", "id": workspace_id}}
                }
            }
        }
    )
    run_id = run_response.json()["data"]["id"]
    
    # Poll until terminal state
    self.poll_run_status(run_id, timeout=300)
```

**Load Profile**:
- Concurrent runs: 50-200
- Run duration: 1-5 minutes (simulated with sleep in Terraform)
- Workers: 5-10 (configurable in TFE)

**Success Criteria**:
- Queue depth manageable (< 100 pending)
- No run starvation
- Worker utilization 70-90%
- Run completion rate matches creation rate

**Code Reference**:
```go
// From release/shared/tfe/smoke_tester.go
errWaitGroup := errgroup.Group{}
errWaitGroup.SetLimit(cmd.WorkspaceCount)

for i := 0; i < cmd.WorkspaceCount; i++ {
    errWaitGroup.Go(client.dispatchSmokeTest(t, dispatchSmokeTestCmd{
        OrganizationName: org.Name,
        ExecutionID: cmd.ExecutionID,
        SourceModuleDir: cmd.TestModuleAbsPath,
        WorkspacesCh: workspacesCh,
        Timeout: timeout,
    }))
}
```

### Scenario 4: State File Download Concurrency

**Objective**: Test state file retrieval under concurrent load.

**Pattern**:
```python
@task(weight=8)
def download_state(self):
    # Get current state version
    state_response = self.client.get(
        f"/api/v2/workspaces/{workspace_id}/current-state-version"
    )
    download_url = state_response.json()["data"]["attributes"]["hosted-state-download-url"]
    
    # Download state file
    state_content = self.client.get(download_url)
    
    # Validate JSON
    json.loads(state_content.text)
```

**Load Profile**:
- Users: 50-200 concurrent
- State file sizes: 100KB-10MB
- Duration: 5-10 minutes

**Success Criteria**:
- Download success rate > 99.5%
- p95 latency < 5 seconds
- No presigned URL expiration issues
- Encryption/decryption not bottleneck

### Scenario 5: Mixed Workload (Realistic Usage)

**Objective**: Simulate realistic TFE usage patterns.

**Task Distribution**:
```python
class TFEUser(HttpUser):
    @task(5)
    def list_workspaces(self): pass
    
    @task(10)
    def create_workspace(self): pass
    
    @task(15)
    def upload_configuration(self): pass
    
    @task(25)
    def trigger_run(self): pass
    
    @task(8)
    def read_run_status(self): pass
    
    @task(5)
    def download_state(self): pass
    
    @task(3)
    def update_variables(self): pass
    
    @task(2)
    def cancel_run(self): pass
```

**Load Profile**:
- Users: 50-100 concurrent
- Think time: 5-15 seconds between tasks
- Duration: 30-60 minutes

**Success Criteria**:
- Overall error rate < 1%
- p95 response times within SLA
- No resource exhaustion
- Stable performance over duration

---

## Advanced Scenarios

### Scenario 6: VCS Webhook Flood

**Objective**: Test webhook processing capacity.

**Pattern**:
- Simulate GitHub/GitLab webhooks
- Trigger configuration version creation
- Auto-queue runs if enabled

**Load Profile**:
- 100-500 webhooks/minute
- Varied payload sizes

### Scenario 7: API Rate Limit Testing

**Objective**: Validate rate limiting behavior.

**Pattern**:
- Rapid API calls from single token
- Monitor 429 responses
- Test rate limit headers

**Code Reference**:
```go
// From pkg/admin_api/server/middleware/ratelimit.go
// Rate limiting is implemented in admin API
```

### Scenario 8: Long-Running Run Cancellation

**Objective**: Test run cancellation under load.

**Pattern**:
- Create long-running runs (10+ minutes)
- Cancel at various stages
- Monitor cleanup and resource release

### Scenario 9: Concurrent Organization Operations

**Objective**: Test multi-tenancy isolation.

**Pattern**:
- Multiple organizations
- Concurrent operations per org
- Verify no cross-org interference

### Scenario 10: State Locking Contention

**Objective**: Test state locking mechanism.

**Pattern**:
- Multiple runs on same workspace
- Verify proper queuing
- Test lock timeout handling

---

## Performance Bottleneck Areas

Based on codebase analysis, these areas are likely bottlenecks:

### 1. Database Connection Pool

**Location**: `pkg/database/db.go`

**Indicators**:
- Connection pool exhaustion
- Query timeout errors
- Slow transaction commits

**Monitoring**:
- Active connections
- Connection wait time
- Query execution time

### 2. Redis Queue

**Location**: `pkg/client/redis/queue.go`

**Indicators**:
- Queue depth growth
- Message processing lag
- Redis memory usage

**Monitoring**:
- Queue length
- Message throughput
- Redis CPU/memory

### 3. Object Storage (S3/MinIO)

**Location**: `pkg/objectstore/client.go`

**Indicators**:
- Upload/download failures
- Presigned URL expiration
- Bandwidth saturation

**Monitoring**:
- Request rate
- Error rate
- Bandwidth utilization

### 4. Worker Capacity

**Location**: `pkg/worker/worker.go`

**Indicators**:
- Run queue depth
- Worker utilization
- Run wait time

**Monitoring**:
- Active workers
- Queue depth
- Average run duration

### 5. TLS/Encryption Overhead

**Location**: `pkg/crypto/crypto.go`

**Indicators**:
- High CPU on encryption/decryption
- Slow state file operations

**Monitoring**:
- CPU usage
- Encryption operation latency

---

## Metrics to Monitor

### Application Metrics

From TFE monitoring stack (Prometheus + Grafana):

```yaml
# TFE-specific metrics (from platform/tfe/tfe-exporter)
- tfe_workspaces_total
- tfe_workspaces_locked
- tfe_runs_total{status}
- tfe_run_queue_depth
- tfe_api_request_duration_seconds
- tfe_api_requests_total{endpoint}
- tfe_api_errors_total{type}
```

### Database Metrics

```yaml
# PostgreSQL metrics
- pg_stat_database_numbackends  # Active connections
- pg_stat_database_xact_commit  # Transaction rate
- pg_stat_database_xact_rollback
- pg_locks  # Lock contention
```

### System Metrics

```yaml
# Standard metrics
- cpu_usage_percent
- memory_usage_percent
- disk_io_operations
- network_throughput
```

### Locust Metrics

```yaml
# Built-in Locust metrics
- requests_per_second
- response_time_percentiles (p50, p95, p99)
- failure_rate
- concurrent_users
```

---

## Implementation Recommendations

### 1. Test Data Management

**Approach**:
- Generate unique workspace names: `ws-{test_id}-{uuid}`
- Use test organization: `load-test-{timestamp}`
- Cleanup strategy: Delete after test or mark for cleanup

**Code Pattern**:
```python
class TFETestData:
    def __init__(self, org_name):
        self.org_name = org_name
        self.workspaces = []
    
    def cleanup(self):
        for ws in self.workspaces:
            self.delete_workspace(ws)
        self.delete_organization()
```

### 2. Authentication

**Approach**:
- Use TFE API tokens (user or team tokens)
- Rotate tokens if rate limited
- Store in environment variables

**Pattern**:
```python
class TFEUser(HttpUser):
    def on_start(self):
        self.client.headers.update({
            "Authorization": f"Bearer {os.getenv('TFE_TOKEN')}",
            "Content-Type": "application/vnd.api+json"
        })
```

### 3. Configuration Files

**Approach**:
- Pre-generate test Terraform configurations
- Vary sizes: small (1KB), medium (100KB), large (10MB)
- Include realistic resources (null_resource with sleep)

**Example**:
```hcl
# test-config/main.tf
resource "null_resource" "test" {
  provisioner "local-exec" {
    command = "sleep ${var.duration}"
  }
}

variable "duration" {
  default = 30
}
```

### 4. Polling Strategy

**Approach**:
- Use exponential backoff for polling
- Implement timeout handling
- Log polling iterations

**Pattern**:
```python
def poll_run_status(self, run_id, timeout=300):
    start_time = time.time()
    interval = 5
    
    while time.time() - start_time < timeout:
        response = self.client.get(f"/api/v2/runs/{run_id}")
        status = response.json()["data"]["attributes"]["status"]
        
        if status in ["applied", "errored", "canceled", "discarded"]:
            return status
        
        time.sleep(interval)
        interval = min(interval * 1.5, 30)  # Exponential backoff
    
    raise TimeoutError(f"Run {run_id} did not complete")
```

### 5. Error Handling

**Approach**:
- Distinguish between expected errors (429 rate limit) and failures
- Retry transient errors
- Log detailed error information

**Pattern**:
```python
@task
def create_workspace(self):
    try:
        response = self.client.post(...)
        if response.status_code == 429:
            # Rate limited - expected, not a failure
            self.environment.events.request.fire(
                request_type="POST",
                name="/api/v2/workspaces",
                response_time=response.elapsed.total_seconds() * 1000,
                response_length=len(response.content),
                exception=None,
                context={"rate_limited": True}
            )
        elif response.status_code >= 500:
            # Server error - retry
            raise Exception(f"Server error: {response.status_code}")
    except Exception as e:
        logger.error(f"Failed to create workspace: {e}")
        raise
```

### 6. Scenario Configuration

**Approach**:
- Use YAML for scenario definitions
- Support multiple load profiles
- Enable/disable scenarios dynamically

**Example**:
```yaml
# scenarios/workspace-burst.yaml
name: "Workspace Creation Burst"
duration: 600  # 10 minutes
users: 50
spawn_rate: 5
tasks:
  - name: create_workspace
    weight: 10
  - name: upload_configuration
    weight: 5
success_criteria:
  max_error_rate: 0.01
  max_p95_latency: 2000
```

### 7. Reporting

**Approach**:
- Generate HTML reports with Locust
- Export metrics to Prometheus
- Create custom dashboards in Grafana

**Integration**:
```python
# Export to Prometheus
from prometheus_client import Counter, Histogram

tfe_requests = Counter('tfe_requests_total', 'Total TFE API requests', ['endpoint', 'status'])
tfe_latency = Histogram('tfe_request_duration_seconds', 'TFE API request latency', ['endpoint'])
```

---

## Next Steps

1. **Implement Base Framework**
   - Set up Locust project structure
   - Create TFE API client wrapper
   - Implement authentication handling

2. **Develop Core Scenarios**
   - Start with Scenario 1 (Workspace Creation)
   - Add Scenario 2 (Configuration Upload)
   - Implement Scenario 3 (Run Queue)

3. **Add Monitoring**
   - Integrate with TFE monitoring stack
   - Set up Grafana dashboards
   - Configure alerting

4. **Validate Against Local TFE**
   - Use local TFE setup (platform/tfe)
   - Run baseline tests
   - Tune scenarios based on results

5. **Documentation**
   - Create user guide
   - Document scenario customization
   - Provide troubleshooting guide

---

## References

### TFE Codebase Locations

- **API Client**: `release/shared/tfe/tfe.go`
- **Smoke Tests**: `release/shared/tfe/smoke_tester.go`
- **E2E Tests**: `e2e/tfe.go`
- **Worker**: `pkg/worker/worker.go`
- **Queue**: `pkg/client/redis/queue.go`
- **Database**: `pkg/database/`
- **Rate Limiting**: `pkg/admin_api/server/middleware/ratelimit.go`

### External Resources

- [Locust Documentation](https://docs.locust.io/)
- [TFE API Documentation](https://developer.hashicorp.com/terraform/cloud-docs/api-docs)
- [go-tfe SDK](https://github.com/hashicorp/go-tfe)

---

**End of Document**
