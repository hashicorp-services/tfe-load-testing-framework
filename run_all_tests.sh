#!/bin/bash
#
# TFE Load Testing Framework - Run All Tests
#
# This script runs all load test scenarios sequentially and generates
# comprehensive analysis reports for each test.
#
# Usage:
#   ./run_all_tests.sh [options]
#
# Options:
#   --users NUM          Number of concurrent users (default: 10)
#   --spawn-rate NUM     User spawn rate per second (default: 2)
#   --run-time TIME      Test duration (default: 5m)
#   --host URL           TFE hostname (default: https://tfe.localdemo.me)
#   --with-grafana       Include Grafana metrics in analysis
#   --grafana-url URL    Grafana URL (default: http://localhost:3000)
#   --skip-workspace     Skip workspace operations test
#   --skip-run           Skip run operations test
#   --skip-state         Skip state operations test
#   --ci-mode            CI/CD mode (fail fast on first failure)
#   --help               Show this help message

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default configuration
USERS=10
SPAWN_RATE=2
RUN_TIME="5m"
HOST="https://tfe.localdemo.me"
WITH_GRAFANA=false
GRAFANA_URL="http://localhost:3000"
SKIP_WORKSPACE=false
SKIP_RUN=false
SKIP_STATE=false
CI_MODE=false

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --users)
            USERS="$2"
            shift 2
            ;;
        --spawn-rate)
            SPAWN_RATE="$2"
            shift 2
            ;;
        --run-time)
            RUN_TIME="$2"
            shift 2
            ;;
        --host)
            HOST="$2"
            shift 2
            ;;
        --with-grafana)
            WITH_GRAFANA=true
            shift
            ;;
        --grafana-url)
            GRAFANA_URL="$2"
            shift 2
            ;;
        --skip-workspace)
            SKIP_WORKSPACE=true
            shift
            ;;
        --skip-run)
            SKIP_RUN=true
            shift
            ;;
        --skip-state)
            SKIP_STATE=true
            shift
            ;;
        --ci-mode)
            CI_MODE=true
            shift
            ;;
        --help)
            grep '^#' "$0" | grep -v '#!/bin/bash' | sed 's/^# //'
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Validate environment
echo -e "${CYAN}=================================${NC}"
echo -e "${CYAN}TFE Load Testing Framework${NC}"
echo -e "${CYAN}=================================${NC}"
echo ""

# Check if virtual environment is activated
if [[ -z "$VIRTUAL_ENV" ]]; then
    echo -e "${YELLOW}⚠️  Virtual environment not activated. Activating...${NC}"
    if [[ -f "venv/bin/activate" ]]; then
        source venv/bin/activate
    else
        echo -e "${RED}❌ Virtual environment not found. Run: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt${NC}"
        exit 1
    fi
fi

# Load environment variables from .env if it exists
if [[ -f ".env" ]]; then
    echo -e "${BLUE}📄 Loading environment from .env...${NC}"
    set -a
    source .env
    set +a
else
    echo -e "${YELLOW}⚠️  No .env file found. Using environment variables from shell.${NC}"
fi

# Check required environment variables
echo -e "${BLUE}🔍 Checking required environment variables...${NC}"
MISSING_VARS=()

if [[ -z "$TFE_TOKEN" ]]; then
    MISSING_VARS+=("TFE_TOKEN")
fi

if [[ -z "$TFE_ORGANIZATION" ]]; then
    MISSING_VARS+=("TFE_ORGANIZATION")
fi

