import argparse
import pyodbc  # pymssqlからpyodbcに変更
import socket
import logging
import sys
import time
import traceback
import os
from contextlib import contextmanager
from dotenv import load_dotenv  # .envファイルサポートのためのライブラリを追加
from pathlib import Path

# .envファイルの読み込み
load_dotenv()

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
    parser = argparse.ArgumentParser(
        description='SQL Server接続のデバッグツール（.envファイルもサポート）'
    )
    parser.add_argument('--server', help='SQLサーバーのホスト名またはIPアドレス（デフォルト: MSSQL_SERVER環境変数）')
    parser.add_argument('--database', help='データベース名（デフォルト: MSSQL_DATABASE環境変数）')
    parser.add_argument('--user', help='SQLユーザー名（デフォルト: MSSQL_USER環境変数、Windows認証の場合は不要）')
    parser.add_argument('--password', help='SQLパスワード（デフォルト: MSSQL_PASSWORD環境変数、Windows認証の場合は不要）')
    parser.add_argument('--timeout', type=int, help='接続タイムアウト（秒）（デフォルト: 30秒）')
    parser.add_argument('--auth', choices=['sql', 'windows', 'entra'], help='認証タイプ（sql/windows/entra）（デフォルト: MSSQL_AUTH_TYPE環境変数または sql）')
    parser.add_argument('--debug', action='store_true', help='詳細なデバッグ情報を出力')
    parser.add_argument('--env-file', help='.envファイルのパス（デフォルト: カレントディレクトリの.env）')
    parser.add_argument('--driver', help='ODBCドライバー名（デフォルト: MSSQL_DRIVER環境変数または "ODBC Driver 17 for SQL Server"）')
    return parser.parse_args()

def get_config_from_env_and_args(args):
    """環境変数とコマンドライン引数から設定を取得する"""
    # カスタム.envファイルが指定されている場合は読み込む
    if args.env_file and os.path.exists(args.env_file):
        logger.info(f"カスタム.envファイルを読み込み中: {args.env_file}")
        load_dotenv(args.env_file)
    
    # 環境変数からデフォルト値を取得
    env_server = os.getenv("MSSQL_SERVER")
    env_database = os.getenv("MSSQL_DATABASE")
    env_user = os.getenv("MSSQL_USER")
    env_password = os.getenv("MSSQL_PASSWORD")
    env_auth_type = os.getenv("MSSQL_AUTH_TYPE", "sql").lower()
    env_timeout = os.getenv("MSSQL_TIMEOUT")
    env_encrypt = os.getenv("ENCRYPT")
    env_driver = os.getenv("MSSQL_DRIVER", "ODBC Driver 18 for SQL Server")
    
    # タイムアウトを整数に変換（環境変数から取得した場合）
    timeout = 30  # デフォルト値
    if args.timeout is not None:
        timeout = args.timeout
    elif env_timeout:
        try:
            timeout = int(env_timeout)
        except ValueError:
            logger.warning(f"環境変数のタイムアウト値'{env_timeout}'を解析できません。デフォルト値30秒を使用します。")
    
    # コマンドライン引数と環境変数の組み合わせ（コマンドライン引数が優先）
    config = {
        "server": args.server or env_server or "localhost",
        "database": args.database or env_database,
        "user": args.user or env_user,
        "password": args.password or env_password,
        "timeout": timeout,
        "auth": args.auth or env_auth_type,
        "driver": args.driver or env_driver
    }
    
    # 暗号化設定があれば追加
    if env_encrypt:
        config["encrypt"] = env_encrypt
    
    # 必須パラメータの検証
    if not config["database"]:
        logger.error("データベース名が指定されていません。--databaseオプションまたはMSSQL_DATABASE環境変数を設定してください。")
        sys.exit(1)
    
    if config["auth"] == "sql" and (not config["user"] or not config["password"]):
        logger.error("SQL認証には、ユーザー名とパスワードが必要です。")
        logger.error("--userと--passwordオプション、またはMSSQL_USERとMSSQL_PASSWORD環境変数を設定してください。")
        sys.exit(1)
    
    return config

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
    
    # 基本的な接続文字列パーツを構築
    conn_str_parts = [
        f"DRIVER={{{config['driver']}}}",
        f"SERVER={config['server']}",
        f"DATABASE={config['database']}"
    ]
    
    # タイムアウト設定
    if config["timeout"]:
        conn_str_parts.append(f"Connection Timeout={config['timeout']}")
    
    # 暗号化設定
    if "encryption" in config:
        conn_str_parts.append(f"Encrypt={config['encryption']}")
    elif os.getenv("ENCRYPTION"):
        conn_str_parts.append(f"Encrypt={os.getenv('ENCRYPTION')}")
    
    # 認証タイプに応じてパラメータを追加
    if config["auth"] == "sql":
        if not config.get("user") or not config.get("password"):
            logger.error("✗ SQL認証にはユーザー名とパスワードが必要です")
            return None
        conn_str_parts.append(f"UID={config['user']}")
        conn_str_parts.append(f"PWD={config['password']}")
        auth_type = "SQL認証"
    elif config["auth"] == "windows":
        conn_str_parts.append("Trusted_Connection=yes")
        auth_type = "Windows認証"
    elif config["auth"] == "entra":
        conn_str_parts.append("Authentication=ActiveDirectoryInteractive")
        auth_type = "Entra ID"
    else:
        conn_str_parts.append("Trusted_Connection=yes")
        auth_type = "Windows認証"
    
    # 接続文字列を構築
    conn_str = ";".join(conn_str_parts)
    
    # 接続文字列のログ出力（機密情報はマスク）
    safe_conn_str = conn_str
    if config["auth"] == "sql":
        safe_conn_str = safe_conn_str.replace(config["password"], "******")
    
    logger.info(f"接続文字列: {safe_conn_str}")
    logger.info(f"認証タイプ: {auth_type}")
    
    try:
        with measure_time("SQL Server接続"):
            conn = pyodbc.connect(conn_str)
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
        elif "driver" in error_str:
            logger.error("  - 指定されたODBCドライバーが見つかりません")
            logger.error(f"  - 利用可能なドライバー: {', '.join(pyodbc.drivers())}")
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

