#!/bin/bash

##
# Test runner for the cryptoAccounting project (Linux/macOS)
#
# Usage:
#   ./run_tests.sh              # Run all tests
#   ./run_tests.sh -v           # Verbose output
#   ./run_tests.sh -c           # With coverage report
#   ./run_tests.sh -v -c        # Verbose + coverage
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Parse arguments
VERBOSE=false
COVERAGE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -c|--coverage)
            COVERAGE=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [-v|--verbose] [-c|--coverage]"
            exit 1
            ;;
    esac
done

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Print header
echo -e "\n${CYAN}=== cryptoAccounting Test Runner ===${NC}"

# Check for local virtualenv and prefer it if available
if [ -f "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON_CMD="$SCRIPT_DIR/.venv/bin/python"
    echo -e "${GREEN}Using local virtualenv: .venv${NC}"
elif [ -f "$SCRIPT_DIR/venv/bin/python" ]; then
    PYTHON_CMD="$SCRIPT_DIR/venv/bin/python"
    echo -e "${GREEN}Using local virtualenv: venv${NC}"
# Check if Python is available
elif ! command -v python3 &> /dev/null; then
    if ! command -v python &> /dev/null; then
        echo -e "${RED}ERROR: Python is not installed or not in PATH${NC}"
        exit 1
    fi
    PYTHON_CMD="python"
else
    PYTHON_CMD="python3"
fi

PYTHON_VERSION=$($PYTHON_CMD --version 2>&1)
echo -e "${CYAN}Python: $PYTHON_VERSION${NC}"

# Build the test command
TEST_CMD="$PYTHON_CMD -m unittest discover -s tests -p test_*.py"

if [ "$VERBOSE" = true ]; then
    TEST_CMD="$TEST_CMD -v"
    echo -e "${CYAN}Running tests in verbose mode...${NC}"
else
    echo -e "${CYAN}Running tests...${NC}"
fi

# Run tests
echo ""
if eval "$TEST_CMD"; then
    TEST_RESULT=0
    echo -e "\n${GREEN}All tests passed!${NC}"
else
    TEST_RESULT=$?
    echo -e "\n${RED}Tests failed with exit code: $TEST_RESULT${NC}"
fi

# Optional: Run coverage if requested
if [ "$COVERAGE" = true ]; then
    echo -e "\n${CYAN}=== Coverage Report ===${NC}"
    
    # Check if coverage is installed
    if ! $PYTHON_CMD -m pip show coverage &> /dev/null; then
        echo -e "${YELLOW}Installing coverage package...${NC}"
        $PYTHON_CMD -m pip install coverage > /dev/null 2>&1
    fi
    
    # Run coverage
    echo -e "${CYAN}Running coverage analysis...${NC}"
    $PYTHON_CMD -m coverage run -m unittest discover -s tests -p test_*.py > /dev/null 2>&1 || true
    $PYTHON_CMD -m coverage report -m --include="src/python/*"
fi

exit $TEST_RESULT
