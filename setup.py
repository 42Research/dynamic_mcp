#!/usr/bin/env python3
"""Setup script with systemd service installation support."""

import os
import subprocess
import shutil
from pathlib import Path
from setuptools import setup
from setuptools.command.install import install
from setuptools.command.develop import develop
import logging

logger = logging.getLogger(__name__)


def _configure_crash_dump_permissions():
    """Configure permissions for dynamic-mcp user to read /var/crash directory.

    This function:
    1. Attempts to use ACLs (Access Control Lists) for fine-grained permissions
    2. Falls back to group-based permissions if ACLs are not available
    3. Ensures dynamic-mcp user can read crash dump files without root privileges
    """
    crash_path = Path("/var/crash")

    if not crash_path.exists():
        print(f"   ⚠️  /var/crash does not exist (will be created by kdump)")
        return

    try:
        # Try ACL-based approach first (more flexible)
        print("   Attempting ACL-based permission configuration...")

        # Check if setfacl is available
        result = subprocess.run(
            ["which", "setfacl"],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            # setfacl is available, use ACLs
            print("   Using ACLs for fine-grained permissions...")

            # Set ACL for dynamic-mcp user on /var/crash directory
            result = subprocess.run(
                ["setfacl", "-m", "u:dynamic-mcp:rx", str(crash_path)],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                print(f"   ✓ ACL set for dynamic-mcp user on {crash_path}")

                # Also set default ACL for future subdirectories
                subprocess.run(
                    ["setfacl", "-d", "-m", "u:dynamic-mcp:rx", str(crash_path)],
                    capture_output=True,
                    check=False
                )

                # Set ACL for existing crash dump files
                result = subprocess.run(
                    ["find", str(crash_path), "-type", "f", "-exec", "setfacl", "-m", "u:dynamic-mcp:r", "{}", "+"],
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                if result.returncode == 0:
                    print(f"   ✓ ACL set for existing crash dump files")
                else:
                    print(f"   ⚠️  Could not set ACL on all files: {result.stderr.strip()}")

                return
            else:
                print(f"   ⚠️  setfacl failed: {result.stderr.strip()}")
                # Fall through to group-based approach
        else:
            print("   ⚠️  setfacl not available, using group-based permissions...")

        # Fall back to group-based permissions
        print("   Using group-based permission configuration...")

        # Get the group that owns /var/crash
        result = subprocess.run(
            ["stat", "-c", "%G", str(crash_path)],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            crash_group = result.stdout.strip()

            # Add dynamic-mcp user to the group that owns /var/crash
            if crash_group != "dynamic-mcp":
                result = subprocess.run(
                    ["usermod", "-a", "-G", crash_group, "dynamic-mcp"],
                    capture_output=True,
                    text=True
                )

                if result.returncode == 0:
                    print(f"   ✓ Added dynamic-mcp to {crash_group} group")
                else:
                    print(f"   ⚠️  Could not add dynamic-mcp to {crash_group}: {result.stderr.strip()}")

            # Ensure group has read and execute permissions on /var/crash
            result = subprocess.run(
                ["chmod", "g+rx", str(crash_path)],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                print(f"   ✓ Group permissions configured on {crash_path}")
            else:
                print(f"   ⚠️  Could not set group permissions: {result.stderr.strip()}")
        else:
            print(f"   ⚠️  Could not determine /var/crash owner: {result.stderr.strip()}")

    except subprocess.TimeoutExpired:
        print(f"   ⚠️  Permission configuration timed out")
    except Exception as e:
        print(f"   ⚠️  Error configuring permissions: {e}")


def _install_systemd_service():
    """Install and configure systemd service."""
    print("\n" + "="*60)
    print("Setting up systemd service...")
    print("="*60)

    try:
        # Paths - look in both locations
        service_file = Path(__file__).parent / "dynamic-mcp.service"
        if not service_file.exists():
            service_file = Path(__file__).parent / "src" / "dynamic_mcp" / "dynamic-mcp.service"

        systemd_dir = Path("/etc/systemd/system")
        service_dest = systemd_dir / "dynamic-mcp.service"

        # 1. Copy service file
        print("1. Installing service file...")
        if not service_file.exists():
            print(f"   ❌ Service file not found: {service_file}")
            return

        shutil.copy2(str(service_file), str(service_dest))
        print(f"   ✓ Copied to {service_dest}")

        # 2. Create dynamic-mcp user and group
        print("2. Creating dynamic-mcp user and group...")
        try:
            subprocess.run(["useradd", "-r", "-s", "/bin/false", "dynamic-mcp"],
                         capture_output=True, check=False)
            print("   ✓ User/group created")
        except Exception as e:
            print(f"   ⚠️  Could not create user: {e}")

        # 3. Create required directories
        print("3. Creating required directories...")
        dirs = [
            Path("/opt/dynamic-mcp"),
            Path("/var/log/dynamic-mcp"),
            Path("/var/crash-dumps")
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
            subprocess.run(["chown", "dynamic-mcp:dynamic-mcp", str(d)],
                         capture_output=True, check=False)
            print(f"   ✓ {d}")

        # 4. Configure /var/crash permissions
        print("4. Configuring /var/crash permissions...")
        _configure_crash_dump_permissions()

        # 5. Reload systemd daemon
        print("5. Reloading systemd daemon...")
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        print("   ✓ Daemon reloaded")

        print("\n✅ Systemd service installed successfully!")
        print("\nNext steps:")
        print("  1. Enable service: sudo systemctl enable dynamic-mcp.service")
        print("  2. Start service:  sudo systemctl start dynamic-mcp.service")
        print("  3. Check status:   sudo systemctl status dynamic-mcp.service")

    except Exception as e:
        print(f"\n❌ Error setting up systemd service: {e}")
        print("   You can manually setup the service later.")


class SystemdInstallCommand(install):
    """Custom install command that sets up systemd service."""

    def run(self):
        """Run install and then setup systemd service."""
        super().run()
        if os.geteuid() == 0:
            _install_systemd_service()
        else:
            print("\n⚠️  Skipping systemd service setup (requires sudo)")
            print("   To enable systemd service, run: sudo pip install .")
            print("   Or manually run: sudo dynamic-mcp-install-systemd")


class SystemdDevelopCommand(develop):
    """Custom develop command that sets up systemd service."""

    def run(self):
        """Run develop and then setup systemd service."""
        super().run()
        if os.geteuid() == 0:
            _install_systemd_service()
        else:
            print("\n⚠️  Skipping systemd service setup (requires sudo)")
            print("   To enable systemd service, run: sudo pip install -e .")
            print("   Or manually run: sudo dynamic-mcp-install-systemd")


if __name__ == "__main__":
    setup(
        cmdclass={
            'install': SystemdInstallCommand,
            'develop': SystemdDevelopCommand,
        }
    )

