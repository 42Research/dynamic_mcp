"""Configuration for dynamic MCP server."""

import logging
import os
import subprocess
from pathlib import Path
from typing import Dict, Any

from dynamic_mcp.permission_manager import check_crash_dump_access, configure_crash_dump_permissions


class Config:
    """Configuration class for crash MCP server."""
    
    def __init__(self):
        self.crash_dump_path = Path(os.getenv("CRASH_DUMP_PATH", "/var/crash"))
        self.kernel_path = Path(os.getenv("KERNEL_PATH", "/boot"))
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        self.crash_timeout = int(os.getenv("CRASH_TIMEOUT", "360"))
        self.max_crash_dumps = int(os.getenv("MAX_CRASH_DUMPS", "10"))
        self.session_init_timeout = int(os.getenv("SESSION_INIT_TIMEOUT", "1024"))


def setup_logging():
    """Setup logging configuration."""
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )


def check_system_requirements() -> Dict[str, Any]:
    """Check system requirements for crash analysis."""
    requirements = {
        "crash_utility": False,
        "crash_dump_access": False,
        "kernel_access": False,
        "root_access": False,
        "crash_dump_readable": False
    }

    # Check crash utility
    try:
        result = subprocess.run(["crash", "--version"], capture_output=True, text=True, timeout=10)
        requirements["crash_utility"] = result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Check crash dump access
    crash_path = Path("/var/crash")
    requirements["crash_dump_access"] = crash_path.exists() and crash_path.is_dir()

    # Check if crash dump directory is readable
    requirements["crash_dump_readable"] = check_crash_dump_access(crash_path)

    # Check kernel access
    kernel_path = Path("/boot")
    requirements["kernel_access"] = kernel_path.exists() and kernel_path.is_dir()

    # Check root access
    requirements["root_access"] = os.geteuid() == 0

    return requirements


def validate_crash_utility() -> str:
    """Validate crash utility availability and return version."""
    try:
        result = subprocess.run(["crash", "--version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return ""


def ensure_crash_dump_access(crash_path: Path = Path("/var/crash")) -> bool:
    """Ensure crash dump directory is readable at runtime.

    Attempts to configure permissions if not already readable.

    Args:
        crash_path: Path to crash dump directory

    Returns:
        True if readable or successfully configured, False otherwise
    """
    logger = logging.getLogger(__name__)

    # Check if already readable
    if check_crash_dump_access(crash_path):
        logger.debug(f"Crash dump directory already readable: {crash_path}")
        return True

    logger.info(f"Crash dump directory not readable, attempting to configure permissions...")

    # Try to configure permissions
    success, message = configure_crash_dump_permissions(crash_path)

    if success:
        logger.info(f"Permission configuration: {message}")
        # Verify it worked
        return check_crash_dump_access(crash_path)
    else:
        logger.warning(f"Permission configuration failed: {message}")
        return False
