#!/bin/bash
#
# Run Workspace Operations Load Test
#
# This script runs the workspace operations load test scenario against a TFE instance.
# It loads configuration from .env file and runs Locust with appropriate parameters.

set -e

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "TFE Workspace Operations Load Test"
echo "=========================================="
echo ""

# Check if .env file exists
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    echo -e "${RED}Error: .env file not found${NC}"
    echo "Please copy .env.example to .env and configure it:"
    echo "  cp .env.example .env"
    echo "  # Edit .env with your TFE credentials"
    exit 1
fi

# Load environment variables
echo "Loading configuration from .env..."
set -a
source "$PROJECT_ROOT/.env"
set +a

# Validate required variables
if [ -z "$TFE_TOKEN" ]; then
    echo -e "${RED}Error: TFE_TOKEN not set in .env${NC}"
    exit 1
fi

if [ -z "$TFE_ORGANIZATION" ]; then
    echo -e "${RED}Error: TFE_ORGANIZATION not set in .env${NC}"
    exit 1
fi

# Set defaults
TFE_HOSTNAME=${TFE_HOSTNAME:-tfe.localdemo.me}
LOCUST_USERS=${LOCUST_USERS:-10}
LOCUST_SPAWN_RATE=${LOCUST_SPAWN_RATE:-2}
LOCUST_RUN_TIME=${LOCUST_RUN_TIME:-5m}
LOCUST_WEB_HOST=${LOCUST_WEB_HOST:-0.0.0.0}
LOCUST_WEB_PORT=${LOCUST_WEB_PORT:-8089}

echo "Configuration:"
echo "  TFE Hostname: $TFE_HOSTNAME"
echo "  Organization: $TFE_ORGANIZATION"
echo "  Users: $LOCUST_USERS"
echo "  Spawn Rate: $LOCUST_SPAWN_RATE users/sec"
echo "  Run Time: $LOCUST_RUN_TIME"
echo ""

# Check if Python virtual environment exists
if [ ! -d "$PROJECT_ROOT/venv" ]; then
    echo -e "${YELLOW}Warning: Virtual environment not found${NC}"
    echo "Creating virtual environment..."
    python3 -m venv "$PROJECT_ROOT/venv"
    echo "Installing dependencies..."
    "$PROJECT_ROOT/venv/bin/pip" install -r "$PROJECT_ROOT/requirements.txt"
fi

# Activate virtual environment
source "$PROJECT_ROOT/venv/bin/activate"

# Create reports directory
mkdir -p "$PROJECT_ROOT/reports"

# Determine run mode
RUN_MODE=${1:-headless}

if [ "$RUN_MODE" = "web" ]; then
    echo -e "${GREEN}Starting Locust in web UI mode...${NC}"
    echo "Open your browser to: http://localhost:$LOCUST_WEB_PORT"
    echo "Press Ctrl+C to stop"
    echo ""
    
    locust \
        -f "$PROJECT_ROOT/src/locustfiles/workspace_operations.py" \
        --host "https://$TFE_HOSTNAME" \
        --web-host "$LOCUST_WEB_HOST" \
        --web-port "$LOCUST_WEB_PORT"
else
    echo -e "${GREEN}Starting Locust in headless mode...${NC}"
    echo "Test will run for $LOCUST_RUN_TIME"
    echo ""
    
    REPORT_FILE="$PROJECT_ROOT/reports/workspace_operations_$(date +%Y%m%d_%H%M%S).html"
    
    locust \
        -f "$PROJECT_ROOT/src/locustfiles/workspace_operations.py" \
        --host "https://$TFE_HOSTNAME" \
        --users "$LOCUST_USERS" \
        --spawn-rate "$LOCUST_SPAWN_RATE" \
        --run-time "$LOCUST_RUN_TIME" \
        --headless \
        --html "$REPORT_FILE" \
        --csv "$PROJECT_ROOT/reports/workspace_operations_$(date +%Y%m%d_%H%M%S)"
    
    echo ""
    echo -e "${GREEN}Test completed!${NC}"
    echo "Report saved to: $REPORT_FILE"
fi

echo ""
echo "=========================================="
