# WindowsマシンでPythonからSQL Serverに接続するための環境構築ガイド

このガイドでは、WindowsマシンでPythonからSQL Serverに接続するための環境構築手順を詳細に説明します。Windows認証とEntra ID認証（旧Azure AD）の両方の方法を含めて体系的に説明します。

## 1. 基本環境のセットアップ

### 1.1 Pythonのインストール

1. **Pythonのダウンロードとインストール**
   - [Python公式サイト](https://www.python.org/downloads/)から最新版をダウンロード
   - インストール時に「Add Python to PATH」オプションにチェックを入れる
   - カスタムインストールの場合は、「pip」が含まれていることを確認

2. **インストール確認**
   ```bash
   python --version
   pip --version
   ```
### 1.2 必要なライブラリのインストール

1. **pyodbcのインストール**（SQLサーバー接続用ドライバー）
   ```bash
   pip install pyodbc
   ```

2. **その他の便利なライブラリ**（必要に応じて）
   ```bash
   pip install pandas  # データ分析用
   pip install msal    # Entra認証用
   ```

## 2. SQL Serverの設定

### 2.1 SQL Serverの基本設定

1. **TCP/IP接続の有効化**
   - スタートメニューから「SQL Server構成マネージャー」を開く
   - 「SQL Serverネットワークの構成」→「(インスタンス名)のプロトコル」を展開
   - 「TCP/IP」を右クリックして「有効」に設定

2. **ポート設定**
   - 「TCP/IP」をダブルクリック→「IPアドレス」タブを選択
   - 「IPALL」セクションの「TCPポート」に「1433」を入力
   - 「OK」をクリックして設定を保存

3. **SQLサービスの再起動**
   - 「SQL Server構成マネージャー」で「SQLサービス」を選択
   - 「SQL Server (インスタンス名)」を右クリックして「再起動」

### 2.2 ファイアウォール設定

1. **Windows Firewall設定**
   - コントロールパネル→システムとセキュリティ→Windows Defender ファイアウォール
   - 「詳細設定」→「受信の規則」→「新しい規則」
   - 「ポート」を選択→TCP→特定のローカルポート「1433」→許可→規則名を入力して完了

## 3. Windows認証での接続設定

### 3.1 Windows認証の前提条件

1. **アクセス権限の確認**
   - SQLサーバーに対してWindows認証で接続できるユーザー権限があることを確認
   - 必要に応じてSQLサーバーで権限設定

### 3.2 接続コードの実装例

```python
import pyodbc

def connect_with_windows_auth():
    server = 'サーバー名'  # SQLサーバー名またはIPアドレス
    database = 'データベース名'  # 接続するデータベース名
    
    # Windows認証の接続文字列
    conn_str = (
        f'DRIVER={{SQL Server}};'
        f'SERVER={server};'
        f'DATABASE={database};'
        f'Trusted_Connection=yes;'  # Windows認証を使用
    )
    
    try:
        # 接続を確立
        conn = pyodbc.connect(conn_str)
        print("Windows認証での接続に成功しました。")
        
        # 接続テスト用の簡単なクエリ
        cursor = conn.cursor()
        cursor.execute("SELECT @@VERSION")
        row = cursor.fetchone()
        print(f"SQL Serverバージョン: {row[0]}")
        
        # リソースの解放
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"接続エラー: {str(e)}")

if __name__ == "__main__":
    connect_with_windows_auth()
```

## 4. Entra ID認証での接続設定

### 4.1 Entra ID認証の前提条件

1. **Azure Active Directory (Entra ID) の設定**
   - Azure Portalでアプリケーション登録
   - クライアントID（アプリケーションID）の取得
   - クライアントシークレットの生成（サービスプリンシパル認証の場合）
   - 適切なAPIアクセス許可の設定

2. **SQL Serverでの設定**
   - Azure SQL DatabaseまたはSQL Managed InstanceでEntra ID認証が有効になっていることを確認
   - Entra IDユーザーのデータベースユーザー作成：
     ```sql
     CREATE USER [user@yourdomain.com] FROM EXTERNAL PROVIDER;
     ALTER ROLE db_datareader ADD MEMBER [user@yourdomain.com];
     ```

### 4.2 MSALライブラリを使用した接続設定

1. **必要なライブラリのインストール**
   ```bash
   pip install msal pyodbc
   ```

2. **サービスプリンシパル認証の実装例**

```python
import pyodbc
import msal

def connect_with_entra_auth():
    # Entra ID認証情報
    client_id = 'アプリケーションID'
    client_secret = 'クライアントシークレット'
    tenant_id = 'テナントID'
    
    # SQLサーバー接続情報
    server = 'サーバー名.database.windows.net'
    database = 'データベース名'
    
    # MSALを使用してトークン取得
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    app = msal.ConfidentialClientApplication(
        client_id=client_id,
        authority=authority,
        client_credential=client_secret
    )
    
    # SQLサーバー用のスコープ
    scopes = ["https://database.windows.net/.default"]
    
    # トークン取得
    result = app.acquire_token_for_client(scopes=scopes)
    
    if "access_token" in result:
        token = result["access_token"]
        
        # 接続文字列
        conn_str = (
            f'DRIVER={{ODBC Driver 17 for SQL Server}};'
            f'SERVER={server};'
            f'DATABASE={database};'
            f'UID=任意のユーザー名;'  # 実際の認証はトークンで行われる
            f'PWD={token};'  # トークンをパスワードとして使用
            f'Authentication=ActiveDirectoryServicePrincipal;'
        )
        
        try:
            # 接続を確立
            conn = pyodbc.connect(conn_str)
            print("Entra ID認証での接続に成功しました。")
            
            # 接続テスト用の簡単なクエリ
            cursor = conn.cursor()
            cursor.execute("SELECT @@VERSION")
            row = cursor.fetchone()
            print(f"SQL Serverバージョン: {row[0]}")
            
            # リソースの解放
            cursor.close()
            conn.close()
            
        except Exception as e:
            print(f"接続エラー: {str(e)}")
            
    else:
        print(f"トークン取得エラー: {result.get('error_description', result.get('error', '不明なエラー'))}")

if __name__ == "__main__":
    connect_with_entra_auth()
```

3. **ユーザー名/パスワード認証の実装例**

```python
import pyodbc
import msal
import os

def connect_with_entra_username():
    # Entra ID認証情報
    client_id = 'アプリケーションID'
    tenant_id = 'テナントID'
    username = 'user@yourdomain.com'
    password = os.environ.get('ENTRA_PASSWORD')  # 安全のため環境変数から取得
    
    # SQLサーバー接続情報
    server = 'サーバー名.database.windows.net'
    database = 'データベース名'
    
    # MSALを使用してトークン取得
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    app = msal.PublicClientApplication(
        client_id=client_id,
        authority=authority
    )
    
    # SQLサーバー用のスコープ
    scopes = ["https://database.windows.net/.default"]
    
    # ユーザー名/パスワードでトークン取得
    result = app.acquire_token_by_username_password(
        username=username,
        password=password,
        scopes=scopes
    )
    
    if "access_token" in result:
        token = result["access_token"]
        
        # 接続文字列
        conn_str = (
            f'DRIVER={{ODBC Driver 17 for SQL Server}};'
            f'SERVER={server};'
            f'DATABASE={database};'
            f'UID={username};'
            f'PWD={token};'
            f'Authentication=ActiveDirectoryPassword;'
        )
        
        try:
            # 接続を確立
            conn = pyodbc.connect(conn_str)
            print("Entra ID (ユーザー名/パスワード)認証での接続に成功しました。")
            
            # 接続テスト用の簡単なクエリ
            cursor = conn.cursor()
            cursor.execute("SELECT @@VERSION")
            row = cursor.fetchone()
            print(f"SQL Serverバージョン: {row[0]}")
            
            # リソースの解放
            cursor.close()
            conn.close()
            
        except Exception as e:
            print(f"接続エラー: {str(e)}")
            
    else:
        print(f"トークン取得エラー: {result.get('error_description', result.get('error', '不明なエラー'))}")

if __name__ == "__main__":
    connect_with_entra_username()
```

## 5. 接続テストと診断

### 5.1 簡単な接続テストスクリプト

```python
import pyodbc
import time

def test_connection(connection_type="windows", config=None):
    """
    SQLサーバー接続のテストを行う関数
    """
    print(f"===== {connection_type}認証での接続テスト =====")
    start_time = time.time()
    
    if connection_type == "windows":
        conn_str = (
            f'DRIVER={{SQL Server}};'
            f'SERVER={config["server"]};'
            f'DATABASE={config["database"]};'
            f'Trusted_Connection=yes;'
        )
    else:
        # Entra認証の場合はconfigから必要な情報を取得
        # この部分は実際の認証方法によって異なる
        pass
    
    try:
        # 接続試行
        print("接続中...")
        conn = pyodbc.connect(conn_str)
        connection_time = time.time() - start_time
        print(f"接続成功! ({connection_time:.2f}秒)")
        
        # バージョン情報取得
        cursor = conn.cursor()
        cursor.execute("SELECT @@VERSION")
        version = cursor.fetchone()[0]
        print(f"SQLサーバーバージョン: {version[:100]}...")
        
        # テーブル一覧取得
        cursor.execute("SELECT TOP 5 name FROM sys.tables")
        tables = cursor.fetchall()
        if tables:
            print("データベース内のテーブル (最大5件):")
            for table in tables:
                print(f"- {table[0]}")
        else:
            print("テーブルが見つかりませんでした")
        
        # リソース解放
        cursor.close()
        conn.close()
        print("テスト完了: 接続は正常に機能しています")
        
    except Exception as e:
        error_str = str(e).lower()
        print(f"接続エラー: {str(e)}")
        
        # エラー診断
        if "timeout" in error_str:
            print("- ネットワークタイムアウトが発生しました")
            print("- ファイアウォール設定を確認してください")
            print("- タイムアウト時間を長くしてみてください")
        elif "login failed" in error_str:
            print("- ユーザー名/パスワードが間違っています")
            print("- 権限が適切に設定されているか確認してください")
        elif "database" in error_str and "not exist" in error_str:
            print("- 指定されたデータベースが存在しません")
        elif "network" in error_str or "connection" in error_str:
            print("- ネットワーク接続に問題があります")
            print("- サーバー名が正しいか確認してください")
            print("- SQLサーバーが実行中か確認してください")
            print("- TCP/IPが有効になっているか確認してください")

# テスト実行例
if __name__ == "__main__":
    config = {
        "server": "サーバー名",
        "database": "データベース名"
    }
    test_connection("windows", config)
```

## 6. トラブルシューティング

### 6.1 一般的な接続問題

1. **接続文字列の問題**
   - ドライバー名、サーバー名、データベース名などが正しいことを確認
   - `pyodbc.drivers()` を実行して利用可能なドライバーを確認

2. **ネットワーク問題**
   - ファイアウォール設定を確認
   - サーバーに対してping実行で疎通確認
   - TCP/IPが有効化されているか確認

3. **認証問題**
   - Windows認証：実行ユーザーにSQLサーバーへのアクセス権があるか確認
   - Entra ID認証：クライアントID、シークレット、テナントIDが正しいか確認

4. **ドライバー問題**
   - 適切なODBCドライバーがインストールされているか確認
   - 最新のドライバーへの更新を検討

## 7. 環境構築の完全なチェックリスト

1. **Pythonセットアップ**
   - Python 3.x インストール
   - pip最新版の確認
   - 仮想環境の作成（推奨）

2. **必要なライブラリ**
   - pyodbc
   - msal（Entra認証用）
   - pandas（必要に応じて）

3. **SQLサーバー設定**
   - TCP/IP有効化
   - ポート1433開放
   - ファイアウォール設定
   - SQLサービス再起動

4. **接続設定**
   - Windows認証：ドメイン参加確認、権限確認
   - Entra ID認証：アプリ登録、権限設定

5. **接続テスト**
   - 基本接続
   - クエリ実行
   - エラーの場合のトラブルシューティング

このガイドに従って環境を構築すれば、WindowsマシンからPythonを使用してSQL Serverへのアクセスが可能になります。Windows認証とEntra ID認証の両方の方法をサポートできるようになります。