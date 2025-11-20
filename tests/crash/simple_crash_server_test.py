#!/usr/bin/env python3
"""
Simple test for crash-related functionality without MCP framework
"""

import sys
import os
import logging

# Add the crashmcp src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'crashmcp', 'src'))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_crash_modules():
    """Test that crash modules can be imported and used."""
    try:
        logger.info("Testing crash module imports...")

        # Test config
        from dynamic_mcp.config import Config, check_system_requirements, validate_crash_utility
        config = Config()
        logger.info(f"✓ Config loaded: {config}")

        # Test crash discovery
        from dynamic_mcp.crash_discovery import CrashDumpDiscovery
        crash_discovery = CrashDumpDiscovery(str(config.crash_dump_path))
        crash_dumps = crash_discovery.find_crash_dumps()
        logger.info(f"✓ Found {len(crash_dumps)} crash dumps")

        # Test kernel detection
        from dynamic_mcp.kernel_detection import KernelDetection
        kernel_detection = KernelDetection(str(config.kernel_path))
        kernels = kernel_detection.find_kernel_files()
        logger.info(f"✓ Found {len(kernels)} kernel files")

        # Test session manager
        from dynamic_mcp.crash_session import CrashSessionManager
        session_manager = CrashSessionManager()
        logger.info(f"✓ Session manager created, active: {session_manager.is_session_active()}")

        # Test system requirements
        requirements = check_system_requirements()
        logger.info(f"✓ System requirements: {requirements}")
        
        # Test crash utility validation
        crash_version = validate_crash_utility()
        if crash_version:
            logger.info(f"✓ Crash utility found: {crash_version}")
        else:
            logger.warning("⚠ Crash utility not found")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Crash module test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_crash_tools_logic():
    """Test the logic that would be used in MCP tools."""
    try:
        logger.info("Testing crash tools logic...")

        from dynamic_mcp.config import Config
        from dynamic_mcp.crash_discovery import CrashDumpDiscovery
        from dynamic_mcp.kernel_detection import KernelDetection
        from dynamic_mcp.crash_session import CrashSessionManager

        config = Config()
        crash_discovery = CrashDumpDiscovery(str(config.crash_dump_path))
        kernel_detection = KernelDetection(str(config.kernel_path))
        session_manager = CrashSessionManager()
        
        # Simulate list_crash_dumps tool
        crash_dumps = crash_discovery.find_crash_dumps()
        if crash_dumps:
            logger.info(f"✓ list_crash_dumps would return {len(crash_dumps)} dumps")
            for i, dump in enumerate(crash_dumps[:3], 1):
                logger.info(f"  {i}. {dump.name} ({dump.size:,} bytes)")
        else:
            logger.info("✓ list_crash_dumps would return 'No crash dumps found'")
        
        # Simulate get_crash_info tool
        info = {
            "session": {"is_active": session_manager.is_session_active()},
            "available_dumps": [dump.to_dict() for dump in crash_dumps[:3]],
            "available_kernels": [kernel.to_dict() for kernel in kernel_detection.find_kernel_files()[:3]]
        }
        logger.info(f"✓ get_crash_info would return info with {len(info)} sections")
        
        # Simulate start_crash_session tool logic
        if crash_dumps:
            latest_dump = crash_discovery.get_latest_crash_dump()
            if latest_dump and crash_discovery.is_valid_crash_dump(latest_dump):
                matching_kernel = kernel_detection.find_matching_kernel(latest_dump)
                if matching_kernel:
                    logger.info(f"✓ start_crash_session would use dump: {latest_dump.name} with kernel: {matching_kernel.name}")
                else:
                    logger.info("✓ start_crash_session would fail: No matching kernel found")
            else:
                logger.info("✓ start_crash_session would fail: Invalid crash dump")
        else:
            logger.info("✓ start_crash_session would fail: No crash dumps found")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Crash tools logic test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main test function."""
    logger.info("Starting Crash MCP functionality tests...")
    
    # Test crash modules
    modules_success = test_crash_modules()
    
    # Test crash tools logic
    tools_success = test_crash_tools_logic()
    
    if modules_success and tools_success:
        logger.info("✓ All crash functionality tests passed!")
        logger.info("✓ The crash MCP server should work correctly with proper MCP framework")
        return 0
    else:
        logger.error("✗ Some tests failed!")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
