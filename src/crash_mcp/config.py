"""Configuration for crash MCP server."""

import logging
import os
import subprocess
from pathlib import Path
from typing import Dict, Any


class Config:
    """Configuration class for crash MCP server."""
    
    def __init__(self):
        self.crash_dump_path = Path(os.getenv("CRASH_DUMP_PATH", "/var/crash"))
        self.kernel_path = Path(os.getenv("KERNEL_PATH", "/boot"))
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        self.crash_timeout = int(os.getenv("CRASH_TIMEOUT", "120"))
        self.max_crash_dumps = int(os.getenv("MAX_CRASH_DUMPS", "10"))
        self.session_init_timeout = int(os.getenv("SESSION_INIT_TIMEOUT", "180"))


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
        "root_access": False
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
