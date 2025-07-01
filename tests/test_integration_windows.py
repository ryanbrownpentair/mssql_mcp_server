import pytest
import os
import logging
import pymssql

from mssql_mcp_server.server import create_connection, get_db_config
from mssql_mcp_server.server_manager import get_server_manager

# テスト用のロガー設定
logger = logging.getLogger("test_windows_integration")
logger.setLevel(logging.INFO)

@pytest.mark.skipif(os.name != "nt", reason="Windows統合テストはWindowsプラットフォームでのみ実行")
class TestWindowsIntegration:
    """Windows環境での統合テスト - 実際のWindows認証を使用"""
    
    def setup_method(self):
        """各テスト前に元の環境変数を保存"""
        self.original_env = os.environ.copy()
        
    def teardown_method(self):
        """各テスト後に環境変数を元に戻す"""
        os.environ.clear()
        os.environ.update(self.original_env)
    
    @pytest.mark.skipif(not os.getenv("RUN_WINDOWS_AUTH_TESTS"), 
                       reason="Windows認証テストはRUN_WINDOWS_AUTH_TESTS環境変数が設定されている場合のみ実行")
    def test_actual_windows_auth(self):
        """実際のWindows認証での接続テスト"""
        # 環境変数を設定
        os.environ["MSSQL_AUTH_TYPE"] = "windows"
        os.environ["MSSQL_SERVER"] = os.getenv("TEST_WIN_SERVER", "localhost")
        os.environ["MSSQL_DATABASE"] = os.getenv("TEST_WIN_DATABASE", "master")
        
        try:
            # 設定を取得
            config = get_db_config()
            logger.info(f"Windows認証で接続を試行: {config['server']}/{config['database']}")
            
            # 接続を試行
            connection = create_connection(config)
            
            # 基本的なクエリを実行して接続が有効か確認
            cursor = connection.cursor()
            cursor.execute("SELECT 1 AS test")
            result = cursor.fetchone()
            
            # 接続が成功し、クエリが正常に実行されたか確認
            assert result[0] == 1
            logger.info("Windows認証での接続に成功しました")
            
            # リソースをクリーンアップ
            cursor.close()
            connection.close()
        except Exception as e:
            logger.error(f"Windows認証での接続試行中にエラーが発生しました: {str(e)}")
            pytest.fail(f"Windows認証での接続に失敗しました: {str(e)}")
    
    @pytest.mark.skipif(not os.getenv("RUN_WINDOWS_AUTH_TESTS"), 
                       reason="Windows認証テストはRUN_WINDOWS_AUTH_TESTS環境変数が設定されている場合のみ実行")
    def test_windows_auth_with_dotenv(self):
        """Windows認証での.envファイルを使用した接続テスト"""
        import tempfile
        from dotenv import load_dotenv
        
        # 一時的な.envファイルを作成
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', encoding='utf-8', delete=False) as tmp:
            tmp.write(f"""
# Default server
MSSQL_DEFAULT_SERVER=win-server

[win-server]
MSSQL_AUTH_TYPE=windows
MSSQL_SERVER={os.getenv("TEST_WIN_SERVER", "localhost")}
MSSQL_DATABASE={os.getenv("TEST_WIN_DATABASE", "master")}
            """)
            tmp_path = tmp.name
        
        try:
            # 環境変数DOTENVを設定して、一時ファイルを読み込むようにする
            os.environ["DOTENV_PATH"] = tmp_path
            load_dotenv(tmp_path)
            
            # サーバーマネージャーのインスタンスを取得
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr('mssql_mcp_server.server_manager._server_manager', None)
                server_manager = get_server_manager()
                
                # アクティブサーバーを確認
                assert server_manager.active_server == "win-server"
                
                # 設定を取得
                config = server_manager.get_active_config()
                assert config["auth_type"] == "windows"
                
                # 接続を試行（実際の接続テストは別の関数で行うので省略可能）
                if os.getenv("RUN_ACTUAL_CONNECTION_TESTS"):
                    connection = create_connection(config)
                    cursor = connection.cursor()
                    cursor.execute("SELECT 1 AS test")
                    result = cursor.fetchone()
                    assert result[0] == 1
                    cursor.close()
                    connection.close()
                    logger.info("Windows認証での.envファイルを使用した接続に成功しました")
        finally:
            # 一時ファイルを削除
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
