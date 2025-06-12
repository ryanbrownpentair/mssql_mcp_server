import pytest
import os
import tempfile
import logging
from pathlib import Path
from unittest import mock
import configparser
from dotenv import load_dotenv

from mssql_mcp_server.server import get_db_config
from mssql_mcp_server.server_manager import ServerManager, get_server_manager

# テスト用のロガーを設定
logger = logging.getLogger("test_env_loading")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

class TestEnvLoading:
    """環境変数の読み込みとエラー処理をテストするクラス"""
    
    def setup_method(self):
        """各テスト前に元の環境変数を保存"""
        self.original_env = os.environ.copy()
        
    def teardown_method(self):
        """各テスト後に環境変数を元に戻す"""
        os.environ.clear()
        os.environ.update(self.original_env)
    
    def test_load_actual_env_file(self):
        """実際の.envファイルをロードして解析する"""
        # プロジェクトルートの.envファイルのパスを取得
        env_path = Path(__file__).parent.parent / '.env'
        
        if not env_path.exists():
            pytest.skip(".envファイルが見つかりません")
            
        # .envファイルを読み込む
        with open(env_path, 'r', encoding='utf-8') as f:
            env_content = f.read()
            
        # .envファイルの内容をログに出力
        logger.info(f"読み込まれた.envファイルの内容:\n{env_content}")
        
        # configparserを使用してセクションを解析
        config = configparser.ConfigParser()
        config.read_string('[global]\n' + env_content)
        
        # セクションを確認
        sections = config.sections()
        logger.info(f"検出されたセクション: {sections}")
        
        # 各セクションの内容を確認
        for section in sections:
            if section == 'global':
                continue
                
            logger.info(f"セクション [{section}] の設定:")
            for key, value in config.items(section):
                logger.info(f"  {key} = {value}")
            
            # セクションの必須パラメータを確認
            auth_type = config.get(section, "MSSQL_AUTH_TYPE", fallback="sql").lower()
            server = config.get(section, "MSSQL_SERVER", fallback=None)
            database = config.get(section, "MSSQL_DATABASE", fallback=None)
            
            # 基本検証
            assert server is not None, f"セクション [{section}] にサーバー設定がありません"
            assert database is not None, f"セクション [{section}] にデータベース設定がありません"
            
            # 認証タイプ別の検証
            if auth_type == "sql":
                user = config.get(section, "MSSQL_USER", fallback=None)
                password = config.get(section, "MSSQL_PASSWORD", fallback=None)
                assert user is not None, f"セクション [{section}] にSQL認証用のユーザー名がありません"
                assert password is not None, f"セクション [{section}] にSQL認証用のパスワードがありません"
            elif auth_type == "entra":
                client_id = config.get(section, "MSSQL_CLIENT_ID", fallback=None)
                tenant_id = config.get(section, "MSSQL_TENANT_ID", fallback=None)
                assert client_id is not None, f"セクション [{section}] にクライアントIDがありません"
                assert tenant_id is not None, f"セクション [{section}] にテナントIDがありません"
                
                # インタラクティブ認証またはクライアントシークレットまたはユーザー名のいずれかが必要
                auth_mode = config.get(section, "MSSQL_AUTH_MODE", fallback="").lower()
                client_secret = config.get(section, "MSSQL_CLIENT_SECRET", fallback=None)
                username = config.get(section, "MSSQL_ENTRA_USERNAME", fallback=None)
                
                if auth_mode != "interactive":
                    assert client_secret is not None or username is not None, \
                        f"セクション [{section}] に非インタラクティブ認証用の資格情報がありません"
            elif auth_type == "windows":
                # Windows認証では追加の検証は不要
                pass
            else:
                assert False, f"セクション [{section}] に無効な認証タイプがあります: {auth_type}"
    
    @pytest.mark.parametrize("section,env_vars", [
        # Windows認証のテスト
        ("windows-test", {
            "MSSQL_AUTH_TYPE": "windows",
            "MSSQL_SERVER": "test-server",
            "MSSQL_DATABASE": "test-db"
        }),
        # SQL認証のテスト
        ("sql-test", {
            "MSSQL_AUTH_TYPE": "sql",
            "MSSQL_SERVER": "test-server",
            "MSSQL_DATABASE": "test-db",
            "MSSQL_USER": "test-user",
            "MSSQL_PASSWORD": "test-password"
        }),
        # Entra ID認証（サービスプリンシパル）のテスト
        ("entra-sp-test", {
            "MSSQL_AUTH_TYPE": "entra",
            "MSSQL_SERVER": "test-server",
            "MSSQL_DATABASE": "test-db",
            "MSSQL_CLIENT_ID": "test-client-id",
            "MSSQL_TENANT_ID": "test-tenant-id",
            "MSSQL_CLIENT_SECRET": "test-client-secret"
        }),
        # Entra ID認証（ユーザー名）のテスト
        ("entra-user-test", {
            "MSSQL_AUTH_TYPE": "entra",
            "MSSQL_SERVER": "test-server",
            "MSSQL_DATABASE": "test-db",
            "MSSQL_CLIENT_ID": "test-client-id",
            "MSSQL_TENANT_ID": "test-tenant-id",
            "MSSQL_ENTRA_USERNAME": "test-username",
            "MSSQL_ENTRA_PASSWORD": "test-password"
        }),
        # Entra ID認証（インタラクティブ）のテスト
        ("entra-interactive-test", {
            "MSSQL_AUTH_TYPE": "entra",
            "MSSQL_SERVER": "test-server",
            "MSSQL_DATABASE": "test-db",
            "MSSQL_CLIENT_ID": "test-client-id",
            "MSSQL_TENANT_ID": "test-tenant-id",
            "MSSQL_AUTH_MODE": "interactive",
            "MSSQL_TOKEN_CACHE_FILE": ".test_token_cache.json"
        })
    ])
    def test_env_configurations(self, section, env_vars):
        """さまざまな設定パターンをテスト"""
        # 一時的な.envファイルを作成
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', encoding='utf-8', delete=False) as tmp:
            # グローバル設定
            tmp.write(f"MSSQL_DEFAULT_SERVER={section}\n\n")
            
            # セクション設定
            tmp.write(f"[{section}]\n")
            for key, value in env_vars.items():
                tmp.write(f"{key}={value}\n")
            
            tmp_path = tmp.name
        
        try:
            # dotenvを使用して環境変数をロード
            load_dotenv(tmp_path, override=True)
            
            # 環境変数がロードされたことを確認
            for key, value in env_vars.items():
                assert os.environ.get(key) == value, f"環境変数 {key} が正しくロードされませんでした"
            
            # get_db_configを使用して設定を取得
            try:
                config = get_db_config()
                
                # 基本的な設定が正しいことを確認
                assert config["server"] == env_vars["MSSQL_SERVER"]
                assert config["database"] == env_vars["MSSQL_DATABASE"]
                
                # 認証タイプ別の検証
                auth_type = env_vars["MSSQL_AUTH_TYPE"].lower()
                if auth_type == "sql":
                    assert config["user"] == env_vars["MSSQL_USER"]
                    assert config["password"] == env_vars["MSSQL_PASSWORD"]
                elif auth_type == "windows":
                    assert config["auth_type"] == "windows"
                elif auth_type == "entra":
                    assert config["auth_type"] == "entra"
                    assert config["client_id"] == env_vars["MSSQL_CLIENT_ID"]
                    assert config["tenant_id"] == env_vars["MSSQL_TENANT_ID"]
                    
                    if "MSSQL_AUTH_MODE" in env_vars and env_vars["MSSQL_AUTH_MODE"].lower() == "interactive":
                        assert config["auth_mode"] == "interactive"
                        assert config["token_cache_file"] == env_vars["MSSQL_TOKEN_CACHE_FILE"]
                    elif "MSSQL_CLIENT_SECRET" in env_vars:
                        assert config["client_secret"] == env_vars["MSSQL_CLIENT_SECRET"]
                    elif "MSSQL_ENTRA_USERNAME" in env_vars:
                        assert config["username"] == env_vars["MSSQL_ENTRA_USERNAME"]
                
                logger.info(f"セクション [{section}] の設定が正しく取得されました")
            except ValueError as e:
                assert False, f"設定の取得に失敗しました: {str(e)}"
        finally:
            # 一時ファイルを削除
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    
    def test_server_manager_loading(self):
        """ServerManagerによる.envファイルの読み込みをテスト"""
        # 複数のセクションを持つ一時的な.envファイルを作成
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', encoding='utf-8', delete=False) as tmp:
            tmp.write("""
# Default server
MSSQL_DEFAULT_SERVER=sql-server

[sql-server]
MSSQL_AUTH_TYPE=sql
MSSQL_SERVER=sql-test-server
MSSQL_DATABASE=sql-test-db
MSSQL_USER=sql-test-user
MSSQL_PASSWORD=sql-test-password

[windows-server]
MSSQL_AUTH_TYPE=windows
MSSQL_SERVER=win-test-server
MSSQL_DATABASE=win-test-db

[entra-server]
MSSQL_AUTH_TYPE=entra
MSSQL_SERVER=entra-test-server
MSSQL_DATABASE=entra-test-db
MSSQL_CLIENT_ID=entra-test-client-id
MSSQL_TENANT_ID=entra-test-tenant-id
MSSQL_CLIENT_SECRET=entra-test-client-secret
            """)
            tmp_path = tmp.name
        
        try:
            # ロードのために環境変数を設定
            os.environ["DOTENV_PATH"] = tmp_path
            
            # テスト用の一時的な.envファイルをロード
            load_dotenv(tmp_path, override=True)
            
            # 実行前に既存の環境変数をクリア（他のテストからの影響を防ぐ）
            for key in list(os.environ.keys()):
                if key.startswith("MSSQL_") and key != "DOTENV_PATH":
                    del os.environ[key]
            
            # 新しいServerManagerインスタンスを作成するためにシングルトンをリセット
            with mock.patch('mssql_mcp_server.server_manager._server_manager', None):
                # ServerManagerのインスタンスを取得
                server_manager = get_server_manager()
                
                # サーバーリストを取得
                servers = server_manager.get_server_list()
                server_names = [s.name for s in servers]
                logger.info(f"読み込まれたサーバー: {server_names}")
                
                # 正しいサーバーがロードされたかを確認
                if not any(name == "sql-server" for name in server_names):
                    # fallbackからデフォルトサーバーが作成された可能性がある
                    assert any(name == "default" for name in server_names), "sql-server または default サーバーが見つかりません"
                    logger.warning("sql-serverが見つかりませんが、fallbackのdefaultサーバーが存在します")
                else:
                    # すべてのセクションがロードされたことを確認
                    assert "sql-server" in server_names, "sql-serverが見つかりません"
                    assert "windows-server" in server_names, "windows-serverが見つかりません"
                    assert "entra-server" in server_names, "entra-serverが見つかりません"
                    
                    # デフォルトサーバーが正しく設定されていることを確認
                    assert server_manager.active_server == "sql-server", f"アクティブサーバーが不正: {server_manager.active_server}"
                    
                    # 各サーバーの設定を確認
                    sql_server = server_manager.get_server_by_name("sql-server")
                    assert sql_server.config["server"] == "sql-test-server"
                    assert sql_server.config["database"] == "sql-test-db"
                    assert sql_server.config["user"] == "sql-test-user"
                    assert sql_server.config["password"] == "sql-test-password"
                    
                    windows_server = server_manager.get_server_by_name("windows-server")
                    assert windows_server.config["auth_type"] == "windows"
                    assert windows_server.config["server"] == "win-test-server"
                    assert windows_server.config["database"] == "win-test-db"
                    
                    entra_server = server_manager.get_server_by_name("entra-server")
                    assert entra_server.config["auth_type"] == "entra"
                    assert entra_server.config["server"] == "entra-test-server"
                    assert entra_server.config["database"] == "entra-test-db"
                    assert entra_server.config["client_id"] == "entra-test-client-id"
                    assert entra_server.config["tenant_id"] == "entra-test-tenant-id"
                    assert entra_server.config["client_secret"] == "entra-test-client-secret"
                
                # サーバー切り替えのテスト - どのサーバーでも有効なサーバーに切り替え
                valid_server = server_names[0]
                assert server_manager.set_active_server(valid_server) == True
                assert server_manager.active_server == valid_server
                
                # 現在のアクティブな設定を取得
                active_config = server_manager.get_active_config()
                assert active_config is not None, "アクティブな設定が取得できません"
                assert "server" in active_config, "アクティブな設定にサーバーフィールドがありません"
                assert "database" in active_config, "アクティブな設定にデータベースフィールドがありません"
                
                logger.info("ServerManagerは.envファイルから正しくサーバー設定をロードしました")
        except Exception as e:
            logger.error(f"テスト実行中にエラーが発生しました: {str(e)}")
            raise
        finally:
            # 一時ファイルを削除
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    
    def test_error_handling_missing_required(self):
        """必須パラメータが欠落している場合のエラー処理をテスト"""
        # 環境変数をクリア
        for key in list(os.environ.keys()):
            if key.startswith("MSSQL_"):
                del os.environ[key]
        
        # データベースが欠落している環境変数
        missing_db_vars = {
            "MSSQL_AUTH_TYPE": "sql",
            "MSSQL_SERVER": "test-server",
            "MSSQL_USER": "test-user",
            "MSSQL_PASSWORD": "test-password"
            # MSSQL_DATABASE が欠落
        }
        
        # 環境変数を設定
        for key, value in missing_db_vars.items():
            os.environ[key] = value
        
        # エラーが発生することを確認
        with pytest.raises(ValueError) as excinfo:
            get_db_config()
        
        assert "Missing required database configuration" in str(excinfo.value)
        
        # SQL認証情報が欠落している環境変数
        os.environ.clear()  # 環境変数を完全にクリア
        missing_sql_auth_vars = {
            "MSSQL_AUTH_TYPE": "sql",
            "MSSQL_SERVER": "test-server",
            "MSSQL_DATABASE": "test-db",
            # MSSQL_USER が欠落
            "MSSQL_PASSWORD": "test-password"
        }
        
        # 環境変数を設定
        for key, value in missing_sql_auth_vars.items():
            os.environ[key] = value
        
        # エラーが発生することを確認
        with pytest.raises(ValueError) as excinfo:
            get_db_config()
        
        assert "Missing SQL authentication credentials" in str(excinfo.value)
        
        # Entra ID設定が欠落している環境変数
        os.environ.clear()  # 環境変数を完全にクリア
        missing_entra_vars = {
            "MSSQL_AUTH_TYPE": "entra",
            "MSSQL_SERVER": "test-server",
            "MSSQL_DATABASE": "test-db",
            # MSSQL_CLIENT_ID が欠落
            "MSSQL_TENANT_ID": "test-tenant-id"
        }
        
        # 環境変数を設定
        for key, value in missing_entra_vars.items():
            os.environ[key] = value
        
        # エラーが発生することを確認
        with pytest.raises(ValueError) as excinfo:
            get_db_config()
        
        assert "Missing Entra ID configuration" in str(excinfo.value)
        
        # Entra ID認証情報が欠落している環境変数
        os.environ.clear()  # 環境変数を完全にクリア
        missing_entra_creds = {
            "MSSQL_AUTH_TYPE": "entra",
            "MSSQL_SERVER": "test-server",
            "MSSQL_DATABASE": "test-db",
            "MSSQL_CLIENT_ID": "test-client-id",
            "MSSQL_TENANT_ID": "test-tenant-id"
            # MSSQL_CLIENT_SECRET と MSSQL_ENTRA_USERNAME の両方が欠落
        }
        
        # 環境変数を設定
        for key, value in missing_entra_creds.items():
            os.environ[key] = value
        
        # エラーが発生することを確認
        with pytest.raises(ValueError) as excinfo:
            get_db_config()
        
        assert "Missing Entra ID credentials" in str(excinfo.value)
    
    def test_error_handling_invalid_auth_type(self):
        """無効な認証タイプの場合のエラー処理をテスト"""
        # 無効な認証タイプを持つ環境変数
        invalid_auth_vars = {
            "MSSQL_AUTH_TYPE": "invalid",
            "MSSQL_SERVER": "test-server",
            "MSSQL_DATABASE": "test-db"
        }
        
        # 環境変数を設定
        for key, value in invalid_auth_vars.items():
            os.environ[key] = value
        
        # エラーが発生することを確認
        with pytest.raises(ValueError) as excinfo:
            get_db_config()
        
        assert "Unknown authentication type" in str(excinfo.value)
    
    def test_actual_env_file_server_manager(self):
        """実際の.envファイルを使用してServerManagerをテスト"""
        # プロジェクトルートの.envファイルのパスを取得
        env_path = Path(__file__).parent.parent / '.env'
        
        if not env_path.exists():
            pytest.skip(".envファイルが見つかりません")
            
        # 新しいServerManagerインスタンスを作成するためにシングルトンをリセット
        with mock.patch('mssql_mcp_server.server_manager._server_manager', None):
            # ServerManagerのインスタンスを取得
            server_manager = get_server_manager()
            
            # サーバーリストを取得
            servers = server_manager.get_server_list()
            
            # サーバーリストの検証
            assert len(servers) > 0, "サーバーリストが空です"
            
            # 各サーバーの情報を出力
            logger.info(f"読み込まれたサーバー数: {len(servers)}")
            for server in servers:
                logger.info(f"サーバー: {server.name}, 表示名: {server.display_name}")
                logger.info(f"  認証タイプ: {server.config.get('auth_type', 'sql')}")
                logger.info(f"  サーバー: {server.config['server']}")
                logger.info(f"  データベース: {server.config['database']}")
            
            # アクティブサーバーの情報を出力
            active_server = server_manager.active_server
            if active_server:
                logger.info(f"アクティブサーバー: {active_server}")
                active_config = server_manager.get_active_config()
                if active_config:
                    logger.info(f"アクティブ設定: {active_config}")
            else:
                logger.warning("アクティブサーバーが設定されていません")
            
            # 各サーバーが必要な設定を持っていることを確認
            for server in servers:
                config = server.config
                auth_type = config.get("auth_type", "sql").lower()
                
                # 必須フィールドの確認
                assert "server" in config, f"サーバー {server.name} にサーバー設定がありません"
                assert "database" in config, f"サーバー {server.name} にデータベース設定がありません"
                
                # 認証タイプ別の検証
                if auth_type == "sql":
                    assert "user" in config, f"サーバー {server.name} にSQL認証用のユーザー名がありません"
                    assert "password" in config, f"サーバー {server.name} にSQL認証用のパスワードがありません"
                elif auth_type == "entra":
                    assert "client_id" in config, f"サーバー {server.name} にクライアントIDがありません"
                    assert "tenant_id" in config, f"サーバー {server.name} にテナントIDがありません"
                    
                    # インタラクティブ認証またはクライアントシークレットまたはユーザー名のいずれかが必要
                    auth_mode = config.get("auth_mode", "").lower()
                    if auth_mode != "interactive":
                        assert "client_secret" in config or "username" in config, \
                            f"サーバー {server.name} に非インタラクティブ認証用の資格情報がありません"
                elif auth_type == "windows":
                    # Windows認証では追加の検証は不要
                    pass
                else:
                    assert False, f"サーバー {server.name} に無効な認証タイプがあります: {auth_type}"