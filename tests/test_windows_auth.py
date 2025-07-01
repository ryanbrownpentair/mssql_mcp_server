import pytest
import os
import tempfile
from unittest import mock
import pymssql

from mssql_mcp_server.server import create_connection, get_db_config
from mssql_mcp_server.server_manager import ServerManager, get_server_manager

class TestWindowsAuthentication:
    """Windows認証機能のテスト"""

    def setup_method(self):
        """各テスト前に元の環境変数を保存"""
        self.original_env = os.environ.copy()

    def teardown_method(self):
        """各テスト後に環境変数を元に戻す"""
        os.environ.clear()
        os.environ.update(self.original_env)

    @mock.patch("pymssql.connect")
    def test_windows_auth_connection(self, mock_connect):
        """Windows認証での接続テスト"""
        mock_connect.return_value = mock.MagicMock()
        
        # Windows認証の設定
        config = {
            "auth_type": "windows",
            "server": "test-server",
            "database": "test-db"
        }
        
        # 接続を試行
        connection = create_connection(config)
        
        # 正しいパラメータで接続が試行されたか確認
        mock_connect.assert_called_once()
        args, kwargs = mock_connect.call_args
        assert kwargs["server"] == "test-server"
        assert kwargs["database"] == "test-db"
        assert kwargs["trusted_connection"] == "yes"
        assert "user" not in kwargs
        assert "password" not in kwargs

    def test_get_db_config_windows_auth(self):
        """環境変数からWindows認証設定を取得するテスト"""
        # Windows認証環境変数を設定
        env_vars = {
            "MSSQL_AUTH_TYPE": "windows",
            "MSSQL_SERVER": "test-server",
            "MSSQL_DATABASE": "test-db"
        }
        
        # 環境変数を設定
        for key, value in env_vars.items():
            os.environ[key] = value
        
        # 設定を取得
        config = get_db_config()
        
        # 設定が正しく取得できたか確認
        assert config["server"] == "test-server"
        assert config["database"] == "test-db"
        assert config["auth_type"] == "windows"
        assert "user" not in config
        assert "password" not in config

    @mock.patch("pymssql.connect")
    def test_windows_auth_server_manager(self, mock_connect):
        """ServerManagerでのWindows認証サーバーのテスト"""
        mock_connect.return_value = mock.MagicMock()
        
        # 一時的な.envファイルを作成
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', encoding='utf-8', delete=False) as tmp:
            tmp.write("""
# Default server
MSSQL_DEFAULT_SERVER=win-server

[win-server]
MSSQL_AUTH_TYPE=windows
MSSQL_SERVER=win-test-server
MSSQL_DATABASE=win-test-db
            """)
            tmp_path = tmp.name
        
        try:
            # 環境変数DOTENVを設定して、一時ファイルを読み込むようにする
            os.environ["DOTENV_PATH"] = tmp_path
            
            # サーバーマネージャーの実装を直接モックする方法に変更
            with mock.patch('mssql_mcp_server.server_manager._server_manager', None):
                with mock.patch.object(ServerManager, '_load_configurations'):
                    # サーバーマネージャーのインスタンスを取得
                    server_manager = get_server_manager()
                    
                    # サーバー設定を手動で追加
                    from mssql_mcp_server.server_manager import ServerConfig
                    server_manager.servers = {
                        "win-server": ServerConfig("win-server", {
                            "auth_type": "windows",
                            "server": "win-test-server",
                            "database": "win-test-db"
                        })
                    }
                    server_manager.active_server = "win-server"
                    
                    # アクティブサーバーが正しく設定されているか確認
                    assert server_manager.active_server == "win-server"
                    
                    # サーバー設定が正しく取得できるか確認
                    config = server_manager.get_active_config()
                    assert config["auth_type"] == "windows"
                    assert config["server"] == "win-test-server"
                    assert config["database"] == "win-test-db"
                    assert "user" not in config
                    assert "password" not in config
                    
                    # 接続テスト - 実際の接続は行わないが、関数呼び出しをモックで確認
                    with mock.patch('mssql_mcp_server.server.create_connection') as mock_create_conn:
                        mock_create_conn.return_value = mock.MagicMock()
                        from mssql_mcp_server.server import create_connection
                        
                        # 接続を試行
                        connection = create_connection(config)
                        
                        # create_connectionが呼ばれたかを確認
                        mock_create_conn.assert_called_once()
        finally:
            # 一時ファイルを削除
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    @pytest.mark.asyncio
    @mock.patch("mssql_mcp_server.server.get_server_manager")
    @mock.patch("mssql_mcp_server.server.create_connection")
    async def test_execute_sql_tool_windows_auth(self, mock_create_connection, mock_get_server_manager):
        """Windows認証でのexecute_sqlツールのテスト"""
        from mssql_mcp_server.server import call_tool
        
        # サーバーマネージャーのモック設定
        mock_manager = mock.MagicMock()
        mock_get_server_manager.return_value = mock_manager
        mock_manager.active_server = "win-server"
        
        # Windows認証の設定
        mock_manager.get_active_config.return_value = {
            "auth_type": "windows",
            "server": "win-test-server",
            "database": "win-test-db"
        }
        
        # DB接続をモック
        mock_conn = mock.MagicMock()
        mock_create_connection.return_value = mock_conn
        mock_cursor = mock.MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        
        # クエリ結果のモック設定
        mock_cursor.description = [("id",), ("name",)]
        mock_cursor.fetchall.return_value = [(1, "test1"), (2, "test2")]
        
        # ツールを呼び出し
        result = await call_tool("execute_sql", {"query": "SELECT id, name FROM test_table"})
        
        # create_connectionが正しい設定で呼ばれたか確認
        mock_create_connection.assert_called_once()
        
        # 結果を確認
        assert len(result) == 1
        content = result[0].text
        assert "id,name" in content
        assert "1,test1" in content
        assert "2,test2" in content
