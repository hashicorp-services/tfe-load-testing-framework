# TFE Load Testing Monitoring Stack

This directory contains the monitoring configuration for the TFE load testing framework, providing comprehensive observability into TFE performance, system resources, and database metrics.

## Components

### 1. Prometheus
- **Purpose**: Metrics collection and storage
- **Port**: 9090
- **URL**: http://localhost:9090
- **Scrape Interval**: 15 seconds
- **Retention**: Default (15 days)

### 2. Grafana
- **Purpose**: Visualization and dashboards
- **Port**: 3000
- **URL**: http://localhost:3000
- **Default Credentials**: admin/admin (configurable via `.env`)
- **Pre-configured Dashboard**: TFE Load Testing Overview

### 3. TFE Exporter
- **Purpose**: Custom Python exporter for TFE-specific metrics
- **Port**: 9101
- **Metrics Endpoint**: http://localhost:9101/metrics
- **Configuration**: Requires `TFE_TOKEN` and `TFE_ORGANIZATION` in `.env`

**Metrics Exposed**:
- `tfe_workspaces_total` - Total number of workspaces
- `tfe_workspaces_locked` - Number of locked workspaces
- `tfe_runs_total{status}` - Total runs by status
- `tfe_run_queue_depth` - Number of runs in queue
- `tfe_api_request_duration_seconds` - API request latency histogram
- `tfe_api_requests_total{endpoint}` - Total API requests by endpoint
- `tfe_api_errors_total{type}` - API errors by type

### 4. PostgreSQL Exporter
- **Purpose**: Database performance metrics
- **Port**: 9187
- **Metrics Endpoint**: http://localhost:9187/metrics

**Metrics Exposed**:
- `pg_stat_database_numbackends` - Active database connections
- `pg_stat_database_xact_commit` - Transaction commit rate
- `pg_stat_database_xact_rollback` - Transaction rollback rate
- `pg_locks` - Lock contention
- `pg_stat_database_tup_*` - Tuple statistics

### 5. cAdvisor
- **Purpose**: Container resource metrics (CPU, Memory, Network, Disk)
- **Port**: 8080
- **URL**: http://localhost:8080
- **Metrics Endpoint**: http://localhost:8080/metrics

**Metrics Exposed**:
- `container_cpu_usage_seconds_total` - CPU usage per container
- `container_memory_usage_bytes` - Memory usage per container
- `container_network_receive_bytes_total` - Network RX per container
- `container_network_transmit_bytes_total` - Network TX per container
- `container_fs_reads_bytes_total` - Disk read per container
- `container_fs_writes_bytes_total` - Disk write per container

## Grafana Dashboard

The **TFE Load Testing Overview** dashboard provides comprehensive monitoring across three main sections:

### TFE Overview Section
- **Total Workspaces** - Current workspace count
- **Run Queue Depth** - Number of runs waiting in queue
- **Total Runs** - Cumulative run count
- **API Errors** - Error rate over 5-minute window
- **Runs by Status** - Time series of run statuses
- **Run Queue Depth Over Time** - Queue depth trends
- **API Request Duration** - p50 and p95 latency by endpoint
- **API Request Rate** - Requests per second by endpoint

### System Resources Section
- **CPU Usage** - CPU utilization for TFE and PostgreSQL containers
- **Memory Usage** - Memory consumption for TFE and PostgreSQL
- **Network I/O** - Network receive/transmit rates
- **Disk I/O** - Disk read/write rates

### Database Metrics Section
- **PostgreSQL Active Connections** - Current database connections
- **PostgreSQL Transaction Rate** - Commits and rollbacks per second

## Configuration

### Environment Variables

Add to `platform/tfe/.env`:

```bash
# Monitoring Configuration
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=admin

# TFE Exporter (required for TFE metrics)
TFE_TOKEN=<your-tfe-api-token>
TFE_ORGANIZATION=<your-org-name>
```

### Prometheus Configuration

Edit `prometheus.yml` to add custom scrape targets:

```yaml
scrape_configs:
  - job_name: 'custom-exporter'
    static_configs:
      - targets: ['custom-exporter:9999']
```

### Grafana Provisioning

Dashboards are automatically provisioned from:
- `grafana/dashboards/*.json` - Dashboard definitions
- `grafana/provisioning/dashboards/` - Dashboard provisioning config
- `grafana/provisioning/datasources/` - Datasource config

## Usage

### Starting the Monitoring Stack

The monitoring stack starts automatically with TFE:

```bash
task tfe:up
```

### Accessing Dashboards

1. **Grafana Dashboard**:
   ```bash
   open http://localhost:3000
   # Login: admin/admin
   # Navigate to: Dashboards → TFE Load Testing Overview
   ```

2. **Prometheus UI**:
   ```bash
   open http://localhost:9090
   # Explore metrics and run PromQL queries
   ```

