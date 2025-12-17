"""Tests for kernel detection functionality."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from dynamic_mcp.kernel_detection import KernelDetection, KernelFile


class TestVmlinuxInDumpDirectory:
    """Test finding vmlinux in crash dump directory."""
    
    def test_find_vmlinux_in_dump_directory_success(self):
        """Test finding vmlinux in the same directory as crash dump."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a fake vmlinux file
            vmlinux_path = Path(tmpdir) / "vmlinux"
            vmlinux_path.write_text("fake vmlinux content")
            
            # Create a fake crash dump file
            dump_path = Path(tmpdir) / "vmcore"
            dump_path.write_text("fake vmcore content")
            
            # Create KernelDetection with crash dump path
            kd = KernelDetection("/boot", str(dump_path))
            
            # Find vmlinux in dump directory
            kernel = kd.find_vmlinux_in_dump_directory()
            
            assert kernel is not None
            assert kernel.name == "vmlinux"
            assert kernel.path == vmlinux_path
            assert kernel.version == "unknown"  # No version in temp dir name
    
    def test_find_vmlinux_in_dump_directory_not_found(self):
        """Test when vmlinux is not in crash dump directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create only crash dump, no vmlinux
            dump_path = Path(tmpdir) / "vmcore"
            dump_path.write_text("fake vmcore content")
            
            kd = KernelDetection("/boot", str(dump_path))
            kernel = kd.find_vmlinux_in_dump_directory()
            
            assert kernel is None
    
    def test_find_vmlinux_in_dump_directory_no_dump_path(self):
        """Test when no crash dump path is provided."""
        kd = KernelDetection("/boot")
        kernel = kd.find_vmlinux_in_dump_directory()
        
        assert kernel is None
    
    def test_find_matching_kernel_prioritizes_dump_directory(self):
        """Test that find_matching_kernel prioritizes dump directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create vmlinux in dump directory
            vmlinux_path = Path(tmpdir) / "vmlinux"
            vmlinux_path.write_text("fake vmlinux content")
            
            dump_path = Path(tmpdir) / "vmcore"
            dump_path.write_text("fake vmcore content")
            
            kd = KernelDetection("/boot", str(dump_path))
            
            # Mock find_kernel_files to return a different kernel
            with patch.object(kd, 'find_kernel_files') as mock_find:
                mock_find.return_value = [
                    KernelFile(
                        name="vmlinuz-4.18.0-553",
                        path=Path("/boot/vmlinuz-4.18.0-553"),
                        version="4.18.0-553",
                        size=5000000
                    )
                ]
                
                kernel = kd.find_matching_kernel(None)
                
                # Should return vmlinux from dump directory, not vmlinuz from /boot
                assert kernel is not None
                assert kernel.name == "vmlinux"
                assert kernel.path == vmlinux_path

