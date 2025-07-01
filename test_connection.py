import pymssql
import sys
import time
import traceback

config = {
    "server": "{DB Server}",
    "user": "{SQL account}",
    "password": "{SQL password}",
    "database": "{DB Name}",
    "login_timeout": 30,  # 接続タイムアウトを追加（秒）
    "timeout": 30        # クエリタイムアウトを追加（秒）
}

# 接続テストを段階的に実行
def test_connection_step_by_step():
    print("===== pymssql 接続テスト（ステップバイステップ） =====")
    
    # ステップ1: 基本的な接続情報の確認
    print("\nステップ1: 接続情報の確認")
    print(f"サーバー: {config['server']}")
    print(f"データベース: {config['database']}")
    print(f"ユーザー: {config['user']}")
    print(f"タイムアウト設定: {config['timeout']}秒")
    
    # ステップ2: 接続試行
    print("\nステップ2: SQL Server接続試行...")
    connection_start = time.time()
    
    try:
        print("  接続中...")
        conn = pymssql.connect(**config)
        connection_time = time.time() - connection_start
        print(f"  ✓ 接続成功！（{connection_time:.2f}秒）")
    except Exception as e:
        connection_time = time.time() - connection_start
        print(f"  ✗ 接続失敗: {str(e)}（{connection_time:.2f}秒）")
        print("\n詳細なエラー情報:")
        traceback.print_exc()
        print("\n考えられる原因:")
        
        error_str = str(e).lower()
        if "timeout" in error_str:
            print("- ネットワークタイムアウト: サーバーに到達できません")
            print("  • ファイアウォールの設定を確認してください")
            print("  • サーバー名/IPアドレスが正しいか確認してください")
            print("  • タイムアウト時間を長くしてみてください")
        elif "login failed" in error_str:
            print("- 認証エラー: ログインに失敗しました")
            print("  • ユーザー名とパスワードが正しいか確認してください")
            print("  • SQLユーザーがアクティブで、このデータベースへのアクセス権があるか確認してください")
        elif "database" in error_str and "not exist" in error_str:
            print("- データベースエラー: 指定されたデータベースが存在しません")
        elif "network" in error_str or "connection" in error_str:
            print("- ネットワークエラー: 接続できませんでした")
            print("  • SQLサーバーが実行中か確認してください")
            print("  • ポート1433が開いているか確認してください")
        return
    
    # ステップ3: 簡単なクエリ実行
    print("\nステップ3: テストクエリ実行...")
    try:
        cursor = conn.cursor()
        query_start = time.time()
        cursor.execute("SELECT @@VERSION")
        query_time = time.time() - query_start
        row = cursor.fetchone()
        print(f"  ✓ クエリ実行成功！（{query_time:.2f}秒）")
        print(f"  SQL Serverバージョン: {row[0][:50]}...")
        
        # ステップ4: 実際のテーブルからデータを取得
        print("\nステップ4: テーブル一覧の取得...")
        query_start = time.time()
        cursor.execute("SELECT TOP 5 name FROM sys.tables")
        query_time = time.time() - query_start
        tables = cursor.fetchall()
        print(f"  ✓ テーブル取得成功！（{query_time:.2f}秒）")
        
        if tables:
            print("  データベース内のテーブル（最大5件）:")
            for table in tables:
                print(f"  - {table[0]}")
        else:
            print("  このデータベースにはテーブルが見つかりませんでした")
        
        cursor.close()
        conn.close()
        print("\n✓ すべてのテストが成功しました！SQL Server接続は正常に動作しています。")
    except Exception as e:
        print(f"  ✗ クエリ実行エラー: {str(e)}")
        print("\n詳細なエラー情報:")
        traceback.print_exc()
        try:
            conn.close()
        except:
            pass

# メイン実行
if __name__ == "__main__":
    test_connection_step_by_step()
