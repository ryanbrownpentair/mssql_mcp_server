import pytest
import os
import json
from unittest import mock

from mssql_mcp_server.server import create_connection, get_db_config
from mssql_mcp_server.server_manager import ServerManager

@pytest.fixture
def mock_invalid_sql_config():
    """不完全なSQL認証設定を返すモック"""
    return {
        "server": "test-server",
        "database": "test-db",
        # userキーがない
        "password": "test-password"
    }

@pytest.fixture
def mock_valid_sql_config():
    """有効なSQL認証設定を返すモック"""
    return {
        "server": "test-server",
        "database": "test-db",
        "user": "test-user",
        "password": "test-password"
    }

@pytest.fixture
def mock_valid_windows_config():
    """有効なWindows認証設定を返すモック"""
    return {
        "auth_type": "windows",
        "server": "test-server",
        "database": "test-db"
    }

@pytest.fixture
def mock_valid_entra_config():
    """有効なEntra ID認証設定を返すモック"""
    return {
        "auth_type": "entra",
        "server": "test-server",
        "database": "test-db",
        "client_id": "test-client-id",
        "tenant_id": "test-tenant-id",
        "client_secret": "test-client-secret"
    }

def test_create_connection_missing_user(mock_invalid_sql_config):
    """userキーが欠けている場合のテスト"""
    with pytest.raises(KeyError) as excinfo:
        create_connection(mock_invalid_sql_config)
    
    assert "'user'" in str(excinfo.value)

@mock.patch("pymssql.connect")
def test_create_connection_sql_auth(mock_connect, mock_valid_sql_config):
    """SQL認証で正常に接続できる場合のテスト"""
    mock_connect.return_value = "test-connection"
    
    connection = create_connection(mock_valid_sql_config)
    
    mock_connect.assert_called_once_with(
        server="test-server",
        user="test-user",
        password="test-password",
        database="test-db"
    )
    assert connection == "test-connection"

@mock.patch("pymssql.connect")
def test_create_connection_windows_auth(mock_connect, mock_valid_windows_config):
    """Windows認証で正常に接続できる場合のテスト"""
    mock_connect.return_value = "test-connection"
    
    connection = create_connection(mock_valid_windows_config)
    
    mock_connect.assert_called_once()
    args, kwargs = mock_connect.call_args
    assert kwargs["server"] == "test-server"
    assert kwargs["database"] == "test-db"
    assert kwargs["trusted_connection"] == "yes"
    assert connection == "test-connection"

@mock.patch("mssql_mcp_server.server.get_entra_token")
@mock.patch("pymssql.connect")
def test_create_connection_entra_auth(mock_connect, mock_get_token, mock_valid_entra_config):
    """Entra ID認証で正常に接続できる場合のテスト"""
    mock_get_token.return_value = "test-token"
    mock_connect.return_value = "test-connection"
    
    connection = create_connection(mock_valid_entra_config)
    
    mock_get_token.assert_called_once_with(mock_valid_entra_config)
    mock_connect.assert_called_once()
    args, kwargs = mock_connect.call_args
    assert kwargs["server"] == "test-server"
    assert kwargs["database"] == "test-db"
    assert kwargs["password"] == "test-token"
    assert connection == "test-connection"

@mock.patch("pymssql.connect", side_effect=Exception("Connection error"))
def test_create_connection_error(mock_connect, mock_valid_sql_config):
    """接続エラーが発生した場合のテスト"""
    with pytest.raises(Exception) as excinfo:
        create_connection(mock_valid_sql_config)
    
    assert "Connection error" in str(excinfo.value)

@mock.patch("mssql_mcp_server.server_manager.get_server_manager")
@mock.patch("mssql_mcp_server.server.create_connection")
def test_server_manager_missing_user(mock_create_connection, mock_get_server_manager):
    """ServerManagerでuserキーが欠けている場合のテスト"""
    # サーバーマネージャーのモック設定
    mock_manager = mock.MagicMock()
    mock_get_server_manager.return_value = mock_manager
    
    # userキーが欠けている不完全な設定
    mock_manager.get_active_config.return_value = {
        "server": "test-server",
        "database": "test-db",
        # userキーがない
        "password": "test-password"
    }
    
    # create_connectionがKeyErrorを発生させるようにする
    mock_create_connection.side_effect = KeyError('user')
    
    # サーバーマネージャーが接続を試みる処理を模倣
    with pytest.raises(KeyError) as excinfo:
        config = mock_manager.get_active_config()
        create_connection(config)
    
    assert "'user'" in str(excinfo.value)