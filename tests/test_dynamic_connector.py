"""Tests for Dynamic reverse connection functionality."""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from crash_mcp.config import Config
from crash_mcp.dynamic_connector import DynamicConnector


@pytest.fixture
def mock_config():
    """Create a mock configuration."""
    config = MagicMock(spec=Config)
    config.enable_reverse_connection = True
    config.dynamic_url = "http://localhost:8787"
    config.dynamic_api_key = "test-api-key"
    config.heartbeat_interval = 1  # Short interval for testing
    return config


@pytest.fixture
def mock_crash_mcp_server():
    """Create a mock CrashMCPServer."""
    server = MagicMock()
    
    # Mock tool handlers
    async def mock_crash_command(params):
        return [MagicMock(text="crash command output")]
    
    async def mock_get_crash_info(params):
        return [MagicMock(text='{"session": {"is_active": false}}')]
    
    async def mock_list_crash_dumps(params):
        return [MagicMock(text='{"dumps": []}')]
    
    async def mock_start_crash_session(params):
        return [MagicMock(text="Session started")]
    
    async def mock_close_crash_session(params):
        return [MagicMock(text="Session closed")]
    
    server._handle_crash_command = mock_crash_command
    server._handle_get_crash_info = mock_get_crash_info
    server._handle_list_crash_dumps = mock_list_crash_dumps
    server._handle_start_crash_session = mock_start_crash_session
    server._handle_close_crash_session = mock_close_crash_session
    
    return server


@pytest.mark.asyncio
async def test_dynamic_connector_initialization(mock_config, mock_crash_mcp_server):
    """Test DynamicConnector initialization."""
    connector = DynamicConnector(mock_config, mock_crash_mcp_server)
    
    assert connector.config == mock_config
    assert connector.crash_mcp_server == mock_crash_mcp_server
    assert connector.server_id is None
    assert connector.heartbeat_task is None
    assert connector.session is None


@pytest.mark.asyncio
async def test_registration_disabled(mock_crash_mcp_server):
    """Test that registration is skipped when disabled."""
    config = MagicMock(spec=Config)
    config.enable_reverse_connection = False
    
    connector = DynamicConnector(config, mock_crash_mcp_server)
    await connector.start()
    
    assert connector.session is None
    assert connector.server_id is None


@pytest.mark.asyncio
async def test_registration_success(mock_config, mock_crash_mcp_server):
    """Test successful registration with Dynamic."""
    connector = DynamicConnector(mock_config, mock_crash_mcp_server)
    
    # Mock aiohttp session
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={"id": "mcp-test-123"})
    
    with patch('aiohttp.ClientSession') as mock_session_class:
        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.post.return_value.__aexit__ = AsyncMock()
        mock_session_class.return_value = mock_session
        
        await connector.start()
        
        # Verify session was created
        assert connector.session is not None
        
        # Verify registration was called
        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args
        assert call_args[0][0] == "http://localhost:8787/api/mcp/connect"
        
        # Verify server_id was set
        assert connector.server_id == "mcp-test-123"
        
        # Clean up
        await connector.stop()


@pytest.mark.asyncio
async def test_registration_failure(mock_config, mock_crash_mcp_server):
    """Test registration failure handling."""
    connector = DynamicConnector(mock_config, mock_crash_mcp_server)
    
    # Mock aiohttp session with error response
    mock_response = AsyncMock()
    mock_response.status = 500
    mock_response.text = AsyncMock(return_value="Internal Server Error")
    
    with patch('aiohttp.ClientSession') as mock_session_class:
        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.post.return_value.__aexit__ = AsyncMock()
        mock_session_class.return_value = mock_session
        
        await connector.start()
        
        # Verify server_id was not set
        assert connector.server_id is None
        
        # Clean up
        await connector.stop()


@pytest.mark.asyncio
async def test_handle_crash_command_request(mock_config, mock_crash_mcp_server):
    """Test handling crash_command request."""
    connector = DynamicConnector(mock_config, mock_crash_mcp_server)
    
    result = await connector.handle_dynamic_request(
        "crash_command",
        {"command": "sys", "timeout": 120}
    )
    
    assert result["success"] is True
    assert "crash command output" in result["data"]


@pytest.mark.asyncio
async def test_handle_get_crash_info_request(mock_config, mock_crash_mcp_server):
    """Test handling get_crash_info request."""
    connector = DynamicConnector(mock_config, mock_crash_mcp_server)
    
    result = await connector.handle_dynamic_request("get_crash_info", {})
    
    assert result["success"] is True
    assert "session" in result["data"]


@pytest.mark.asyncio
async def test_handle_unknown_method(mock_config, mock_crash_mcp_server):
    """Test handling unknown method."""
    connector = DynamicConnector(mock_config, mock_crash_mcp_server)
    
    result = await connector.handle_dynamic_request("unknown_method", {})
    
    assert result["success"] is False
    assert "Unknown method" in result["error"]


@pytest.mark.asyncio
async def test_handle_request_error(mock_config, mock_crash_mcp_server):
    """Test error handling in request processing."""
    connector = DynamicConnector(mock_config, mock_crash_mcp_server)
    
    # Make the handler raise an exception
    async def error_handler(params):
        raise ValueError("Test error")
    
    mock_crash_mcp_server._handle_crash_command = error_handler
    
    result = await connector.handle_dynamic_request(
        "crash_command",
        {"command": "sys"}
    )
    
    assert result["success"] is False
    assert "Test error" in result["error"]


@pytest.mark.asyncio
async def test_stop_connector(mock_config, mock_crash_mcp_server):
    """Test stopping the connector."""
    connector = DynamicConnector(mock_config, mock_crash_mcp_server)
    
    # Mock session
    mock_session = AsyncMock()
    connector.session = mock_session
    
    # Mock heartbeat task
    mock_task = AsyncMock()
    connector.heartbeat_task = mock_task
    
    await connector.stop()
    
    # Verify task was cancelled
    mock_task.cancel.assert_called_once()
    
    # Verify session was closed
    mock_session.close.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

