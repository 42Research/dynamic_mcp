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
            ["groupadd", "-r", "crash-mcp"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0 or "already exists" in result.stderr:
            print("   ✓ Group ready")
        else:
            print(f"   ⚠️  {result.stderr.strip()}")

        result = subprocess.run(
            ["useradd", "-r", "-g", "crash-mcp", "-s", "/usr/sbin/nologin", "-d", "/opt/crash-mcp", "crash-mcp"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0 or "already exists" in result.stderr:
            print("   ✓ User ready")
        else:
            print(f"   ⚠️  {result.stderr.strip()}")

        # 3. Create required directories with proper permissions
        print("3. Creating required directories...")
        dirs = [
            (Path("/opt/crash-mcp"), "crash-mcp:crash-mcp", "0755"),
            (Path("/var/log/crash-mcp"), "crash-mcp:crash-mcp", "0755"),
            (Path("/var/crash-dumps"), "crash-mcp:crash-mcp", "0755")
        ]
        for d, owner, perms in dirs:
            d.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["chown", owner, str(d)],
                capture_output=True,
                check=False
            )
            subprocess.run(
                ["chmod", perms, str(d)],
                capture_output=True,
                check=False
            )
            print(f"   ✓ {d}")

        # 4. Configure /var/crash permissions for crash-mcp user read access
        print("4. Configuring /var/crash permissions...")
        crash_path = Path("/var/crash")
        if crash_path.exists():
            # Add crash-mcp user to group that can read /var/crash
            # Try to add crash-mcp to the group that owns /var/crash
            result = subprocess.run(
                ["stat", "-c", "%G", str(crash_path)],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                crash_group = result.stdout.strip()
                if crash_group != "crash-mcp":
                    subprocess.run(
                        ["usermod", "-a", "-G", crash_group, "crash-mcp"],
                        capture_output=True,
                        check=False
                    )
                    print(f"   ✓ Added crash-mcp to {crash_group} group")

            # Ensure /var/crash is readable by group
            subprocess.run(
                ["chmod", "g+rx", str(crash_path)],
                capture_output=True,
                check=False
            )
            print(f"   ✓ /var/crash permissions configured")
        else:
            print(f"   ⚠️  /var/crash does not exist (will be created by kdump)")

        # 5. Reload systemd daemon
        print("5. Reloading systemd daemon...")
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