def load_env_config(section=None):
    """環境設定ファイルから設定を読み込む"""
    load_dotenv()
    
    # デフォルトサーバーを取得
    default_server = os.getenv("MSSQL_DEFAULT_SERVER")
    if section is None:
        section = default_server
        logger.info(f"デフォルトサーバーを使用します: {section}")
    
    # 指定されたセクションの設定を読み込む
    env_path = Path('.env')
    if not env_path.exists():
        logger.error("エラー: .env ファイルが見つかりません")
        sys.exit(1)
        
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        # UTF-8でダメな場合はLatin-1で試みる
        with open(env_path, 'r', encoding='latin-1') as f:
            lines = f.readlines()
    
    in_section = False
    config = {}
    
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
            
        if line.startswith('[') and line.endswith(']'):
            current_section = line[1:-1]
            in_section = (current_section == section)
            continue
            
        if in_section and '=' in line:
            key, value = line.split('=', 1)
            config[key.strip()] = value.strip()
    
    return config

def load_all_env_configs():
    """環境設定ファイルからすべてのサーバー設定を読み込む"""
    load_dotenv()
    
    env_path = Path('.env')
    if not env_path.exists():
        logger.error("エラー: .env ファイルが見つかりません")
        return {}
        
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        with open(env_path, 'r', encoding='latin-1') as f:
            lines = f.readlines()
    
    configs = {}
    current_section = None
    
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
            
        if line.startswith('[') and line.endswith(']'):
            current_section = line[1:-1]
            if current_section != 'default': # 'default'セクションは無視
                configs[current_section] = {}
            continue
            
        if current_section and current_section != 'default' and '=' in line:
            key, value = line.split('=', 1)
            configs[current_section][key.strip()] = value.strip()
            
    # MSSQL_SERVER を持たないセクションを除外
    final_configs = {
        section: config for section, config in configs.items() 
        if 'MSSQL_SERVER' in config
    }

    return final_configs

