source .venv/bin/activate
source .env
python src/chat.py

## csv(excelでできる仕事)
・情報をまとめること（整理）(物資の要請、道路状況)（電話）
・excelファイルを、共有すること（勝手に書いてくれている）
・万が一対応できない場合に、共有するexcelファイルを作ること


## それ以外の仕事
・物資を渡すこと（物資の供給を指示する）
・情報を渡すこと（資料を渡す。他の人に情報を伝えて対応をお願いする。）


## くる情報
・避難所の状況
・各関係機関の状況
・物資要請
・道路状況・土砂系（土木部..?）


⏺ 各エージェントの情報をまとめます。

  エージェント機能・記憶領域まとめ

  Information Manager (information_manager.py)

  役割: 情報管理担当者

  Functions (できること):
  1. create_csv_file - CSVファイル新規作成
  2. update_csv_from_knowledge - CSVファイル更新（行追加、列追加、セル更新）
  3. read_document - RAG検索（防災計画ドキュメント検索）

  記憶領域:
  - ✓ Knowledge: knowledge_information.txt (保有CSV情報、CSV更新記録、追加した知識を保存)
  - ✓ 会話履歴: 保有（システムプロンプトに含まれる）
  - ✓ CSV: csv/information/ (情報管理用CSV)

  ---
  Supply Manager (supply_manager.py)

  役割: 物資管理担当者（ワーカーA/B/Cを統括）

  Functions (できること):
  1. check_inventory - 在庫確認（ワーカーまたは自身で実行）
  2. deliver_supplies - 物資配送（ワーカーまたは自身で実行）
  3. show_inventory - 在庫一覧表示（ワーカーまたは自身で実行）
  4. show_delivery_log - 配送記録確認（ワーカーまたは自身で実行）
  5. procure_supplies - 物資調達（ワーカーまたは自身で実行）

  記憶領域:
  - ✓ Knowledge: knowledge_supply.txt (保有CSV情報、CSV更新記録)
  - ✓ 会話履歴: 保有（システムプロンプトに含まれる、ただし【情報付与】を除外）
  - ✓ CSV: csv/supply/物資在庫情報.csv, csv/supply/物資配送記録.csv

  ---
  Supply Worker A/B/C (supply_worker.py)

  役割: 物資管理実務担当（Supply Managerの部下）

  Functions (できること):
  1. deliver_supplies - 物資配送実行
  2. procure_supplies - 物資調達実行

  記憶領域:
  - ✗ Knowledge: なし（独自のknowledgeファイルは持たない）
  - ✗ 会話履歴: なし（Managerからタスクを受けて実行するのみ）
  - ✓ CSV: csv/supply/物資在庫情報.csv, csv/supply/物資配送記録.csv（直接操作）

  注意: WorkerはManagerから指示されたタスクを実行するだけで、LLMによる判断や会話機能は持たない

  ---
  現在の課題

  - Supply WorkerがCSVを直接操作している（supply_worker.py:64-96）
  - 統一するならupdate_csv_from_knowledgeを使うべき

  - supplyがworkerに対してできることと、workerが実際にできることが違う。csvの確認だけは、supplyerがするように
  - csvのcheckは、すぐに行えるように。

    Supply Manager の Functions:
  - 確認系（マネージャー専用）:
    - check_inventory - 在庫確認（即座に実行）
    - show_inventory - 在庫一覧表示（即座に実行）
    - show_delivery_log - 配送記録確認（即座に実行）
  - 実行系（ワーカーに依頼可能）:
    - deliver_supplies - 物資配送
    - procure_supplies - 物資調達

  Supply Worker が実際にできること:
  - deliver_supplies - 物資配送
  - procure_supplies - 物資調達


  Playerと会話(物資のmanagerとの会話が普通に行くか)