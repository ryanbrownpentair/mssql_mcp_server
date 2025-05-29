import pytest
import os
import json
import tempfile
from unittest import mock
from mssql_mcp_server.server import (
    get_db_config, 
    get_entra_token, 
    create_connection, 
    load_token_cache,
    save_token_cache
)

@pytest.fixture
def mock_env_sql_auth():
    """Set environment variables for SQL Server authentication"""
    with mock.patch.dict(os.environ, {
        "MSSQL_AUTH_TYPE": "sql",
        "MSSQL_SERVER": "test-server",
        "MSSQL_DATABASE": "test-db",
        "MSSQL_USER": "test-user",
        "MSSQL_PASSWORD": "test-password"
    }):
        yield

@pytest.fixture
def mock_env_windows_auth():
    """Set environment variables for Windows authentication"""
    with mock.patch.dict(os.environ, {
        "MSSQL_AUTH_TYPE": "windows",
        "MSSQL_SERVER": "test-server",
        "MSSQL_DATABASE": "test-db"
    }):
        yield

@pytest.fixture
def mock_env_entra_auth():
    """Set environment variables for Entra ID authentication"""
    with mock.patch.dict(os.environ, {
        "MSSQL_AUTH_TYPE": "entra",
        "MSSQL_SERVER": "test-server",
        "MSSQL_DATABASE": "test-db",
        "MSSQL_CLIENT_ID": "test-client-id",
        "MSSQL_TENANT_ID": "test-tenant-id",
        "MSSQL_CLIENT_SECRET": "test-client-secret"
    }):
        yield

@pytest.fixture
def mock_env_entra_interactive():
    """Set environment variables for Entra ID interactive authentication"""
    with mock.patch.dict(os.environ, {
        "MSSQL_AUTH_TYPE": "entra",
        "MSSQL_SERVER": "test-server",
        "MSSQL_DATABASE": "test-db",
        "MSSQL_CLIENT_ID": "test-client-id",
        "MSSQL_TENANT_ID": "test-tenant-id",
        "MSSQL_AUTH_MODE": "interactive",
        "MSSQL_TOKEN_CACHE_FILE": "/tmp/token_cache.json"
    }):
        yield

@pytest.fixture
def mock_env_entra_device_code():
    """Set environment variables for Entra ID device code flow"""
    with mock.patch.dict(os.environ, {
        "MSSQL_AUTH_TYPE": "entra",
        "MSSQL_SERVER": "test-server",
        "MSSQL_DATABASE": "test-db",
        "MSSQL_CLIENT_ID": "test-client-id",
        "MSSQL_TENANT_ID": "test-tenant-id",
        "MSSQL_AUTH_MODE": "interactive",
        "MSSQL_USE_DEVICE_CODE": "true",
        "MSSQL_TOKEN_CACHE_FILE": "/tmp/token_cache.json"
    }):
        yield

@pytest.fixture
def mock_env_entra_username():
    """Set environment variables for Entra ID username authentication"""
    with mock.patch.dict(os.environ, {
        "MSSQL_AUTH_TYPE": "entra",
        "MSSQL_SERVER": "test-server",
        "MSSQL_DATABASE": "test-db",
        "MSSQL_CLIENT_ID": "test-client-id",
        "MSSQL_TENANT_ID": "test-tenant-id",
        "MSSQL_ENTRA_USERNAME": "test-username",
        "MSSQL_ENTRA_PASSWORD": "test-password"
    }):
        yield

def test_get_db_config_sql_auth(mock_env_sql_auth):
    """Test get_db_config with SQL Server authentication"""
    config = get_db_config()
    assert config["server"] == "test-server"
    assert config["database"] == "test-db"
    assert config["user"] == "test-user"
    assert config["password"] == "test-password"
    assert "auth_type" not in config

def test_get_db_config_windows_auth(mock_env_windows_auth):
    """Test get_db_config with Windows authentication"""
    config = get_db_config()
    assert config["server"] == "test-server"
    assert config["database"] == "test-db"
    assert config["auth_type"] == "windows"

