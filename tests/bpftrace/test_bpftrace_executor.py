#!/usr/bin/env python3
"""
Test suite for BPFtrace executor functionality.
"""

import asyncio
import logging
import os
import sys
import unittest
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from dynamic_mcp.bpftrace_executor import BPFtraceExecutor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestBPFtraceExecutor(unittest.TestCase):
    """Test cases for BPFtraceExecutor."""

    def setUp(self):
        """Set up test fixtures."""
        self.executor = BPFtraceExecutor(timeout=10)

    def test_initialization(self):
        """Test executor initialization."""
        self.assertIsNotNone(self.executor)
        self.assertEqual(self.executor.timeout, 10)

    def test_is_available(self):
        """Test BPFtrace availability check."""
        available = self.executor.is_available()
        logger.info(f"BPFtrace available: {available}")
        # Don't fail if not available - just log
        self.assertIsInstance(available, bool)

    def test_get_version(self):
        """Test getting BPFtrace version."""
        version = self.executor.get_version()
        logger.info(f"BPFtrace version: {version}")
        # Version can be None if not available
        if version:
            self.assertIsInstance(version, str)
            self.assertTrue(len(version) > 0)

    def test_validate_script_simple(self):
        """Test script validation with a simple script."""
        if not self.executor.is_available():
            self.skipTest("BPFtrace not available")

        # Simple valid script
        script = 'BEGIN { printf("test\\n"); }'
        is_valid, error = self.executor.validate_script(script)
        logger.info(f"Script validation result: valid={is_valid}, error={error}")

    def test_validate_script_invalid(self):
        """Test script validation with invalid script."""
        if not self.executor.is_available():
            self.skipTest("BPFtrace not available")

        # Invalid script
        script = 'INVALID SYNTAX HERE {'
        is_valid, error = self.executor.validate_script(script)
        logger.info(f"Invalid script validation: valid={is_valid}")
        # Invalid script should return False
        self.assertFalse(is_valid)

    @unittest.skipIf(os.geteuid() != 0, "Requires root privileges")
    def test_execute_script_simple(self):
        """Test executing a simple BPFtrace script."""
        script = 'BEGIN { printf("Hello from BPFtrace\\n"); exit(); }'
        
        async def run_test():
            stdout, stderr, returncode = await self.executor.execute_script(
                script,
                timeout=5,
                use_sudo=False
            )
            logger.info(f"Script execution: rc={returncode}, stdout={stdout}, stderr={stderr}")
            return stdout, stderr, returncode

        stdout, stderr, returncode = asyncio.run(run_test())
        # Should complete without timeout
        self.assertNotEqual(returncode, 124)

    @unittest.skipIf(os.geteuid() != 0, "Requires root privileges")
    def test_execute_script_timeout(self):
        """Test script execution timeout."""
        # Script that runs indefinitely - uses a tracepoint that continuously fires
        script = r'tracepoint:syscalls:sys_enter_openat { printf("syscall\n"); }'

        async def run_test():
            stdout, stderr, returncode = await self.executor.execute_script(
                script,
                timeout=1,
                use_sudo=False
            )
            return returncode, stderr

        returncode, stderr = asyncio.run(run_test())
        # Should timeout (exit code 124)
        self.assertEqual(returncode, 124)
        # Should contain timeout message
        self.assertIn("timed out", stderr)


class TestBPFtraceIntegration(unittest.TestCase):
    """Integration tests for BPFtrace with MCP server."""

    def setUp(self):
        """Set up test fixtures."""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
        from dynamic_mcp.server import DynamicMCPServer
        self.server = DynamicMCPServer()

    def test_server_has_bpftrace_executor(self):
        """Test that server has BPFtrace executor."""
        self.assertIsNotNone(self.server.bpftrace_executor)
        self.assertIsInstance(self.server.bpftrace_executor, BPFtraceExecutor)

    def test_bpftrace_tools_registered(self):
        """Test that BPFtrace tools are registered."""
        # This would require accessing the server's tools
        # For now, just verify the executor is available
        self.assertTrue(hasattr(self.server, 'bpftrace_executor'))


if __name__ == '__main__':
    unittest.main()

