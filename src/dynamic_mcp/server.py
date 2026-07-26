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
from dynamic_mcp.source_rag import SourceRAG
from dynamic_mcp.background_jobs import BackgroundJobManager

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


class ExecuteBashParams(BaseModel):
    """Parameters for execute_bash_command tool."""
    command: str
    timeout: Optional[int] = 60
    working_dir: Optional[str] = None


class ExecuteBashBackgroundParams(BaseModel):
    """Parameters for execute_bash_background tool."""
    command: str
    working_dir: Optional[str] = None


class ExecuteBPFtraceBackgroundParams(BaseModel):
    """Parameters for execute_bpftrace_background tool."""
    script: str
    use_sudo: Optional[bool] = True


class GetJobOutputParams(BaseModel):
    """Parameters for get_job_output tool."""
    job_id: str


class KillJobParams(BaseModel):
    """Parameters for kill_job tool."""
    job_id: str


class SearchSourceParams(BaseModel):
    """Parameters for search_source_files tool."""
    query: str
    max_files: Optional[int] = 5


class GetSourceFileParams(BaseModel):
    """Parameters for get_source_file tool."""
    path: str


class DynamicMCPServer:
    """MCP Server for crash dump analysis."""

    def __init__(self, source_dir: Optional[str] = None):
        self.config = Config()
        self.server = Server("dynamic-mcp")
        self.crash_discovery = CrashDumpDiscovery(str(self.config.crash_dump_path))
        self.crash_session_manager = CrashSessionManager()
        self.kernel_detection = KernelDetection(str(self.config.kernel_path))
        self.bpftrace_executor = BPFtraceExecutor()
        self.job_manager = BackgroundJobManager()

        # Source RAG — optional, enabled when --source-dir is provided
        self.source_rag: Optional[SourceRAG] = None
        resolved_dir = source_dir or os.getenv("SOURCE_DIR")
        if resolved_dir:
            print(f"[Source RAG] Indexing: {resolved_dir}", flush=True)
            try:
                self.source_rag = SourceRAG(resolved_dir)
                abs_path = str(self.source_rag.source_dir)
                print(f"[Source RAG] ✓ Ready — {self.source_rag.indexed_count} files indexed", flush=True)
                print(f"[Source RAG]   Path: {abs_path}", flush=True)
            except Exception as e:
                print(f"[Source RAG] ✗ Failed to index {resolved_dir}: {e}", flush=True)
                logger.error(f"Failed to index source directory: {e}")

        # Generate unique, secure MCP server name
        self.mcp_server_name = self._generate_secure_server_name()

        # Dynamic service configuration
        self.dynamic_url = os.getenv(
            "DYNAMIC_URL",
            "https://production.dynamic-agent.workers.dev"
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
                ),
                Tool(
                    name="execute_bash_command",
                    description="Execute a bash command on the host system for dynamic analysis",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "Bash command to execute"
                            },
                            "timeout": {
                                "type": "integer",
                                "description": "Execution timeout in seconds (optional, default 60s)",
                                "default": 60
                            },
                            "working_dir": {
                                "type": "string",
                                "description": "Working directory for the command (optional)"
                            }
                        },
                        "required": ["command"]
                    }
                ),
                Tool(
                    name="execute_bash_background",
                    description="Start a bash command in the background and return immediately with a job_id. Use get_job_output to poll for output.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "Bash command to execute"
                            },
                            "working_dir": {
                                "type": "string",
                                "description": "Working directory for the command (optional)"
                            }
                        },
                        "required": ["command"]
                    }
                ),
                Tool(
                    name="execute_bpftrace_background",
                    description="Start a BPFtrace script in the background and return immediately with a job_id. Use get_job_output to poll for output, kill_job to stop it.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "script": {
                                "type": "string",
                                "description": "BPFtrace script content"
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
                    name="get_job_output",
                    description="Get current accumulated stdout/stderr and status of a background job started with execute_bash_background or execute_bpftrace_background.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "job_id": {
                                "type": "string",
                                "description": "Job ID returned by execute_bash_background or execute_bpftrace_background"
                            }
                        },
                        "required": ["job_id"]
                    }
                ),
                Tool(
                    name="kill_job",
                    description="Terminate a running background job.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "job_id": {
                                "type": "string",
                                "description": "Job ID to terminate"
                            }
                        },
                        "required": ["job_id"]
                    }
                ),
                Tool(
                    name="list_jobs",
                    description="List all background jobs (running and completed).",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                ),
            ] + (self._source_rag_tools() if self.source_rag else [])

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
            elif name == "execute_bash_command":
                return await self._handle_execute_bash(arguments)
            elif name == "execute_bash_background":
                return await self._handle_execute_bash_background(arguments)
            elif name == "execute_bpftrace_background":
                return await self._handle_execute_bpftrace_background(arguments)
            elif name == "get_job_output":
                return await self._handle_get_job_output(arguments)
            elif name == "kill_job":
                return await self._handle_kill_job(arguments)
            elif name == "list_jobs":
                return await self._handle_list_jobs(arguments)
            elif name == "search_source_files":
                return await self._handle_search_source_files(arguments)
            elif name == "get_source_file":
                return await self._handle_get_source_file(arguments)
            elif name == "list_source_files":
                return await self._handle_list_source_files(arguments)
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

    async def _handle_execute_bash(self, arguments: Dict[str, Any]) -> Sequence[TextContent]:
        """Handle bash command execution."""
        try:
            params = ExecuteBashParams(**arguments)
            logger.info(f"Executing bash command: {params.command!r}")

            process = await asyncio.create_subprocess_exec(
                "bash", "-c", params.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=params.working_dir,
            )

            try:
                stdout_b, stderr_b = await asyncio.wait_for(
                    process.communicate(), timeout=params.timeout
                )
                return_code = process.returncode
            except asyncio.TimeoutError:
                try:
                    process.terminate()
                    await asyncio.wait_for(process.wait(), timeout=2)
                except Exception:
                    process.kill()
                return_code = 124
                stdout_b, stderr_b = b"", b"Timed out"

            stdout = stdout_b.decode(errors="replace")
            stderr = stderr_b.decode(errors="replace")

            result_text = f"Exit code: {return_code}\n"
            if stdout:
                result_text += f"\nOutput:\n{stdout}"
            if stderr:
                result_text += f"\nStderr:\n{stderr}"
            if not stdout and not stderr:
                result_text += "\n(no output)"

            return [TextContent(type="text", text=result_text)]

        except Exception as e:
            logger.error(f"Error executing bash command: {e}")
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    # ------------------------------------------------------------------
    # Background job handlers
    # ------------------------------------------------------------------

    async def _handle_execute_bash_background(self, arguments: Dict[str, Any]) -> Sequence[TextContent]:
        """Start a bash command in the background."""
        try:
            params = ExecuteBashBackgroundParams(**arguments)
            job_id = await self.job_manager.start_bash(params.command, params.working_dir)
            text = (
                f"Job started.\n"
                f"job_id: {job_id}\n"
                f"Use get_job_output(job_id=\"{job_id}\") to poll output.\n"
                f"Use kill_job(job_id=\"{job_id}\") to stop it."
            )
            return [TextContent(type="text", text=text)]
        except Exception as e:
            logger.error(f"Error starting bash background job: {e}")
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    async def _handle_execute_bpftrace_background(self, arguments: Dict[str, Any]) -> Sequence[TextContent]:
        """Start a BPFtrace script in the background."""
        try:
            params = ExecuteBPFtraceBackgroundParams(**arguments)
            job_id = await self.job_manager.start_bpftrace(params.script, params.use_sudo)
            text = (
                f"Job started.\n"
                f"job_id: {job_id}\n"
                f"Use get_job_output(job_id=\"{job_id}\") to poll output.\n"
                f"Use kill_job(job_id=\"{job_id}\") to stop it."
            )
            return [TextContent(type="text", text=text)]
        except Exception as e:
            logger.error(f"Error starting bpftrace background job: {e}")
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    async def _handle_get_job_output(self, arguments: Dict[str, Any]) -> Sequence[TextContent]:
        """Get accumulated output of a background job."""
        try:
            params = GetJobOutputParams(**arguments)
            info = self.job_manager.get_output(params.job_id)
            if "error" in info:
                return [TextContent(type="text", text=f"Error: {info['error']}")]
            exit_code_str = str(info["exit_code"]) if info["exit_code"] is not None else "—"
            text = (
                f"job_id: {info['job_id']}\n"
                f"status: {info['status']}\n"
                f"elapsed: {info['elapsed_s']}s\n"
                f"exit_code: {exit_code_str}\n"
            )
            if info["stdout"]:
                text += f"\n--- stdout ---\n{info['stdout']}"
            if info["stderr"]:
                text += f"\n--- stderr ---\n{info['stderr']}"
            if not info["stdout"] and not info["stderr"]:
                text += "\n(no output yet)"
            return [TextContent(type="text", text=text)]
        except Exception as e:
            logger.error(f"Error getting job output: {e}")
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    async def _handle_kill_job(self, arguments: Dict[str, Any]) -> Sequence[TextContent]:
        """Terminate a background job."""
        try:
            params = KillJobParams(**arguments)
            was_running = await self.job_manager.kill_job(params.job_id)
            if was_running:
                text = f"Job {params.job_id} terminated."
            else:
                info = self.job_manager.get_output(params.job_id)
                if "error" in info:
                    text = f"Error: {info['error']}"
                else:
                    text = f"Job {params.job_id} was not running (status: {info['status']})."
            return [TextContent(type="text", text=text)]
        except Exception as e:
            logger.error(f"Error killing job: {e}")
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    async def _handle_list_jobs(self, arguments: Dict[str, Any]) -> Sequence[TextContent]:
        """List all background jobs."""
        try:
            jobs = self.job_manager.list_jobs()
            if not jobs:
                return [TextContent(type="text", text="No background jobs.")]
            lines = [f"{len(jobs)} job(s):"]
            for j in jobs:
                exit_str = f"  exit={j['exit_code']}" if j["exit_code"] is not None else ""
                lines.append(
                    f"  {j['job_id']}  [{j['status']}]  {j['label']}: \"{j['command_desc']}\"  "
                    f"{j['elapsed_s']}s{exit_str}"
                )
            return [TextContent(type="text", text="\n".join(lines))]
        except Exception as e:
            logger.error(f"Error listing jobs: {e}")
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    # ------------------------------------------------------------------
    # Source RAG helpers
    # ------------------------------------------------------------------

    def _source_rag_tools(self) -> List[Tool]:
        """Return Tool definitions for source RAG (only when source_rag is set)."""
        return [
            Tool(
                name="search_source_files",
                description=(
                    "Search the indexed local source directory for files relevant to a query. "
                    "Returns code snippets from the most relevant files. "
                    "Use this whenever the user asks about the codebase, a function, a class, "
                    "or any source-level question."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language or keyword query describing what to search for"
                        },
                        "max_files": {
                            "type": "integer",
                            "description": "Maximum number of files to include in the result (default 5)",
                            "default": 5
                        }
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="get_source_file",
                description=(
                    "Retrieve the full content of a specific source file from the indexed directory. "
                    "Use this when you need to read an exact file identified via search_source_files or list_source_files."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path of the file within the source directory (e.g. src/utils/helper.py)"
                        }
                    },
                    "required": ["path"]
                }
            ),
            Tool(
                name="list_source_files",
                description=(
                    "List all source files that have been indexed from the local source directory. "
                    "Useful for discovering what files are available before searching."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            ),
        ]

    async def _handle_search_source_files(self, arguments: Dict[str, Any]) -> Sequence[TextContent]:
        """Handle source file search."""
        if not self.source_rag:
            return [TextContent(type="text", text="Error: Source RAG is not enabled (no source directory indexed)")]
        try:
            params = SearchSourceParams(**arguments)
            result = self.source_rag.search(params.query, max_files=params.max_files or 5)
            if not result:
                return [TextContent(type="text", text=f"No source files matched the query: {params.query!r}")]
            return [TextContent(type="text", text=result)]
        except Exception as e:
            logger.error(f"Error searching source files: {e}")
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    async def _handle_get_source_file(self, arguments: Dict[str, Any]) -> Sequence[TextContent]:
        """Handle fetching a specific source file."""
        if not self.source_rag:
            return [TextContent(type="text", text="Error: Source RAG is not enabled (no source directory indexed)")]
        try:
            params = GetSourceFileParams(**arguments)
            content = self.source_rag.get_file(params.path)
            if content is None:
                return [TextContent(type="text", text=f"File not found in index: {params.path!r}")]
            return [TextContent(type="text", text=f"### {params.path}\n```\n{content}\n```")]
        except Exception as e:
            logger.error(f"Error getting source file: {e}")
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    async def _handle_list_source_files(self, arguments: Dict[str, Any]) -> Sequence[TextContent]:
        """Handle listing all indexed source files."""
        if not self.source_rag:
            return [TextContent(type="text", text="Error: Source RAG is not enabled (no source directory indexed)")]
        try:
            files = self.source_rag.list_files()
            if not files:
                return [TextContent(type="text", text="No source files indexed.")]
            lines = [f"Indexed source files ({len(files)} total):"] + [f"  {f}" for f in files]
            return [TextContent(type="text", text="\n".join(lines))]
        except Exception as e:
            logger.error(f"Error listing source files: {e}")
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
                        elif method == "execute_bash_command":
                            result = await self._handle_execute_bash(params)
                        elif method == "execute_bash_background":
                            result = await self._handle_execute_bash_background(params)
                        elif method == "execute_bpftrace_background":
                            result = await self._handle_execute_bpftrace_background(params)
                        elif method == "get_job_output":
                            result = await self._handle_get_job_output(params)
                        elif method == "kill_job":
                            result = await self._handle_kill_job(params)
                        elif method == "list_jobs":
                            result = await self._handle_list_jobs(params)
                        elif method == "search_source_files":
                            result = await self._handle_search_source_files(params)
                        elif method == "get_source_file":
                            result = await self._handle_get_source_file(params)
                        elif method == "list_source_files":
                            result = await self._handle_list_source_files(params)
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
                            },
                            {
                                "name": "execute_bash_command",
                                "description": "Execute a bash command on the host system for dynamic analysis",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "command": {
                                            "type": "string",
                                            "description": "Bash command to execute"
                                        },
                                        "timeout": {
                                            "type": "integer",
                                            "description": "Execution timeout in seconds (optional, default 60s)",
                                            "default": 60
                                        },
                                        "working_dir": {
                                            "type": "string",
                                            "description": "Working directory for the command (optional)"
                                        }
                                    },
                                    "required": ["command"]
                                }
                            },
                            {
                                "name": "execute_bash_background",
                                "description": "Start a bash command in the background and return immediately with a job_id",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "command": {"type": "string", "description": "Bash command to execute"},
                                        "working_dir": {"type": "string", "description": "Working directory (optional)"}
                                    },
                                    "required": ["command"]
                                }
                            },
                            {
                                "name": "execute_bpftrace_background",
                                "description": "Start a BPFtrace script in the background and return immediately with a job_id",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "script": {"type": "string", "description": "BPFtrace script content"},
                                        "use_sudo": {"type": "boolean", "description": "Use sudo (default true)", "default": True}
                                    },
                                    "required": ["script"]
                                }
                            },
                            {
                                "name": "get_job_output",
                                "description": "Get accumulated output and status of a background job",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "job_id": {"type": "string", "description": "Job ID"}
                                    },
                                    "required": ["job_id"]
                                }
                            },
                            {
                                "name": "kill_job",
                                "description": "Terminate a running background job",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "job_id": {"type": "string", "description": "Job ID to terminate"}
                                    },
                                    "required": ["job_id"]
                                }
                            },
                            {
                                "name": "list_jobs",
                                "description": "List all background jobs (running and completed)",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {},
                                    "required": []
                                }
                            }
                        ]

                        # Append source RAG tools if enabled
                        if self.source_rag:
                            tools_list += [
                                {
                                    "name": "search_source_files",
                                    "description": "Search the indexed local source directory for files relevant to a query",
                                    "inputSchema": {
                                        "type": "object",
                                        "properties": {
                                            "query": {"type": "string", "description": "Search query"},
                                            "max_files": {"type": "integer", "description": "Max files to return", "default": 5}
                                        },
                                        "required": ["query"]
                                    }
                                },
                                {
                                    "name": "get_source_file",
                                    "description": "Retrieve the full content of a specific indexed source file",
                                    "inputSchema": {
                                        "type": "object",
                                        "properties": {
                                            "path": {"type": "string", "description": "Relative file path"}
                                        },
                                        "required": ["path"]
                                    }
                                },
                                {
                                    "name": "list_source_files",
                                    "description": "List all source files indexed from the local source directory",
                                    "inputSchema": {
                                        "type": "object",
                                        "properties": {},
                                        "required": []
                                    }
                                },
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
                capabilities = [
                    "crash_command",
                    "get_crash_info",
                    "list_crash_dumps",
                    "start_crash_session",
                    "close_crash_session",
                    "execute_bpftrace_script",
                    "get_bpftrace_info",
                    "execute_bash_command",
                    "execute_bash_background",
                    "execute_bpftrace_background",
                    "get_job_output",
                    "kill_job",
                    "list_jobs",
                ]
                if self.source_rag:
                    capabilities += [
                        "search_source_files",
                        "get_source_file",
                        "list_source_files",
                    ]
                payload = {
                    "id": self.mcp_server_name,
                    "name": self.mcp_server_name,
                    "type": "crash_analysis",
                    "version": "0.1.0",
                    "capabilities": capabilities,
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

    async def heartbeat_loop(self):
        """Send periodic heartbeats to Dynamic to keep the registration alive.

        The Dynamic worker marks a server inactive after 30 s without a heartbeat
        and stops routing chat requests to it.  We ping every 20 s to stay well
        inside that window.
        """
        import aiohttp
        while True:
            await asyncio.sleep(20)
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.dynamic_url}/api/mcp/registry/heartbeat",
                        json={"serverId": self.mcp_server_name},
                        timeout=aiohttp.ClientTimeout(total=5),
                    ) as resp:
                        if resp.status != 200:
                            logger.warning(f"Heartbeat returned HTTP {resp.status}, re-registering")
                            await self.register_with_dynamic()
            except Exception as e:
                logger.warning(f"Heartbeat failed: {e}, attempting re-registration")
                try:
                    await self.register_with_dynamic()
                except Exception:
                    pass

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

            # Register with Dynamic and start heartbeat loop (if tunnel is available)
            if self.mcp_server_url:
                asyncio.create_task(self.register_with_dynamic())
                asyncio.create_task(self.heartbeat_loop())

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

    # Parse --source-dir argument
    source_dir: Optional[str] = None
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--source-dir" and i + 1 < len(args):
            source_dir = args[i + 1]
            break
        if arg.startswith("--source-dir="):
            source_dir = arg.split("=", 1)[1]
            break

    server = DynamicMCPServer(source_dir=source_dir)

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
    if "--stdio" in sys.argv:
        await server.run_stdio()
    else:
        # HTTP/SSE mode (default) — collect positional args skipping flags and their values
        host = "0.0.0.0"
        port = 8080
        positional = []
        skip_next = False
        for arg in sys.argv[1:]:
            if skip_next:
                skip_next = False
                continue
            if arg in ("--source-dir", "--http"):
                skip_next = True
                continue
            if arg.startswith("--"):
                continue
            positional.append(arg)
        if len(positional) > 0:
            host = positional[0]
        if len(positional) > 1:
            port = int(positional[1])
        await server.run_http(host, port)


def main():
    """Synchronous main entry point for console script."""
    asyncio.run(async_main())


def main_http():
    """Entry point for HTTP server (alias for main, HTTP is now the default)."""
    main()


if __name__ == "__main__":
    main()
