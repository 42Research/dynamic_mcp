# Crash MCP Migration Notes

## Tunnel Functionality Removal

As of commit c44082e, tunnel and Dynamic service integration functionality has been removed from crash_mcp.

### Rationale

**Separation of Concerns:**
- crash_mcp focuses on core crash dump analysis
- Tunnel management moved to crash_vscode (TypeScript VSCode extension)
- This allows both projects to evolve independently

### What Was Removed

**Commits Reverted:**
- `03bb531` - Heartbeat handling for Dynamic registration
- `dcb59bd` - Local server URL in registration payload
- `83a72e6` - Dynamic URL configuration fix
- `c4fecdd` - Dynamic URL configuration update
- `cce3292` - Dynamic reverse connection functionality

**Files Deleted:**
- `src/crash_mcp/dynamic_connector.py` - Reverse connection handler
- `tests/test_dynamic_connector.py` - Dynamic connector tests
- `test_integration.py` - Integration tests

**Code Removed:**
- `/api/mcp/request` endpoint in server.py
- Dynamic URL configuration in config.py
- `aiohttp` dependency from pyproject.toml and requirements.txt
- Tunnel-related environment variables from .env.example

### What Was Preserved

✅ **Core Functionality:**
- Crash dump analysis tools
- Session management
- Kernel detection
- Crash discovery
- `/api/tools` endpoint for listing available tools

### Migration Path

If you were using crash_mcp with Dynamic service:

1. **Install crash_vscode extension:**
   - This extension now handles tunnel setup and server management
   - Automatically starts crash-mcp-http with tunnel support

2. **Configure tunnel:**
   - Open VSCode settings
   - Set `crashMcp.enableTunnel` to true (default)
   - Extension will automatically set up cloudflared tunnel

3. **Server Registration:**
   - crash_vscode passes tunnel URL to crash-mcp-http via `MCP_SERVER_URL`
   - Server can use this for reverse connection to Dynamic

### Environment Variables

crash_mcp no longer reads tunnel-related environment variables:
- ❌ `ENABLE_REVERSE_CONNECTION` - Removed
- ❌ `DYNAMIC_URL` - Removed
- ❌ `DYNAMIC_HEARTBEAT_INTERVAL` - Removed

crash_mcp still reads:
- ✅ `PORT` - HTTP port (default: 8080)
- ✅ `LOG_LEVEL` - Logging level (default: INFO)
- ✅ `MCP_SERVER_URL` - Public server URL (set by crash_vscode)

### API Changes

**Removed Endpoints:**
- `POST /api/mcp/request` - Dynamic service requests

**Preserved Endpoints:**
- `GET /sse` - Server-Sent Events for MCP protocol
- `GET /api/tools` - List available tools
- `POST /api/crash/command` - Execute crash commands
- `GET /api/crash/info` - Get crash session info
- `GET /api/crash/dumps` - List crash dumps
- `POST /api/crash/session/start` - Start crash session
- `POST /api/crash/session/close` - Close crash session

### Dependency Changes

**Removed:**
- `aiohttp` - Was used for Dynamic service communication

**Kept:**
- `mcp` - MCP protocol implementation
- `uvicorn` - ASGI server
- `pydantic` - Data validation
- `python-dotenv` - Environment variable loading

### Testing

To verify the migration:

```bash
# Verify tunnel code is removed
ls src/crash_mcp/ | grep -i dynamic  # Should return nothing

# Verify tools endpoint still works
curl http://localhost:8080/api/tools

# Verify no aiohttp dependency
grep aiohttp pyproject.toml requirements.txt  # Should return nothing

# Verify core functionality
python -m crash_mcp.server  # Should start without errors
```

### Troubleshooting

**Issue:** "Module 'crash_mcp.dynamic_connector' not found"
- **Solution:** Update to latest version with tunnel code removed

**Issue:** Server won't start with `ENABLE_REVERSE_CONNECTION`
- **Solution:** This variable is no longer used. Use crash_vscode extension instead.

**Issue:** Can't connect to Dynamic service
- **Solution:** Use crash_vscode extension which handles tunnel setup

### For Developers

If you need to extend crash_mcp:

1. **Add new crash analysis tools:**
   - Modify `_setup_tools()` in server.py
   - Add tool handler with `@self.server.call_tool()`

2. **Add new API endpoints:**
   - Modify `asgi_app()` in server.py
   - Add path handling in the ASGI handler

3. **Extend configuration:**
   - Modify Config class in config.py
   - Add environment variable support

### Support

For questions about the migration:
1. Check this document
2. Review MIGRATION_SUMMARY.md in repository root
3. Check crash_vscode documentation for tunnel setup
4. Open an issue on GitHub

### Version History

- **v0.1.0+** - Tunnel functionality removed, core crash analysis only
- **v0.0.x** - Previous versions with tunnel support (deprecated)

### Related Projects

- **crash_vscode** - VSCode extension with server and tunnel management
- **crash-mcp-vscode** - Reference implementation for server management
- **Dynamic** - Cloudflare Workers service for crash analysis chat

