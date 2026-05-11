# Testing the Workspace Operations Load Test

This document provides instructions for testing the workspace operations load test implementation.

## Prerequisites

Before testing, ensure you have:

1. **Local TFE instance running** (or access to a TFE instance)
2. **TFE organization created**
3. **TFE API token generated**
4. **Python 3.8+ installed**

## Setting Up Local TFE (Recommended for Testing)

If you don't have a TFE instance, use the included local setup:

```bash
# 1. Check prerequisites
task check-prereqs

# 2. Configure TFE environment
cp platform/tfe/.env.example platform/tfe/.env
# Edit platform/tfe/.env - add your TFE license

# 3. Generate certificates
task generate-certs

# 4. Detect host alias IP
task detect-host-alias-ip
# Update TFE_HOST_ALIAS_IP in platform/tfe/.env

# 5. Start TFE stack
task tfe:up

# 6. Wait for TFE to be ready (2-3 minutes)
task tfe:logs  # Monitor startup

# 7. Check health
task tfe:health
```

## Initial TFE Setup

1. **Access TFE web interface**: https://tfe.localdemo.me
   - Accept self-signed certificate warning

2. **Complete initial setup**:
   - Create admin account
   - Create organization (e.g., "loadtest-org")

3. **Generate API token**:
   - Go to User Settings → Tokens
   - Create new token
   - Copy token for next step

## Configure Load Test Environment

```bash
# 1. Copy environment template
cp .env.example .env

# 2. Edit .env with your values
nano .env  # or your preferred editor
```

Example `.env` configuration:
```bash
TFE_HOSTNAME=tfe.localdemo.me
TFE_TOKEN=your-token-from-step-3
TFE_ORGANIZATION=loadtest-org
TFE_VERIFY_SSL=false

CLEANUP_WORKSPACES=true

LOCUST_USERS=5
LOCUST_SPAWN_RATE=1
LOCUST_RUN_TIME=2m
```

## Install Python Dependencies

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Run Test Scenarios

### Test 1: Minimal Load (Smoke Test)

Verify basic functionality with minimal load:

```bash
# Set minimal load
export LOCUST_USERS=2
export LOCUST_SPAWN_RATE=1
export LOCUST_RUN_TIME=1m

# Run test
./examples/run_workspace_test.sh
```

**Expected Results:**
- ✅ Test completes without errors
- ✅ 2 users spawn successfully
- ✅ Workspaces created and deleted
- ✅ Report generated in `reports/`

### Test 2: Light Load

Test with light concurrent load:

```bash
export LOCUST_USERS=5
export LOCUST_SPAWN_RATE=1
export LOCUST_RUN_TIME=2m

./examples/run_workspace_test.sh
```

**Expected Results:**
- ✅ All requests succeed (failure rate < 1%)
- ✅ p95 response time < 2 seconds
- ✅ ~10-20 workspaces created
- ✅ Cleanup successful

### Test 3: Medium Load

Test with moderate concurrent load:

```bash
export LOCUST_USERS=10
export LOCUST_SPAWN_RATE=2
export LOCUST_RUN_TIME=5m

./examples/run_workspace_test.sh
```

**Expected Results:**
- ✅ Failure rate < 2%
- ✅ p95 response time < 3 seconds
- ✅ ~50-100 workspaces created
- ✅ No connection errors

### Test 4: Web UI Mode

Test interactive mode with web interface:

```bash
./examples/run_workspace_test.sh web
```

Then:
1. Open http://localhost:8089
2. Set users: 5, spawn rate: 1
3. Click "Start swarming"
4. Monitor real-time metrics
5. Stop test after 2-3 minutes

**Expected Results:**
- ✅ Web UI loads successfully
- ✅ Real-time metrics display
- ✅ Charts update during test
- ✅ Can stop/start test manually

## Verify Results

### 1. Check HTML Report

```bash
# Open latest report
open reports/workspace_operations_*.html
```

Verify:
- Request statistics table shows all operations
- Response time charts display properly
- Failure rate is acceptable
- No exceptions in failures tab

### 2. Check TFE Web Interface

1. Log into TFE: https://tfe.localdemo.me
2. Navigate to your organization
3. Check workspaces list
4. Verify workspaces were created/deleted

