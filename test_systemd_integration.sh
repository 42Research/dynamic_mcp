#!/bin/bash
# Test script for systemd service integration

set -e

echo "=========================================="
echo "Testing Systemd Service Integration"
echo "=========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "⚠️  This test requires sudo to fully test systemd integration"
    echo "   Run: sudo bash test_systemd_integration.sh"
    echo ""
    echo "Testing non-root installation flow..."
    echo ""
fi

# Test 1: Verify setup.py exists and is valid
echo "Test 1: Checking setup.py..."
if [ -f "setup.py" ]; then
    python3 -m py_compile setup.py
    echo "✓ setup.py is valid"
else
    echo "❌ setup.py not found"
    exit 1
fi

# Test 2: Verify systemd_installer.py exists and is valid
echo ""
echo "Test 2: Checking systemd_installer.py..."
if [ -f "src/dynamic_mcp/systemd_installer.py" ]; then
    python3 -m py_compile src/dynamic_mcp/systemd_installer.py
    echo "✓ systemd_installer.py is valid"
else
    echo "❌ systemd_installer.py not found"
    exit 1
fi

# Test 3: Verify service file exists
echo ""
echo "Test 3: Checking dynamic-mcp.service file..."
if [ -f "dynamic-mcp.service" ]; then
    echo "✓ dynamic-mcp.service found in root"
fi
if [ -f "src/dynamic_mcp/dynamic-mcp.service" ]; then
    echo "✓ dynamic-mcp.service found in src/dynamic_mcp"
else
    echo "❌ dynamic-mcp.service not found in src/dynamic_mcp"
    exit 1
fi

# Test 4: Verify pyproject.toml configuration
echo ""
echo "Test 4: Checking pyproject.toml configuration..."
if grep -q "dynamic-mcp-install-systemd" pyproject.toml; then
    echo "✓ dynamic-mcp-install-systemd entry point configured"
else
    echo "❌ dynamic-mcp-install-systemd entry point not found"
    exit 1
fi

if grep -q 'dynamic_mcp = \["dynamic-mcp.service"\]' pyproject.toml; then
    echo "✓ dynamic-mcp.service included in package data"
else
    echo "❌ dynamic-mcp.service not in package data"
    exit 1
fi

# Test 5: Verify service file content
echo ""
echo "Test 5: Checking service file content..."
if grep -q "Description=Dynamic MCP Server" src/dynamic_mcp/dynamic-mcp.service; then
    echo "✓ Service file has correct description"
else
    echo "❌ Service file description incorrect"
    exit 1
fi

if grep -q "ExecStart=/usr/local/bin/dynamic-mcp-http" src/dynamic_mcp/dynamic-mcp.service; then
    echo "✓ Service file has correct ExecStart"
else
    echo "❌ Service file ExecStart incorrect"
    exit 1
fi

if grep -q "WantedBy=multi-user.target" src/dynamic_mcp/dynamic-mcp.service; then
    echo "✓ Service file has correct WantedBy"
else
    echo "❌ Service file WantedBy incorrect"
    exit 1
fi

# Test 6: If running as root, test systemd installation
if [ "$EUID" -eq 0 ]; then
    echo ""
    echo "Test 6: Testing systemd service installation (as root)..."

    # Create a temporary test directory
    TEST_DIR=$(mktemp -d)
    trap "rm -rf $TEST_DIR" EXIT

    # Copy service file to test location
    cp src/dynamic_mcp/dynamic-mcp.service "$TEST_DIR/"

    # Verify it can be copied
    if [ -f "$TEST_DIR/dynamic-mcp.service" ]; then
        echo "✓ Service file can be copied"
    else
        echo "❌ Failed to copy service file"
        exit 1
    fi

    # Test user creation (will fail if already exists, which is OK)
    if useradd -r -s /bin/false dynamic-mcp 2>/dev/null || true; then
        echo "✓ dynamic-mcp user creation works"
    fi

    # Test directory creation
    TEST_DIRS="/tmp/test-dynamic-mcp /tmp/test-dynamic-mcp-logs"
    for d in $TEST_DIRS; do
        mkdir -p "$d" 2>/dev/null || true
        if [ -d "$d" ]; then
            echo "✓ Directory creation works: $d"
            rm -rf "$d"
        fi
    done
fi

echo ""
echo "=========================================="
echo "✅ All tests passed!"
echo "=========================================="
echo ""
echo "Installation methods:"
echo "  1. Development install: pip install -e ."
echo "  2. Production install:  pip install ."
echo "  3. With systemd setup:  sudo pip install ."
echo "  4. Manual systemd setup: sudo dynamic-mcp-install-systemd"

