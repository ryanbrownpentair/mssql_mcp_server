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
logger = logging.getLogger("test_windows_sql_execution")

# プロジェクトのルートディレクトリをPythonパスに追加
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

# 環境変数を.envファイルから読み込む
load_dotenv()

from mssql_mcp_server.server_manager import get_server_manager
from mssql_mcp_server.server import call_tool

async def test_execute_sql_on_windows_servers():
    """WindowsサーバーでのツールによるSQL実行テスト"""
    logger.info("WindowsサーバーでのSQL実行テストを開始します...")
    
    # サーバーマネージャーを初期化
    server_manager = get_server_manager()
    
    # テスト対象のサーバー
    windows_servers = [
        "USCHITDB63-PTODS",
        "USCHITDB63-WQSDW"
    ]
    
    # 各サーバーでSQLクエリを実行
    for server_name in windows_servers:
        logger.info(f"サーバー {server_name} でSQL実行テストを行います...")
        
        # テストケース: サーバー切り替え
        result = await call_tool("switch_server", {"server": server_name})
        if result and result[0].text and "Switched to server" in result[0].text:
            logger.info(f"サーバー {server_name} に切り替えました")
        else:
            logger.error(f"サーバー {server_name} への切り替えに失敗しました")
            continue
        
        # テストケース: テーブル一覧取得
        try:
            result = await call_tool("execute_sql", {
                "query": "SELECT TOP 5 TABLE_NAME, TABLE_TYPE FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE'"
            })
            
            if result and result[0].text:
                logger.info(f"サーバー {server_name} のテーブル一覧クエリの結果:")
                logger.info(result[0].text)
            else:
                logger.error(f"サーバー {server_name} のテーブル一覧取得に失敗しました")
        except Exception as e:
            logger.error(f"テーブル一覧クエリの実行中にエラーが発生しました: {str(e)}")
        
        # テストケース: データベースバージョン取得
        try:
            result = await call_tool("execute_sql", {
                "query": "SELECT @@VERSION AS version"
            })
            
            if result and result[0].text:
                logger.info(f"サーバー {server_name} のバージョン情報:")
                logger.info(result[0].text)
            else:
                logger.error(f"サーバー {server_name} のバージョン情報取得に失敗しました")
        except Exception as e:
            logger.error(f"バージョンクエリの実行中にエラーが発生しました: {str(e)}")
    
    logger.info("WindowsサーバーでのSQL実行テストが完了しました")

if __name__ == "__main__":
    asyncio.run(test_execute_sql_on_windows_servers())