def test_connection(server_name, config):
    """設定を使用してデータベース接続をテスト"""
    logger.info(f"--- {server_name} の接続テスト開始 ---")
    auth_type = config.get('MSSQL_AUTH_TYPE', '').lower()
    server = config.get('MSSQL_SERVER', '')
    database = config.get('MSSQL_DATABASE', '')
    driver = config.get('MSSQL_DRIVER', 'ODBC Driver 18 for SQL Server')
    encryption = config.get('ENCRYPTION', 'yes') # デフォルトで暗号化を試みる
    
    if not server or not database:
        logger.error("エラー: サーバーまたはデータベースが設定されていません")
        return False
    
    try:
        conn_str_parts = [
            f"DRIVER={{{driver}}}",
            f"SERVER={server}",
            f"DATABASE={database}",
            f"Encrypt={encryption}"
        ]
        
        if auth_type == 'windows':
            conn_str_parts.append("Trusted_Connection=yes")
            logger.info("認証タイプ: Windows認証")
        elif auth_type == 'sql':
            user = config.get('MSSQL_USER', '')
            password = config.get('MSSQL_PASSWORD', '')
            if not user or not password:
                logger.error("✗ SQL認証にはユーザー名とパスワードが必要です")
                return False
            conn_str_parts.append(f"UID={user}")
            conn_str_parts.append(f"PWD={password}")
            logger.info("認証タイプ: SQL認証")
        elif auth_type == 'entra':
            auth_mode = config.get('MSSQL_AUTH_MODE', 'interactive').lower()
            if auth_mode == 'interactive':
                use_device_code = config.get('MSSQL_USE_DEVICE_CODE', 'false').lower() == 'true'
                if use_device_code:
                    conn_str_parts.append("Authentication=ActiveDirectoryDeviceCodeLogin")
                    logger.info("認証タイプ: Entra ID (Device Code)")
                else:
                    conn_str_parts.append("Authentication=ActiveDirectoryInteractive")
                    logger.info("認証タイプ: Entra ID (Interactive)")
            else: # client_secret, etc.
                # ここではインタラクティブなフローのみを実装
                logger.warning(f"Entra ID の認証モード '{auth_mode}' は現在サポートされていません。")
                return False
        
        conn_string = ';'.join(conn_str_parts)
        
        # パスワードをマスクして接続文字列をログに出力
        safe_conn_str = conn_string
        if auth_type == 'sql':
            safe_conn_str = safe_conn_str.replace(config.get('MSSQL_PASSWORD', ''), '******')
        logger.info(f"接続文字列: {safe_conn_str}")
        
        with measure_time(f"{server_name} への接続"):
            conn = pyodbc.connect(conn_string, timeout=15)

        cursor = conn.cursor()
        cursor.execute("SELECT @@VERSION")
        row = cursor.fetchone()
        logger.info(f"✓ 接続成功: {server_name}")
        logger.info(f"  SQL Server バージョン: {row[0].splitlines()[0]}")
        cursor.close()
        conn.close()
        return True
    except pyodbc.OperationalError as e:
        if "Login timeout expired" in str(e):
            logger.error(f"✗ 接続エラー ({server_name}): ログインタイムアウト")
            logger.error("  - サーバーが応答しません。サーバーが起動しているか、ネットワーク経路を確認してください。")
        elif "Cannot open server" in str(e):
            logger.error(f"✗ 接続エラー ({server_name}): サーバーに接続できません")
            logger.error("  - ファイアウォールがポート1433をブロックしている可能性があります。")
        else:
            logger.error(f"✗ 接続エラー ({server_name}): {str(e).splitlines()[0]}")
        return False
    except Exception as e:
        logger.error(f"✗ 予期せぬエラー ({server_name}): {str(e).splitlines()[0]}")
        return False
    finally:
        logger.info(f"--- {server_name} の接続テスト終了 ---\n")

def main():
    """メイン実行関数"""
    parser = argparse.ArgumentParser(description='SQL Server接続のデバッグツール')
    parser.add_argument('server_name', nargs='?', default=None, 
                        help='テストするサーバー名（.envファイルのセクション名）。指定しない場合はすべてのサーバーをテストします。')
    parser.add_argument('--debug', action='store_true', help='詳細なデバッグ情報を出力')
    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)

    logger.info("=== SQL Server一括接続デバッグツール ===")
    
    all_configs = load_all_env_configs()
    if not all_configs:
        logger.warning(".envファイルにサーバー設定が見つかりませんでした。")
        return

    if args.server_name:
        if args.server_name in all_configs:
            test_connection(args.server_name, all_configs[args.server_name])
        else:
            logger.error(f"エラー: サーバー '{args.server_name}' の設定が.envファイルに見つかりません。")
            logger.info(f"利用可能なサーバー: {', '.join(all_configs.keys())}")
    else:
        logger.info(".envファイル内のすべてのサーバーの接続をテストします...")
        results = {}
        for name, config in all_configs.items():
            results[name] = test_connection(name, config)
        
        logger.info("=== 全サーバーのテスト結果概要 ===")
        for name, success in results.items():
            status = "✓ 成功" if success else "✗ 失敗"
            logger.info(f"- {name}: {status}")

if __name__ == "__main__":
    main()