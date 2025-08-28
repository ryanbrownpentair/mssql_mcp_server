# ITDA-516解決策：WQSDWのInventoryデータ問題分析

## 問題概要

チケット「ITDA-516：人工知能之力を見せて上げろ。」では、WQSDWのInventoryデータに異常があると報告されています。この問題を解決するため、人工知能（AI）の力を活用した分析と解決策を提案します。

## 現状分析結果

WQSDWデータベースに接続し、Inventoryデータの現状を調査しました。

### 発見事項

1. **対象テーブル**: 
   - `InventoryDaily` - 日次在庫データ（空のテーブル）
   - `inventorylog` - 在庫変更履歴（データあり）
   - `VW_MTDInventorySummary` - 月次在庫サマリービュー

2. **データの状態**:
   - `InventoryDaily`テーブルにデータが存在しない（0行）
   - `inventorylog`テーブルには2017年からのデータが存在する
   - 最も古いログレコードは「Inventory quantities import」という情報で登録されている

3. **問題の特定**:
   - `InventoryDaily`テーブルのデータ欠損が主な問題
   - ETL処理または定期データ更新が正常に機能していない可能性
   - 最新の在庫データが適切に更新されていない

## 分析アプローチ

### 1. データ接続診断

WQSDWデータベースへの接続問題がないか確認するため、リポジトリ内の接続診断ツールを使用します。このプロジェクトには既に`debug_connection.py`ツールが含まれています。

```bash
python debug_connection.py --server USCHITDB63-WQSDW --database WQSDW
```

このコマンドは、以下の診断を行います：
- ネットワーク接続テスト
- データベース認証テスト
- 基本クエリ実行テスト
- タイムアウト設定の検証
- 権限チェック

または、リポジトリ内の`run_debug.bat`スクリプトを使用して診断を実行することもできます：

```bash
run_debug.bat USCHITDB63-WQSDW
```

### 2. データ整合性チェック

Inventoryデータの整合性問題を特定するため、以下のチェックを実施します：

1. **テーブル構造の確認**：
   ```sql
   -- テーブル構造の詳細確認
   SELECT 
     COLUMN_NAME, 
     DATA_TYPE, 
     CHARACTER_MAXIMUM_LENGTH, 
     IS_NULLABLE
   FROM INFORMATION_SCHEMA.COLUMNS
   WHERE TABLE_NAME = 'InventoryDaily'
   ORDER BY ORDINAL_POSITION;
   
   -- 主キーと外部キーの確認
   SELECT 
     tc.CONSTRAINT_NAME,
     tc.CONSTRAINT_TYPE,
     ccu.COLUMN_NAME
   FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
   JOIN INFORMATION_SCHEMA.CONSTRAINT_COLUMN_USAGE ccu 
     ON tc.CONSTRAINT_NAME = ccu.CONSTRAINT_NAME
   WHERE tc.TABLE_NAME = 'InventoryDaily'
   AND tc.CONSTRAINT_TYPE IN ('PRIMARY KEY', 'FOREIGN KEY');
   ```

2. **ETL処理状態の確認**：
   ```sql
   SELECT TOP 100
     TableName,
     LastUpdateDate,
     Status,
     ErrorMessage
   FROM ETL_ProcessingLog
   WHERE TableName LIKE '%Inventory%'
   ORDER BY LastUpdateDate DESC;
   ```

3. **ETLジョブの実行履歴確認**：
   ```sql
   -- SSISDBを使用している場合のジョブ実行履歴
   USE SSISDB;
   SELECT TOP 100
     e.execution_id,
     p.name AS package_name,
     e.start_time,
     e.end_time,
     e.status,
     e.status_desc
   FROM catalog.executions e
   JOIN catalog.packages p ON e.package_id = p.package_id
   WHERE p.name LIKE '%Inventory%'
   ORDER BY e.start_time DESC;
   ```

4. **InventoryDaily再構築の検証**：
   ```sql
   -- InventoryDailyの再構築状態を確認
   SELECT COUNT(*) AS RecordCount FROM InventoryDaily;
   
   -- inventorylogから最新データを取得して集計
   SELECT 
     partId, 
     MAX(eventDate) as LastUpdateDate,
     SUM(changeQty) as TotalChange,
     COUNT(*) as TransactionCount
   FROM inventorylog
   GROUP BY partId
   ORDER BY LastUpdateDate DESC;
   ```

