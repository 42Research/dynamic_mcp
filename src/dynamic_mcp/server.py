#!/usr/bin/env python3
"""
Dynamic MCP Server

An MCP server that provides crash dump analysis tools.
"""

import asyncio
import json
import logging
import os
import secrets
import string
import sys
from typing import Any, Dict, List, Optional, Sequence

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv():
        pass
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.server.sse import SseServerTransport
import uvicorn
from mcp.types import (
    CallToolRequest,
    CallToolResult,
    ListToolsRequest,
    TextContent,
    Tool,
)
from pydantic import BaseModel

# Import crash-related modules from dynamic_mcp
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'dynamic_mcp', 'src'))
from dynamic_mcp.config import Config, setup_logging, check_system_requirements, validate_crash_utility, ensure_crash_dump_access
from dynamic_mcp.crash_discovery import CrashDumpDiscovery
from dynamic_mcp.crash_session import CrashSessionManager
from dynamic_mcp.kernel_detection import KernelDetection
from dynamic_mcp.tunnel_manager import TunnelManager
from dynamic_mcp.bpftrace_executor import BPFtraceExecutor

# Load environment variables
try:
    load_dotenv()
except:
    pass

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class CrashCommandParams(BaseModel):
    """Parameters for crash command tool."""
    command: str
    timeout: Optional[int] = 120


class StartSessionParams(BaseModel):
    """Parameters for start session tool."""
    dump_name: Optional[str] = None
    timeout: Optional[int] = 120


class ListDumpsParams(BaseModel):
    """Parameters for list dumps tool."""
    max_dumps: Optional[int] = 10


class ExecuteBPFtraceParams(BaseModel):
    """Parameters for execute BPFtrace script tool."""
    script: str
    timeout: Optional[int] = 30
    use_sudo: Optional[bool] = True