### 3. Check Monitoring (Local TFE Only)

**Grafana Dashboard:**
```bash
open http://localhost:3000
# Login: admin/admin
# Navigate to: TFE Load Testing Overview
```

Verify:
- Workspace count increased during test
- API request rate shows activity
- No database connection issues
- No errors in TFE exporter

**Prometheus Metrics:**
```bash
open http://localhost:9090
```

Query examples:
- `tfe_workspaces_total` - Total workspaces
- `tfe_api_requests_total` - API request count
- `rate(tfe_api_requests_total[1m])` - Request rate

### 4. Check TFE Logs

```bash
task tfe:logs
```

Look for:
- ✅ Successful API requests
- ✅ Workspace creation/deletion events
- ❌ No error messages
- ❌ No database connection errors

## Troubleshooting Test Issues

### Issue: "TFE_TOKEN not configured"

**Solution:**
```bash
# Verify .env exists
ls -la .env

# Check token is set
grep TFE_TOKEN .env

# Regenerate token in TFE if needed
```

### Issue: "Connection refused"

**Solution:**
```bash
# Check TFE is running
task tfe:health

# Check hostname
ping tfe.localdemo.me

# Verify port 443 is accessible
curl -k https://tfe.localdemo.me/_health_check
```

### Issue: "SSL certificate verification failed"

**Solution:**
```bash
# For local TFE, disable SSL verification
echo "TFE_VERIFY_SSL=false" >> .env

# Or trust the CA certificate
sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain platform/tfe/certs/ca.pem
```

### Issue: High failure rate (>5%)

**Possible causes:**
1. TFE overloaded - reduce users/spawn rate
2. Database issues - check `task tfe:logs`
3. Network issues - check connectivity
4. Rate limiting - use multiple tokens

**Solution:**
```bash
# Reduce load
export LOCUST_USERS=2
export LOCUST_SPAWN_RATE=1

# Check TFE health
task tfe:health

# Review logs
task tfe:logs | grep -i error
```

### Issue: Workspaces not cleaned up

**Solution:**
```bash
# Verify cleanup is enabled
grep CLEANUP_WORKSPACES .env

# Manually cleanup via TFE API
python3 << EOF
from src.utils.tfe_client import TFEClient
import os

client = TFEClient(
    hostname=os.getenv("TFE_HOSTNAME"),
    token=os.getenv("TFE_TOKEN"),
    organization=os.getenv("TFE_ORGANIZATION"),
    verify_ssl=False
)

# List and delete loadtest workspaces
workspaces = client.list_workspaces()
for ws in workspaces["data"]:
    if ws["attributes"]["name"].startswith("loadtest-"):
        print(f"Deleting {ws['attributes']['name']}")
        client.delete_workspace(ws["id"])
EOF
```

## Performance Benchmarks

Expected performance on local TFE (M1 Mac, 8GB RAM):

| Users | Spawn Rate | Duration | Requests/sec | p95 Latency | Failure Rate |
|-------|------------|----------|--------------|-------------|--------------|
| 2     | 1          | 1m       | 0.5-1        | <1s         | 0%           |
| 5     | 1          | 2m       | 1-2          | <1.5s       | <1%          |
| 10    | 2          | 5m       | 2-4          | <2s         | <2%          |
| 20    | 5          | 10m      | 4-8          | <3s         | <5%          |

## Next Steps After Testing

1. **Document baseline performance** - Record metrics for your TFE instance
2. **Test other scenarios** - Configuration upload, run operations (when available)
3. **Stress test** - Gradually increase load to find breaking point
4. **Production testing** - Test against production TFE (with caution)

## Cleanup After Testing

```bash
# Stop TFE stack
task tfe:down

# Remove test data (optional)
rm -rf reports/
rm .env

# Deactivate virtual environment
deactivate
```

## Reporting Issues

If you encounter issues:

1. Check this troubleshooting guide
2. Review [QUICKSTART.md](QUICKSTART.md)
3. Check [AGENTS.md](../AGENTS.md) for detailed documentation
4. Open an issue with:
   - Error message
   - Test configuration
   - TFE logs (if applicable)
   - Locust output

---

**Happy Testing!** 🧪
