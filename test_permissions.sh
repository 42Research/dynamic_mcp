#!/bin/bash
# Test script to verify dynamic-mcp user permissions for /var/crash access

set -e

echo "=========================================="
echo "Testing dynamic-mcp Permissions"
echo "=========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "❌ This test must be run as root"
    exit 1
fi

# Check if dynamic-mcp user exists
if ! id "dynamic-mcp" &>/dev/null; then
    echo "❌ dynamic-mcp user does not exist"
    exit 1
fi

echo "✓ dynamic-mcp user exists"

# Check if /var/crash exists
if [ ! -d "/var/crash" ]; then
    echo "⚠️  /var/crash does not exist (will be created by kdump)"
    echo "   Creating test directory for verification..."
    mkdir -p /var/crash
    chmod 700 /var/crash
fi

echo "✓ /var/crash directory exists"

# Test 1: Check if dynamic-mcp can read /var/crash directory
echo ""
echo "Test 1: Directory read access"
if sudo -u dynamic-mcp test -r /var/crash && sudo -u dynamic-mcp test -x /var/crash; then
    echo "✓ dynamic-mcp can read and execute /var/crash"
else
    echo "❌ dynamic-mcp cannot read/execute /var/crash"
    exit 1
fi

# Test 2: Check ACL configuration (if available)
echo ""
echo "Test 2: ACL configuration"
if command -v getfacl &>/dev/null; then
    echo "   Current ACLs on /var/crash:"
    getfacl /var/crash 2>/dev/null || echo "   (No ACLs configured)"

    # Check if dynamic-mcp has ACL entry
    if getfacl /var/crash 2>/dev/null | grep -q "user:dynamic-mcp"; then
        echo "✓ dynamic-mcp has ACL entry on /var/crash"
    else
        echo "⚠️  No ACL entry for dynamic-mcp (using group permissions)"
    fi
else
    echo "⚠️  getfacl not available (ACLs may not be supported)"
fi

# Test 3: Check group membership
echo ""
echo "Test 3: Group membership"
crash_group=$(stat -c "%G" /var/crash)
echo "   /var/crash is owned by group: $crash_group"

if id -G dynamic-mcp | grep -q "$(getent group $crash_group | cut -d: -f3)"; then
    echo "✓ dynamic-mcp is member of $crash_group group"
else
    echo "⚠️  dynamic-mcp is not member of $crash_group group"
fi

# Test 4: Create test crash dump file and verify access
echo ""
echo "Test 4: Test file access"
test_file="/var/crash/test_vmcore_$$"
echo "test data" > "$test_file"
chmod 600 "$test_file"

if sudo -u dynamic-mcp test -r "$test_file"; then
    echo "✓ dynamic-mcp can read test crash dump file"
    rm -f "$test_file"
else
    echo "❌ dynamic-mcp cannot read test crash dump file"
    rm -f "$test_file"
    exit 1
fi

# Test 5: Verify crash utility can be invoked by dynamic-mcp user
echo ""
echo "Test 5: Crash utility availability"
if command -v crash &>/dev/null; then
    echo "✓ crash utility is installed"

    # Check if dynamic-mcp can execute crash
    if sudo -u dynamic-mcp crash --version &>/dev/null; then
        echo "✓ dynamic-mcp can execute crash utility"
    else
        echo "⚠️  dynamic-mcp may have issues executing crash utility"
    fi
else
    echo "⚠️  crash utility is not installed"
fi

echo ""
echo "=========================================="
echo "✅ All permission tests passed!"
echo "=========================================="

