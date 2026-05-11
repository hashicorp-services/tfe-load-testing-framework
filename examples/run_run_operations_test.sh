#!/bin/bash

# TFE Run Operations Load Test Runner
# This script runs the run operations load test scenario

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}TFE Run Operations Load Test${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check if .env file exists
if [ ! -f .env ]; then
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
source .env
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

# Set default values
LOCUST_USERS=${LOCUST_USERS:-5}
LOCUST_SPAWN_RATE=${LOCUST_SPAWN_RATE:-1}
LOCUST_RUN_TIME=${LOCUST_RUN_TIME:-5m}

echo -e "${YELLOW}Configuration:${NC}"
echo "  TFE Hostname: $TFE_HOSTNAME"
echo "  Organization: $TFE_ORGANIZATION"
echo "  Users: $LOCUST_USERS"
echo "  Spawn Rate: $LOCUST_SPAWN_RATE/s"
echo "  Run Time: $LOCUST_RUN_TIME"
echo "  SSL Verification: ${TFE_VERIFY_SSL:-true}"
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Virtual environment not found. Creating...${NC}"
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

echo -e "${GREEN}Starting load test...${NC}"
echo ""
echo -e "${YELLOW}Note: This test will:${NC}"
echo "  - Create temporary workspaces"
echo "  - Upload Terraform configurations"
echo "  - Trigger multiple runs"
echo "  - Monitor run status"
echo "  - Test run queue depth"
echo "  - Cancel some runs"
echo "  - Clean up all resources on completion"
echo ""
echo -e "${YELLOW}Monitor the test:${NC}"
echo "  - Web UI: http://localhost:8089"
echo "  - Grafana: http://localhost:3000"
echo "  - Prometheus: http://localhost:9090"
echo ""

# Run the load test
# Note: Run operations take time (workspace creation, config upload, run execution)
# Using longer timeout to allow test to complete naturally
timeout 400 locust \
    -f src/locustfiles/run_operations.py \
    --host=https://$TFE_HOSTNAME \
    --users=$LOCUST_USERS \
    --spawn-rate=$LOCUST_SPAWN_RATE \
    --run-time=$LOCUST_RUN_TIME \
    --headless \
    --html=reports/run_operations_$(date +%Y%m%d_%H%M%S).html \
    --csv=reports/run_operations_$(date +%Y%m%d_%H%M%S)

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Load test completed!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Reports saved in: reports/"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "  1. Review the HTML report in reports/"
echo "  2. Check Grafana dashboard: http://localhost:3000"
echo "  3. Analyze run queue depth and API performance"
echo ""