def test_get_db_config_entra_auth(mock_env_entra_auth):
    """Test get_db_config with Entra ID authentication"""
    config = get_db_config()
    assert config["server"] == "test-server"
    assert config["database"] == "test-db"
    assert config["auth_type"] == "entra"
    assert config["client_id"] == "test-client-id"
    assert config["tenant_id"] == "test-tenant-id"
    assert config["client_secret"] == "test-client-secret"

def test_get_db_config_entra_interactive(mock_env_entra_interactive):
    """Test get_db_config with Entra ID interactive authentication"""
    config = get_db_config()
    assert config["auth_type"] == "entra"
    assert config["auth_mode"] == "interactive"
    assert config["token_cache_file"] == "/tmp/token_cache.json"
    assert not config.get("use_device_code")

def test_get_db_config_entra_device_code(mock_env_entra_device_code):
    """Test get_db_config with Entra ID device code flow"""
    config = get_db_config()
    assert config["auth_type"] == "entra"
    assert config["auth_mode"] == "interactive"
    assert config["use_device_code"] is True

def test_get_db_config_entra_username(mock_env_entra_username):
    """Test get_db_config with Entra ID username authentication"""
    config = get_db_config()
    assert config["auth_type"] == "entra"
    assert config["username"] == "test-username"
    assert "auth_mode" not in config

def test_get_db_config_missing_required():
    """Test error is raised when required parameters are missing"""
    with mock.patch.dict(os.environ, {
        "MSSQL_SERVER": "test-server"
    }):
        with pytest.raises(ValueError, match="Missing required database configuration"):
            get_db_config()

def test_get_db_config_missing_sql_auth():
    """Test error is raised when SQL authentication credentials are missing"""
    with mock.patch.dict(os.environ, {
        "MSSQL_AUTH_TYPE": "sql",
        "MSSQL_SERVER": "test-server",
        "MSSQL_DATABASE": "test-db",
        "MSSQL_USER": "test-user"
        # password missing
    }):
        with pytest.raises(ValueError, match="Missing SQL authentication credentials"):
            get_db_config()

def test_get_db_config_missing_entra_auth():
    """Test error is raised when Entra ID configuration is missing"""
    with mock.patch.dict(os.environ, {
        "MSSQL_AUTH_TYPE": "entra",
        "MSSQL_SERVER": "test-server",
        "MSSQL_DATABASE": "test-db"
        # client_id and tenant_id missing
    }):
        with pytest.raises(ValueError, match="Missing Entra ID configuration"):
            get_db_config()

def test_get_db_config_invalid_auth_type():
    """Test error is raised when authentication type is invalid"""
    with mock.patch.dict(os.environ, {
        "MSSQL_AUTH_TYPE": "invalid",
        "MSSQL_SERVER": "test-server",
        "MSSQL_DATABASE": "test-db"
    }):
        with pytest.raises(ValueError, match="Unknown authentication type"):
            get_db_config()

def test_token_cache_operations():
    """Test token cache read/write operations"""
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        try:
            # Read from empty cache
            cache_data = load_token_cache(tmp.name)
            assert cache_data == {}
            
            # Write data
            test_data = {"test": "data"}
            save_token_cache(test_data, tmp.name)
            
            # Read data
            cache_data = load_token_cache(tmp.name)
            assert cache_data == test_data
        finally:
            os.unlink(tmp.name)

def test_load_token_cache_nonexistent_file():
    """Test loading token cache from non-existent file"""
    cache_data = load_token_cache("/nonexistent/path")
    assert cache_data == {}

def test_save_token_cache_invalid_path():
    """Test saving token cache to invalid path"""
    # Should handle invalid paths without raising exceptions
    save_token_cache({"test": "data"}, None)  # None path is ignored
    save_token_cache({"test": "data"}, "")  # Empty path is ignored

