"""Permission management for dynamic-mcp server.

Handles runtime permission checking and configuration for crash dump access.
"""

import logging
import os
import subprocess
from pathlib import Path
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


def check_crash_dump_access(crash_path: Path = Path("/var/crash")) -> bool:
    """Check if current user can read crash dump directory.
    
    Args:
        crash_path: Path to crash dump directory
        
    Returns:
        True if readable, False otherwise
    """
    if not crash_path.exists():
        logger.debug(f"Crash dump path does not exist: {crash_path}")
        return False
    
    try:
        # Try to list directory contents
        list(crash_path.iterdir())
        return True
    except (PermissionError, OSError) as e:
        logger.debug(f"Cannot read crash dump directory: {e}")
        return False


def configure_crash_dump_permissions(crash_path: Path = Path("/var/crash")) -> Tuple[bool, str]:
    """Configure permissions for crash dump access at runtime.
    
    Attempts to configure permissions using:
    1. ACL-based approach (preferred)
    2. Group-based approach (fallback)
    
    Args:
        crash_path: Path to crash dump directory
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    if not crash_path.exists():
        msg = f"Crash dump path does not exist: {crash_path}"
        logger.info(msg)
        return True, msg  # Not an error, will be created by kdump
    
    # Check if already readable
    if check_crash_dump_access(crash_path):
        msg = f"Crash dump directory already readable: {crash_path}"
        logger.info(msg)
        return True, msg
    
    logger.info(f"Attempting to configure permissions for {crash_path}")
    
    # Try ACL-based approach first
    success, msg = _try_acl_permissions(crash_path)
    if success:
        return True, msg
    
    logger.debug(f"ACL approach failed: {msg}")
    
    # Fall back to group-based approach
    success, msg = _try_group_permissions(crash_path)
    return success, msg


def _try_acl_permissions(crash_path: Path) -> Tuple[bool, str]:
    """Try to configure permissions using ACLs.
    
    Args:
        crash_path: Path to crash dump directory
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        # Check if setfacl is available
        result = subprocess.run(
            ["which", "setfacl"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode != 0:
            return False, "setfacl not available"

        # Get current user
        current_user = os.getenv("SUDO_USER") or os.getenv("USER", "dynamic-mcp")
        
        # Set ACL for user on directory
        result = subprocess.run(
            ["sudo", "setfacl", "-m", f"u:{current_user}:rx", str(crash_path)],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return False, f"setfacl failed: {result.stderr.strip()}"
        
        logger.info(f"ACL configured for {current_user} on {crash_path}")
        
        # Also set default ACL for future subdirectories
        subprocess.run(
            ["sudo", "setfacl", "-d", "-m", f"u:{current_user}:rx", str(crash_path)],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        # Apply to existing files (non-blocking, may timeout on large directories)
        try:
            subprocess.run(
                ["sudo", "find", str(crash_path), "-type", "f", "-exec", "setfacl", "-m", f"u:{current_user}:r", "{}", "+"],
                capture_output=True,
                text=True,
                timeout=30
            )
        except subprocess.TimeoutExpired:
            logger.warning("Timeout applying ACL to existing files (continuing)")
        
        return True, f"ACL permissions configured for {current_user}"
        
    except subprocess.TimeoutExpired:
        return False, "Permission configuration timed out"
    except Exception as e:
        return False, f"ACL configuration error: {e}"


def _try_group_permissions(crash_path: Path) -> Tuple[bool, str]:
    """Try to configure permissions using group membership.
    
    Args:
        crash_path: Path to crash dump directory
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        # Get group owning crash_path
        result = subprocess.run(
            ["stat", "-c", "%G", str(crash_path)],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode != 0:
            return False, "Could not determine crash path owner"
        
        crash_group = result.stdout.strip()
        current_user = os.getenv("SUDO_USER") or os.getenv("USER")
        
        if not current_user:
            return False, "Could not determine current user"
        
        # Add user to group
        result = subprocess.run(
            ["sudo", "usermod", "-a", "-G", crash_group, current_user],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return False, f"usermod failed: {result.stderr.strip()}"
        
        logger.info(f"Added {current_user} to {crash_group} group")
        
        # Ensure group has read+execute permissions
        subprocess.run(
            ["sudo", "chmod", "g+rx", str(crash_path)],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        return True, f"Group permissions configured ({crash_group})"
        
    except subprocess.TimeoutExpired:
        return False, "Permission configuration timed out"
    except Exception as e:
        return False, f"Group configuration error: {e}"