class DynamicMCPServer:
    """MCP Server for crash dump analysis."""

    def __init__(self):
        self.config = Config()
        self.server = Server("dynamic-mcp")
        self.crash_discovery = CrashDumpDiscovery(str(self.config.crash_dump_path))
        self.crash_session_manager = CrashSessionManager()
        self.kernel_detection = KernelDetection(str(self.config.kernel_path))
        self.bpftrace_executor = BPFtraceExecutor()

        # Generate unique, secure MCP server name
        self.mcp_server_name = self._generate_secure_server_name()

        # Dynamic service configuration
        self.dynamic_url = os.getenv(
            "DYNAMIC_URL",
            "https://dynamic.artem-blagodarenko.workers.dev"
        )
        self.mcp_server_url = os.getenv("MCP_SERVER_URL")

        # Tunnel management
        self.tunnel_manager: Optional[TunnelManager] = None
        self.enable_reverse_connection = os.getenv("ENABLE_REVERSE_CONNECTION", "false").lower() == "true"

        self._setup_tools()

    def _generate_secure_server_name(self) -> str:
        """Generate a unique, URL-safe, cryptographically secure server name."""
        # Use alphanumeric characters for URL safety
        alphabet = string.ascii_lowercase + string.digits
        # Generate 16 random characters (128 bits of entropy)
        random_part = ''.join(secrets.choice(alphabet) for _ in range(16))
        return f"mcp-{random_part}"

    async def setup_tunnel(self, port: int) -> Optional[str]:
        """Setup reverse connection tunnel if enabled.

        Args:
            port: Local port to expose via tunnel

        Returns:
            The public tunnel URL if tunnel is enabled, None otherwise
        """
        if not self.enable_reverse_connection:
            logger.info("Reverse connection disabled (ENABLE_REVERSE_CONNECTION=false)")
            return None

        try:
            logger.info("Setting up reverse connection tunnel...")
            self.tunnel_manager = TunnelManager(port)
            tunnel_url = await self.tunnel_manager.start_tunnel()

            # Update MCP server URL if not already set
            if not self.mcp_server_url:
                self.mcp_server_url = tunnel_url

            return tunnel_url
        except Exception as e:
            logger.error(f"Failed to setup tunnel: {e}")
            logger.warning("Continuing without tunnel - server will run in local mode only")
            self.tunnel_manager = None
            return None

    async def cleanup_tunnel(self) -> None:
        """Stop the tunnel if it's running."""
        if self.tunnel_manager:
            await self.tunnel_manager.stop_tunnel()
            self.tunnel_manager = None
    
    def _setup_tools(self):
        """Register MCP tools."""

        @self.server.list_tools()
        async def handle_list_tools() -> List[Tool]:
            """List available tools."""
            return [
                Tool(
                    name="crash_command",
                    description="Execute a command in the crash utility session",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "The crash command to execute"
                            },
                            "timeout": {
                                "type": "integer",
                                "description": "Command timeout in seconds (optional, default 120s for large dumps)",
                                "default": 120
                            }
                        },
                        "required": ["command"]
                    }
                ),
                Tool(
                    name="get_crash_info",
                    description="Get information about the current crash dump and session",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                ),
                Tool(
                    name="list_crash_dumps",
                    description="List all available crash dumps",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "max_dumps": {
                                "type": "integer",
                                "description": "Maximum number of dumps to return (optional)",
                                "default": 10
                            }
                        },
                        "required": []
                    }
                ),
                Tool(
                    name="start_crash_session",
                    description="Start a new crash session with a specific dump",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "dump_name": {
                                "type": "string",
                                "description": "Name of the crash dump file (optional, uses latest if not specified)"
                            },
                            "timeout": {
                                "type": "integer",
                                "description": "Session timeout in seconds (optional, default 120s for large dumps)",
                                "default": 120
                            }
                        },
                        "required": []
                    }
                ),
                Tool(
                    name="close_crash_session",
                    description="Close the current crash session",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                ),
                Tool(
                    name="execute_bpftrace_script",
                    description="Execute a BPFtrace script for system tracing and analysis",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "script": {
                                "type": "string",
                                "description": "BPFtrace script content"
                            },
                            "timeout": {
                                "type": "integer",
                                "description": "Script execution timeout in seconds (optional, default 30s)",
                                "default": 30
                            },
                            "use_sudo": {
                                "type": "boolean",
                                "description": "Whether to use sudo for execution (optional, default true)",
                                "default": True
                            }
                        },
                        "required": ["script"]
                    }
                ),
                Tool(
                    name="get_bpftrace_info",
                    description="Get information about BPFtrace availability and version",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                )
            ]

        @self.server.call_tool()
        async def handle_call_tool(
            name: str, arguments: Dict[str, Any]
        ) -> Sequence[TextContent]:
            """Handle tool calls."""
            if name == "crash_command":
                return await self._handle_crash_command(arguments)
            elif name == "get_crash_info":
                return await self._handle_get_crash_info(arguments)
            elif name == "list_crash_dumps":
                return await self._handle_list_crash_dumps(arguments)
            elif name == "start_crash_session":
                return await self._handle_start_crash_session(arguments)
            elif name == "close_crash_session":
                return await self._handle_close_crash_session(arguments)
            elif name == "execute_bpftrace_script":
                return await self._handle_execute_bpftrace_script(arguments)
            elif name == "get_bpftrace_info":
                return await self._handle_get_bpftrace_info(arguments)
            else:
                raise ValueError(f"Unknown tool: {name}")

    async def _handle_crash_command(self, arguments: Dict[str, Any]) -> Sequence[TextContent]:
        """Handle crash command execution."""
        try:
            params = CrashCommandParams(**arguments)

            logger.info(f"Executing crash command: {params.command}")

            # Ensure we have an active session
            if not self.crash_session_manager.is_session_active():
                # Try to start a session with the latest crash dump
                await self._handle_start_crash_session({})

                if not self.crash_session_manager.is_session_active():
                    return [TextContent(
                        type="text",
                        text="Error: No active crash session and could not start one"
                    )]

            # Execute the command
            output, error, return_code = self.crash_session_manager.execute_command(params.command, params.timeout)

            # Format the result
            if return_code == 0:
                result_text = output if output else "Command executed successfully (no output)"
            else:
                result_text = f"Command failed (exit code {return_code})\nOutput: {output}\nError: {error}"

            return [TextContent(type="text", text=result_text)]

        except Exception as e:
            logger.error(f"Error handling crash command: {e}")
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    async def _handle_get_crash_info(self, arguments: Dict[str, Any]) -> Sequence[TextContent]:
        """Handle getting crash information."""
        try:
            info = {}

            # Get session info
            session_info = self.crash_session_manager.get_session_info()
            if session_info:
                info["session"] = session_info
            else:
                info["session"] = {"is_active": False}

            # Get available crash dumps
            crash_dumps = self.crash_discovery.find_crash_dumps()
            info["available_dumps"] = [dump.to_dict() for dump in crash_dumps[:5]]

            # Get available kernels
            kernels = self.kernel_detection.find_kernel_files()
            info["available_kernels"] = [kernel.to_dict() for kernel in kernels[:5]]

            return [TextContent(type="text", text=json.dumps(info, indent=2))]

        except Exception as e:
            logger.error(f"Error getting crash info: {e}")
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    async def _handle_list_crash_dumps(self, arguments: Dict[str, Any]) -> Sequence[TextContent]:
        """Handle listing crash dumps."""
        try:
            params = ListDumpsParams(**arguments)

            crash_dumps = self.crash_discovery.find_crash_dumps()

            if not crash_dumps:
                return [TextContent(type="text", text="No crash dumps found")]

            # Limit results
            crash_dumps = crash_dumps[:params.max_dumps]

            # Format output
            output = f"Found {len(crash_dumps)} crash dumps:\n\n"
            for i, dump in enumerate(crash_dumps, 1):
                output += f"{i}. {dump.name}\n"
                output += f"   Path: {dump.path}\n"
                output += f"   Size: {dump.size:,} bytes\n"
                output += f"   Modified: {dump.mtime}\n\n"

            return [TextContent(type="text", text=output)]

        except Exception as e:
            logger.error(f"Error listing crash dumps: {e}")
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    async def _handle_start_crash_session(self, arguments: Dict[str, Any]) -> Sequence[TextContent]:
        """Handle starting a crash session."""
        try:
            params = StartSessionParams(**arguments)

            # Find crash dump
            if params.dump_name:
                crash_dump = self.crash_discovery.get_crash_dump_by_name(params.dump_name)
                if not crash_dump:
                    return [TextContent(type="text", text=f"Error: Crash dump '{params.dump_name}' not found")]
            else:
                crash_dump = self.crash_discovery.get_latest_crash_dump()
                if not crash_dump:
                    return [TextContent(type="text", text="Error: No crash dumps found")]

            # Validate crash dump
            if not self.crash_discovery.is_valid_crash_dump(crash_dump):
                return [TextContent(type="text", text=f"Error: Invalid crash dump: {crash_dump.name}")]

            # Find matching kernel - create KernelDetection with specific crash dump path
            kernel_detection = KernelDetection(str(self.config.kernel_path), str(crash_dump.path))
            kernel = kernel_detection.find_matching_kernel(crash_dump)
            if not kernel:
                return [TextContent(type="text", text="Error: No matching kernel found")]

            # Start session
            success = self.crash_session_manager.start_session(crash_dump, kernel, params.timeout)

            if success:
                return [TextContent(type="text", text=f"Crash session started successfully\nDump: {crash_dump.name}\nKernel: {kernel.name}")]
            else:
                return [TextContent(type="text", text="Error: Failed to start crash session")]

        except Exception as e:
            logger.error(f"Error starting crash session: {e}")
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    async def _handle_close_crash_session(self, arguments: Dict[str, Any]) -> Sequence[TextContent]:
        """Handle closing the crash session."""
        try:
            if self.crash_session_manager.is_session_active():
                self.crash_session_manager.close_session()
                return [TextContent(type="text", text="Crash session closed")]
            else:
                return [TextContent(type="text", text="No active crash session to close")]

        except Exception as e:
            logger.error(f"Error closing crash session: {e}")
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    async def _handle_execute_bpftrace_script(self, arguments: Dict[str, Any]) -> Sequence[TextContent]:
        """Handle BPFtrace script execution."""
        try:
            params = ExecuteBPFtraceParams(**arguments)

            if not self.bpftrace_executor.is_available():
                return [TextContent(type="text", text="Error: BPFtrace is not available on this system")]

            logger.info(f"Executing BPFtrace script (timeout: {params.timeout}s)")

            # Execute the script
            stdout, stderr, return_code = await self.bpftrace_executor.execute_script(
                params.script,
                timeout=params.timeout,
                use_sudo=params.use_sudo
            )

            # Format the result
            result_text = f"BPFtrace execution completed (exit code: {return_code})\n\n"
            if stdout:
                result_text += f"Output:\n{stdout}\n"
            if stderr:
                result_text += f"Errors:\n{stderr}\n"
            if not stdout and not stderr:
                result_text += "No output produced"

            return [TextContent(type="text", text=result_text)]

        except Exception as e:
            logger.error(f"Error executing BPFtrace script: {e}")
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    async def _handle_get_bpftrace_info(self, arguments: Dict[str, Any]) -> Sequence[TextContent]:
        """Handle getting BPFtrace information."""
        try:
            info = {
                "available": self.bpftrace_executor.is_available(),
                "version": self.bpftrace_executor.get_version(),
                "default_timeout": self.bpftrace_executor.timeout
            }

            return [TextContent(type="text", text=json.dumps(info, indent=2))]

        except Exception as e:
            logger.error(f"Error getting BPFtrace info: {e}")
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    async def run_stdio(self):
        """Run the MCP server with stdio transport."""
        logger.info("Starting Dynamic MCP Server (stdio)")

        async with stdio_server() as (read_stream, write_stream):
            try:
                await self.server.run(
                    read_stream,
                    write_stream,
                    InitializationOptions(
                        server_name="dynamic-mcp",
                        server_version="0.1.0",
                        capabilities=self.server.get_capabilities(
                            notification_options=NotificationOptions(),
                            experimental_capabilities=None,
                        ),
                    ),
                )
            except Exception as e:
                logger.error(f"Server error: {e}")
                raise
            finally:
                # Clean up crash session if active
                if self.crash_session_manager.is_session_active():
                    self.crash_session_manager.close_session()

    def create_sse_app(self):
        """Create Starlette app for SSE transport."""
        # Create the transport with the message endpoint
        transport = SseServerTransport("/message")

        # Create the ASGI app using the transport
        async def asgi_app(scope, receive, send):
            if scope["type"] == "http":
                path = scope["path"]

                if path == "/sse":
                    # Handle SSE endpoint
                    try:
                        # Wrapper to add streaming-friendly headers
                        async def send_with_headers(message):
                            if message['type'] == 'http.response.start':
                                # Add headers that help with SSE streaming through proxies/tunnels
                                headers = list(message.get('headers', []))

                                # Add streaming headers if not already present
                                header_names = {h[0].lower() for h in headers}

                                if b'cache-control' not in header_names:
                                    headers.append([b'cache-control', b'no-cache, no-transform'])
                                if b'connection' not in header_names:
                                    headers.append([b'connection', b'keep-alive'])
                                if b'x-accel-buffering' not in header_names:
                                    headers.append([b'x-accel-buffering', b'no'])

                                message['headers'] = headers

                            await send(message)

                        async with transport.connect_sse(
                            scope, receive, send_with_headers
                        ) as streams:
                            await self.server.run(
                                *streams,
                                InitializationOptions(
                                    server_name="dynamic-mcp",
                                    server_version="0.1.0",
                                    capabilities=self.server.get_capabilities(
                                        notification_options=NotificationOptions(),
                                        experimental_capabilities=None,
                                    ),
                                )
                            )
                    except Exception as e:
                        logger.error(f"SSE transport error: {e}")
                        # Send error response
                        await send({
                            'type': 'http.response.start',
                            'status': 500,
                            'headers': [[b'content-type', b'text/plain']],
                        })
                        await send({
                            'type': 'http.response.body',
                            'body': f'Server Error: {str(e)}'.encode(),
                        })
                elif path == "/message":
                    # Handle message endpoint
                    try:
                        await transport.handle_post_message(scope, receive, send)
                    except Exception as e:
                        logger.error(f"Message endpoint error: {e}")
                        # Send error response
                        await send({
                            'type': 'http.response.start',
                            'status': 500,
                            'headers': [[b'content-type', b'application/json']],
                        })
                        await send({
                            'type': 'http.response.body',
                            'body': json.dumps({"error": str(e)}).encode(),
                        })
                elif path == "/api/mcp/request":
                    # Handle MCP request endpoint (called by Dynamic worker)
                    try:
                        # Read request body
                        body = b""
                        while True:
                            message = await receive()
                            if message["type"] == "http.request":
                                body += message.get("body", b"")
                                if not message.get("more_body", False):
                                    break

                        # Parse request
                        request_data = json.loads(body.decode())
                        method = request_data.get("method")
                        params = request_data.get("params", {})

                        logger.info(f"[MCP Request] Received method: {method}")

                        # Call the appropriate tool handler
                        result = None
                        if method == "crash_command":
                            result = await self._handle_crash_command(params)
                        elif method == "get_crash_info":
                            result = await self._handle_get_crash_info(params)
                        elif method == "list_crash_dumps":
                            result = await self._handle_list_crash_dumps(params)
                        elif method == "start_crash_session":
                            result = await self._handle_start_crash_session(params)
                        elif method == "close_crash_session":
                            result = await self._handle_close_crash_session(params)
                        elif method == "execute_bpftrace_script":
                            result = await self._handle_execute_bpftrace_script(params)
                        elif method == "get_bpftrace_info":
                            result = await self._handle_get_bpftrace_info(params)
                        else:
                            raise ValueError(f"Unknown method: {method}")

                        # Convert TextContent results to strings
                        if isinstance(result, (list, tuple)):
                            result_text = "\n".join([
                                item.text if hasattr(item, 'text') else str(item)
                                for item in result
                            ])
                        else:
                            result_text = str(result)

                        # Send success response
                        logger.debug(f"Sending success response for method: {method}")
                        await send({
                            'type': 'http.response.start',
                            'status': 200,
                            'headers': [[b'content-type', b'application/json']],
                        })
                        logger.debug("Response start sent")
                        await send({
                            'type': 'http.response.body',
                            'body': json.dumps({
                                "success": True,
                                "data": result_text
                            }).encode(),
                        })
                        logger.debug("Response body sent")
                    except Exception as e:
                        logger.error(f"MCP request error: {e}")
                        # Send error response
                        await send({
                            'type': 'http.response.start',
                            'status': 400,
                            'headers': [[b'content-type', b'application/json']],
                        })
                        await send({
                            'type': 'http.response.body',
                            'body': json.dumps({
                                "success": False,
                                "error": str(e)
                            }).encode(),
                        })
                elif path == "/api/tools":
                    # Handle tools listing request
                    try:
                        # Get available tools - list_tools is a handler, not a coroutine
                        # We need to manually construct the tools list
                        tools_list = [
                            {
                                "name": "crash_command",
                                "description": "Execute a command in the crash utility session",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "command": {
                                            "type": "string",
                                            "description": "The crash command to execute"
                                        },
                                        "timeout": {
                                            "type": "integer",
                                            "description": "Command timeout in seconds (optional, default 120s for large dumps)",
                                            "default": 120
                                        }
                                    },
                                    "required": ["command"]
                                }
                            },
                            {
                                "name": "get_crash_info",
                                "description": "Get information about the current crash dump and session",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {},
                                    "required": []
                                }
                            },
                            {
                                "name": "list_crash_dumps",
                                "description": "List all available crash dumps",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "max_dumps": {
                                            "type": "integer",
                                            "description": "Maximum number of dumps to return (optional)",
                                            "default": 10
                                        }
                                    },
                                    "required": []
                                }
                            },
                            {
                                "name": "start_crash_session",
                                "description": "Start a new crash session with a specific dump",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "dump_name": {
                                            "type": "string",
                                            "description": "Name of the crash dump file (optional, uses latest if not specified)"
                                        },
                                        "timeout": {
                                            "type": "integer",
                                            "description": "Session timeout in seconds (optional, default 120s for large dumps)",
                                            "default": 120
                                        }
                                    },
                                    "required": []
                                }
                            },
                            {
                                "name": "close_crash_session",
                                "description": "Close the current crash session",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {},
                                    "required": []
                                }
                            },
                            {
                                "name": "execute_bpftrace_script",
                                "description": "Execute a BPFtrace script for system tracing and analysis",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "script": {
                                            "type": "string",
                                            "description": "BPFtrace script content"
                                        },
                                        "timeout": {
                                            "type": "integer",
                                            "description": "Script execution timeout in seconds (optional, default 30s)",
                                            "default": 30
                                        },
                                        "use_sudo": {
                                            "type": "boolean",
                                            "description": "Whether to use sudo for execution (optional, default true)",
                                            "default": True
                                        }
                                    },
                                    "required": ["script"]
                                }
                            },
                            {
                                "name": "get_bpftrace_info",
                                "description": "Get information about BPFtrace availability and version",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {},
                                    "required": []
                                }
                            }
                        ]

                        # Send response
                        await send({
                            'type': 'http.response.start',
                            'status': 200,
                            'headers': [[b'content-type', b'application/json']],
                        })
                        await send({
                            'type': 'http.response.body',
                            'body': json.dumps({"tools": tools_list}).encode(),
                        })
                    except Exception as e:
                        logger.error(f"Tools endpoint error: {e}")
                        # Send error response
                        await send({
                            'type': 'http.response.start',
                            'status': 500,
                            'headers': [[b'content-type', b'application/json']],
                        })
                        await send({
                            'type': 'http.response.body',
                            'body': json.dumps({"error": str(e)}).encode(),
                        })
                else:
                    # 404 for other paths
                    await send({
                        'type': 'http.response.start',
                        'status': 404,
                        'headers': [[b'content-type', b'text/plain']],
                    })
                    await send({
                        'type': 'http.response.body',
                        'body': b'Not Found',
                    })

        return asgi_app

    async def register_with_dynamic(self):
        """Register this MCP server with Dynamic service."""
        if not self.mcp_server_url:
            logger.warning("MCP_SERVER_URL not set, skipping Dynamic registration")
            return

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                payload = {
                    "id": self.mcp_server_name,
                    "name": self.mcp_server_name,
                    "type": "crash_analysis",
                    "version": "0.1.0",
                    "capabilities": [
                        "crash_command",
                        "get_crash_info",
                        "list_crash_dumps",
                        "start_crash_session",
                        "close_crash_session",
                        "execute_bpftrace_script",
                        "get_bpftrace_info"
                    ],
                    "url": self.mcp_server_url
                }

                connect_url = f"{self.dynamic_url}/api/mcp/connect"
                logger.info(f"Registering with Dynamic at {connect_url}")
                logger.info(f"Using unique server name: {self.mcp_server_name}")

                async with session.post(
                    connect_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    result = await resp.json()
                    if result.get("status") == "success":
                        server_id = result.get("serverId")
                        chat_url = result.get("chatUrl")
                        logger.info(f"✓ Registered with Dynamic as @{server_id}")
                        logger.info(f"✓ Use @{server_id} in Dynamic chat to access this server")
                        if chat_url:
                            logger.info(f"✓ Chat URL: {chat_url}")
                    else:
                        logger.error(f"✗ Registration failed: {result.get('message')}")
        except Exception as e:
            logger.error(f"✗ Failed to register with Dynamic: {e}")

    async def run_http(self, host: str = "0.0.0.0", port: int = 8080):
        """Run the MCP server with HTTP/SSE transport."""
        logger.info(f"Starting Crash MCP Server (HTTP) on {host}:{port}")
        logger.info(f"Reverse connection: {'ENABLED' if self.enable_reverse_connection else 'DISABLED'}")

        try:
            # Setup tunnel if reverse connection is enabled
            if self.enable_reverse_connection:
                logger.info("")
                logger.info("═══════════════════════════════════════════════════════")
                logger.info("Step 1: Setting up public tunnel...")
                logger.info("═══════════════════════════════════════════════════════")
                tunnel_url = await self.setup_tunnel(port)
                if tunnel_url:
                    logger.info(f"✓ Tunnel URL: {tunnel_url}")
                    logger.info("")
                    logger.info("═══════════════════════════════════════════════════════")
                    logger.info("Step 2: Starting HTTP server...")
                    logger.info("═══════════════════════════════════════════════════════")
                else:
                    logger.info("")
                    logger.info("═══════════════════════════════════════════════════════")
                    logger.info("Step 2: Starting HTTP server (local mode)...")
                    logger.info("═══════════════════════════════════════════════════════")

            asgi_app = self.create_sse_app()

            config = uvicorn.Config(
                app=asgi_app,
                host=host,
                port=port,
                log_level="info"
            )
            server = uvicorn.Server(config)

            # Register with Dynamic after server starts (if tunnel is available)
            if self.mcp_server_url:
                asyncio.create_task(self.register_with_dynamic())

            await server.serve()
        finally:
            # Clean up tunnel
            await self.cleanup_tunnel()

            # Clean up crash session if active
            if self.crash_session_manager.is_session_active():
                self.crash_session_manager.close_session()


async def async_main():
    """Async main entry point."""
    # Enable reverse connection by default if not explicitly set
    if "ENABLE_REVERSE_CONNECTION" not in os.environ:
        os.environ["ENABLE_REVERSE_CONNECTION"] = "true"

    server = DynamicMCPServer()

    # Ensure crash dump directory is readable (configure permissions if needed)
    logger.info("Checking crash dump directory access...")
    if not ensure_crash_dump_access():
        logger.warning("Could not ensure crash dump directory is readable - some functionality may not work")

    # Check system requirements
    requirements = check_system_requirements()
    logger.info(f"System requirements: {requirements}")

    # Validate crash utility
    crash_version = validate_crash_utility()
    if not crash_version:
        logger.error("Crash utility not available - some functionality may not work")

    # Check for warnings
    if not requirements.get("crash_dump_access", False):
        logger.warning("No access to crash dump directories")
    if not requirements.get("crash_dump_readable", False):
        logger.warning("Crash dump directory is not readable - may have permission issues")
    if not requirements.get("kernel_access", False):
        logger.warning("No access to kernel directories")
    if not requirements.get("root_access", False):
        logger.warning("Not running as root - may have limited access to crash dumps")

    # Check command line arguments for transport mode
    if len(sys.argv) > 1 and sys.argv[1] == "--http":
        # HTTP/SSE mode
        host = sys.argv[2] if len(sys.argv) > 2 else "0.0.0.0"
        port = int(sys.argv[3]) if len(sys.argv) > 3 else 8080

        await server.run_http(host, port)
    else:
        # Default stdio mode
        await server.run_stdio()


def main():
    """Synchronous main entry point for console script."""
    asyncio.run(async_main())


def main_http():
    """Entry point for HTTP server."""
    sys.argv = [sys.argv[0], "--http"] + sys.argv[1:]
    main()


if __name__ == "__main__":
    main()
