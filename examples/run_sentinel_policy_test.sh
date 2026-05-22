#!/bin/bash
# Copyright (c) 2026 IBM Corporation
# SPDX-License-Identifier: IPL-1.0

# Example script to run TFE Sentinel Policy Evaluation load test
#
# Policy Set Behavior:
#   - Default (loadtest-policies-synthetic-heavy): Auto-created with synthetic-heavy sample policies if it doesn't exist
#   - Standard profile: Use --policy-profile standard for the lighter sample policies
#   - Custom name: Must exist in TFE and is the preferred path for representative benchmarking
#
# Usage:
#   # Option 1: Use default synthetic-heavy policy set (auto-created)
#   ./examples/run_sentinel_policy_test.sh
#
#   # Option 2: Benchmark your own custom policy set
#   export TFE_POLICY_SET_NAME=my-custom-policy-set
#   ./examples/run_sentinel_policy_test.sh
#
#   # Option 3: Use command line arguments
#   ./examples/run_sentinel_policy_test.sh --users 10 --spawn-rate 2 --run-time 5m
#   ./examples/run_sentinel_policy_test.sh --policy-set my-policies --run-time 15m
#
#   # Option 4: Explicitly tune synthetic-heavy local policies for policy-stage calibration
#   ./examples/run_sentinel_policy_test.sh --synthetic-resource-count 300 --heavy-policy-scan-count 150 --users 2 --run-time 5m

set -e

# Configuration
TFE_HOSTNAME="${TFE_HOSTNAME:-tfe.localdemo.me}"
TFE_TOKEN="${TFE_TOKEN}"
TFE_ORGANIZATION="${TFE_ORGANIZATION}"
TFE_SENTINEL_POLICY_PROFILE="${TFE_SENTINEL_POLICY_PROFILE:-synthetic-heavy}"
DEFAULT_POLICY_SET_NAME="loadtest-policies"
if [ "$TFE_SENTINEL_POLICY_PROFILE" = "synthetic-heavy" ]; then
    DEFAULT_POLICY_SET_NAME="loadtest-policies-synthetic-heavy"
fi
TFE_POLICY_SET_NAME="${TFE_POLICY_SET_NAME:-$DEFAULT_POLICY_SET_NAME}"
TFE_SENTINEL_SYNTHETIC_RESOURCE_COUNT="${TFE_SENTINEL_SYNTHETIC_RESOURCE_COUNT:-}"
TFE_SENTINEL_HEAVY_POLICY_SCAN_COUNT="${TFE_SENTINEL_HEAVY_POLICY_SCAN_COUNT:-}"
TFE_VERIFY_SSL="${TFE_VERIFY_SSL:-false}"

# Load test parameters (can be overridden via command line or environment)
USERS="${LOCUST_USERS:-5}"
SPAWN_RATE="${LOCUST_SPAWN_RATE:-1}"
RUN_TIME="${LOCUST_RUN_TIME:-10m}"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --users=*)
            USERS="${1#*=}"
            shift
            ;;
        --users)
            USERS="$2"
            shift 2
            ;;
        --spawn-rate=*)
            SPAWN_RATE="${1#*=}"
            shift
            ;;
        --spawn-rate)
            SPAWN_RATE="$2"
            shift 2
            ;;
        --run-time=*)
            RUN_TIME="${1#*=}"
            shift
            ;;
        --run-time)
            RUN_TIME="$2"
            shift 2
            ;;
        --policy-set=*)
            TFE_POLICY_SET_NAME="${1#*=}"
            shift
            ;;
        --policy-set)
            TFE_POLICY_SET_NAME="$2"
            shift 2
            ;;
        --policy-profile=*)
            TFE_SENTINEL_POLICY_PROFILE="${1#*=}"
            shift
            ;;
        --policy-profile)
            TFE_SENTINEL_POLICY_PROFILE="$2"
            shift 2
            ;;
        --synthetic-resource-count=*)
            TFE_SENTINEL_SYNTHETIC_RESOURCE_COUNT="${1#*=}"
            shift
            ;;
        --synthetic-resource-count)
            TFE_SENTINEL_SYNTHETIC_RESOURCE_COUNT="$2"
            shift 2
            ;;
        --heavy-policy-scan-count=*)
            TFE_SENTINEL_HEAVY_POLICY_SCAN_COUNT="${1#*=}"
            shift
            ;;
        --heavy-policy-scan-count)
            TFE_SENTINEL_HEAVY_POLICY_SCAN_COUNT="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--users N] [--spawn-rate N] [--run-time TIME] [--policy-set NAME] [--policy-profile standard|synthetic-heavy]"
            echo "  --users N          Number of concurrent users (default: 5)"
            echo "  --spawn-rate N     User spawn rate per second (default: 1)"
            echo "  --run-time TIME    Test duration (e.g., 5m, 30s, 1h) (default: 10m)"
            echo "  --policy-set NAME  Policy set name (default: loadtest-policies-synthetic-heavy)"
            echo "  --policy-profile   Policy profile: standard or synthetic-heavy (default: synthetic-heavy)"
            echo "  --synthetic-resource-count N    Terraform resources for synthetic-heavy profile (default: 150)"
            echo "  --heavy-policy-scan-count N     Repeated Sentinel plan scans (default: 80)"
            echo ""
            echo "Note: Arguments can use either --option=value or --option value format"
            exit 1
            ;;
    esac
