# Quick Start - Systemd Service

## Installation with Systemd (Recommended)

```bash
# Install with automatic systemd setup
sudo pip install .

# Enable service to start on boot
sudo systemctl enable crash-mcp.service

# Start the service
sudo systemctl start crash-mcp.service

# Check status
sudo systemctl status crash-mcp.service
```

## Installation without Systemd

```bash
# Regular installation (no systemd)
pip install .

# Or development mode
pip install -e .
```

## Manual Systemd Setup (if needed)

```bash
# If you installed without sudo, setup systemd manually
sudo crash-mcp-install-systemd
```

## Service Management

```bash
# Start service
sudo systemctl start crash-mcp.service

# Stop service
sudo systemctl stop crash-mcp.service

# Restart service
sudo systemctl restart crash-mcp.service

# Check status
sudo systemctl status crash-mcp.service

# View logs
sudo journalctl -u crash-mcp.service -f

# Enable on boot
sudo systemctl enable crash-mcp.service

# Disable on boot
sudo systemctl disable crash-mcp.service
```

## Configuration

```bash
# Set environment variables
sudo systemctl set-environment PORT=9000
sudo systemctl set-environment LOG_LEVEL=DEBUG

# Restart to apply
sudo systemctl restart crash-mcp.service
```

## Troubleshooting

```bash
# View recent logs
sudo journalctl -u crash-mcp.service -n 50

# View all logs
sudo journalctl -u crash-mcp.service

# Check service file
sudo systemctl cat crash-mcp.service

# Reload systemd daemon
sudo systemctl daemon-reload
```

## Uninstall

```bash
# Stop and disable service
sudo systemctl stop crash-mcp.service
sudo systemctl disable crash-mcp.service

# Remove service file
sudo rm /etc/systemd/system/crash-mcp.service

# Reload systemd
sudo systemctl daemon-reload

# Uninstall package
pip uninstall crash-mcp
```

## What Gets Installed

When you run `sudo pip install .`:

1. **Service File**: `/etc/systemd/system/crash-mcp.service`
2. **User**: `crash-mcp` (system user)
3. **Directories**:
   - `/opt/crash-mcp` - Working directory
   - `/var/log/crash-mcp` - Log directory
   - `/var/crash-dumps` - Crash dumps directory

## Default Configuration

- **Port**: 8080
- **User**: crash-mcp
- **Group**: crash-mcp
- **Restart Policy**: on-failure (max 3 times in 60s)
- **Logging**: systemd journal

See [SYSTEMD_INSTALLATION.md](SYSTEMD_INSTALLATION.md) for detailed documentation.

