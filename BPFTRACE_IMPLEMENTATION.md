# BPFtrace MCP Implementation

## Overview
Added comprehensive BPFtrace support to the dynamic_mcp project, enabling MCP clients to execute BPFtrace scripts for system tracing and analysis.

## Components Implemented

### 1. Core Module: `bpftrace_executor.py`
**Location:** `src/dynamic_mcp/bpftrace_executor.py`

**Features:**
- `BPFtraceExecutor` class for managing BPFtrace script execution
- Automatic BPFtrace binary detection via system PATH
- Version detection and availability checking
- Async script execution with timeout handling
- Script validation with syntax checking
- Proper permission handling (sudo support)
- Graceful timeout management (exit code 124)

**Key Methods:**
- `is_available()` - Check if BPFtrace is installed
- `get_version()` - Get BPFtrace version string
- `execute_script(script, timeout, use_sudo)` - Execute BPFtrace script asynchronously
- `validate_script(script)` - Validate script syntax before execution

### 2. MCP Server Integration: `server.py`
**Location:** `src/dynamic_mcp/server.py`

**Changes:**
- Added `ExecuteBPFtraceParams` Pydantic model for parameter validation
- Initialized `BPFtraceExecutor` in `DynamicMCPServer.__init__()`
- Added two new MCP tools:
  - `execute_bpftrace_script` - Execute BPFtrace scripts
  - `get_bpftrace_info` - Get BPFtrace availability and version info

**Tool Handlers:**
- `_handle_execute_bpftrace_script()` - Executes scripts and returns output
- `_handle_get_bpftrace_info()` - Returns BPFtrace status and version

**HTTP/SSE Endpoints:**
- Updated `/api/mcp` endpoint to handle BPFtrace requests
- Updated `/api/tools` endpoint to list BPFtrace tools
- Added BPFtrace capabilities to Dynamic service registration

### 3. Test Suite: `tests/bpftrace/test_bpftrace_executor.py`
**Location:** `tests/bpftrace/test_bpftrace_executor.py`

**Test Coverage:**
- Executor initialization
- BPFtrace availability detection
- Version retrieval
- Script validation (valid and invalid scripts)
- Script execution (with root privilege checks)
- Timeout handling
- MCP server integration

## Usage

### Via MCP Protocol (Stdio)
```python
# Execute a BPFtrace script
{
  "method": "execute_bpftrace_script",
  "params": {
    "script": "BEGIN { printf(\"Hello\\n\"); exit(); }",
    "timeout": 30,
    "use_sudo": true
  }
}

# Get BPFtrace info
{
  "method": "get_bpftrace_info",
  "params": {}
}
```

### Via HTTP/SSE
```bash
# Execute script
curl -X POST http://localhost:8080/api/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "method": "execute_bpftrace_script",
    "params": {
      "script": "BEGIN { printf(\"test\\n\"); exit(); }"
    }
  }'

# Get tools list
curl http://localhost:8080/api/tools
```

## Permission Handling

- Scripts execute with `sudo -n` (non-interactive) by default
- Requires passwordless sudo for BPFtrace
- Gracefully handles permission errors
- Returns meaningful error messages

## Timeout Handling

- Default timeout: 30 seconds
- Configurable per-script
- Async execution with proper cleanup
- Exit code 124 indicates timeout

## Architecture

Follows existing crash_mcp patterns:
- Core functionality in dedicated module (`bpftrace_executor.py`)
- MCP server handles orchestration (`server.py`)
- Proper error handling and logging
- Async/await for non-blocking execution
- Structured output for MCP clients

## Testing

Run tests with:
```bash
python3 -m unittest tests.bpftrace.test_bpftrace_executor -v
```

All tests pass successfully. Root-privilege tests are skipped in non-root environments.

