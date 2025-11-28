"""BPFtrace script execution and management."""

import asyncio
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class BPFtraceExecutor:
    """Executes BPFtrace scripts with proper permission handling."""

    def __init__(self, timeout: int = 30):
        """Initialize BPFtrace executor.
        
        Args:
            timeout: Default timeout for script execution in seconds
        """
        self.timeout = timeout
        self.bpftrace_path = self._find_bpftrace()

    def _find_bpftrace(self) -> Optional[str]:
        """Find bpftrace binary in system PATH."""
        try:
            result = subprocess.run(
                ["which", "bpftrace"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                timeout=5
            )
            if result.returncode == 0:
                path = result.stdout.strip()
                logger.info(f"Found bpftrace at: {path}")
                return path
        except Exception as e:
            logger.warning(f"Could not find bpftrace: {e}")
        return None

    def is_available(self) -> bool:
        """Check if bpftrace is available on the system."""
        return self.bpftrace_path is not None

    def get_version(self) -> Optional[str]:
        """Get bpftrace version."""
        if not self.bpftrace_path:
            return None
        try:
            result = subprocess.run(
                [self.bpftrace_path, "--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                timeout=5
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception as e:
            logger.warning(f"Could not get bpftrace version: {e}")
            return None

    async def execute_script(
        self,
        script: str,
        timeout: Optional[int] = None,
        use_sudo: bool = True
    ) -> Tuple[str, str, int]:
        """Execute a BPFtrace script.
        
        Args:
            script: BPFtrace script content
            timeout: Execution timeout in seconds (uses default if None)
            use_sudo: Whether to use sudo for execution
            
        Returns:
            Tuple of (stdout, stderr, return_code)
        """
        if not self.bpftrace_path:
            return "", "BPFtrace not available on system", 1

        timeout = timeout or self.timeout

        # Write script to temporary file
        try:
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.bt',
                delete=False
            ) as f:
                f.write(script)
                script_path = f.name

            return await self._execute_script_file(
                script_path,
                timeout,
                use_sudo
            )
        finally:
            # Clean up temporary file
            try:
                os.unlink(script_path)
            except Exception as e:
                logger.warning(f"Could not delete temp script: {e}")

    async def _execute_script_file(
        self,
        script_path: str,
        timeout: int,
        use_sudo: bool
    ) -> Tuple[str, str, int]:
        """Execute a BPFtrace script from file."""
        cmd = [self.bpftrace_path, script_path]

        if use_sudo:
            cmd = ["sudo", "-n"] + cmd

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
                return (
                    stdout.decode('utf-8', errors='ignore'),
                    stderr.decode('utf-8', errors='ignore'),
                    process.returncode
                )
            except asyncio.TimeoutError:
                logger.info(f"BPFtrace script execution timeout after {timeout}s, terminating process")

                # Try graceful termination first with SIGTERM
                process.terminate()
                logger.debug("Sent SIGTERM to process")
                try:
                    # Wait for graceful termination with a short timeout
                    logger.debug("Waiting for graceful termination...")
                    await asyncio.wait_for(process.wait(), timeout=2)
                    logger.debug("Process terminated gracefully")
                except asyncio.TimeoutError:
                    # If graceful termination fails, force kill
                    logger.warning("Graceful termination failed, force killing process")
                    process.kill()
                    logger.debug("Sent SIGKILL to process")
                    try:
                        logger.debug("Waiting for process to be killed...")
                        await asyncio.wait_for(process.wait(), timeout=1)
                        logger.debug("Process killed successfully")
                    except asyncio.TimeoutError:
                        logger.error("Process did not respond to SIGKILL")

                # Capture any partial output that was produced before timeout
                # Don't try to read from streams as they may block
                stdout_text = ""
                stderr_text = f"Script execution timed out after {timeout}s"

                logger.debug(f"Returning timeout result: exit_code=124")
                return stdout_text, stderr_text, 124

        except Exception as e:
            logger.error(f"Error executing BPFtrace script: {e}")
            return "", str(e), 1

    def validate_script(self, script: str) -> Tuple[bool, str]:
        """Validate BPFtrace script syntax.
        
        Args:
            script: BPFtrace script content
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not self.bpftrace_path:
            return False, "BPFtrace not available"

        try:
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.bt',
                delete=False
            ) as f:
                f.write(script)
                script_path = f.name

            try:
                result = subprocess.run(
                    ["sudo", "-n", self.bpftrace_path, "-c", script_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                    timeout=5
                )
                if result.returncode == 0:
                    return True, ""
                else:
                    return False, result.stderr
            finally:
                os.unlink(script_path)

        except Exception as e:
            return False, str(e)

