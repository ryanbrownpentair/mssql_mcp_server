import asyncio
import logging
import os
import sys
from dotenv import load_dotenv

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("test_windows_servers")

# プロジェクトのルートディレクトリをPythonパスに追加
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

# 環境変数を.envファイルから読み込む
load_dotenv()

from mssql_mcp_server.server_manager import get_server_manager
from mssql_mcp_server.server import create_connection

async def test_windows_servers():
    """設定された2つのWindowsサーバーをテストする"""
    logger.info("Windowsサーバーのテストを開始します...")
    
    # サーバーマネージャーを初期化
    server_manager = get_server_manager()
    
    # 利用可能なサーバーを表示
    servers = server_manager.get_server_list()
    logger.info(f"読み込まれたサーバー数: {len(servers)}")
    
    for server in servers:
        logger.info(f"サーバー: {server.name}, 表示名: {server.display_name}")
        logger.info(f"  認証タイプ: {server.config.get('auth_type', 'sql')}")
        logger.info(f"  サーバー: {server.config['server']}")
        logger.info(f"  データベース: {server.config['database']}")
    
    # .envファイルで定義された特定のWindowsサーバーをテスト
    windows_servers = [
        "USCHITDB63-PTODS",
        "USCHITDB63-WQSDW"
    ]
    
    # 各Windowsサーバーをテスト
    for server_name in windows_servers:
        server = server_manager.get_server_by_name(server_name)
        if server:
            logger.info(f"サーバー {server_name} の接続をテストします...")
            
            # アクティブサーバーとして設定
            server_manager.set_active_server(server_name)
            config = server_manager.get_active_config()
            
            # 認証タイプを確認
            auth_type = config.get("auth_type", "").lower()
            if auth_type != "windows":
                logger.warning(f"サーバー {server_name} はWindows認証を使用していません: {auth_type}")
                continue
            
            # 接続を試行
            try:
                connection = create_connection(config)
                logger.info(f"サーバー {server_name} に正常に接続しました")
                
                # 基本的なクエリを実行
                cursor = connection.cursor()
                cursor.execute("SELECT 1 AS test")
                result = cursor.fetchone()
                
                if result and result[0] == 1:
                    logger.info(f"サーバー {server_name} でクエリが正常に実行されました")
                else:
                    logger.error(f"サーバー {server_name} でクエリの結果が期待通りではありません: {result}")
                
                # テーブル一覧を取得
                logger.info(f"サーバー {server_name} のテーブル一覧を取得します...")
                cursor.execute("""
                    SELECT TOP 10 TABLE_NAME 
                    FROM INFORMATION_SCHEMA.TABLES 
                    WHERE TABLE_TYPE = 'BASE TABLE'
                """)
                tables = cursor.fetchall()
                
                if tables:
                    logger.info(f"サーバー {server_name} で見つかったテーブル（最大10件）:")
                    for table in tables:
                        logger.info(f"  - {table[0]}")
                else:
                    logger.warning(f"サーバー {server_name} ではテーブルが見つかりませんでした")
                
                # リソースをクリーンアップ
                cursor.close()
                connection.close()
                
            except Exception as e:
                logger.error(f"サーバー {server_name} への接続中にエラーが発生しました: {str(e)}")
        else:
            logger.error(f"サーバー {server_name} が見つかりません")
    
    logger.info("Windowsサーバーのテストが完了しました")

if __name__ == "__main__":
    asyncio.run(test_windows_servers())