@pytest.mark.asyncio
@mock.patch("mssql_mcp_server.server.get_entra_token")
@mock.patch("pymssql.connect")
async def test_create_connection_entra(mock_connect, mock_get_token):
    """Test creating connection with Entra ID authentication"""
    mock_get_token.return_value = "test-token"
    mock_connect.return_value = "test-connection"
    
    config = {
        "auth_type": "entra",
        "server": "test-server",
        "database": "test-db",
        "client_id": "test-client-id",
        "tenant_id": "test-tenant-id",
        "username": "test-username"
    }
    
    connection = create_connection(config)
    
    # Verify get_entra_token was called
    mock_get_token.assert_called_once_with(config)
    
    # Verify pymssql.connect was called with correct parameters
    mock_connect.assert_called_once()
    args, kwargs = mock_connect.call_args
    assert kwargs["server"] == "test-server"
    assert kwargs["database"] == "test-db"
    assert kwargs["user"] == "test-username"
    assert kwargs["password"] == "test-token"
    assert "Authentication=ActiveDirectoryServicePrincipal" in kwargs["conn_properties"]

@pytest.mark.asyncio
@mock.patch("pymssql.connect")
async def test_create_connection_sql(mock_connect):
    """Test creating connection with SQL authentication"""
    mock_connect.return_value = "test-connection"
    
    config = {
        "server": "test-server",
        "user": "test-user",
        "password": "test-password",
        "database": "test-db"
    }
    
    connection = create_connection(config)
    
    # Verify pymssql.connect was called with correct parameters
    mock_connect.assert_called_once_with(
        server="test-server",
        user="test-user",
        password="test-password",
        database="test-db"
    )

@pytest.mark.asyncio
@mock.patch("pymssql.connect")
async def test_create_connection_windows(mock_connect):
    """Test creating connection with Windows authentication"""
    mock_connect.return_value = "test-connection"
    
    config = {
        "auth_type": "windows",
        "server": "test-server",
        "database": "test-db"
    }
    
    connection = create_connection(config)
    
    # Verify pymssql.connect was called with correct parameters
    mock_connect.assert_called_once()
    args, kwargs = mock_connect.call_args
    assert kwargs["server"] == "test-server"
    assert kwargs["database"] == "test-db"
    assert "trusted_connection" in kwargs
    assert kwargs["trusted_connection"] == "yes"

@pytest.mark.asyncio
@mock.patch("mssql_mcp_server.server.msal.ConfidentialClientApplication")
async def test_get_entra_token_service_principal(mock_confidential_app):
    """Test getting Entra token with service principal"""
    # Set up mock
    mock_app_instance = mock.MagicMock()
    mock_confidential_app.return_value = mock_app_instance
    mock_app_instance.acquire_token_for_client.return_value = {"access_token": "test-token"}
    
    config = {
        "client_id": "test-client-id",
        "tenant_id": "test-tenant-id",
        "client_secret": "test-client-secret"
    }
    
    token = get_entra_token(config)
    
    # Verify ConfidentialClientApplication was created correctly
    mock_confidential_app.assert_called_once_with(
        client_id="test-client-id",
        authority=f"https://login.microsoftonline.com/test-tenant-id",
        client_credential="test-client-secret",
        token_cache=None
    )
    
    # Verify acquire_token_for_client was called correctly
    mock_app_instance.acquire_token_for_client.assert_called_once_with(
        scopes=["https://database.windows.net/.default"]
    )
    
    assert token == "test-token"

@pytest.mark.asyncio
@mock.patch("mssql_mcp_server.server.msal.PublicClientApplication")
async def test_get_entra_token_username_password(mock_public_app):
    """Test getting Entra token with username and password"""
    # Set up mock
    mock_app_instance = mock.MagicMock()
    mock_public_app.return_value = mock_app_instance
    mock_app_instance.acquire_token_by_username_password.return_value = {"access_token": "test-token"}
    
    config = {
        "client_id": "test-client-id",
        "tenant_id": "test-tenant-id",
        "username": "test-username"
    }
    
    with mock.patch.dict(os.environ, {"MSSQL_ENTRA_PASSWORD": "test-password"}):
        token = get_entra_token(config)
    
    # Verify PublicClientApplication was created correctly
    mock_public_app.assert_called_once_with(
        client_id="test-client-id",
        authority=f"https://login.microsoftonline.com/test-tenant-id",
        token_cache=None
    )
    
    # Verify acquire_token_by_username_password was called correctly
    mock_app_instance.acquire_token_by_username_password.assert_called_once_with(
        "test-username",
        "test-password",
        scopes=["https://database.windows.net/.default"]
    )
    
    assert token == "test-token"

