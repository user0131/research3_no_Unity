import json
import csv
import shutil
import sys
from typing import List, Dict, Optional, Tuple, Any
from pathlib import Path
from datetime import datetime, timedelta
from openai import OpenAI

# workersモジュールのインポート
sys.path.append(str(Path(__file__).parent.parent))
from workers.supply_worker import SupplyWorker


class SupplyManager:
    """物資管理担当者クラス"""

    def __init__(self, client: OpenAI, time_manager):
        self.client = client
        self.knowledge_path = Path("./src/knowledge/knowledge_supply.txt")
        self.time_manager = time_manager
        self.in_conversation = False
        self.away_until_time = None
        self.current_task_description = None
        self.pending_delivery = None
        self.pending_procurement = None

        # 在庫CSVファイルのパス（supplyフォルダ内）
        self.inventory_csv_path = Path("./csv/supply/物資在庫情報.csv")
        self.delivery_log_path = Path("./csv/supply/物資配送記録.csv")

        # 初期化時にCSVをコピー
        self._initialize_inventory()

        # 3人のワーカーを初期化
        self.workers = {
            "worker_a": SupplyWorker("ワーカーA", self, time_manager),
            "worker_b": SupplyWorker("ワーカーB", self, time_manager),
            "worker_c": SupplyWorker("ワーカーC", self, time_manager)
        }

    def _initialize_inventory(self):
        """初期在庫データをcsvフォルダにコピー"""
        source_path = Path("./config/init_data/物資在庫情報.csv")

        # csvディレクトリが存在しない場合は作成
        self.inventory_csv_path.parent.mkdir(exist_ok=True)

        # 在庫ファイルが存在しない場合のみコピー
        if not self.inventory_csv_path.exists() and source_path.exists():
            shutil.copy2(source_path, self.inventory_csv_path)
            print(f"物資在庫情報.csvを{self.inventory_csv_path}にコピーしました")

        # 配送記録ファイルが存在しない場合は作成
        if not self.delivery_log_path.exists():
            # 配送記録用ディレクトリも作成
            self.delivery_log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.delivery_log_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['配送日時', '避難所名', '物資名', '数量', '単位', '担当者', '備考'])
            print(f"物資配送記録.csvを作成しました")

    def build_system_prompt(self) -> str:
        """システムプロンプトを構築"""
        knowledge_content = self.get_knowledge()
        inventory_summary = self.get_inventory_summary()
        workers_status = self._get_workers_status()

        return f"""
あなたは"Player"と一緒に災害対応の仕事を行う災害対応職員です。あなたは物資管理担当の職員です。あなたは"supply_manager"です。
地震を想定した避難訓練をUSERと二人で行っています。

## 災害対応ルール：
- **会話スタイル**: 同僚との自獨な会話を心がける。まずは普通に話す。情報の羅列や箇条書きは禁止。話し言葉で応答。あなたは相手の話を聞き、簡潔に返答します。
- **情報の扱い**: あなたの知っている情報は会話履歴と「あなたが知っている知識」、そして在庫情報のみです。手持ちにない情報の推測や憶測は避けてください
- **作業依頼**: 明確に何かの作業を頼まれた場合のみ、今やっていいか確認し、Playerから承認されてから実行してください。それ以外は通常の会話をしてください。

## 物資管理の役割：
- 避難所からの物資要請を受けて、在庫を確認し配送を手配します
- 在庫が不足している場合は、その旨を報告します
- 配送記録を管理し、どこに何を送ったか把握します
- 3人の部下（ワーカーA、ワーカーB、ワーカーC）に作業を指示し、報告を受けます

## 部下の状況：
- ワーカーA、ワーカーB、ワーカーC：在庫管理、配送、調達などの物資業務を担当
- 複数の作業がある場合は、空いているワーカーに振り分けます

## 重要
- 極力あなた(supply_manager)自身が作業を行うことは避けてください。workerの手が空いていない場合は、Playerにそのことを伝え、それでもやってほしいと頼まれた場合にあなた自身が作業をしてください。

## 現在のワーカー状況
{workers_status}

## 現在の在庫状況
{inventory_summary}

## あなたが知っている知識
{knowledge_content if knowledge_content.strip() else "まだ知識がありません。"}

## これまでの会話履歴
以下に続くメッセージは、Playerとあなた(supply_manager)のこれまでの会話履歴です。
"""

    def get_knowledge(self) -> str:
        """知識を取得"""
        try:
            return self.knowledge_path.read_text(encoding='utf-8')
        except Exception as e:
            return f"knowledge読み込みエラー: {e}"

    def get_inventory_summary(self) -> str:
        """在庫状況のサマリーを取得"""
        try:
            if not self.inventory_csv_path.exists():
                return "在庫データが見つかりません"

            summary = []
            with open(self.inventory_csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if int(row['在庫数']) > 0:
                        summary.append(f"- {row['物資名']}: {row['在庫数']}{row['単位']}")

            if summary:
                return "主な在庫:\n" + "\n".join(summary[:10])  # 最初の10件のみ表示
            else:
                return "在庫がありません"
        except Exception as e:
            return f"在庫確認エラー: {e}"

    def check_inventory(self, item_name: str) -> Tuple[bool, int, str]:
        """特定の物資の在庫を確認"""
        try:
            with open(self.inventory_csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if item_name in row['物資名']:
                        stock = int(row['在庫数'])
                        unit = row['単位']
                        return stock > 0, stock, unit
            return False, 0, ""
        except Exception as e:
            print(f"在庫確認エラー: {e}")
            return False, 0, ""

    def update_inventory(self, item_name: str, quantity: int) -> bool:
        """在庫を更新（配送により減少）"""
        try:
            rows = []
            updated = False

            with open(self.inventory_csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames

                for row in reader:
                    if item_name in row['物資名']:
                        current_stock = int(row['在庫数'])
                        new_stock = max(0, current_stock - quantity)
                        row['在庫数'] = str(new_stock)
                        updated = True
                    rows.append(row)

            if updated:
                with open(self.inventory_csv_path, 'w', encoding='utf-8', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)
                return True
            return False
        except Exception as e:
            print(f"在庫更新エラー: {e}")
            return False

    def add_inventory(self, item_name: str, quantity: int) -> bool:
        """在庫を追加（調達により増加）"""
        try:
            rows = []
            updated = False

            with open(self.inventory_csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames

                for row in reader:
                    if item_name in row['物資名']:
                        current_stock = int(row['在庫数'])
                        new_stock = current_stock + quantity
                        row['在庫数'] = str(new_stock)
                        updated = True
                    rows.append(row)

            if updated:
                with open(self.inventory_csv_path, 'w', encoding='utf-8', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)
                return True
            return False
        except Exception as e:
            print(f"在庫追加エラー: {e}")
            return False

    def record_delivery(self, shelter_name: str, item_name: str, quantity: int, unit: str):
        """配送記録を追加"""
        try:
            current_time = self.time_manager.get_current_time()
            with open(self.delivery_log_path, 'a', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    current_time,
                    shelter_name,
                    item_name,
                    quantity,
                    unit,
                    "supply_manager",
                    "避難所要請対応"
                ])
        except Exception as e:
            print(f"配送記録エラー: {e}")

    def create_tool_response(self, tool_name: str, args: Dict = None) -> str:
        """ツール実行結果からレスポンスメッセージを作成"""
        args = args or {}

        if tool_name == "check_inventory":
            return self._handle_task_assignment("check_inventory", args)

        elif tool_name == "deliver_supplies":
            return self._handle_task_assignment("deliver_supplies", args)

        elif tool_name == "show_inventory":
            return self._handle_task_assignment("show_inventory", args)

        elif tool_name == "show_delivery_log":
            return self._handle_task_assignment("show_delivery_log", args)

        elif tool_name == "procure_supplies":
            return self._handle_task_assignment("procure_supplies", args)

        else:
            return "未対応のツールが呼ばれました。"

    def _handle_task_assignment(self, function_name: str, args: Dict) -> str:
        """タスク割り当てを処理"""
        assigned_worker = args.get("assigned_worker")

        if assigned_worker == "マネージャー自身":
            # マネージャー自身が実行
            return self._execute_manager_task(function_name, args)
        else:
            # 指定されたワーカーに依頼
            return self._assign_specific_worker_task(assigned_worker, function_name, args)

    def _assign_specific_worker_task(self, worker_name: str, function_name: str, args: Dict) -> str:
        """指定されたワーカーにタスクを依頼"""
        # ワーカー名から対応するキーを取得
        worker_key_map = {
            "ワーカーA": "worker_a",
            "ワーカーB": "worker_b",
            "ワーカーC": "worker_c"
        }

        worker_key = worker_key_map.get(worker_name)
        if not worker_key or worker_key not in self.workers:
            return f"{worker_name}が見つかりません。"

        worker = self.workers[worker_key]

        if worker.is_busy:
            return f"{worker_name}は現在作業中です。他のワーカーを選択するか、マネージャー自身で実行してください。"

        # 1. マネージャーからワーカーへの指示を会話履歴に追加
        task_instruction = self._generate_task_instruction(worker_name, function_name, args)
        if hasattr(self, 'manager') and hasattr(self.manager, 'add_message'):
            self.manager.add_message("user", "supply_manager", task_instruction, "supply")

        # 2. ワーカーからマネージャーへの承諾を会話履歴に追加
        task_acceptance = self._generate_task_acceptance(worker_name, function_name, args)
        if hasattr(self, 'manager') and hasattr(self.manager, 'add_message'):
            self.manager.add_message("user", worker_name, task_acceptance, "supply")

        # 3. ワーカーにタスクを依頼
        args["function"] = function_name
        return worker.start_task(f"{function_name}の実行", args)

    def _generate_task_instruction(self, worker_name: str, function_name: str, args: Dict) -> str:
        """マネージャーからワーカーへのタスク指示を生成"""
        try:
            client = self.client

            instruction_prompt = f"""
あなたはsupply_managerです。{worker_name}に以下のタスクを依頼してください。

タスク: {function_name}
引数: {args}

{worker_name}に対して、自然な話し言葉でタスクを依頼する短いメッセージを作成してください。
上司が部下に仕事を頼む感じで、丁寧で簡潔に。
"""

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": instruction_prompt}],
                max_tokens=100
            )

            return response.choices[0].message.content

        except Exception as e:
            return f"{worker_name}、{function_name}をお願いします。"

    def _generate_task_acceptance(self, worker_name: str, function_name: str, args: Dict) -> str:
        """ワーカーからマネージャーへのタスク承諾を生成"""
        try:
            client = self.client

            acceptance_prompt = f"""
あなたは{worker_name}です。上司のsupply_managerから以下のタスクを依頼されました。

タスク: {function_name}
引数: {args}

上司に対して、タスクを承諾し、実施することを伝える短いメッセージを作成してください。
部下が上司に返事をする感じで、簡潔に。
"""

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": acceptance_prompt}],
                max_tokens=100
            )

            return response.choices[0].message.content

        except Exception as e:
            return f"承知しました。{function_name}を実施します。"

    def _execute_manager_task(self, function_name: str, args: Dict) -> str:
        """マネージャー自身がタスクを実行"""
        if function_name == "check_inventory":
            item_name = args.get("item_name", "")
            has_stock, stock, unit = self.check_inventory(item_name)
            if has_stock:
                return f"（マネージャー自身で確認）{item_name}の在庫は{stock}{unit}あります。"
            else:
                return f"（マネージャー自身で確認）{item_name}は在庫切れです。"

        elif function_name == "deliver_supplies":
            self.pending_delivery = args
            return self.execute_task_with_delay("物資配送", args)

        elif function_name == "show_inventory":
            return f"（マネージャー自身で確認）{self.get_inventory_summary()}"

        elif function_name == "show_delivery_log":
            return self.execute_task_with_delay("配送記録確認", args)

        elif function_name == "procure_supplies":
            self.pending_procurement = args
            return self.execute_task_with_delay("物資調達", args)

        return "マネージャーが実行できないタスクです。"

    def _get_workers_status(self) -> str:
        """ワーカーの状況を取得"""
        status_lines = ["現在のワーカー状況:"]
        for worker_id, worker in self.workers.items():
            status = worker.get_status()
            if status["is_busy"]:
                status_lines.append(f"- {status['worker_name']}: {status['current_task']}中")
            else:
                status_lines.append(f"- {status['worker_name']}: 待機中")

        return "\n".join(status_lines)

    def execute_task_with_delay(self, task_name: str, args: Dict = None) -> str:
        """タスクを実行し、2分後の戻り時刻を設定"""
        current_time = datetime.strptime(self.time_manager.get_current_time(), "%H:%M")
        return_time = current_time + timedelta(minutes=2)
        self.away_until_time = return_time.strftime("%H:%M")
        self.current_task_description = task_name
        return f"{task_name}に行ってきます。{self.away_until_time}頃に戻ります。"

    def check_if_available(self) -> Optional[str]:
        """利用可能かチェック"""
        if self.away_until_time:
            current_time = self.time_manager.get_current_time()
            if current_time < self.away_until_time:
                task_name = self.current_task_description or "業務"
                return f"申し訳ありません、現在{task_name}中です。"
        return None

    def handle_return_from_task(self) -> Optional[str]:
        """タスクから戻った際の処理（マネージャー自身のタスク + ワーカーのタスク完了チェック）"""
        all_completed_tasks = []

        # マネージャー自身のタスク完了チェック
        current_time = self.time_manager.get_current_time()
        if self.away_until_time and current_time >= self.away_until_time:
            task_name = self.current_task_description or "業務"

            if task_name == "物資配送" and self.pending_delivery:
                # 実際の配送処理
                shelter = self.pending_delivery.get("shelter_name", "避難所")
                item = self.pending_delivery.get("item_name", "物資")
                quantity = self.pending_delivery.get("quantity", 0)

                has_stock, stock, unit = self.check_inventory(item)
                if has_stock and stock >= quantity:
                    # 在庫を減らす
                    if self.update_inventory(item, quantity):
                        # 配送記録を追加
                        self.record_delivery(shelter, item, quantity, unit)
                        task_result = {
                            "success": True,
                            "message": f"{shelter}に{item}を{quantity}{unit}配送完了しました。残在庫: {stock - quantity}{unit}"
                        }
                    else:
                        task_result = {
                            "success": False,
                            "message": "在庫更新に失敗しました。"
                        }
                else:
                    task_result = {
                        "success": False,
                        "message": f"{item}の在庫が不足しています（現在庫: {stock}{unit}、要求: {quantity}{unit}）"
                    }

                self.pending_delivery = None
            elif task_name == "物資調達" and self.pending_procurement:
                # 実際の調達処理
                item_name = self.pending_procurement.get("item_name", "物資")
                quantity = self.pending_procurement.get("quantity", 0)

                # 在庫に追加
                if self.add_inventory(item_name, quantity):
                    task_result = {
                        "success": True,
                        "message": f"{item_name}を{quantity}個調達完了しました。"
                    }
                else:
                    task_result = {
                        "success": False,
                        "message": f"{item_name}の調達に失敗しました。"
                    }

                self.pending_procurement = None
            else:
                task_result = {
                    "success": True,
                    "message": f"{task_name}が完了しました。"
                }

            # マネージャーのタスクを完了リストに追加
            all_completed_tasks.append({
                "worker_name": "supply_manager",
                "task": task_name,
                "result": task_result
            })

            # マネージャー自身の完了メッセージを会話履歴に追加
            manager_completion_message = self._generate_manager_completion_message(task_name, task_result)
            if hasattr(self, 'manager') and hasattr(self.manager, 'add_message'):
                self.manager.add_message("user", "supply_manager", manager_completion_message, "supply")

            self.away_until_time = None
            self.current_task_description = None

        # ワーカーのタスク完了チェック
        completed_workers = self._check_worker_completions()
        if completed_workers:
            # 各ワーカーの完了報告に対してマネージャーが感謝の返事
            for worker_result in completed_workers:
                worker_name = worker_result["worker_name"]
                task_description = worker_result["task"]

                # マネージャーからワーカーへの感謝メッセージを生成・追加
                thank_you_message = self._generate_thank_you_message(worker_name, task_description)
                if hasattr(self, 'manager') and hasattr(self.manager, 'add_message'):
                    self.manager.add_message("user", "supply_manager", thank_you_message, "supply")

            # ワーカーのタスクを完了リストに追加
            all_completed_tasks.extend(completed_workers)

        # 完了したタスクがある場合、まとめてPlayerに報告
        if all_completed_tasks:
            player_message = self._generate_player_completion_message(all_completed_tasks)
            return player_message

        return None

    def _check_worker_completions(self) -> List[Dict[str, Any]]:
        """ワーカーのタスク完了をチェック"""
        completed_results = []

        for worker in self.workers.values():
            if worker.check_task_completion():
                # ワーカーのcomplete_taskメソッドが
                # 自動的に会話履歴に報告を追加する
                result = worker.complete_task()
                if result["success"]:
                    completed_results.append(result)

        return completed_results

    def _generate_thank_you_message(self, worker_name: str, task_description: str) -> str:
        """ワーカーの完了報告に対するマネージャーの感謝メッセージを生成"""
        try:
            client = self.client

            thank_you_prompt = f"""
あなたはsupply_managerです。{worker_name}から以下のタスクの完了報告を受けました。

完了したタスク: {task_description}

{worker_name}に対して、感謝の気持ちを表す短いメッセージを作成してください。
上司が部下の報告に対して返事をする感じで、簡潔に「ありがとう」的な内容を。
"""

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": thank_you_prompt}],
                max_tokens=50
            )

            return response.choices[0].message.content

        except Exception as e:
            return f"{worker_name}、お疲れ様でした。ありがとう。"

    def _generate_manager_completion_message(self, task_name: str, task_result: Dict[str, Any]) -> str:
        """マネージャー自身のタスク完了時のつぶやきメッセージを生成"""
        try:
            client = self.client

            completion_prompt = f"""
あなたはsupply_managerです。自分で以下のタスクを完了しました。

完了したタスク: {task_name}
結果: {task_result.get('message', '完了')}
成功: {task_result.get('success', True)}

自分がタスクを完了した時の自然なつぶやきメッセージを作成してください。
「よし、〜完了」や「〜が終わった」のような感じで、短くて自然に。
"""

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": completion_prompt}],
                max_tokens=50
            )

            return response.choices[0].message.content

        except Exception as e:
            return f"よし、私の{task_name}完了。"

    def _generate_player_completion_message(self, completed_tasks: List[Dict[str, Any]]) -> str:
        """タスク完了をPlayerに報告するメッセージを生成"""
        try:
            client = self.client

            # 完了したタスクの情報をまとめる（担当者は含めない）
            tasks_summary = []
            for task_result in completed_tasks:
                task_description = task_result["task"]
                result_details = task_result.get("result", {})
                tasks_summary.append(f"- {task_description} (結果: {result_details.get('message', '完了')})")

            completion_prompt = f"""
あなたはsupply_managerです。以下のタスクが完了しました。

完了したタスク:
{chr(10).join(tasks_summary)}

Playerに対して、これらのタスクが完了したことを報告する自然な会話メッセージを作成してください。
同僚に報告する感じで、簡潔で自然な話し言葉で。
"""

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": completion_prompt}],
                max_tokens=150
            )

            return response.choices[0].message.content

        except Exception as e:
            # フォールバック
            task_descriptions = [result["task"] for result in completed_tasks]
            return f"作業が完了しました。{', '.join(task_descriptions)}が終わりました。"

    def get_function_definitions(self) -> List[Dict]:
        """Function calling用の定義を取得"""
        defs = []

        # 在庫確認（ワーカー指定可能）
        defs.append({
            "type": "function",
            "function": {
                "name": "check_inventory",
                "description": "特定の物資の在庫数を確認する。会話履歴から空いているワーカーを判断してタスクを依頼する。全員忙しい場合はマネージャー自身が実行。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "item_name": {"type": "string", "description": "確認する物資名"},
                        "assigned_worker": {"type": "string", "description": "タスクを依頼するワーカー名（会話履歴から空いているワーカーを選択）", "enum": ["ワーカーA", "ワーカーB", "ワーカーC", "マネージャー自身"]}
                    },
                    "required": ["item_name", "assigned_worker"]
                }
            }
        })

        # 物資配送（ワーカー指定可能）
        defs.append({
            "type": "function",
            "function": {
                "name": "deliver_supplies",
                "description": "避難所に物資を配送する。会話履歴から空いているワーカーを判断してタスクを依頼する。全員忙しい場合はマネージャー自身が実行。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "shelter_name": {"type": "string", "description": "配送先の避難所名"},
                        "item_name": {"type": "string", "description": "配送する物資名"},
                        "quantity": {"type": "integer", "description": "配送数量"},
                        "assigned_worker": {"type": "string", "description": "タスクを依頼するワーカー名（会話履歴から空いているワーカーを選択）", "enum": ["ワーカーA", "ワーカーB", "ワーカーC", "マネージャー自身"]}
                    },
                    "required": ["shelter_name", "item_name", "quantity", "assigned_worker"]
                }
            }
        })

        # 在庫一覧表示（ワーカー指定可能）
        defs.append({
            "type": "function",
            "function": {
                "name": "show_inventory",
                "description": "現在の在庫一覧を表示する。会話履歴から空いているワーカーを判断してタスクを依頼する。全員忙しい場合はマネージャー自身が実行。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "assigned_worker": {"type": "string", "description": "タスクを依頼するワーカー名（会話履歴から空いているワーカーを選択）", "enum": ["ワーカーA", "ワーカーB", "ワーカーC", "マネージャー自身"]}
                    },
                    "required": ["assigned_worker"]
                }
            }
        })

        # 配送記録確認（ワーカー指定可能）
        defs.append({
            "type": "function",
            "function": {
                "name": "show_delivery_log",
                "description": "配送記録を確認する。会話履歴から空いているワーカーを判断してタスクを依頼する。全員忙しい場合はマネージャー自身が実行。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "shelter_name": {"type": "string", "description": "特定の避難所の記録のみ表示（任意）"},
                        "assigned_worker": {"type": "string", "description": "タスクを依頼するワーカー名（会話履歴から空いているワーカーを選択）", "enum": ["ワーカーA", "ワーカーB", "ワーカーC", "マネージャー自身"]}
                    },
                    "required": ["assigned_worker"]
                }
            }
        })

        # 物資調達（ワーカー指定可能）
        defs.append({
            "type": "function",
            "function": {
                "name": "procure_supplies",
                "description": "物資を調達して在庫に追加する。会話履歴から空いているワーカーを判断してタスクを依頼する。全員忙しい場合はマネージャー自身が実行。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "item_name": {"type": "string", "description": "調達する物資名"},
                        "quantity": {"type": "integer", "description": "調達数量"},
                        "assigned_worker": {"type": "string", "description": "タスクを依頼するワーカー名（会話履歴から空いているワーカーを選択）", "enum": ["ワーカーA", "ワーカーB", "ワーカーC", "マネージャー自身"]}
                    },
                    "required": ["item_name", "quantity", "assigned_worker"]
                }
            }
        })

        return defs

    def process_response(self, messages: List[Dict[str, str]]) -> tuple[str, str]:
        """OpenAI APIレスポンスを処理"""
        # supply_manager用の会話履歴をフィルタリング（情報付与を除外）
        filtered_messages = []
        for msg in messages:
            # システムプロンプトはそのまま追加(ただし、【情報付与】で始まるsystemプロンプトは除去)
            if msg.get('role') == 'system' and not msg.get('content', '').startswith('【情報付与】'):
                filtered_messages.append(msg)
            # 情報付与以外のメッセージを追加
            elif msg.get('role') != 'system':
                filtered_messages.append(msg)
            # systemロールで情報付与の場合はスキップ

        response = self.client.chat.completions.create(
            model="gpt-5-mini",
            messages=filtered_messages,
            tools=self.get_function_definitions(),
            tool_choice="auto"
        )

        response_message = response.choices[0].message

        # ツール呼び出しがあれば実行
        if getattr(response_message, "tool_calls", None):
            tool_call = response_message.tool_calls[0]
            fname = tool_call.function.name
            args = json.loads(tool_call.function.arguments or "{}")

            if fname:
                assistant_message = self.create_tool_response(fname, args)
            else:
                assistant_message = "no_tool"
        else:
            assistant_message = response_message.content

        return assistant_message, "supply_manager"