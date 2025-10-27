"""Dynamic reverse connection handler for crash MCP server."""

import asyncio
import json
import logging
from typing import Any, Dict, Optional
import aiohttp

logger = logging.getLogger(__name__)


class DynamicConnector:
    """Handles reverse connection to Dynamic service."""
    
    def __init__(self, config, crash_mcp_server):
        """
        Initialize Dynamic connector.
        
        Args:
            config: Configuration object with Dynamic settings
            crash_mcp_server: Reference to the CrashMCPServer instance
        """
        self.config = config
        self.crash_mcp_server = crash_mcp_server
        self.server_id: Optional[str] = None
        self.heartbeat_task: Optional[asyncio.Task] = None
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def start(self):
        """Start the Dynamic connection."""
        if not self.config.enable_reverse_connection:
            logger.info("Reverse connection to Dynamic is disabled")
            return
            
        logger.info(f"Starting reverse connection to Dynamic at {self.config.dynamic_url}")
        
        # Create HTTP session
        self.session = aiohttp.ClientSession()
        
        # Register with Dynamic
        await self.register_with_dynamic()
        
        # Start heartbeat task
        if self.server_id:
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            
    async def stop(self):
        """Stop the Dynamic connection."""
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
                
        if self.session:
            await self.session.close()
            
        logger.info("Dynamic connection stopped")
        
    async def register_with_dynamic(self):
        """Register this MCP server with Dynamic."""
        if not self.session:
            logger.error("HTTP session not initialized")
            return

        url = f"{self.config.dynamic_url}/api/mcp/connect"

        # Prepare registration payload
        # Note: Dynamic expects the MCP server to provide its endpoint URL
        # so Dynamic can send requests back to it
        payload = {
            "name": "crash_mcp",
            "type": "crash_analysis",
            "version": "0.1.0",
            "capabilities": [
                "crash_command",
                "get_crash_info",
                "list_crash_dumps",
                "start_crash_session",
                "close_crash_session"
            ]
        }

        headers = {
            "Content-Type": "application/json"
        }

        if self.config.dynamic_api_key:
            headers["Authorization"] = f"Bearer {self.config.dynamic_api_key}"

        try:
            async with self.session.post(url, json=payload, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    self.server_id = data.get("id")
                    logger.info(f"Successfully registered with Dynamic as {self.server_id}")
                    logger.info(f"Registration response: {data}")
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to register with Dynamic: {response.status} - {error_text}")
        except Exception as e:
            logger.error(f"Error registering with Dynamic: {e}")
            
    async def _heartbeat_loop(self):
        """Send periodic heartbeats to Dynamic."""
        while True:
            try:
                await asyncio.sleep(self.config.heartbeat_interval)
                await self._send_heartbeat()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
                
    async def _send_heartbeat(self):
        """Send a single heartbeat to Dynamic."""
        if not self.server_id or not self.session:
            return
            
        url = f"{self.config.dynamic_url}/api/mcp/registry/heartbeat"
        
        payload = {
            "serverId": self.server_id
        }
        
        headers = {
            "Content-Type": "application/json"
        }
        
        if self.config.dynamic_api_key:
            headers["Authorization"] = f"Bearer {self.config.dynamic_api_key}"
            
        try:
            async with self.session.post(url, json=payload, headers=headers) as response:
                if response.status != 200:
                    logger.warning(f"Heartbeat failed: {response.status}")
        except Exception as e:
            logger.error(f"Heartbeat request failed: {e}")
            
    async def handle_dynamic_request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle incoming request from Dynamic.
        
        Args:
            method: The tool/method name to execute
            params: Parameters for the method
            
        Returns:
            Result dictionary with success status and data/error
        """
        try:
            logger.info(f"Handling Dynamic request: {method}")
            
            # Map Dynamic method names to MCP tool handlers
            if method == "crash_command":
                result = await self.crash_mcp_server._handle_crash_command(params)
            elif method == "get_crash_info":
                result = await self.crash_mcp_server._handle_get_crash_info(params)
            elif method == "list_crash_dumps":
                result = await self.crash_mcp_server._handle_list_crash_dumps(params)
            elif method == "start_crash_session":
                result = await self.crash_mcp_server._handle_start_crash_session(params)
            elif method == "close_crash_session":
                result = await self.crash_mcp_server._handle_close_crash_session(params)
            else:
                return {
                    "success": False,
                    "error": f"Unknown method: {method}"
                }
                
            # Extract text content from MCP response
            if result and len(result) > 0:
                text_content = result[0].text if hasattr(result[0], 'text') else str(result[0])
                return {
                    "success": True,
                    "data": text_content
                }
            else:
                return {
                    "success": True,
                    "data": ""
                }
                
        except Exception as e:
            logger.error(f"Error handling Dynamic request: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

