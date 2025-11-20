# Dynamic MCP Server

A professional MCP (Model Context Protocol) server for crash dump analysis and kernel debugging.

## Features

- **Real Crash Utility Integration**: Execute actual crash utility commands with real output
- **Automatic Crash Dump Discovery**: Find and list crash dumps in `/var/crash`
- **Intelligent Kernel Matching**: Automatic kernel debug symbol detection and matching
- **Session Management**: Robust crash analysis session lifecycle management
- **Multiple Dump Formats**: Support for vmcore, core, crash, and dump files
- **Professional Forensics**: Real kernel debugging and system forensics capabilities

## Requirements

- **Crash Utility**: Version 8.0.4+ (system package: `crash`)
- **Python**: 3.10+ (3.11+ recommended)
- **Kernel Debug Symbols**: Available in `/usr/lib/debug/lib/modules/`
- **Crash Dumps**: Accessible in `/var/crash/` or custom location
- **Permissions**: Read access to crash dumps and kernel files

## Installation

### Quick Install (Recommended)

```bash
# Install directly from source
pip install -e .
```

### Development Install

```bash
# Create virtual environment (optional but recommended)
python3 -m venv dynamic_mcp_env
source dynamic_mcp_env/bin/activate

# Install dependencies and package
pip install -e .
```

### System Install

```bash
# Install system-wide (requires sudo)
sudo pip install .
```

### System Install with Systemd Service

```bash
# Install system-wide with automatic systemd service setup
sudo pip install .
```

This automatically:
- Installs the package
- Copies the systemd service file
- Creates the dynamic-mcp user and group
- Creates required directories
- Registers the service with systemd

See [SYSTEMD_INSTALLATION.md](SYSTEMD_INSTALLATION.md) for detailed systemd setup instructions.

## Usage

### Running the MCP Server

#### Stdio Mode (Default)
```bash
# Run the server with stdio transport
dynamic-mcp

# Or with module syntax
python -m dynamic_mcp.server
```

#### HTTP/SSE Mode
```bash
# Run the server with HTTP transport on default port 8080
dynamic-mcp-http

# Or with module syntax
python -m dynamic_mcp.server --http

# Access the server at: http://localhost:8080/sse
```

### MCP Client Configuration

#### For Stdio Transport
Add to your MCP client configuration (e.g., Claude Desktop):

```json
{
  "mcpServers": {
    "dynamic-mcp": {
      "command": "python",
      "args": ["-m", "dynamic_mcp.server"],
      "env": {
        "LOG_LEVEL": "INFO"
      }
    }
  }
}
```

#### For HTTP/SSE Transport
Configure your MCP client to connect to the HTTP endpoint:

```json
{
  "mcpServers": {
    "dynamic-mcp": {
      "url": "http://localhost:8080/sse",
      "env": {
        "LOG_LEVEL": "INFO"
      }
    }
  }
}
```

### Testing

```bash
# Run crash analysis tests
pytest tests/crash/

# Test crash utility integration
python tests/crash/test_crash_server.py

# Run all tests
pytest
```

## Configuration

Create a `.env` file with optional configuration:

```bash
# Crash dump paths
CRASH_DUMP_PATH=/var/crash
KERNEL_PATH=/boot

# Session timeouts
CRASH_SESSION_TIMEOUT=180
CRASH_COMMAND_TIMEOUT=120

# Logging configuration
LOG_LEVEL=INFO
SUPPRESS_MCP_WARNINGS=true
```

## MCP Tools

The server provides 5 comprehensive crash analysis tools:

### 1. crash_command
Execute crash utility commands with real output.

**Parameters:**
- `command` (string): Crash utility command to execute
- `timeout` (integer, optional): Command timeout in seconds (default: 120)

**Example:**
```json
{
  "command": "sys",
  "timeout": 60
}
```

### 2. get_crash_info
Get information about current crash dump and session.

**Returns:**
- Active session details
- Available crash dumps
- System requirements status

### 3. list_crash_dumps
List all available crash dumps.

**Parameters:**
- `max_dumps` (integer, optional): Maximum number of dumps to return (default: 10)

