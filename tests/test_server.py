import pytest
import os
import json
import tempfile
from unittest import mock
from mssql_mcp_server.server import app, list_tools, list_resources, read_resource, call_tool
from mssql_mcp_server.server_manager import ServerInfo
from pydantic import AnyUrl

def test_server_initialization():
    """Test that the server initializes correctly."""
    assert app.name == "mssql_mcp_server"

@pytest.mark.asyncio
async def test_list_tools():
    """Test that list_tools returns expected tools."""
    tools = await list_tools()
    assert len(tools) >= 1
    
    # At least the execute_sql tool should exist
    tool_names = [tool.name for tool in tools]
    assert "execute_sql" in tool_names
    
    # Check if new authentication-related tools exist
    assert "switch_server" in tool_names
    assert "list_servers" in tool_names
    assert "refresh_auth" in tool_names
    
    # Check the schema of execute_sql tool
    execute_sql_tool = next(tool for tool in tools if tool.name == "execute_sql")
    assert "query" in execute_sql_tool.inputSchema["properties"]
    assert "server" in execute_sql_tool.inputSchema["properties"]

@pytest.mark.asyncio
@mock.patch("mssql_mcp_server.server.get_server_manager")
async def test_list_servers_tool(mock_get_server_manager):
    """Test the list_servers tool"""
    # Mock the server manager
    mock_manager = mock.MagicMock()
    mock_get_server_manager.return_value = mock_manager
    
    # Mock the server list
    mock_manager.get_server_list.return_value = [
        ServerInfo(
            name="server1", 
            display_name="Test Server 1", 
            config={"auth_type": "sql"}
        ),
        ServerInfo(
            name="server2", 
            display_name="Test Server 2", 
            config={"auth_type": "entra", "auth_mode": "interactive"}
        )
    ]
    mock_manager.active_server = "server1"
    
    # Call the tool
    result = await call_tool("list_servers", {})
    
    # Verify results
    assert len(result) == 1
    content = result[0].text
    assert "Test Server 1" in content
    assert "Test Server 2" in content
    assert "SQL Auth" in content
    assert "Entra ID (Interactive)" in content
    assert "ACTIVE" in content

@pytest.mark.asyncio
@mock.patch("mssql_mcp_server.server.get_server_manager")
async def test_switch_server_tool(mock_get_server_manager):
    """Test the switch_server tool"""
    # Mock the server manager
    mock_manager = mock.MagicMock()
    mock_get_server_manager.return_value = mock_manager
    
    # Simulate successful server switch
    mock_manager.set_active_server.return_value = True
    mock_manager.get_server_by_name.return_value = ServerInfo(
        name="server2", 
        display_name="Test Server 2", 
        config={}
    )
    
    # Call the tool
    result = await call_tool("switch_server", {"server": "server2"})
    
    # Verify results
    assert len(result) == 1
    content = result[0].text
    assert "Switched to server: Test Server 2" in content
    
    # When server name doesn't exist
    mock_manager.set_active_server.return_value = False
    mock_manager.get_server_list.return_value = [
        ServerInfo(name="server1", display_name="Test Server 1", config={})
    ]
    
    result = await call_tool("switch_server", {"server": "nonexistent"})
    content = result[0].text
    assert "Error: Unknown server" in content
    assert "server1" in content  # Available server list

@pytest.mark.asyncio
@mock.patch("mssql_mcp_server.server.get_server_manager")
@mock.patch("mssql_mcp_server.server.create_connection")
async def test_refresh_auth_tool(mock_create_connection, mock_get_server_manager):
    """Test the refresh_auth tool"""
    # Mock the server manager
    mock_manager = mock.MagicMock()
    mock_get_server_manager.return_value = mock_manager
    mock_manager.active_server = "server1"
    
    # Server configuration using Entra ID authentication
    mock_manager.get_active_config.return_value = {
        "auth_type": "entra",
        "token_cache_file": "/tmp/token_cache.json"
    }
    
    # Simulate successful connection
    mock_create_connection.return_value = mock.MagicMock()
    
    # Mock file deletion operations
    with mock.patch("os.path.exists", return_value=True), \
         mock.patch("os.remove") as mock_remove:
        
        # Call the tool
        result = await call_tool("refresh_auth", {})
        
        # Verify results
        assert len(result) == 1
        content = result[0].text
        assert "Authentication refreshed successfully" in content
        
        # Verify cache file was deleted
        mock_remove.assert_called_once()
    
    # When run on a server with SQL authentication
    mock_manager.get_active_config.return_value = {
        "auth_type": "sql"
    }
    
    result = await call_tool("refresh_auth", {})
    content = result[0].text
    assert "Error: Server 'server1' does not use Entra ID authentication" in content

@pytest.mark.asyncio
@mock.patch("mssql_mcp_server.server.get_server_manager")
@mock.patch("mssql_mcp_server.server.create_connection")
async def test_execute_sql_tool(mock_create_connection, mock_get_server_manager):
    """Test the execute_sql tool"""
    # Mock the server manager
    mock_manager = mock.MagicMock()
    mock_get_server_manager.return_value = mock_manager
    mock_manager.active_server = "server1"
    mock_manager.get_active_config.return_value = {
        "database": "test_db"
    }
    
    # Mock DB connection
    mock_conn = mock.MagicMock()
    mock_create_connection.return_value = mock_conn
    mock_cursor = mock.MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    
    # Simulate SELECT query results
    mock_cursor.description = [("id",), ("name",)]
    mock_cursor.fetchall.return_value = [(1, "test1"), (2, "test2")]
    
    # Call the tool
    result = await call_tool("execute_sql", {"query": "SELECT id, name FROM test_table"})
    
    # Verify results
    assert len(result) == 1
    content = result[0].text
    assert "id,name" in content
    assert "1,test1" in content
    assert "2,test2" in content
    
    # When query parameter is missing
    result = await call_tool("execute_sql", {})
    content = result[0].text
    assert "Error: Query is required" in content