5. **最新更新日時と履歴の確認**：
   ```sql
   -- 更新日時の範囲と統計
   SELECT 
     MAX(eventDate) AS latest_update,
     MIN(eventDate) AS oldest_record,
     DATEDIFF(day, MIN(eventDate), MAX(eventDate)) AS date_range_days,
     COUNT(*) AS total_records,
     COUNT(DISTINCT partId) AS unique_parts
   FROM inventorylog;
   
   -- 日ごとのトランザクション数の分析
   SELECT 
     CAST(eventDate AS DATE) AS transaction_date,
     COUNT(*) AS daily_transaction_count,
     COUNT(DISTINCT partId) AS unique_parts_affected
   FROM inventorylog
   GROUP BY CAST(eventDate AS DATE)
   ORDER BY transaction_date DESC;
   ```

6. **データ不整合の特定**：
   ```sql
   -- 負の在庫数値を持つ可能性のある部品を特定
   SELECT 
     partId,
     SUM(changeQty) AS total_quantity_change
   FROM inventorylog
   GROUP BY partId
   HAVING SUM(changeQty) < 0
   ORDER BY total_quantity_change;
   
   -- 異常な数値変更を特定
   SELECT *
   FROM inventorylog
   WHERE ABS(changeQty) > 10000  -- 異常に大きな数値変更
   ORDER BY eventDate DESC;
   ```

7. **依存システムとの連携確認**：
   ```sql
   -- VW_MTDInventorySummaryビューの検証
   SELECT TOP 100 * FROM VW_MTDInventorySummary;
   
   -- 関連レポートやダッシュボードで使用されるクエリの特定
   SELECT 
     o.name AS procedure_name,
     o.create_date,
     o.modify_date,
     m.definition
   FROM sys.sql_modules m
   JOIN sys.objects o ON m.object_id = o.object_id
   WHERE m.definition LIKE '%InventoryDaily%'
   ORDER BY o.name;
   ```

### 3. AIを活用したデータパターン分析

このプロジェクトのMCP（Model Context Protocol）サーバー機能を活用して、AIによるデータパターン分析を実施します：

1. **時系列異常検出**：
   ```python
   # server.pyを使用した異常検出の実行
   from src.mssql_mcp_server.server import analyze_time_series_data

   # 在庫データの時系列分析
   results = analyze_time_series_data(
       server="USCHITDB63-WQSDW",
       query="""
       SELECT 
           CAST(eventDate AS DATE) AS date,
           SUM(changeQty) AS daily_change
       FROM inventorylog
       GROUP BY CAST(eventDate AS DATE)
       ORDER BY date
       """
   )
   
   # 異常ポイントの特定
   anomalies = [point for point in results if point['is_anomaly']]
   print(f"検出された異常ポイント: {len(anomalies)}")
   ```

2. **データクラスタリング分析**：
   ```python
   # 在庫変動パターンによる部品グループ化
   from sklearn.cluster import KMeans
   import pandas as pd
   import pyodbc
   
   # データベース接続
   conn = pyodbc.connect('DRIVER={ODBC Driver 17 for SQL Server};SERVER=USCHITDB63;DATABASE=WQSDW;Trusted_Connection=yes;')
   
   # 部品ごとの在庫変動パターン取得
   query = """
   SELECT 
       partId,
       DATEPART(month, eventDate) AS month,
       SUM(changeQty) AS monthly_change
   FROM inventorylog
   WHERE eventDate >= DATEADD(year, -1, GETDATE())
   GROUP BY partId, DATEPART(month, eventDate)
   """
   
   df = pd.read_sql(query, conn)
   pivot_df = df.pivot(index='partId', columns='month', values='monthly_change').fillna(0)
   
   # クラスタリング実行
   kmeans = KMeans(n_clusters=5, random_state=0).fit(pivot_df)
   pivot_df['cluster'] = kmeans.labels_
   
   # クラスタごとの特性分析
   for cluster in range(5):
       print(f"クラスタ {cluster} の部品数: {len(pivot_df[pivot_df['cluster'] == cluster])}")
   ```

### 4. データリカバリと検証計画

データの修復と検証のための段階的アプローチを計画します：

1. **バックアップと検証環境の準備**：
   ```sql
   -- 現在の状態をバックアップ
   SELECT * INTO InventoryDaily_Backup_20250711 FROM InventoryDaily;
   ```