**Returns:**
- Crash dump details (name, path, size, timestamp)
- Readability status

### 4. start_crash_session
Start a new crash analysis session.

**Parameters:**
- `dump_name` (string, optional): Specific dump name (uses latest if not specified)
- `timeout` (integer, optional): Session startup timeout (default: 180)

**Returns:**
- Session startup status
- Matched kernel information

### 5. close_crash_session
Close the active crash analysis session.

**Returns:**
- Session closure status

## Example Usage

### Basic Crash Analysis Workflow

1. **List available crash dumps:**
   ```bash
   # Use the list_crash_dumps tool
   ```

2. **Start a crash session:**
   ```bash
   # Use start_crash_session tool (auto-selects latest dump)
   ```

3. **Execute crash commands:**
   ```bash
   # System information
   crash_command: "sys"

   # Backtrace
   crash_command: "bt"

   # Process list
   crash_command: "ps"

   # Kernel log
   crash_command: "log"

   # Module information
   crash_command: "mod"
   ```

4. **Close session when done:**
   ```bash
   # Use close_crash_session tool
   ```

## Troubleshooting

### System Requirements

**Crash utility not found:**
```bash
# Install crash utility (RHEL/CentOS/Fedora)
sudo yum install crash
# or
sudo dnf install crash

# Install crash utility (Ubuntu/Debian)
sudo apt-get install crash
```

**No crash dumps found:**
- Check `/var/crash/` directory exists and has crash dumps
- Ensure read permissions on crash dump files
- Verify crash dumps are valid format (vmcore, core, etc.)

**Kernel debug symbols missing:**
- Install kernel debug packages
- Check `/usr/lib/debug/lib/modules/` for debug symbols
- Ensure kernel version matches crash dump

### MCP Initialization Warnings

You may see warnings like:
```
WARNING - Failed to validate request: Received request before initialization was complete
```

**This is normal MCP protocol behavior** and doesn't affect functionality.

**To suppress these warnings:**
```bash
export SUPPRESS_MCP_WARNINGS=true
```

## How It Works

1. **Crash Dump Discovery**: Automatically scans `/var/crash/` for crash dumps
2. **Kernel Matching**: Finds matching kernel debug symbols in `/usr/lib/debug/`
3. **Session Management**: Starts crash utility process with proper kernel and dump
4. **Command Execution**: Uses pexpect to interact with crash utility process
5. **Output Capture**: Returns real crash utility output with proper formatting

## Supported Crash Analysis

### Crash Commands
- **System Info**: `sys`, `mach`, `help`
- **Process Analysis**: `ps`, `task`, `files`
- **Memory Analysis**: `kmem`, `vm`, `search`
- **Stack Analysis**: `bt`, `bt -a`, `bt -f`
- **Kernel Analysis**: `log`, `dmesg`, `mod`
- **Disassembly**: `dis`, `gdb`
- **Lustre Analysis**: Lustre-specific commands for filesystem debugging

### Crash Dump Formats
- **vmcore**: Standard Linux kernel crash dumps
- **core**: Core dump files
- **crash**: Crash utility format
- **dump**: Generic dump files

### Kernel Support
- **Debug Symbols**: Automatic detection from `/usr/lib/debug/`
- **Kernel Versions**: Support for multiple kernel versions
- **Lustre Kernels**: Special support for Lustre filesystem kernels

## Architecture

- **MCP Protocol**: Full compliance with Model Context Protocol
- **Real Integration**: Uses actual crash utility (not simulation)
- **Session Management**: Robust process lifecycle management
- **Error Handling**: Comprehensive error handling and recovery
- **Logging**: Detailed logging for debugging and monitoring

## License

This project is licensed under the MIT License.

Copyright © 2025 42Research Ltd

Permission is hereby granted, free of charge, to any person obtaining a copy of this software
and associated documentation files (the "Software"), to deal in the Software without restriction,
including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software.

For full license terms, see the [LICENSE](LICENSE) file.

**Contact**: Email: software@42research.co.uk | Website: https://42research.co.uk

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## Support

For issues and questions:
- Check the troubleshooting section above
- Review system requirements
- Ensure crash utility and debug symbols are properly installed
