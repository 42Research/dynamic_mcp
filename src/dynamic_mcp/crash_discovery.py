"""Crash dump discovery functionality."""

import logging
import os
from pathlib import Path
from typing import List, NamedTuple, Optional
from datetime import datetime


logger = logging.getLogger(__name__)


class CrashDump(NamedTuple):
    """Represents a crash dump file."""
    name: str
    path: Path
    size: int
    timestamp: datetime

    @property
    def mtime(self) -> datetime:
        """Get modification time (alias for timestamp)."""
        return self.timestamp

    def to_dict(self) -> dict:
        """Convert crash dump to dictionary."""
        return {
            "name": self.name,
            "path": str(self.path),
            "size": self.size,
            "size_mb": round(self.size / (1024 * 1024), 2),
            "timestamp": self.timestamp.isoformat(),
            "mtime": self.mtime.isoformat(),
            "readable": os.access(self.path, os.R_OK)
        }


class CrashDumpDiscovery:
    """Discovers crash dump files in the system."""
    
    def __init__(self, crash_dump_path: str):
        self.crash_dump_path = Path(crash_dump_path)
        self.dump_patterns = [
            "vmcore*",
            "core*", 
            "crash*",
            "dump*"
        ]
    
    def find_crash_dumps(self, max_dumps: int = 10) -> List[CrashDump]:
        """Find crash dump files in the system."""
        dumps = []
        
        if not self.crash_dump_path.exists():
            logger.warning(f"Crash dump path does not exist: {self.crash_dump_path}")
            return dumps
        
        try:
            # Search in main directory and subdirectories
            for root, dirs, files in os.walk(self.crash_dump_path):
                root_path = Path(root)
                
                for file in files:
                    file_path = root_path / file
                    
                    # Check if file matches dump patterns
                    if any(file_path.match(pattern) for pattern in self.dump_patterns):
                        try:
                            stat = file_path.stat()
                            dump = CrashDump(
                                name=file,
                                path=file_path,
                                size=stat.st_size,
                                timestamp=datetime.fromtimestamp(stat.st_mtime)
                            )
                            dumps.append(dump)
                        except (OSError, PermissionError) as e:
                            logger.warning(f"Cannot access dump file {file_path}: {e}")
                            continue
                
                # Limit search depth to avoid excessive recursion
                if len(str(root_path).split(os.sep)) - len(str(self.crash_dump_path).split(os.sep)) > 2:
                    dirs.clear()
        
        except PermissionError as e:
            logger.error(f"Permission denied accessing crash dump directory: {e}")
        
        # Sort by timestamp (newest first) and limit results
        dumps.sort(key=lambda x: x.timestamp, reverse=True)
        return dumps[:max_dumps]
    
    def get_dump_info(self, dump: CrashDump) -> dict:
        """Get detailed information about a crash dump."""
        return {
            "name": dump.name,
            "path": str(dump.path),
            "size": dump.size,
            "size_mb": round(dump.size / (1024 * 1024), 2),
            "timestamp": dump.timestamp.isoformat(),
            "readable": os.access(dump.path, os.R_OK)
        }

    def get_latest_crash_dump(self) -> Optional[CrashDump]:
        """Get the most recent crash dump."""
        dumps = self.find_crash_dumps(max_dumps=1)
        return dumps[0] if dumps else None

    def get_crash_dump_by_name(self, name: str) -> Optional[CrashDump]:
        """Get a crash dump by name."""
        dumps = self.find_crash_dumps()
        for dump in dumps:
            if dump.name == name:
                return dump
        return None

    def is_valid_crash_dump(self, dump) -> bool:
        """Check if a file is a valid crash dump."""
        try:
            # Handle both string paths and CrashDump objects
            if isinstance(dump, CrashDump):
                path = dump.path
                filename = dump.name
            else:
                path = Path(dump)
                filename = path.name

            if not path.exists() or not path.is_file():
                return False

            # Check if filename matches dump patterns
            return any(Path(filename).match(pattern) for pattern in self.dump_patterns)
        except Exception as e:
            logger.warning(f"Error validating crash dump {getattr(dump, 'name', str(dump))}: {e}")
            return False