@pytest.mark.asyncio
async def test_call_tool_invalid_name():
    """Test calling a tool with an invalid name."""
    result = await call_tool("invalid_tool", {})
    assert len(result) == 1
    assert "Unknown tool" in result[0].text

# Skip database-dependent tests if no database connection
@pytest.mark.asyncio
@pytest.mark.skipif(
    not all([
        pytest.importorskip("pymssql"),
        pytest.importorskip("mssql_mcp_server")
    ]),
    reason="SQL Server connection not available"
)
@mock.patch("mssql_mcp_server.server.get_server_manager")
@mock.patch("mssql_mcp_server.server.create_connection")
async def test_list_resources(mock_create_connection, mock_get_server_manager):
    """Test listing resources (requires database connection)."""
    # Mock the server manager
    mock_manager = mock.MagicMock()
    mock_get_server_manager.return_value = mock_manager
    
    # Server list
    mock_manager.get_server_list.return_value = [
        ServerInfo(name="server1", display_name="Test Server 1", config={}),
        ServerInfo(name="server2", display_name="Test Server 2", config={})
    ]
    
    # Active server and its configuration
    mock_manager.active_server = "server1"
    mock_manager.get_active_config.return_value = {
        "server": "test-server",
        "database": "test-db"
    }
    
    # Mock DB connection
    mock_conn = mock.MagicMock()
    mock_create_connection.return_value = mock_conn
    mock_cursor = mock.MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    
    # Table list results
    mock_cursor.fetchall.return_value = [("table1",), ("table2",)]
    
    # Get resource list
    resources = await list_resources()
    
    # Verify results
    assert len(resources) >= 4  # 2 servers + 2 tables
    
    # Check server resources
    server_resources = [r for r in resources if r.uri.startswith("mssql://") and "/tables/" not in r.uri]
    assert len(server_resources) >= 2
    assert any(r.name.startswith("Server: Test Server 1") for r in server_resources)
    assert any(r.name.startswith("Server: Test Server 2") for r in server_resources)
    
    # Check table resources
    table_resources = [r for r in resources if "/tables/" in r.uri]
    assert len(table_resources) >= 2
    assert any(r.name == "Table: table1" for r in table_resources)
    assert any(r.name == "Table: table2" for r in table_resources)

@pytest.mark.asyncio
@pytest.mark.skipif(
    not all([
        pytest.importorskip("pymssql"),
        pytest.importorskip("mssql_mcp_server")
    ]),
    reason="SQL Server connection not available"
)
@mock.patch("mssql_mcp_server.server.get_server_manager")
@mock.patch("mssql_mcp_server.server.create_connection")
async def test_read_resource_server(mock_create_connection, mock_get_server_manager):
    """Test reading server resource"""
    # Mock the server manager
    mock_manager = mock.MagicMock()
    mock_get_server_manager.return_value = mock_manager
    
    # Set up mock to return server info
    mock_manager.get_server_by_name.return_value = ServerInfo(
        name="server1", 
        display_name="Test Server 1", 
        config={}
    )
    
    # Read server resource
    content = await read_resource(AnyUrl("mssql://server1"))
    
    # Verify results
    assert "Server: Test Server 1" in content
    assert "Connection activated" in content
    
    # Verify set_active_server was called
    mock_manager.set_active_server.assert_called_once_with("server1")
    
    # Non-existent server
    mock_manager.get_server_by_name.return_value = None
    
    with pytest.raises(ValueError, match="Unknown server"):
        await read_resource(AnyUrl("mssql://nonexistent"))

@pytest.mark.asyncio
@pytest.mark.skipif(
    not all([
        pytest.importorskip("pymssql"),
        pytest.importorskip("mssql_mcp_server")
    ]),
    reason="SQL Server connection not available"
)
@mock.patch("mssql_mcp_server.server.get_server_manager")
@mock.patch("mssql_mcp_server.server.create_connection")
async def test_read_resource_table(mock_create_connection, mock_get_server_manager):
    """Test reading table resource"""
    # Mock the server manager
    mock_manager = mock.MagicMock()
    mock_get_server_manager.return_value = mock_manager
    
    # Set up mock to return server info
    mock_manager.get_server_by_name.return_value = ServerInfo(
        name="server1", 
        display_name="Test Server 1", 
        config={}
    )
    
    # Mock DB connection
    mock_conn = mock.MagicMock()
    mock_create_connection.return_value = mock_conn
    mock_cursor = mock.MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    
    # Simulate query results
    mock_cursor.description = [("id",), ("name",)]
    mock_cursor.fetchall.return_value = [(1, "test1"), (2, "test2")]
    
    # Read table resource
    content = await read_resource(AnyUrl("mssql://server1/tables/test_table"))
    
    # Verify results
    assert "id,name" in content
    assert "1,test1" in content
    assert "2,test2" in content
    
    # Invalid resource URI
    with pytest.raises(ValueError, match="Invalid resource URI"):
        await read_resource(AnyUrl("mssql://server1/invalid/path"))
    
    # Invalid scheme
    with pytest.raises(ValueError, match="Invalid URI scheme"):
        await read_resource(AnyUrl("invalid://server1"))
