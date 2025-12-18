"""Kernel detection functionality."""

import logging
import os
import re
from pathlib import Path
from typing import List, NamedTuple, Optional


logger = logging.getLogger(__name__)


class KernelFile(NamedTuple):
    """Represents a kernel file."""
    name: str
    path: Path
    version: str
    size: int

    def to_dict(self) -> dict:
        """Convert kernel file to dictionary."""
        return {
            "name": self.name,
            "path": str(self.path),
            "version": self.version,
            "size": self.size,
            "size_mb": round(self.size / (1024 * 1024), 2),
            "readable": os.access(self.path, os.R_OK)
        }


class KernelDetection:
    """Detects available kernel files for crash analysis."""

    def __init__(self, kernel_path: str, crash_dump_path: Optional[str] = None):
        self.kernel_path = Path(kernel_path)
        self.crash_dump_path = Path(crash_dump_path) if crash_dump_path else None
        self.debug_paths = [
            Path("/usr/lib/debug/lib/modules"),
            Path("/usr/lib/debug/boot"),
            self.kernel_path
        ]
        # Add crash dump directory as highest priority if provided
        if self.crash_dump_path and self.crash_dump_path.is_file():
            crash_dir = self.crash_dump_path.parent
            if crash_dir not in self.debug_paths:
                self.debug_paths.insert(0, crash_dir)
    
    def find_kernel_files(self) -> List[KernelFile]:
        """Find available kernel files."""
        kernels = []
        
        # Search in debug symbol directories first (preferred)
        for debug_path in self.debug_paths:
            if debug_path.exists():
                kernels.extend(self._search_directory(debug_path))
        
        # Remove duplicates based on version
        seen_versions = set()
        unique_kernels = []
        for kernel in kernels:
            if kernel.version not in seen_versions:
                unique_kernels.append(kernel)
                seen_versions.add(kernel.version)
        
        return unique_kernels
    
    def _search_directory(self, directory: Path) -> List[KernelFile]:
        """Search for kernel files in a directory."""
        kernels = []
        
        try:
            for root, dirs, files in os.walk(directory):
                root_path = Path(root)
                
                for file in files:
                    file_path = root_path / file
                    
                    # Look for vmlinux (debug symbols) and vmlinuz (compressed kernel)
                    if file in ["vmlinux", "vmlinuz"] or file.startswith("vmlinuz-"):
                        version = self._extract_version(file, root_path)
                        if version:
                            try:
                                stat = file_path.stat()
                                kernel = KernelFile(
                                    name=file,
                                    path=file_path,
                                    version=version,
                                    size=stat.st_size
                                )
                                kernels.append(kernel)
                            except (OSError, PermissionError) as e:
                                logger.warning(f"Cannot access kernel file {file_path}: {e}")
        
        except PermissionError as e:
            logger.warning(f"Permission denied accessing directory {directory}: {e}")
        
        return kernels
    
    def _extract_version(self, filename: str, directory: Path) -> str:
        """Extract kernel version from filename or directory path."""
        # Try to extract from filename
        if filename.startswith("vmlinuz-"):
            return filename[8:]  # Remove "vmlinuz-" prefix
        
        # Try to extract from directory path (for debug symbols)
        path_parts = str(directory).split(os.sep)
        for part in reversed(path_parts):
            if re.match(r'^\d+\.\d+\.\d+', part):
                return part
        
        # Fallback: use directory name if it looks like a version
        dir_name = directory.name
        if re.match(r'^\d+\.\d+', dir_name):
            return dir_name
        
        return "unknown"
    
    def find_vmlinux_in_dump_directory(self) -> Optional[KernelFile]:
        """Find vmlinux in the same directory as the crash dump.

        This is the highest priority search location.

        Returns:
            KernelFile if found, None otherwise
        """
        logger.info(f"looking for the image in the same directory : {self.crash_dump_path}")
        if not self.crash_dump_path or not self.crash_dump_path.is_file():
            return None

        crash_dir = self.crash_dump_path.parent
        vmlinux_path = crash_dir / "vmlinux"
        logger.info(f"Looking for vmlinux on path: {vmlinux_path}")
        if vmlinux_path.exists() and vmlinux_path.is_file():
            try:
                if os.access(vmlinux_path, os.R_OK):
                    stat = vmlinux_path.stat()
                    # Try to extract version from the dump directory name or use "unknown"
                    version = self._extract_version_from_path(crash_dir)
                    kernel = KernelFile(
                        name="vmlinux",
                        path=vmlinux_path,
                        version=version,
                        size=stat.st_size
                    )
                    logger.info(f"Found vmlinux in crash dump directory: {vmlinux_path}")
                    return kernel
            except (OSError, PermissionError) as e:
                logger.debug(f"Cannot access vmlinux in crash directory: {e}")

        return None

    def _extract_version_from_path(self, directory: Path) -> str:
        """Extract kernel version from directory path."""
        path_parts = str(directory).split(os.sep)
        for part in reversed(path_parts):
            if re.match(r'^\d+\.\d+\.\d+', part):
                return part

        dir_name = directory.name
        if re.match(r'^\d+\.\d+', dir_name):
            return dir_name

        return "unknown"

    def find_matching_kernel(self, crash_dump) -> Optional[KernelFile]:
        """Find a kernel file that matches the crash dump."""
        # Priority 1: Check for vmlinux in the crash dump directory
        kernel = self.find_vmlinux_in_dump_directory()
        if kernel:
            return kernel
        logger.warning("No kernel in the same dir")

        # Priority 2: Search standard locations
        kernels = self.find_kernel_files()

        if not kernels:
            logger.warning("No kernel files found")
            return None

        # For now, return the first available kernel
        # In a real implementation, this would match based on dump metadata
        kernel = kernels[0]
        logger.info(f"Selected kernel: {kernel.name} (version: {kernel.version})")
        return kernel
    
    def get_kernel_info(self, kernel: KernelFile) -> dict:
        """Get detailed information about a kernel file."""
        return {
            "name": kernel.name,
            "path": str(kernel.path),
            "version": kernel.version,
            "size": kernel.size,
            "size_mb": round(kernel.size / (1024 * 1024), 2),
            "readable": os.access(kernel.path, os.R_OK)
        }
