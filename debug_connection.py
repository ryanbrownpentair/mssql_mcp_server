import argparse
import pymssql
import socket
import logging
import sys
import time
import traceback
from contextlib import contextmanager

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("pymssql_debug")

def parse_args():
    """コマンドライン引数のパース"""
    parser = argparse.ArgumentParser(description='SQL Server接続のデバッグツール')
    parser.add_argument('--server', required=True, help='SQLサーバーのホスト名またはIPアドレス')
    parser.add_argument('--database', required=True, help='データベース名')
    parser.add_argument('--user', help='SQLユーザー名（Windows認証の場合は不要）')
    parser.add_argument('--password', help='SQLパスワード（Windows認証の場合は不要）')
    parser.add_argument('--timeout', type=int, default=30, help='接続タイムアウト（秒）')
    parser.add_argument('--auth', choices=['sql', 'windows'], default='sql', help='認証タイプ（sql/windows）')
    parser.add_argument('--debug', action='store_true', help='詳細なデバッグ情報を出力')
    return parser.parse_args()

@contextmanager
def measure_time(description):
    """処理時間を計測するコンテキストマネージャー"""
    start_time = time.time()
    yield
    elapsed_time = time.time() - start_time
    logger.info(f"{description}: {elapsed_time:.2f}秒")

def check_network_connection(server, port=1433):
    """ネットワーク接続をチェック（基本的なTCP接続）"""
    logger.info(f"ステップ1: ネットワーク接続のテスト（{server}:{port}）...")
    
    try:
        with measure_time("ネットワーク接続"):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)  # 5秒のタイムアウト
            result = sock.connect_ex((server, port))
            sock.close()
            
        if result == 0:
            logger.info(f"✓ ネットワーク接続成功: {server}:{port}に接続できました")
            return True
        else:
            logger.error(f"✗ ネットワーク接続失敗: {server}:{port}に接続できません（エラーコード: {result}）")
            logger.error("  - ファイアウォールの設定を確認してください")
            logger.error("  - サーバー名が正しいか確認してください")
            logger.error("  - SQLサーバーが実行中か確認してください")
            return False
    except socket.gaierror:
        logger.error(f"✗ ネットワーク接続失敗: ホスト名'{server}'の解決ができません")
        logger.error("  - サーバー名のスペルが正しいか確認してください")
        logger.error("  - DNSの設定を確認してください")
        return False
    except Exception as e:
        logger.error(f"✗ ネットワーク接続テスト中にエラーが発生しました: {str(e)}")
        return False

def create_test_connection(config, detailed=False):
    """SQL Server接続のテスト（低レベルな詳細を表示）"""
    logger.info(f"ステップ2: SQL Server接続のテスト...")
    
    # 基本的な接続パラメータ
    connection_params = {
        "server": config["server"],
        "database": config["database"],
        "login_timeout": config["timeout"],
        "timeout": config["timeout"]
    }
    
    # 認証タイプに応じてパラメータを追加
    if config["auth"] == "sql":
        if not config.get("user") or not config.get("password"):
            logger.error("✗ SQL認証にはユーザー名とパスワードが必要です")
            return False
        connection_params["user"] = config["user"]
        connection_params["password"] = config["password"]
        auth_type = "SQL認証"
    else:
        auth_type = "Windows認証"
    
    # 接続パラメータのログ出力（機密情報はマスク）
    safe_params = connection_params.copy()
    if "password" in safe_params:
        safe_params["password"] = "******"
    logger.info(f"接続パラメータ: {safe_params}")
    logger.info(f"認証タイプ: {auth_type}")
    
    try:
        with measure_time("SQL Server接続"):
            conn = pymssql.connect(**connection_params)
        logger.info(f"✓ SQL Server接続成功: {config['server']}/{config['database']}に接続できました")
        return conn
    except Exception as e:
        logger.error(f"✗ SQL Server接続失敗: {str(e)}")
        if detailed:
            logger.error("詳細なエラー情報:")
            logger.error(traceback.format_exc())
        
        # エラーの種類に応じたヒントを表示
        error_str = str(e).lower()
        if "timeout" in error_str:
            logger.error("  - ネットワークのタイムアウトが発生しました")
            logger.error("  - ファイアウォールの設定を確認してください")
            logger.error("  - タイムアウト時間を長くしてみてください")
        elif "login failed" in error_str:
            logger.error("  - ユーザー名またはパスワードが間違っています")
            logger.error("  - SQLユーザーがこのデータベースにアクセス権限を持っているか確認してください")
        elif "database" in error_str and "not exist" in error_str:
            logger.error("  - 指定されたデータベースが存在しません")
        elif "network" in error_str or "connection" in error_str:
            logger.error("  - ネットワーク接続に問題があります")
            logger.error("  - サーバー名が正しいか確認してください")
            logger.error("  - SQL Serverが実行中か確認してください")
        return None

def execute_test_query(conn):
    """テストクエリの実行"""
    logger.info("ステップ3: テストクエリの実行...")
    
    try:
        with measure_time("クエリ実行"):
            cursor = conn.cursor()
            cursor.execute("SELECT @@VERSION")
            result = cursor.fetchone()
            cursor.close()
        
        logger.info(f"✓ クエリ実行成功:")
        logger.info(f"  - SQL Serverバージョン: {result[0][:50]}...")
        return True
    except Exception as e:
        logger.error(f"✗ クエリ実行失敗: {str(e)}")
        logger.error(traceback.format_exc())
        return False

def main():
    """メイン実行関数"""
    args = parse_args()
    
    if args.debug:
        logger.setLevel(logging.DEBUG)
    
    logger.info("=== SQL Server接続デバッグツール ===")
    
    # 設定の整理
    config = {
        "server": args.server,
        "database": args.database,
        "user": args.user,
        "password": args.password,
        "timeout": args.timeout,
        "auth": args.auth
    }
    
    # ステップ1: ネットワーク接続テスト
    if not check_network_connection(args.server):
        return
    
    # ステップ2: SQL Server接続テスト
    conn = create_test_connection(config, detailed=args.debug)
    if not conn:
        return
    
    # ステップ3: テストクエリ実行
    success = execute_test_query(conn)
    
    # 接続を閉じる
    try:
        conn.close()
        logger.info("SQL Server接続を正常に閉じました")
    except:
        pass
    
    # 最終結果
    if success:
        logger.info("✓ すべてのテストが成功しました！SQL Server接続は正常に動作しています。")
    else:
        logger.error("✗ テストに失敗しました。上記のエラーメッセージを確認してください。")

if __name__ == "__main__":
    main()