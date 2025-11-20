# Quick Start - Systemd Service

## Installation with Systemd (Recommended)

```bash
# Install with automatic systemd setup
sudo pip install .

# Enable service to start on boot
sudo systemctl enable dynamic-mcp.service

# Start the service
sudo systemctl start dynamic-mcp.service

# Check status
sudo systemctl status dynamic-mcp.service
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
sudo dynamic-mcp-install-systemd
```

## Service Management

```bash
# Start service
sudo systemctl start dynamic-mcp.service

# Stop service
sudo systemctl stop dynamic-mcp.service

# Restart service
sudo systemctl restart dynamic-mcp.service

# Check status
sudo systemctl status dynamic-mcp.service

# View logs
sudo journalctl -u dynamic-mcp.service -f

# Enable on boot
sudo systemctl enable dynamic-mcp.service

# Disable on boot
sudo systemctl disable dynamic-mcp.service
```

## Configuration

```bash
# Set environment variables
sudo systemctl set-environment PORT=9000
sudo systemctl set-environment LOG_LEVEL=DEBUG

# Restart to apply
sudo systemctl restart dynamic-mcp.service
```

## Troubleshooting

```bash
# View recent logs
sudo journalctl -u dynamic-mcp.service -n 50

# View all logs
sudo journalctl -u dynamic-mcp.service

# Check service file
sudo systemctl cat dynamic-mcp.service

# Reload systemd daemon
sudo systemctl daemon-reload
```

## Uninstall

```bash
# Stop and disable service
sudo systemctl stop dynamic-mcp.service
sudo systemctl disable dynamic-mcp.service

# Remove service file
sudo rm /etc/systemd/system/dynamic-mcp.service

# Reload systemd
sudo systemctl daemon-reload

# Uninstall package
pip uninstall dynamic-mcp
```

## What Gets Installed

When you run `sudo pip install .`:

1. **Service File**: `/etc/systemd/system/dynamic-mcp.service`
2. **User**: `dynamic-mcp` (system user)
3. **Directories**:
   - `/opt/dynamic-mcp` - Working directory
   - `/var/log/dynamic-mcp` - Log directory
   - `/var/crash-dumps` - Crash dumps directory

## Default Configuration

- **Port**: 8080
- **User**: dynamic-mcp
- **Group**: dynamic-mcp
- **Restart Policy**: on-failure (max 3 times in 60s)
- **Logging**: systemd journal

See [SYSTEMD_INSTALLATION.md](SYSTEMD_INSTALLATION.md) for detailed documentation.

