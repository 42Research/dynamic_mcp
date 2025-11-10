#!/usr/bin/env python3
"""Setup script with systemd service installation support."""

import os
import subprocess
import shutil
from pathlib import Path
from setuptools import setup
from setuptools.command.install import install
from setuptools.command.develop import develop


def _install_systemd_service():
    """Install and configure systemd service."""
    print("\n" + "="*60)
    print("Setting up systemd service...")
    print("="*60)

    try:
        # Paths - look in both locations
        service_file = Path(__file__).parent / "crash-mcp.service"
        if not service_file.exists():
            service_file = Path(__file__).parent / "src" / "crash_mcp" / "crash-mcp.service"

        systemd_dir = Path("/etc/systemd/system")
        service_dest = systemd_dir / "crash-mcp.service"

        # 1. Copy service file
        print("1. Installing service file...")
        if not service_file.exists():
            print(f"   ❌ Service file not found: {service_file}")
            return

        shutil.copy2(str(service_file), str(service_dest))
        print(f"   ✓ Copied to {service_dest}")

        # 2. Create crash-mcp user and group
        print("2. Creating crash-mcp user and group...")
        try:
            subprocess.run(["useradd", "-r", "-s", "/bin/false", "crash-mcp"],
                         capture_output=True, check=False)
            print("   ✓ User/group created")
        except Exception as e:
            print(f"   ⚠️  Could not create user: {e}")

        # 3. Create required directories
        print("3. Creating required directories...")
        dirs = [
            Path("/opt/crash-mcp"),
            Path("/var/log/crash-mcp"),
            Path("/var/crash-dumps")
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
            subprocess.run(["chown", "crash-mcp:crash-mcp", str(d)],
                         capture_output=True, check=False)
            print(f"   ✓ {d}")

        # 4. Reload systemd daemon
        print("4. Reloading systemd daemon...")
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        print("   ✓ Daemon reloaded")

        print("\n✅ Systemd service installed successfully!")
        print("\nNext steps:")
        print("  1. Enable service: sudo systemctl enable crash-mcp.service")
        print("  2. Start service:  sudo systemctl start crash-mcp.service")
        print("  3. Check status:   sudo systemctl status crash-mcp.service")

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
            print("   Or manually run: sudo crash-mcp-install-systemd")


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
            print("   Or manually run: sudo crash-mcp-install-systemd")


if __name__ == "__main__":
    setup(
        cmdclass={
            'install': SystemdInstallCommand,
            'develop': SystemdDevelopCommand,
        }
    )

