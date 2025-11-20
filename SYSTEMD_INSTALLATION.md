# Systemd Service Installation

The dynamic-mcp package now includes automated systemd service installation and configuration.

## Installation Methods

### 1. Development Install (No Systemd)
```bash
pip install -e .
```
Installs the package in development mode. Systemd service setup is skipped.

### 2. Production Install (No Systemd)
```bash
pip install .
```
Installs the package normally. Systemd service setup is skipped.

### 3. Production Install with Systemd (Recommended)
```bash
sudo pip install .
```
Installs the package AND automatically:
- Copies `dynamic-mcp.service` to `/etc/systemd/system/`
- Creates `dynamic-mcp` user and group
- Creates required directories:
  - `/opt/dynamic-mcp`
  - `/var/log/dynamic-mcp`
  - `/var/crash-dumps`
- Reloads systemd daemon

### 4. Development Install with Systemd
```bash
sudo pip install -e .
```
Same as production install but in development mode.

### 5. Manual Systemd Setup
If you installed without sudo, you can manually setup systemd later:
```bash
sudo dynamic-mcp-install-systemd
```

## Post-Installation

After installation with systemd setup, enable and start the service:

```bash
# Enable service to start on boot
sudo systemctl enable dynamic-mcp.service

# Start the service now
sudo systemctl start dynamic-mcp.service

# Check service status
sudo systemctl status dynamic-mcp.service

# View service logs
sudo journalctl -u dynamic-mcp.service -f
```

## Service Configuration

The service runs on port 8080 by default and can be configured via environment variables:

```bash
# Set environment variables
sudo systemctl set-environment PORT=9000
sudo systemctl set-environment LOG_LEVEL=DEBUG

# Restart service to apply changes
sudo systemctl restart dynamic-mcp.service
```

## Troubleshooting

### Service fails to start
Check logs:
```bash
sudo journalctl -u dynamic-mcp.service -n 50
```

### Permission denied errors
Ensure the dynamic-mcp user owns the directories:
```bash
sudo chown -R dynamic-mcp:dynamic-mcp /opt/dynamic-mcp
sudo chown -R dynamic-mcp:dynamic-mcp /var/log/dynamic-mcp
sudo chown -R dynamic-mcp:dynamic-mcp /var/crash-dumps
```

### Service not found
Reload systemd daemon:
```bash
sudo systemctl daemon-reload
```

## Uninstallation

To remove the systemd service:

```bash
# Stop the service
sudo systemctl stop dynamic-mcp.service

# Disable the service
sudo systemctl disable dynamic-mcp.service

# Remove service file
sudo rm /etc/systemd/system/dynamic-mcp.service

# Reload systemd daemon
sudo systemctl daemon-reload

# Remove user and directories (optional)
sudo userdel dynamic-mcp
sudo rm -rf /opt/dynamic-mcp /var/log/dynamic-mcp /var/crash-dumps
```

## Implementation Details

The systemd integration is implemented through:

1. **setup.py**: Custom install commands that detect sudo and run systemd setup
2. **systemd_installer.py**: Standalone module for systemd service installation
3. **dynamic-mcp.service**: Systemd unit file with security hardening
4. **pyproject.toml**: Entry point for manual systemd installation

The implementation gracefully handles:
- Non-root installations (skips systemd setup with helpful message)
- Existing users/groups (doesn't fail if already present)
- Both development and production installs
- Manual setup via `dynamic-mcp-install-systemd` command