3. **cAdvisor UI**:
   ```bash
   open http://localhost:8080
   # View real-time container metrics
   ```

### Querying Metrics

**Example PromQL Queries**:

```promql
# TFE API request rate
rate(tfe_api_requests_total[5m])

# TFE API p95 latency
histogram_quantile(0.95, rate(tfe_api_request_duration_seconds_bucket[5m]))

# Database connections
pg_stat_database_numbackends{datname="tfe"}

# TFE container CPU usage
rate(container_cpu_usage_seconds_total{name=~".*tfe.*"}[5m]) * 100

# TFE container memory usage
container_memory_usage_bytes{name=~".*tfe.*"}

# Network throughput
rate(container_network_receive_bytes_total{name=~".*tfe.*"}[5m])
```

## Monitoring During Load Tests

### Before Starting Load Test

1. Open Grafana dashboard: http://localhost:3000
2. Set time range to "Last 1 hour" or "Last 30 minutes"
3. Enable auto-refresh (10s interval)

### During Load Test

Monitor these key metrics:

**Performance Indicators**:
- API request rate should increase steadily
- p95 latency should remain < 2-3 seconds
- Error rate should stay < 1%

**Resource Utilization**:
- CPU usage should be < 80% for sustained load
- Memory usage should be stable (no leaks)
- Network I/O should correlate with request rate

**Database Health**:
- Active connections should be < max_connections
- Transaction rate should match API activity
- No significant rollback rate

**Queue Management**:
- Run queue depth should not grow unbounded
- Runs should progress through states

### After Load Test

1. Review dashboard for anomalies
2. Check for resource exhaustion
3. Identify performance bottlenecks
4. Export metrics for reporting

## Troubleshooting

### TFE Exporter Not Working

**Symptom**: No TFE metrics in Prometheus

**Solution**:
```bash
# Check TFE exporter logs
task tfe:logs | grep tfe-exporter

# Verify TFE_TOKEN and TFE_ORGANIZATION are set
grep -E "TFE_TOKEN|TFE_ORGANIZATION" platform/tfe/.env

# Test exporter endpoint
curl http://localhost:9101/metrics
```

### cAdvisor Not Showing Metrics

**Symptom**: No container metrics in Grafana

**Solution**:
```bash
# Check cAdvisor is running
podman ps | grep cadvisor

# Test cAdvisor endpoint
curl http://localhost:8080/metrics

# Check Prometheus is scraping cAdvisor
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.job=="cadvisor")'
```

### Grafana Dashboard Empty

**Symptom**: Dashboard shows "No data"

**Solution**:
```bash
# Verify Prometheus datasource
curl http://localhost:3000/api/datasources

# Check Prometheus has data
curl http://localhost:9090/api/v1/query?query=up

# Restart Grafana
task tfe:restart grafana
```

### High Memory Usage

**Symptom**: Prometheus or Grafana consuming excessive memory

**Solution**:
```bash
# Reduce Prometheus retention
# Edit prometheus.yml:
# --storage.tsdb.retention.time=7d

# Limit Grafana dashboard refresh rate
# Set to 30s or 1m instead of 10s
```

## Metrics Retention

- **Prometheus**: 15 days (default)
- **Grafana**: Persistent via volume
- **cAdvisor**: 1 minute in-memory

To change Prometheus retention:

```yaml
# In podman-compose.yml, add to prometheus command:
- '--storage.tsdb.retention.time=30d'
- '--storage.tsdb.retention.size=10GB'
```

## Custom Metrics

### Adding Custom TFE Metrics

Edit `tfe_exporter.py`:

```python
# Add new metric
custom_metric = Gauge('tfe_custom_metric', 'Description')

# Update in collect loop
custom_metric.set(value)
```

### Adding Custom Dashboards

1. Create dashboard in Grafana UI
2. Export as JSON
3. Save to `grafana/dashboards/custom-dashboard.json`
4. Restart Grafana to load

## Performance Considerations

- **Scrape Interval**: 15s is good balance between granularity and load
- **Dashboard Refresh**: 10s for active monitoring, 30s for background
- **Metric Cardinality**: Avoid high-cardinality labels (e.g., workspace IDs)
- **Retention**: Adjust based on disk space and query performance

## Integration with Load Tests

The monitoring stack integrates seamlessly with Locust load tests:

1. **Start monitoring**: `task tfe:up`
2. **Run load test**: `./examples/run_workspace_test.sh`
3. **Monitor in real-time**: Grafana dashboard updates automatically
4. **Correlate metrics**: Match Locust timestamps with Grafana data
5. **Generate reports**: Export Grafana panels to PDF/PNG

## Resources

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [cAdvisor Documentation](https://github.com/google/cadvisor)
- [PostgreSQL Exporter](https://github.com/prometheus-community/postgres_exporter)

---

**Last Updated**: 2026-05-07  
**Status**: Production-ready with comprehensive system metrics