done

if [ "$TFE_SENTINEL_POLICY_PROFILE" = "synthetic-heavy" ] && [ "${TFE_POLICY_SET_NAME:-loadtest-policies}" = "loadtest-policies" ]; then
    TFE_POLICY_SET_NAME="loadtest-policies-synthetic-heavy"
fi

# Validate required environment variables
if [ -z "$TFE_TOKEN" ]; then
    echo "Error: TFE_TOKEN environment variable is required"
    exit 1
fi

if [ -z "$TFE_ORGANIZATION" ]; then
    echo "Error: TFE_ORGANIZATION environment variable is required"
    exit 1
fi

echo "=========================================="
echo "TFE Sentinel Policy Evaluation Load Test"
echo "=========================================="
echo "TFE Hostname: $TFE_HOSTNAME"
echo "Organization: $TFE_ORGANIZATION"
echo "Policy Set: $TFE_POLICY_SET_NAME"
echo "Policy Profile: $TFE_SENTINEL_POLICY_PROFILE"
if [ -n "$TFE_SENTINEL_SYNTHETIC_RESOURCE_COUNT" ]; then
    echo "Synthetic Resource Count: $TFE_SENTINEL_SYNTHETIC_RESOURCE_COUNT"
fi
if [ -n "$TFE_SENTINEL_HEAVY_POLICY_SCAN_COUNT" ]; then
    echo "Heavy Policy Scan Count: $TFE_SENTINEL_HEAVY_POLICY_SCAN_COUNT"
fi
echo "SSL Verification: $TFE_VERIFY_SSL"
echo "Users: $USERS"
echo "Spawn Rate: $SPAWN_RATE/s"
echo "Run Time: $RUN_TIME"
echo "=========================================="
echo ""
if [ "$TFE_POLICY_SET_NAME" = "loadtest-policies" ]; then
    echo "INFO: Using default policy set '$TFE_POLICY_SET_NAME'"
    echo "      Will be auto-created with sample policies if it doesn't exist."
elif [ "$TFE_POLICY_SET_NAME" = "loadtest-policies-synthetic-heavy" ]; then
    echo "INFO: Using synthetic-heavy policy set '$TFE_POLICY_SET_NAME'"
    echo "      Will be auto-created with an additional synthetic duration-calibration policy."
else
    echo "IMPORTANT: Using custom policy set '$TFE_POLICY_SET_NAME'"
    echo "           Ensure it exists in TFE before continuing!"
fi
echo "Press Ctrl+C to cancel, or wait 5 seconds to continue..."
sleep 5

# Create reports directory with timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
REPORT_DIR="reports/run_${TIMESTAMP}"
mkdir -p "$REPORT_DIR"

echo ""
echo "Starting load test..."
echo "Reports will be saved to: $REPORT_DIR"
echo ""

# Run the load test
export TFE_HOSTNAME
export TFE_TOKEN
export TFE_ORGANIZATION
export TFE_POLICY_SET_NAME
export TFE_SENTINEL_POLICY_PROFILE
export TFE_VERIFY_SSL
export LOCUST_USERS="$USERS"
export LOCUST_SPAWN_RATE="$SPAWN_RATE"
export LOCUST_RUN_TIME="$RUN_TIME"
if [ -n "$TFE_SENTINEL_SYNTHETIC_RESOURCE_COUNT" ]; then
    export TFE_SENTINEL_SYNTHETIC_RESOURCE_COUNT
fi
if [ -n "$TFE_SENTINEL_HEAVY_POLICY_SCAN_COUNT" ]; then
    export TFE_SENTINEL_HEAVY_POLICY_SCAN_COUNT
fi

locust \
    -f src/locustfiles/sentinel_policy_operations.py \
    --host="https://${TFE_HOSTNAME}" \
    --users="$USERS" \
    --spawn-rate="$SPAWN_RATE" \
    --run-time="$RUN_TIME" \
    --html="$REPORT_DIR/report.html" \
    --csv="$REPORT_DIR/stats" \
    --headless \
    --only-summary

echo ""
echo "=========================================="
echo "Load test completed!"
echo "=========================================="
echo "Reports saved to: $REPORT_DIR"
echo ""
echo "View results:"
echo "  HTML Report: $REPORT_DIR/report.html"
echo "  CSV Stats: $REPORT_DIR/stats_*.csv"
echo ""
echo "Grafana Dashboard: http://localhost:3000"
echo "  - policy_stage_wall_time_ms"
echo "  - Policy engine duration when TFE reports it"
echo "  - Policy pass/fail rates"
echo "  - Policy override frequency"
echo "=========================================="
echo ""

# Open HTML report in browser (if not in CI mode)
if [[ "${CI:-false}" != "true" ]]; then
    if command -v open &> /dev/null; then
        echo "Opening HTML report in browser..."
        open "$REPORT_DIR/report.html" 2>/dev/null || echo "Failed to open report automatically. Please open manually: $REPORT_DIR/report.html"
    elif command -v xdg-open &> /dev/null; then
        echo "Opening HTML report in browser..."
        xdg-open "$REPORT_DIR/report.html" 2>/dev/null || echo "Failed to open report automatically. Please open manually: $REPORT_DIR/report.html"
    else
        echo "No browser opener found. Please open manually: $REPORT_DIR/report.html"
    fi
fi
