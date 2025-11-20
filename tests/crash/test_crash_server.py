#!/usr/bin/env python3
"""
Test script for the Crash MCP Server
"""

import sys
import os
import asyncio
import logging

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_imports():
    """Test that all imports work correctly."""
    try:
        logger.info("Testing imports...")

        # Test crash-related imports
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'dynamic_mcp', 'src'))
        from dynamic_mcp.config import Config
        from dynamic_mcp.crash_discovery import CrashDumpDiscovery
        from dynamic_mcp.crash_session import CrashSessionManager
        from dynamic_mcp.kernel_detection import KernelDetection
        logger.info("✓ Crash modules imported successfully")

        # Test server import
        from dynamic_mcp.server import DynamicMCPServer
        logger.info("✓ Server module imported successfully")

        return True

    except Exception as e:
        logger.error(f"✗ Import test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_server_initialization():
    """Test that the server can be initialized without errors."""
    try:
        from web_auth_mcp.server import CrashMCPServer

        logger.info("Testing server initialization...")
        server = CrashMCPServer()
        logger.info("✓ Server initialized successfully")

        # Test basic server properties
        logger.info(f"✓ Server name: {server.server.name}")
        logger.info(f"✓ Config: {server.config}")

        return True

    except Exception as e:
        logger.error(f"✗ Server initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main test function."""
    logger.info("Starting Crash MCP Server tests...")

    # Test imports first
    import_success = test_imports()
    if not import_success:
        logger.error("✗ Import tests failed!")
        return 1

    # Test server initialization
    init_success = test_server_initialization()

    if import_success and init_success:
        logger.info("✓ All tests passed!")
        return 0
    else:
        logger.error("✗ Tests failed!")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