if [[ ${#MISSING_VARS[@]} -gt 0 ]]; then
    echo -e "${RED}❌ Missing required environment variables:${NC}"
    for var in "${MISSING_VARS[@]}"; do
        echo "  - $var"
    done
    echo ""
    echo -e "${YELLOW}Please set the required variables:${NC}"
    echo "  export TFE_TOKEN='your-tfe-api-token'"
    echo "  export TFE_ORGANIZATION='your-org-name'"
    echo ""
    echo -e "${YELLOW}Optional variables:${NC}"
    echo "  export TFE_HOSTNAME='tfe.localdemo.me'  # Default: tfe.localdemo.me"
    echo "  export TFE_VERIFY_SSL='false'           # Default: true"
    echo ""
    exit 1
fi

echo -e "${GREEN}✅ All required environment variables are set${NC}"
echo ""

# Create reports directory
mkdir -p reports

# Generate timestamp for this test run
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
REPORT_DIR="reports/run_${TIMESTAMP}"
mkdir -p "$REPORT_DIR"

echo -e "${BLUE}📋 Test Configuration${NC}"
echo "  Users: $USERS"
echo "  Spawn Rate: $SPAWN_RATE/s"
echo "  Run Time: $RUN_TIME"
echo "  Host: $HOST"
echo "  Grafana: $WITH_GRAFANA"
echo "  Report Directory: $REPORT_DIR"
echo ""

# Track test results
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0
FAILED_TESTS=()

# Function to run a single test
run_test() {
    local test_name=$1
    local locustfile=$2
    local description=$3
    
    echo -e "${CYAN}=================================${NC}"
    echo -e "${CYAN}Running: $description${NC}"
    echo -e "${CYAN}=================================${NC}"
    
    TESTS_RUN=$((TESTS_RUN + 1))
    
    # Run Locust test
    echo -e "${BLUE}🚀 Starting load test...${NC}"
    
    if locust -f "$locustfile" \
        --headless \
        --users "$USERS" \
        --spawn-rate "$SPAWN_RATE" \
        --run-time "$RUN_TIME" \
        --host "$HOST" \
        --csv "$REPORT_DIR/${test_name}" \
        --html "$REPORT_DIR/${test_name}_locust.html"; then
        
        echo -e "${GREEN}✅ Load test completed${NC}"
    else
        echo -e "${RED}❌ Load test failed${NC}"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        FAILED_TESTS+=("$description (load test)")
        
        if [[ "$CI_MODE" == "true" ]]; then
            echo -e "${RED}CI mode: Stopping on first failure${NC}"
            exit 1
        fi
        return 1
    fi
    
    # Analyze results
    echo ""
    echo -e "${BLUE}📊 Analyzing results...${NC}"
    
    local analysis_args=(
        "--locust-stats" "$REPORT_DIR/${test_name}_stats.csv"
        "--html-report" "$REPORT_DIR/${test_name}_analysis.html"
        "--users" "$USERS"
        "--spawn-rate" "$SPAWN_RATE"
        "--run-time" "$RUN_TIME"
        "--host" "$HOST"
    )
    
    if [[ "$WITH_GRAFANA" == "true" ]]; then
        analysis_args+=("--grafana-url" "$GRAFANA_URL")
    else
        analysis_args+=("--no-grafana")
    fi
    
    if [[ "$CI_MODE" == "true" ]]; then
        analysis_args+=("--ci-mode")
    fi
    
    if ./analyze_results.py "${analysis_args[@]}"; then
        echo -e "${GREEN}✅ Analysis passed${NC}"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        echo -e "${RED}❌ Analysis failed (metrics exceeded thresholds)${NC}"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        FAILED_TESTS+=("$description (analysis)")
        
        if [[ "$CI_MODE" == "true" ]]; then
            echo -e "${RED}CI mode: Stopping on first failure${NC}"
            exit 1
        fi
    fi
    
    echo ""
    echo -e "${GREEN}Reports generated:${NC}"
    echo "  - Locust HTML: $REPORT_DIR/${test_name}_locust.html"
    echo "  - Analysis HTML: $REPORT_DIR/${test_name}_analysis.html"
    echo "  - CSV Stats: $REPORT_DIR/${test_name}_stats.csv"
    echo ""
}

# Run tests
START_TIME=$(date +%s)

if [[ "$SKIP_WORKSPACE" == "false" ]]; then
    run_test "workspace_operations" \
        "src/locustfiles/workspace_operations.py" \
        "Workspace Operations Test"
fi

if [[ "$SKIP_RUN" == "false" ]]; then
    run_test "run_operations" \
        "src/locustfiles/run_operations.py" \
        "Run Operations Test"
fi

if [[ "$SKIP_STATE" == "false" ]]; then
    run_test "state_operations" \
        "src/locustfiles/state_operations.py" \
        "State Operations Test"
fi

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

# Generate summary report
echo -e "${CYAN}=================================${NC}"
echo -e "${CYAN}Test Run Summary${NC}"
echo -e "${CYAN}=================================${NC}"
echo ""
echo -e "${BLUE}📊 Results${NC}"
echo "  Tests Run: $TESTS_RUN"
echo -e "  Tests Passed: ${GREEN}$TESTS_PASSED${NC}"
echo -e "  Tests Failed: ${RED}$TESTS_FAILED${NC}"
echo "  Duration: ${DURATION}s"
echo ""

if [[ ${#FAILED_TESTS[@]} -gt 0 ]]; then
    echo -e "${RED}❌ Failed Tests:${NC}"
    for test in "${FAILED_TESTS[@]}"; do
        echo "  - $test"
    done
    echo ""
fi

echo -e "${BLUE}📁 All Reports Location${NC}"
echo "  $REPORT_DIR/"
echo ""

# Create index.html for easy navigation
cat > "$REPORT_DIR/index.html" <<EOF
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TFE Load Test Results - $TIMESTAMP</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            border-radius: 8px;
            margin-bottom: 30px;
        }
        .summary {
            background: white;
            padding: 30px;
            border-radius: 8px;
            margin-bottom: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .test-card {
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .test-card h3 {
            margin-top: 0;
            color: #667eea;
        }
        .links {
            display: flex;
            gap: 10px;
            margin-top: 15px;
        }
        .btn {
            display: inline-block;
            padding: 10px 20px;
            background: #667eea;
            color: white;
            text-decoration: none;
            border-radius: 5px;
            transition: background 0.3s;
        }
        .btn:hover {
            background: #5568d3;
        }
        .btn-secondary {
            background: #6b7280;
        }
        .btn-secondary:hover {
            background: #4b5563;
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }
        .stat {
            text-align: center;
        }
        .stat-value {
            font-size: 2em;
            font-weight: bold;
            color: #667eea;
        }
        .stat-label {
            color: #6b7280;
            font-size: 0.9em;
        }
        .passed { color: #10b981; }
        .failed { color: #ef4444; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🧪 TFE Load Test Results</h1>
        <p>Test Run: $TIMESTAMP</p>
        <p>Duration: ${DURATION}s</p>
    </div>
    
    <div class="summary">
        <h2>📊 Summary</h2>
        <div class="stats">
            <div class="stat">
                <div class="stat-value">$TESTS_RUN</div>
                <div class="stat-label">Tests Run</div>
            </div>
            <div class="stat">
                <div class="stat-value passed">$TESTS_PASSED</div>
                <div class="stat-label">Passed</div>
            </div>
            <div class="stat">
                <div class="stat-value failed">$TESTS_FAILED</div>
                <div class="stat-label">Failed</div>
            </div>
        </div>
    </div>
EOF

# Add test cards
if [[ "$SKIP_WORKSPACE" == "false" ]]; then
    cat >> "$REPORT_DIR/index.html" <<EOF
    <div class="test-card">
        <h3>🏢 Workspace Operations Test</h3>
        <p>Tests workspace lifecycle operations: create, list, get, delete</p>
        <div class="links">
            <a href="workspace_operations_analysis.html" class="btn">📊 Analysis Report</a>
            <a href="workspace_operations_locust.html" class="btn btn-secondary">📈 Locust Report</a>
        </div>
    </div>
EOF
fi

if [[ "$SKIP_RUN" == "false" ]]; then
    cat >> "$REPORT_DIR/index.html" <<EOF
    <div class="test-card">
        <h3>🚀 Run Operations Test</h3>
        <p>Tests Terraform run lifecycle and queue management</p>
        <div class="links">
            <a href="run_operations_analysis.html" class="btn">📊 Analysis Report</a>
            <a href="run_operations_locust.html" class="btn btn-secondary">📈 Locust Report</a>
        </div>
    </div>
EOF
fi

if [[ "$SKIP_STATE" == "false" ]]; then
    cat >> "$REPORT_DIR/index.html" <<EOF
    <div class="test-card">
        <h3>💾 State Operations Test</h3>
        <p>Tests state management and file handling operations</p>
        <div class="links">
            <a href="state_operations_analysis.html" class="btn">📊 Analysis Report</a>
            <a href="state_operations_locust.html" class="btn btn-secondary">📈 Locust Report</a>
        </div>
    </div>
EOF
fi

cat >> "$REPORT_DIR/index.html" <<EOF
</body>
</html>
EOF

echo -e "${GREEN}✅ Index page created: $REPORT_DIR/index.html${NC}"
echo ""

# Open index page if not in CI mode
if [[ "$CI_MODE" == "false" ]] && command -v open &> /dev/null; then
    echo -e "${BLUE}Opening results in browser...${NC}"
    open "$REPORT_DIR/index.html"
fi

# Exit with appropriate code
if [[ $TESTS_FAILED -gt 0 ]]; then
    echo -e "${RED}❌ Some tests failed${NC}"
    exit 1
else
    echo -e "${GREEN}✅ All tests passed!${NC}"
    exit 0
fi
