#!/bin/bash
# Copyright (c) 2026 IBM Corporation
# SPDX-License-Identifier: MPL-2.0

# TFE Workspace + Run Scaling Load Test Runner
#
# Each Locust user creates one workspace, then repeatedly uploads config and
# triggers runs. Scale concurrent runs with --max-concurrent-runs /
# MAX_CONCURRENT_RUNS (users and spawn_rate are auto-calculated).
#
# Usage:
#   MAX_CONCURRENT_RUNS=50 ./examples/run_workspace_run_test.sh
#   ./examples/run_workspace_run_test.sh --max-concurrent-runs 100 --run-time 15m
#   ./examples/run_workspace_run_test.sh web
#   ./examples/run_workspace_run_test.sh --users 30 --spawn-rate 10 --run-time 5m

set -e

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}TFE Workspace + Run Scaling Load Test${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check if .env file exists
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    echo -e "${RED}Error: .env file not found${NC}"
    echo "Please create a .env file based on .env.example"
    echo "  cp .env.example .env"
    echo ""
    echo "Required variables:"
    echo "  TFE_HOSTNAME=your-tfe-hostname"
    echo "  TFE_TOKEN=your-tfe-token"
    echo "  TFE_ORGANIZATION=your-org-name"
    echo "  TFE_VERIFY_SSL=false  # for local dev"
    exit 1
fi

# Load environment variables
set -a
source "$PROJECT_ROOT/.env"
set +a

# Validate required variables
if [ -z "$TFE_HOSTNAME" ] || [ -z "$TFE_TOKEN" ] || [ -z "$TFE_ORGANIZATION" ]; then
    echo -e "${RED}Error: Missing required environment variables${NC}"
    echo "Please ensure .env contains:"
    echo "  TFE_HOSTNAME"
    echo "  TFE_TOKEN"
    echo "  TFE_ORGANIZATION"
    exit 1
fi

# Defaults (env can pre-set; CLI may override)
MAX_CONCURRENT_RUNS=${MAX_CONCURRENT_RUNS:-20}
LOCUST_RUN_TIME=${LOCUST_RUN_TIME:-5m}
LOCUST_WEB_HOST=${LOCUST_WEB_HOST:-0.0.0.0}
LOCUST_WEB_PORT=${LOCUST_WEB_PORT:-8089}
RUN_MODE="headless"
USERS_OVERRIDE=""
SPAWN_RATE_OVERRIDE=""
HOST_OVERRIDE=""

usage() {
    echo "Usage: $0 [web|headless] [options]"
    echo ""
    echo "Modes:"
    echo "  web                 Start Locust web UI (default: headless)"
    echo "  headless            Run headless and write reports (default)"
    echo ""
    echo "Options:"
    echo "  --max-concurrent-runs NUM  Target concurrent runs / workspaces (default: 20)"
    echo "  --users NUM                Override Locust users (default: max(5, MAX_CONCURRENT_RUNS))"
    echo "  --spawn-rate NUM           Override spawn rate (default: MAX_CONCURRENT_RUNS)"
    echo "  --run-time TIME            Test duration, e.g. 5m, 15m (default: 5m)"
    echo "  --host HOSTNAME            Override TFE hostname"
    echo "  -h, --help                 Show this help"
    echo ""
    echo "Examples:"
    echo "  MAX_CONCURRENT_RUNS=50 $0"
    echo "  $0 --max-concurrent-runs 100 --run-time 15m"
    echo "  $0 web"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        web|headless)
            RUN_MODE="$1"
            shift
            ;;
        --max-concurrent-runs=*)
            MAX_CONCURRENT_RUNS="${1#*=}"
            shift
            ;;
        --max-concurrent-runs)
            MAX_CONCURRENT_RUNS="$2"
            shift 2
            ;;
        --users=*)
            USERS_OVERRIDE="${1#*=}"
            shift
            ;;
        --users)
            USERS_OVERRIDE="$2"
            shift 2
            ;;
        --spawn-rate=*)
            SPAWN_RATE_OVERRIDE="${1#*=}"
            shift
            ;;
        --spawn-rate)
            SPAWN_RATE_OVERRIDE="$2"
            shift 2
            ;;
        --run-time=*)
            LOCUST_RUN_TIME="${1#*=}"
            shift
            ;;
        --run-time)
            LOCUST_RUN_TIME="$2"
            shift 2
            ;;
        --host=*)
            HOST_OVERRIDE="${1#*=}"
            shift
            ;;
        --host)
            HOST_OVERRIDE="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            usage
            exit 1
            ;;
    esac
done

if [ -n "$HOST_OVERRIDE" ]; then
    TFE_HOSTNAME="$HOST_OVERRIDE"
fi