2. **データ再構築のための段階的アプローチ**：
   - 最初に小規模なサンプルでテスト（例：特定の部品カテゴリのみ）
   - 結果を検証後、完全なデータセットに適用
   - トランザクションログを使用した段階的な適用と検証

3. **データ検証クエリの準備**：
   ```sql
   -- 在庫数量の整合性チェック
   SELECT 
     p.partId,
     p.PartNumber,
     SUM(il.changeQty) AS calculated_qty,
     id.QOH AS reported_qty,
     CASE 
       WHEN id.QOH IS NULL THEN 'Missing in InventoryDaily'
       WHEN ABS(SUM(il.changeQty) - id.QOH) > 0.01 THEN 'Quantity Mismatch'
       ELSE 'OK'
     END AS status
   FROM inventorylog il
   JOIN Parts p ON il.partId = p.PartID
   LEFT JOIN InventoryDaily id ON p.PartNumber = id.ItemNumber
   GROUP BY p.partId, p.PartNumber, id.QOH
   HAVING CASE 
     WHEN id.QOH IS NULL THEN 1
     WHEN ABS(SUM(il.changeQty) - id.QOH) > 0.01 THEN 1
     ELSE 0
   END = 1;
   ```

### 5. ドメインエキスパートとの協業計画

技術的分析だけでなく、業務知識を持つ関係者との協業も重要です：

1. **主要ステークホルダーの特定**：
   - 在庫管理部門のスーパーユーザー
   - データウェアハウス管理者
   - ETLプロセス担当者
   - レポート利用部門の代表者

2. **ワークショップの計画**：
   - データ問題の影響範囲の評価
   - 在庫データフローの全体マッピング
   - 期待される正常値の定義
   - 検証基準の合意

3. **ドキュメント化の準備**：
   - 問題と原因の説明資料
   - 解決策の選択肢と推奨アプローチ
   - 実装計画とタイムライン
   - 検証プロセスと成功基準

## 問題の考えられる原因

1. **ETL処理の失敗**: `InventoryDaily`テーブルを更新するETLジョブが失敗している
2. **データロード未完了**: 日次データロードプロセスが実行されていない
3. **スケジュール設定の問題**: ETLジョブのスケジュールが適切に設定されていない
4. **テーブル構造の変更**: スキーマ変更により古いETLプロセスが機能しなくなった
5. **アクセス権限の問題**: ETLプロセスの実行アカウントに適切な権限がない

## 解決策

### 即時対応（1-2日以内）

1. **ETL処理の診断と修復**:
   - ETLジョブログの確認
   - 失敗したジョブの再実行
   - `inventorylog`からのデータ抽出と`InventoryDaily`テーブルの再構築

2. **データ整合性の修復**:
   ```sql
   -- InventoryDailyテーブルの再構築
   INSERT INTO InventoryDaily (
     DBName, InventoryDate, ItemNumber, ItemNumberShort, 
     Site, Location, QOH, DateLastUpdated
   )
   SELECT 
     'WQSDW' AS DBName,
     CAST(GETDATE() AS DATE) AS InventoryDate,
     p.PartNumber AS ItemNumber,
     p.PartNumberShort AS ItemNumberShort,
     l.SiteName AS Site,
     l.LocationName AS Location,
     SUM(il.changeQty) AS QOH,
     MAX(il.eventDate) AS DateLastUpdated
   FROM inventorylog il
   JOIN Parts p ON il.partId = p.PartID
   JOIN Locations l ON il.endLocationId = l.LocationID
   GROUP BY p.PartNumber, p.PartNumberShort, l.SiteName, l.LocationName;
   ```

3. **検証クエリの実行**:
   ```sql
   -- 再構築後の検証
   SELECT COUNT(*) FROM InventoryDaily;
   SELECT TOP 100 * FROM InventoryDaily ORDER BY DateLastUpdated DESC;
   ```

### 中期対応（1週間以内）

1. **モニタリングの強化**:
   - インベントリデータの日次整合性チェックを実装
   - ETLジョブの実行状態を監視するアラートシステムを構築

2. **ETLプロセスの改善**:
   - 自動再試行メカニズムの実装
   - エラーハンドリングの強化
   - ログ記録の詳細化

3. **ドキュメント作成**:
   - ETLプロセスのフロー図作成
   - エラー対応手順書の作成
   - データリカバリ手順の文書化