@pytest.mark.asyncio
@mock.patch("mssql_mcp_server.server.msal.PublicClientApplication")
async def test_get_entra_token_interactive(mock_public_app):
    """Test getting Entra token with interactive authentication"""
    # Set up mock
    mock_app_instance = mock.MagicMock()
    mock_public_app.return_value = mock_app_instance
    mock_app_instance.get_accounts.return_value = []
    mock_app_instance.acquire_token_interactive.return_value = {"access_token": "test-token"}
    
    config = {
        "client_id": "test-client-id",
        "tenant_id": "test-tenant-id",
        "auth_mode": "interactive",
        "token_cache_file": None
    }
    
    token = get_entra_token(config)
    
    # Verify PublicClientApplication was created correctly
    mock_public_app.assert_called_once()
    
    # Verify acquire_token_interactive was called correctly
    mock_app_instance.acquire_token_interactive.assert_called_once()
    
    assert token == "test-token"

@pytest.mark.asyncio
@mock.patch("mssql_mcp_server.server.msal.PublicClientApplication")
async def test_get_entra_token_cached(mock_public_app):
    """Test getting token from cache"""
    # Set up mock
    mock_app_instance = mock.MagicMock()
    mock_public_app.return_value = mock_app_instance
    mock_app_instance.get_accounts.return_value = [{"username": "test-user"}]
    mock_app_instance.acquire_token_silent.return_value = {"access_token": "cached-token"}
    
    with tempfile.NamedTemporaryFile() as tmp:
        # Create token cache file
        with open(tmp.name, 'w') as f:
            json.dump({"test": "cache"}, f)
        
        config = {
            "client_id": "test-client-id",
            "tenant_id": "test-tenant-id",
            "auth_mode": "interactive",
            "token_cache_file": tmp.name
        }
        
        token = get_entra_token(config)
    
    # Verify acquire_token_silent was called
    mock_app_instance.acquire_token_silent.assert_called_once()
    
    assert token == "cached-token"

@pytest.mark.asyncio
@mock.patch("mssql_mcp_server.server.msal.PublicClientApplication")
async def test_get_entra_token_device_code(mock_public_app):
    """Test getting Entra token with device code flow"""
    # Set up mock
    mock_app_instance = mock.MagicMock()
    mock_public_app.return_value = mock_app_instance
    mock_app_instance.get_accounts.return_value = []
    mock_app_instance.initiate_device_flow.return_value = {
        "user_code": "TEST-CODE",
        "verification_uri": "https://microsoft.com/devicelogin"
    }
    mock_app_instance.acquire_token_by_device_flow.return_value = {"access_token": "device-token"}
    
    config = {
        "client_id": "test-client-id",
        "tenant_id": "test-tenant-id",
        "auth_mode": "interactive",
        "use_device_code": True,
        "token_cache_file": None
    }
    
    with mock.patch("builtins.print") as mock_print:
        token = get_entra_token(config)
    
    # Verify initiate_device_flow was called
    mock_app_instance.initiate_device_flow.assert_called_once_with(scopes=["https://database.windows.net/.default"])
    
    # Verify acquire_token_by_device_flow was called
    mock_app_instance.acquire_token_by_device_flow.assert_called_once()
    
    # Verify instructions were printed to screen
    assert any("TEST-CODE" in str(args) for args, _ in mock_print.call_args_list)
    
    assert token == "device-token"

@pytest.mark.asyncio
@mock.patch("mssql_mcp_server.server.msal.PublicClientApplication")
async def test_get_entra_token_error(mock_public_app):
    """Test error handling when token acquisition fails"""
    # Set up mock
    mock_app_instance = mock.MagicMock()
    mock_public_app.return_value = mock_app_instance
    mock_app_instance.get_accounts.return_value = []
    mock_app_instance.acquire_token_interactive.return_value = {
        "error": "test_error",
        "error_description": "Test error description"
    }
    
    config = {
        "client_id": "test-client-id",
        "tenant_id": "test-tenant-id",
        "auth_mode": "interactive",
        "token_cache_file": None
    }
    
    with pytest.raises(ValueError, match="Failed to acquire token"):
        get_entra_token(config)