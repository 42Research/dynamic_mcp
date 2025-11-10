"""Systemd service installer for crash-mcp."""

import os
import subprocess
import shutil
from pathlib import Path


def install_systemd_service():
    """Install and configure systemd service.
    
    This function:
    1. Copies crash-mcp.service to /etc/systemd/system/
    2. Creates crash-mcp user and group
    3. Creates required directories with proper permissions
    4. Reloads systemd daemon
    
    Returns:
        bool: True if successful, False otherwise
    """
    if os.geteuid() != 0:
        print("\n⚠️  Skipping systemd service setup (requires sudo)")
        print("   To enable systemd service, run: sudo pip install .")
        return False
    
    print("\n" + "="*60)
    print("Setting up systemd service...")
    print("="*60)
    
    try:
        # Find service file in package
        package_dir = Path(__file__).parent
        service_file = package_dir / "crash-mcp.service"

        if not service_file.exists():
            print(f"❌ Service file not found: {service_file}")
            return False
        
        systemd_dir = Path("/etc/systemd/system")
        service_dest = systemd_dir / "crash-mcp.service"
        
        # 1. Copy service file
        print("1. Installing service file...")
        shutil.copy2(str(service_file), str(service_dest))
        print(f"   ✓ Copied to {service_dest}")
        
        # 2. Create crash-mcp user and group
        print("2. Creating crash-mcp user and group...")
        result = subprocess.run(
            ["useradd", "-r", "-s", "/bin/false", "crash-mcp"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0 or "already exists" in result.stderr:
            print("   ✓ User/group ready")
        else:
            print(f"   ⚠️  {result.stderr.strip()}")
        
        # 3. Create required directories
        print("3. Creating required directories...")
        dirs = [
            Path("/opt/crash-mcp"),
            Path("/var/log/crash-mcp"),
            Path("/var/crash-dumps")
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["chown", "crash-mcp:crash-mcp", str(d)],
                capture_output=True,
                check=False
            )
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
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error setting up systemd service: {e}")
        print("   You can manually setup the service later.")
        return False


if __name__ == "__main__":
    install_systemd_service()