### 長期対応（1ヶ月以内）

1. **データパイプラインの改善**:
   - ETLプロセスの見直しと最適化
   - リアルタイムデータ監視システムの構築
   - データ品質スコアカードの導入

2. **AIを活用したデータ監視**:
   - 機械学習モデルによる異常検出
   - 時系列分析による在庫傾向予測
   - 自動修正提案システムの構築

3. **予防措置の導入**:
   - データバリデーションルールの強化
   - ETL前後のデータスナップショット作成
   - データリカバリ自動化の実装

## 実装プラン

### Day 1：診断と即時修復

1. WQSDWデータベース接続の診断
   ```bash
   python debug_connection.py --server USCHITDB63-WQSDW --database WQSDW
   ```

2. ETLログの確認とエラー分析
   ```sql
   SELECT TOP 100 * FROM ETL_ProcessingLog 
   WHERE TableName LIKE '%Inventory%' 
   ORDER BY LogDate DESC;
   ```

3. `InventoryDaily`テーブルの再構築スクリプト作成と実行
4. 修復後の検証クエリを実行し、データの整合性を確認

### Day 2-3：モニタリングと検証の強化

1. 日次データ整合性チェックスクリプトの作成
   ```python
   # daily_inventory_check.py
   import pyodbc
   import datetime
   import smtplib
   from email.mime.text import MIMEText
   
   # データベース接続
   conn = pyodbc.connect('DRIVER={ODBC Driver 17 for SQL Server};SERVER=USCHITDB63;DATABASE=WQSDW;Trusted_Connection=yes;')
   cursor = conn.cursor()
   
   # 整合性チェッククエリの実行
   cursor.execute("""
   SELECT 
     (SELECT COUNT(*) FROM InventoryDaily) AS daily_count,
     (SELECT COUNT(DISTINCT partId) FROM inventorylog) AS log_distinct_parts,
     (SELECT MAX(eventDate) FROM inventorylog) AS last_log_date,
     (SELECT MAX(DateLastUpdated) FROM InventoryDaily) AS last_daily_update
   """)
   
   result = cursor.fetchone()
   
   # 問題の検出
   issues = []
   if result.daily_count == 0:
       issues.append("InventoryDailyテーブルにデータがありません")
   
   if result.last_log_date and result.last_daily_update:
       days_diff = (result.last_log_date - result.last_daily_update).days
       if days_diff > 1:
           issues.append(f"InventoryDailyの最終更新が{days_diff}日前です")
   
   if issues:
       # アラートメール送信のロジック
       message = MIMEText("\n".join(issues))
       message["Subject"] = "WQSDW Inventoryデータ問題検出"
       message["From"] = "monitoring@pentair.com"
       message["To"] = "data.team@pentair.com"
       
       with smtplib.SMTP("smtp.pentair.com") as server:
           server.send_message(message)
   
   conn.close()
   ```

2. スケジュールタスクの設定（毎朝6時に実行など）
3. アラート通知システムの構築（Eメール、チャットなど）

### Day 4-5：ドキュメントと長期計画

1. 問題と解決策の詳細ドキュメント作成
2. ETLプロセスフロー図の作成
3. データリカバリ手順書の作成
4. AIを活用したデータ監視システムの設計

## 期待される結果

この解決策を実装することで、以下の結果が期待できます：

1. WQSDWのInventoryデータの整合性が回復し、正確なレポート作成が可能になる
2. ETL処理の信頼性が向上し、データ更新の安定性が確保される
3. 問題の早期検出と自動対応により、ビジネスへの影響を最小化できる
4. AIを活用したデータ監視により、将来的な問題の予防と予測が可能になる

## まとめ

本チケットで報告されたWQSDWのInventoryデータ問題に対して、実際のデータベース調査に基づいた包括的な解決策を提案しました。

主な問題は`InventoryDaily`テーブルのデータ欠損であることが判明し、`inventorylog`テーブルのデータを活用した再構築プロセスを中心に解決策を設計しました。ETL処理の診断と修復、モニタリングの強化、そしてAIを活用した予測的データ監視の導入により、データの信頼性と可用性を確保します。

この対応により、「人工知能之力を見せて上げろ」というチケットの要請に応える形で、実際のデータ調査からAIを活用した解決策まで、包括的なアプローチを提供しています。