# Apply explicit overrides, otherwise auto-calc from MAX_CONCURRENT_RUNS
if [ -n "$USERS_OVERRIDE" ]; then
    LOCUST_USERS="$USERS_OVERRIDE"
elif [ -z "$LOCUST_USERS" ]; then
    # Formula: users = max(5, max_concurrent_runs)
    LOCUST_USERS=$((MAX_CONCURRENT_RUNS > 5 ? MAX_CONCURRENT_RUNS : 5))
    echo -e "${GREEN}Auto-calculated users: $LOCUST_USERS (based on max_concurrent_runs=$MAX_CONCURRENT_RUNS)${NC}"
fi

if [ -n "$SPAWN_RATE_OVERRIDE" ]; then
    LOCUST_SPAWN_RATE="$SPAWN_RATE_OVERRIDE"
elif [ -z "$LOCUST_SPAWN_RATE" ]; then
    # Formula: spawn_rate = max_concurrent_runs (instant spawn)
    LOCUST_SPAWN_RATE=$MAX_CONCURRENT_RUNS
    echo -e "${GREEN}Auto-calculated spawn_rate: $LOCUST_SPAWN_RATE/s (instant spawn)${NC}"
fi

# Export so Locust event hooks can read them
export MAX_CONCURRENT_RUNS
export LOCUST_USERS
export LOCUST_SPAWN_RATE
export LOCUST_RUN_TIME
export TFE_HOSTNAME

echo -e "${YELLOW}Configuration:${NC}"
echo "  TFE Hostname: $TFE_HOSTNAME"
echo "  Organization: $TFE_ORGANIZATION"
echo "  Max Concurrent Runs: $MAX_CONCURRENT_RUNS"
echo "  Users: $LOCUST_USERS"
echo "  Spawn Rate: $LOCUST_SPAWN_RATE/s"
echo "  Run Time: $LOCUST_RUN_TIME"
echo "  Mode: $RUN_MODE"
echo "  SSL Verification: ${TFE_VERIFY_SSL:-true}"
echo ""

# Check if virtual environment exists
if [ ! -d "$PROJECT_ROOT/venv" ]; then
    echo -e "${YELLOW}Virtual environment not found. Creating...${NC}"
    python3 -m venv "$PROJECT_ROOT/venv"
    source "$PROJECT_ROOT/venv/bin/activate"
    pip install -r "$PROJECT_ROOT/requirements.txt"
else
    source "$PROJECT_ROOT/venv/bin/activate"
fi

# Create reports directory
mkdir -p "$PROJECT_ROOT/reports"

cd "$PROJECT_ROOT"

echo -e "${GREEN}Starting load test...${NC}"
echo ""
echo -e "${YELLOW}Note: This test will:${NC}"
echo "  - Create one workspace per Locust user"
echo "  - Upload Terraform configurations"
echo "  - Trigger runs (config version → upload → create run)"
echo "  - Clean up all resources on completion"
echo ""

if [ "$RUN_MODE" = "web" ]; then
    echo -e "${GREEN}Starting Locust in web UI mode...${NC}"
    echo "Open your browser to: http://localhost:$LOCUST_WEB_PORT"
    echo "Press Ctrl+C to stop"
    echo ""

    MAX_CONCURRENT_RUNS=$MAX_CONCURRENT_RUNS locust \
        -f src/locustfiles/workspace_run_operations.py \
        --host="https://$TFE_HOSTNAME" \
        --web-host "$LOCUST_WEB_HOST" \
        --web-port "$LOCUST_WEB_PORT"
else
    echo -e "${YELLOW}Monitor the test:${NC}"
    echo "  - Grafana: http://localhost:3000"
    echo "  - Prometheus: http://localhost:9090"
    echo ""

    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    REPORT_FILE="reports/workspace_run_operations_${TIMESTAMP}.html"

    MAX_CONCURRENT_RUNS=$MAX_CONCURRENT_RUNS locust \
        -f src/locustfiles/workspace_run_operations.py \
        --host="https://$TFE_HOSTNAME" \
        --users="$LOCUST_USERS" \
        --spawn-rate="$LOCUST_SPAWN_RATE" \
        --run-time="$LOCUST_RUN_TIME" \
        --headless \
        --html="$REPORT_FILE" \
        --csv="reports/workspace_run_operations_${TIMESTAMP}"

    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}Load test completed!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo "Report saved to: $REPORT_FILE"
    echo "Reports directory: reports/"
    echo ""
    echo -e "${YELLOW}Next steps:${NC}"
    echo "  1. Review the HTML report in reports/"
    echo "  2. Check Grafana dashboard: http://localhost:3000"
    echo "  3. Compare concurrent runs vs TFE_CAPACITY_CONCURRENCY"
    echo ""
fi
