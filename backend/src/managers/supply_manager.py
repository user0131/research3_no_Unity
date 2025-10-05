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
from tools.supply_task import SupplyInventoryTool


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

        # 在庫管理ツールを初期化
        self.inventory_tool = SupplyInventoryTool(self.knowledge_path, time_manager)

        # 3人のワーカーを初期化
        self.workers = {
            "worker_a": SupplyWorker("物資ワーカーA", self, time_manager),
            "worker_b": SupplyWorker("物資ワーカーB", self, time_manager),
            "worker_c": SupplyWorker("物資ワーカーC", self, time_manager)
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
                writer.writerow(['避難所名', '物資名', '数量', '単位', '備考'])
            print(f"物資配送記録.csvを作成しました")

    def build_system_prompt(self) -> str:
        """システムプロンプトを構築"""
        knowledge_content = self.get_knowledge()
        workers_status = self._get_workers_status()

        return f"""
あなたは"Player"と一緒に災害対応の仕事を行う災害対応職員です。あなたは物資管理担当の職員です。あなたは"supply_manager"です。
地震を想定した避難訓練を"Player"と行っています。

## 災害対応ルール：
- **会話スタイル**: 同僚との自獨な会話を心がける。まずは普通に話す。情報の羅列や箇条書きは禁止。話し言葉で応答。あなたは相手の話を聞き、簡潔に返答します。ユーザに聞かれたこと以外は極力返さないように。
- **情報の扱い**: あなたの知っている情報は会話履歴と「あなたが知っている知識」のみです。手持ちにない情報の推測や憶測は避けてください
- **作業依頼**: Playerから明確に、具体的に何かの作業を頼まれた場合のみ、作業を実行してください。それ以外は通常の会話をしてください。
- **重要：タスク内容の確認**: 作業を依頼された場合、場所や対象が曖昧・不明確な場合は、ツールを実行せずに詳細を確認してください。例：「避難所に物資配送」→どの避難所か聞き返す、「水を配送」→どこに・何本か聞き返す。具体的な避難所名・物資名・数量が指定されている場合のみツールを実行。
- **重要：在庫確認と承認プロセス**:
  - **配送前の必須確認**: 物資配送を依頼された場合、まず必ずcheck_inventoryツールで在庫を確認し、Playerに現在の在庫状況を報告してください
  - **在庫不足時の対応**: 要請数量に対して在庫が不足している場合は、配送を実行せず、Playerに在庫不足を報告して対応方針を相談してください
  - **勝手な判断禁止**: 在庫が不足していても、勝手に調達したり、部分的に配送したりせず、必ずPlayerと相談してください
- **重要：ツールの使用**: 実際の作業は必ずツールを使って実行してください。会話（テキスト応答）では作業を実行できません。
  - **ツール以外では実行不可**: 会話で「配送します」「手配しました」と言っても実際の作業は実行されません
  - **物資配送**: deliver_suppliesツールを使用（check_inventoryは確認のみで配送は行えません）
  - **物資調達**: procure_suppliesツールを使用
  - **在庫確認**: check_inventoryツールを使用（確認のみ）
  - **在庫一覧**: show_inventoryツールを使用（確認のみ）
  - **配送記録**: show_delivery_logツールを使用（確認のみ）
  - **必須**: タスクを実行する場合は、必ず適切なツールを呼び出してください。JSON形式の情報や配送指示を会話で返すことは禁止です。
  - **複数回のツール呼び出し**: 在庫確認後に配送が必要な場合も、必ずdeliver_suppliesツールを呼び出してください。会話で配送内容を説明せず、ツールで実行してください。
- **ワーカー情報の非開示**: ワーカーA、ワーカーB、ワーカーCといった具体的なワーカー名や、誰が作業をするかの詳細をPlayerに伝える必要はありません。あなたが内部的に判断して「手配します」「対応します」のように伝えてください。また、到着希望時間や担当受け取り等も聞く必要はありません。

## 重要
- 極力あなた(supply_manager)自身が作業を行うことは避けてください。workerの手が空いていない場合は、Playerにそのことを伝え、それでもやってほしいと頼まれた場合にあなた自身が作業をしてください。
- ユーザに聞かれたこと以外は極力返さないように。
- 物資配送や、物資調達のツールでは、Playerに対してツール実行の報告も関数内で行います。物資配送や、物資調達のツールを使う際に、Playerに会話を返答する必要なありません。
- Playerから伝えられたことを実行するために、タスクを工夫する必要はありません。Playerから言われたことがシンプルにできない場合は、できない理由を簡潔にPlayerに伝えるだけで大丈夫です。

## Playerに無理に開示しなくて大丈夫な情報：
以下の情報は、あなたが内部的に判断するために使用します。Playerに対しては詳細を説明する必要はありません。
**重要**: ワーカーの名前（ワーカーA、ワーカーB、ワーカーC）や、誰が何をするかといった内部情報をPlayerに伝えないでください。

### 現在のワーカー(部下の)状況（この情報はPlayerに伝えない）
{workers_status}

Playerに対しては「手配します」「対応します」のように、ワーカー名を出さずに伝えてください。

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

    def _record_tool_execution(self, tool_name: str, args: Dict):
        """ツール実行をknowledge_supply.txtに記録"""
        try:
            current_time = self.time_manager.get_current_time()

            # 引数を整理して記録用テキストを作成
            args_text = ""
            if tool_name == "deliver_supplies":
                shelter = args.get("shelter_name", "")
                item = args.get("item_name", "")
                quantity = args.get("quantity", 0)
                worker = args.get("assigned_worker", "")
                args_text = f"避難所: {shelter}, 物資: {item}, 数量: {quantity}, 担当: {worker}"
            elif tool_name == "procure_supplies":
                item = args.get("item_name", "")
                quantity = args.get("quantity", 0)
                worker = args.get("assigned_worker", "")
                args_text = f"物資: {item}, 数量: {quantity}, 担当: {worker}"
            elif tool_name == "check_inventory":
                item = args.get("item_name", "")
                args_text = f"物資: {item}"
            elif tool_name == "show_delivery_log":
                shelter = args.get("shelter_name", "")
                args_text = f"避難所: {shelter}" if shelter else "全記録"
            else:
                args_text = str(args) if args else "引数なし"

            # 現在のknowledge内容を読み取り
            try:
                current_content = self.knowledge_path.read_text(encoding='utf-8')
            except FileNotFoundError:
                current_content = ""

            # ツール実行記録セクションを探すか作成
            lines = current_content.split('\n')
            tool_section_start = -1

            for i, line in enumerate(lines):
                if line.strip() == "## ツール実行記録":
                    tool_section_start = i
                    break

            # 新しい記録エントリ
            new_entry = f"### {current_time} - {tool_name}\n- {args_text}\n"

            if tool_section_start >= 0:
                # 既存のセクションに追加
                lines.insert(tool_section_start + 1, new_entry)
            else:
                # 新しいセクションを作成
                lines.extend([
                    "",
                    "## ツール実行記録",
                    new_entry
                ])

            # ファイルに書き戻し
            updated_content = '\n'.join(lines)
            self.knowledge_path.write_text(updated_content, encoding='utf-8')

        except Exception as e:
            print(f"ツール実行記録エラー: {e}")

    def create_tool_response(self, tool_name: str, args: Dict = None) -> str:
        """ツール実行結果からレスポンスメッセージを作成"""
        args = args or {}

        # ツール実行を記録
        self._record_tool_execution(tool_name, args)

        # 確認系（マネージャー専用）
        if tool_name == "check_inventory":
            return self._execute_manager_task("check_inventory", args)

        elif tool_name == "show_inventory":
            return self._execute_manager_task("show_inventory", args)

        elif tool_name == "show_delivery_log":
            return self._execute_manager_task("show_delivery_log", args)

        # 実行系（ワーカー指定可能）
        elif tool_name == "deliver_supplies":
            return self._handle_task_assignment("deliver_supplies", args)

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
            "物資ワーカーA": "worker_a",
            "物資ワーカーB": "worker_b",
            "物資ワーカーC": "worker_c"
        }

        worker_key = worker_key_map.get(worker_name)
        if not worker_key or worker_key not in self.workers:
            return f"{worker_name}が見つかりません。"

        worker = self.workers[worker_key]

        if worker.is_busy:
            return f"{worker_name}は現在作業中です。他のワーカーを選択するか、マネージャー自身で実行してください。"

        # 1. Playerに依頼内容を報告（process_responseで一括通知されるため、ここでは個別通知しない）
        # single_task = [{
        #     "tool_call": type('obj', (object,), {
        #         'function': type('obj', (object,), {
        #             'name': function_name,
        #             'arguments': json.dumps(args)
        #         })()
        #     })()
        # }]
        # player_notification = self._generate_combined_assignment_notification(single_task)
        # if hasattr(self, 'manager') and hasattr(self.manager, 'add_message'):
        #     self.manager.add_message("assistant", "supply_manager", player_notification, "supply", from_person="supply_manager", to_person="Player")

        # 2. マネージャーからワーカーへの指示を会話履歴に追加
        task_instruction = self._generate_task_instruction(worker_name, function_name, args)
        if hasattr(self, 'manager') and hasattr(self.manager, 'add_message'):
            self.manager.add_message("user", "supply_manager", task_instruction, "supply", from_person="supply_manager", to_person=worker_name)

        # 3. ワーカーからマネージャーへの承諾を会話履歴に追加
        task_acceptance = self._generate_task_acceptance(worker_name, function_name, args)
        if hasattr(self, 'manager') and hasattr(self.manager, 'add_message'):
            self.manager.add_message("user", worker_name, task_acceptance, "supply", from_person=worker_name, to_person="supply_manager")

        # 4. ワーカーにタスクを依頼
        args["function"] = function_name
        worker_response = worker.start_task(f"{function_name}の実行", args)

        # LLMを使ってPlayerに伝える自然な表現に変換
        return self._convert_to_natural_response(function_name, args, worker_response)

    def _convert_to_natural_response(self, function_name: str, args: Dict, worker_response: str) -> str:
        """ワーカーの応答をPlayerに伝える自然な表現に変換"""
        try:
            client = self.client

            conversion_prompt = f"""
あなたはsupply_managerです。部下に作業を依頼したところ、以下の応答がありました。

タスク: {function_name}
引数: {args}
ワーカーの応答: {worker_response}

この応答をPlayerに伝える際、以下の点に注意してください：
- 技術的な用語（deliver_supplies、procure_suppliesなど）を使わず、自然な日本語に変換
- JSON形式の情報（{"destination":...}など）は一切含めない
- ワーカー名は含めない（「部下が」「担当者が」などで表現）
- 配送の詳細情報は簡潔にまとめる

短く簡潔に、話し言葉で返してください。
"""

            response = client.chat.completions.create(
                model="gpt-5-mini",
                messages=[{"role": "user", "content": conversion_prompt}]
            )

            return response.choices[0].message.content

        except Exception as e:
            # エラーの詳細をログに出力
            print(f"_convert_to_natural_response エラー: {e}")
            return worker_response

    def _generate_completion_summary(self, tool_calls) -> str:
        """実行されたツールの内容をまとめた完了メッセージを生成"""
        try:
            client = self.client

            # ツール実行内容をまとめる
            tasks_summary = []
            for tool_call in tool_calls:
                if tool_call.function.name in ["deliver_supplies", "procure_supplies"]:
                    args = json.loads(tool_call.function.arguments or "{}")

                    if tool_call.function.name == "deliver_supplies":
                        shelter = args.get("shelter_name", "避難所")
                        item = args.get("item_name", "物資")
                        quantity = args.get("quantity", 0)
                        tasks_summary.append(f"{shelter}への{item}{quantity}")
                    elif tool_call.function.name == "procure_supplies":
                        item = args.get("item_name", "物資")
                        quantity = args.get("quantity", 0)
                        tasks_summary.append(f"{item}{quantity}の調達")

            summary_prompt = f"""
あなたはsupply_managerです。以下のタスクを完了しました。

実行したタスク:
{chr(10).join(f"- {task}" for task in tasks_summary)}

Playerに対して、これらのタスクの手配が完了したことを報告する自然な会話メッセージを作成してください。
- 「〜の手配が完了しました」「〜の配送手配が完了しました」のような形で
- 簡潔で話し言葉で作成してください

例：「春日小学校への水100本の配送手配が完了」
"""

            response = client.chat.completions.create(
                model="gpt-5-mini",
                messages=[{"role": "user", "content": summary_prompt}]
            )

            return response.choices[0].message.content

        except Exception:
            return "手配が完了しました。"

    def _process_tool_loop(self, messages: List[Dict], initial_tool_results: List[Dict]) -> str:
        """ループでツール呼び出しを処理（2回目以降対応）"""
        # 最初のツール結果を会話履歴に追加
        messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [tr["tool_call"].model_dump() for tr in initial_tool_results]
        })

        for tr in initial_tool_results:
            messages.append({
                "role": "tool",
                "tool_call_id": tr["tool_call"].id,
                "name": tr["function_name"],
                "content": tr["result"]
            })

        # ループでツール呼び出しを処理
        max_iterations = 5  # 無限ループを防ぐため
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            # LLMに結果を解釈させ、必要に応じて追加ツールを実行
            response = self.client.chat.completions.create(
                model="gpt-5-mini",
                messages=messages,
                tools=self.get_function_definitions(),
                tool_choice="auto"
            )

            message = response.choices[0].message

            # ツール呼び出しがない場合は終了
            if not getattr(message, "tool_calls", None):
                return message.content

            # 実行系ツールがある場合は先にPlayerに一括通知
            execution_tool_calls = [tc for tc in message.tool_calls
                                   if tc.function.name in ["deliver_supplies", "procure_supplies"]]
            if execution_tool_calls:
                # 複数タスクをまとめた通知を生成してPlayerに先に送信
                execution_tasks_preview = []
                for tool_call in execution_tool_calls:
                    args = json.loads(tool_call.function.arguments or "{}")
                    execution_tasks_preview.append({
                        "tool_call": tool_call,
                        "function_name": tool_call.function.name,
                        "result": ""  # まだ実行していないので空
                    })

                combined_notification = self._generate_combined_assignment_notification(execution_tasks_preview)
                if hasattr(self, 'manager') and hasattr(self.manager, 'add_message'):
                    self.manager.add_message("assistant", "supply_manager", combined_notification, "supply", from_person="supply_manager", to_person="Player")

            # ツールを実行
            tool_results = []
            for tool_call in message.tool_calls:
                fname = tool_call.function.name
                args = json.loads(tool_call.function.arguments or "{}")

                tool_result = self.create_tool_response(fname, args)
                tool_results.append(tool_result)

            # 実行系ツールがある場合は完了メッセージを返して終了
            if any(tc.function.name in ["deliver_supplies", "procure_supplies"] for tc in message.tool_calls):
                return self._generate_completion_summary(message.tool_calls)

            # 確認系ツールの場合は会話履歴に追加して継続
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [tc.model_dump() for tc in message.tool_calls]
            })

            for i, tool_call in enumerate(message.tool_calls):
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_call.function.name,
                    "content": tool_results[i]
                })

        # 最大反復回数に達した場合
        return "処理が完了しました。"

    def _generate_combined_assignment_notification(self, execution_tasks: list) -> str:
        """複数のタスクをまとめてPlayerに通知"""
        try:
            client = self.client

            # 実行タスクの情報をまとめる
            tasks_info = []
            for task in execution_tasks:
                tool_call = task["tool_call"]
                args = json.loads(tool_call.function.arguments or "{}")

                if tool_call.function.name == "deliver_supplies":
                    shelter = args.get("shelter_name", "避難所")
                    item = args.get("item_name", "物資")
                    quantity = args.get("quantity", 0)
                    tasks_info.append(f"{shelter}への{item}{quantity}")
                elif tool_call.function.name == "procure_supplies":
                    item = args.get("item_name", "物資")
                    quantity = args.get("quantity", 0)
                    tasks_info.append(f"{item}{quantity}の調達")

            notification_prompt = f"""
あなたはsupply_managerです。以下の複数のタスクを部下に依頼することになり、それをPlayerに報告することになりました。

実行予定のタスク:
{chr(10).join(f"- {task}" for task in tasks_info)}

Playerに対して、これらの作業を今から実行することを報告する自然な返答を作成してください。
- 「部下に〇〇と△△を依頼します」のような形で複数タスクをまとめて表現
- 簡潔で話し言葉で作成してください
"""

            response = client.chat.completions.create(
                model="gpt-5-mini",
                messages=[{"role": "user", "content": notification_prompt}]
            )

            return response.choices[0].message.content

        except Exception:
            # フォールバック
            if len(execution_tasks) == 1:
                return "部下に作業を依頼します。"
            else:
                return f"部下に{len(execution_tasks)}件の作業を依頼します。"

    def _generate_task_instruction(self, worker_name: str, function_name: str, args: Dict) -> str:
        """マネージャーからワーカーへのタスク指示を生成"""
        try:
            client = self.client

            instruction_prompt = f"""
あなたはsupply_managerです。{worker_name}に以下のタスクを依頼してください。

タスク: {function_name}
引数: {args}

{worker_name}に対して、自然な話し言葉でタスクを依頼する短いメッセージを作成してください。
簡潔に。余計なリクエストはせずに。
"""

            response = client.chat.completions.create(
                model="gpt-5-mini",
                messages=[{"role": "user", "content": instruction_prompt}]
            )

            return response.choices[0].message.content

        except Exception as e:
            return f"{worker_name}、{function_name}をお願いします。"

    def _generate_task_acceptance(self, worker_name: str, function_name: str, args: Dict) -> str:
        """ワーカーからマネージャーへのタスク承諾を生成"""
        try:
            client = self.client

            acceptance_prompt = f"""
あなたは{worker_name}です。班長のsupply_managerから以下のタスクを依頼されました。

タスク: {function_name}
引数: {args}

上司に対して、タスクを承諾し、実施することを伝える短いメッセージを作成してください。
部下が上司に返事をする感じで、短く簡潔に、話し言葉で。簡潔に。余計なリクエストはせずに。
"""

            response = client.chat.completions.create(
                model="gpt-5-mini",
                messages=[{"role": "user", "content": acceptance_prompt}]
            )

            return response.choices[0].message.content

        except Exception as e:
            return f"承知しました。{function_name}を実施します。"

    def _execute_manager_task(self, function_name: str, args: Dict) -> str:
        """マネージャー自身がタスクを実行"""
        if function_name == "check_inventory":
            item_name = args.get("item_name", "")
            has_stock, stock, unit = self.inventory_tool.check_inventory(item_name)
            if has_stock:
                return f"（マネージャー自身で確認）{item_name}の在庫は{stock}{unit}あります。"
            else:
                return f"（マネージャー自身で確認）{item_name}は在庫切れです。"

        elif function_name == "deliver_supplies":
            self.pending_delivery = args
            return self.execute_task_with_delay("物資配送", args)

        elif function_name == "show_inventory":
            return f"（マネージャー自身で確認）{self.inventory_tool.get_inventory_summary()}"

        elif function_name == "show_delivery_log":
            shelter_name = args.get("shelter_name", "")
            try:
                logs = []
                with open(self.delivery_log_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if not shelter_name or shelter_name in row.get('避難所名', ''):
                            logs.append(f"{row.get('避難所名', '')}: {row.get('物資名', '')} {row.get('数量', '')}{row.get('単位', '')}")

                if logs:
                    if shelter_name:
                        return f"（マネージャー自身で確認）{shelter_name}への配送記録:\n" + "\n".join(logs[-10:])
                    else:
                        return f"（マネージャー自身で確認）配送記録:\n" + "\n".join(logs[-10:])
                else:
                    return f"（マネージャー自身で確認）配送記録が見つかりません。"
            except Exception:
                return f"（マネージャー自身で確認）配送記録の読み込みに失敗しました。"

        elif function_name == "procure_supplies":
            self.pending_procurement = args
            return self.execute_task_with_delay("物資調達", args)

        return "マネージャーが実行できないタスクです。"

    def execute_task_with_delay(self, task_name: str, args: Dict = None) -> str:
        """タスクを実行し、10分後の戻り時刻を設定"""
        current_time = datetime.strptime(self.time_manager.get_current_time(), "%H:%M")
        return_time = current_time + timedelta(minutes=10)
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

                has_stock, stock, unit = self.inventory_tool.check_inventory(item)
                if has_stock and stock >= quantity:
                    # 在庫を減らす
                    if self.inventory_tool.update_inventory(item, quantity):
                        # 配送記録を追加
                        self.inventory_tool.record_delivery(shelter, item, quantity, unit)
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
                if self.inventory_tool.add_inventory(item_name, quantity):
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

            manager_return_message = manager_completion_message

            self.away_until_time = None
            self.current_task_description = None
        else:
            manager_return_message = None

        # ワーカーのタスク完了チェック
        completed_workers = self._check_worker_completions()
        if completed_workers:
            # 各ワーカーの完了報告を処理
            for worker_result in completed_workers:
                worker_name = worker_result["worker_name"]
                worker_report = worker_result["report"]

                # マネージャーがWorkerの報告を見て、Playerに報告すべきか判断
                manager_response, response_to, needs_additional_task = self._process_worker_report(worker_name, worker_report)

                # 追加タスクが必要な場合、ツールを使って決定する
                if needs_additional_task:
                    # 会話履歴とワーカー報告を元に、次のタスクを決定
                    additional_task_prompt = f"""
あなたはsupply_managerです。{worker_name}の作業完了報告を受けて、追加タスクが必要と判断しました。

理由: {manager_response}

最近の会話履歴とワーカーの報告を踏まえて、次に実行すべきタスクを選択してください。
適切なワーカーも指定してください（空いているワーカーを選ぶか、全員忙しければマネージャー自身）。
"""
                    # 追加タスクを決定するためのメッセージ構築
                    messages = [
                        {"role": "system", "content": self.build_system_prompt()},
                        {"role": "user", "content": additional_task_prompt}
                    ]

                    # ツールを使って追加タスクを決定
                    try:
                        task_response = self.client.chat.completions.create(
                            model="gpt-5-mini",
                            messages=messages,
                            tools=self.get_function_definitions(),
                            tool_choice="auto"
                        )

                        task_message = task_response.choices[0].message

                        # ツール呼び出しがあれば実行
                        if getattr(task_message, "tool_calls", None):
                            tool_call = task_message.tool_calls[0]
                            fname = tool_call.function.name
                            args = json.loads(tool_call.function.arguments or "{}")

                            # 追加タスクを実行
                            tool_result = self.create_tool_response(fname, args)

                            # Playerに追加タスクの実行を報告
                            manager_response = f"{worker_name}の完了報告を受けて、{tool_result}"
                            response_to = "Player"
                        else:
                            # ツールが選択されなかった場合
                            manager_response = f"{worker_name}の作業が完了しました。{manager_response}"
                            response_to = "Player"
                    except Exception:
                        # エラー時はそのまま報告
                        response_to = "Player"

                # 注意: manager_responseは戻り値として返され、chat.pyで履歴に追加される

                all_completed_tasks.append({
                    "worker_name": worker_name,
                    "report": worker_report,
                    "manager_response": manager_response,
                    "response_to": response_to  # 宛先情報を追加
                })

        # マネージャー自身のタスク完了報告
        if manager_return_message and all_completed_tasks:
            # マネージャー自身とワーカーの両方が完了した場合、まとめて報告
            return {
                "message": f"{manager_return_message}\n\n{all_completed_tasks[0]['manager_response']}",
                "to": all_completed_tasks[0]['response_to']
            }
        elif manager_return_message:
            return {"message": manager_return_message, "to": "Player"}
        elif all_completed_tasks:
            # ワーカーのタスクのみ完了した場合、最後のマネージャー応答を返す
            return {
                "message": all_completed_tasks[-1]['manager_response'],
                "to": all_completed_tasks[-1]['response_to']
            }

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

    def _process_worker_report(self, worker_name: str, worker_report: str) -> tuple[str, str, bool]:
        """Workerの完了報告を処理し、Playerへの報告または次のアクションを決定

        Returns:
            tuple[str, str, bool]: (応答メッセージ, 宛先, 追加タスクが必要か)
        """
        try:
            client = self.client

            # 現在の会話履歴を取得（最近の20件程度）
            if hasattr(self, 'manager'):
                recent_history = self.manager.get_conversation_history("supply")[-20:]
                history_text = "\n".join([f"{msg.get('name', msg['role'])}: {msg['content']}" for msg in recent_history])
            else:
                history_text = "（会話履歴なし）"

            process_prompt = f"""
あなたはsupply_managerです。{worker_name}から作業完了の報告を受けました。

【最近の会話履歴】
{history_text}

【{worker_name}からの報告】
{worker_report}

この報告を受けて、あなたは以下のいずれかの対応を取ります：

1. **Playerに報告する**: タスクが成功した場合、またはPlayerの判断が必要な場合
   → 最初の行に「[TO:Player]」と書き、次の行から「〜の作業が完了しました」のように状況を報告してください

   特に重要：在庫不足の報告があった場合は必ずPlayerに報告してください。
   - 「在庫不足」「在庫が完全にありません」「在庫が〜しかありません」などの文言が含まれる場合
   - 「配送できませんでした」「配送に失敗」などの文言が含まれる場合

2. **追加タスクが必要な場合**: 報告内容から追加作業が必要と判断した場合
   → 最初の行に「[ADDITIONAL_TASK:必要]」と書き、次の行から追加タスクの理由を説明してください

   追加タスクが必要な例：
   - 配送完了後、他の避難所にも同じ物資が必要な場合
   - 在庫が少なくなったため調達が必要な場合
   - 関連する別の作業が必要な場合

   ※ただし、在庫不足の場合は追加タスクではなくPlayerへの報告を優先してください

重要: 必ず最初の行に「[TO:Player]」または「[ADDITIONAL_TASK:必要]」のいずれかを明記してください。
在庫不足の場合は必ず「[TO:Player]」を選択してください。

重要: - 詳細情報は簡潔にまとめる
短く簡潔に、話し言葉で返してください。余計なリクエストはせずに。
"""

            response = client.chat.completions.create(
                model="gpt-5-mini",
                messages=[{"role": "user", "content": process_prompt}]
            )

            response_text = response.choices[0].message.content

            # 宛先を解析
            lines = response_text.strip().split('\n')
            needs_additional_task = False

            if lines and lines[0].startswith('[TO:Player]'):
                to_person = "Player"
                message = '\n'.join(lines[1:]).strip()
            elif lines and lines[0].startswith('[ADDITIONAL_TASK:'):
                needs_additional_task = True
                to_person = "Player"  # デフォルトはPlayerに報告
                message = '\n'.join(lines[1:]).strip()
            else:
                # デフォルトはPlayer
                to_person = "Player"
                message = response_text

            return message, to_person, needs_additional_task

        except Exception:
            return f"{worker_name}からの報告を確認しました。Playerに状況を報告します。", "Player", False

    def _generate_thank_you_message(self, worker_name: str, worker_report: str) -> str:
        """ワーカーの完了報告に対するマネージャーの感謝メッセージを生成"""
        try:
            client = self.client

            thank_you_prompt = f"""
あなたはsupply_managerです。{worker_name}から以下の完了報告を受けました。

ワーカーからの報告:
{worker_report}

{worker_name}に対して、感謝の気持ちを表す短いメッセージを作成してください。
上司が部下の報告に対して返事をする感じで、簡潔に「ありがとう」的な内容を。
"""

            response = client.chat.completions.create(
                model="gpt-5-mini",
                messages=[{"role": "user", "content": thank_you_prompt}]
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
                model="gpt-5-mini",
                messages=[{"role": "user", "content": completion_prompt}]
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
                model="gpt-5-mini",
                messages=[{"role": "user", "content": completion_prompt}]
            )

            return response.choices[0].message.content

        except Exception as e:
            # フォールバック
            task_descriptions = [result["task"] for result in completed_tasks]
            return f"作業が完了しました。{', '.join(task_descriptions)}が終わりました。"

    def get_function_definitions(self) -> List[Dict]:
        """Function calling用の定義を取得"""
        defs = []

        # 在庫確認（マネージャー専用）
        defs.append({
            "type": "function",
            "function": {
                "name": "check_inventory",
                "description": "特定の物資の在庫数を確認する。マネージャー自身が実行。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "item_name": {"type": "string", "description": "確認する物資名"}
                    },
                    "required": ["item_name"]
                }
            }
        })

        # 物資配送（ワーカー指定可能）
        defs.append({
            "type": "function",
            "function": {
                "name": "deliver_supplies",
                "description": "避難所に物資を配送する。重要：このツールは在庫確認して報告した後にのみ使用してください。在庫不足の場合は配送されません。会話履歴から空いているワーカーを判断してタスクを依頼する。全員忙しい場合はマネージャー自身が実行。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "shelter_name": {"type": "string", "description": "配送先の避難所名"},
                        "item_name": {"type": "string", "description": "配送する物資名"},
                        "quantity": {"type": "integer", "description": "配送数量"},
                        "assigned_worker": {"type": "string", "description": "タスクを依頼するワーカー名（会話履歴から空いているワーカーを選択）", "enum": ["物資ワーカーA", "物資ワーカーB", "物資ワーカーC", "マネージャー自身"]}
                    },
                    "required": ["shelter_name", "item_name", "quantity", "assigned_worker"]
                }
            }
        })

        # 在庫一覧表示（マネージャー専用）
        defs.append({
            "type": "function",
            "function": {
                "name": "show_inventory",
                "description": "現在の在庫一覧を表示する。マネージャー自身が実行。",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        })

        # 配送記録確認（マネージャー専用）
        defs.append({
            "type": "function",
            "function": {
                "name": "show_delivery_log",
                "description": "配送記録を確認する。マネージャー自身が実行。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "shelter_name": {"type": "string", "description": "特定の避難所の記録のみ表示（任意）"}
                    },
                    "required": []
                }
            }
        })

        # 物資調達（ワーカー指定可能）
        defs.append({
            "type": "function",
            "function": {
                "name": "procure_supplies",
                "description": "物資を調達して在庫に追加する。会話履歴から空いているワーカーを判断してタスクを依頼する。全員忙しい場合はマネージャー自身が実行。このツールを実行した場合、Playerへの報告は関数内で自動的に行われるため、追加の会話応答は不要。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "item_name": {"type": "string", "description": "調達する物資名"},
                        "quantity": {"type": "integer", "description": "調達数量"},
                        "assigned_worker": {"type": "string", "description": "タスクを依頼するワーカー名（会話履歴から空いているワーカーを選択）", "enum": ["物資ワーカーA", "物資ワーカーB", "物資ワーカーC", "マネージャー自身"]}
                    },
                    "required": ["item_name", "quantity", "assigned_worker"]
                }
            }
        })

        return defs

    def process_response(self, messages: List[Dict[str, str]]) -> tuple[str, str]:
        """OpenAI APIレスポンスを処理"""
        response = self.client.chat.completions.create(
            model="gpt-5-mini",
            messages=messages,
            tools=self.get_function_definitions(),
            tool_choice="auto"
        )

        response_message = response.choices[0].message

        # ツール呼び出しがあれば実行（複数対応）
        if getattr(response_message, "tool_calls", None):
            tool_results = []
            combined_messages = []

            # 実行系ツールがある場合は先にPlayerに一括通知
            execution_tool_calls = [tc for tc in response_message.tool_calls
                                   if tc.function.name in ["deliver_supplies", "procure_supplies"]]
            if execution_tool_calls:
                # 複数タスクをまとめた通知を生成してPlayerに先に送信
                execution_tasks_preview = []
                for tool_call in execution_tool_calls:
                    args = json.loads(tool_call.function.arguments or "{}")
                    execution_tasks_preview.append({
                        "tool_call": tool_call,
                        "function_name": tool_call.function.name,
                        "result": ""  # まだ実行していないので空
                    })

                combined_notification = self._generate_combined_assignment_notification(execution_tasks_preview)
                if hasattr(self, 'manager') and hasattr(self.manager, 'add_message'):
                    self.manager.add_message("assistant", "supply_manager", combined_notification, "supply", from_person="supply_manager", to_person="Player")

            # 複数のツール呼び出しを順次処理
            for tool_call in response_message.tool_calls:
                fname = tool_call.function.name
                args = json.loads(tool_call.function.arguments or "{}")

                if fname:
                    tool_result = self.create_tool_response(fname, args)
                    tool_results.append({
                        "tool_call": tool_call,
                        "function_name": fname,
                        "result": tool_result
                    })

            # 複数のツール結果を処理
            if tool_results:
                # 確認系と実行系が混在する可能性があるため、適切に処理
                has_confirmation_tools = any(tr["function_name"] in ["check_inventory", "show_inventory", "show_delivery_log"] for tr in tool_results)
                has_execution_tools = any(tr["function_name"] in ["deliver_supplies", "procure_supplies"] for tr in tool_results)

                if has_execution_tools:
                    # 実行系ツールがある場合
                    execution_tasks = [tr for tr in tool_results if tr["function_name"] in ["deliver_supplies", "procure_supplies"]]

                    # 実行系ツールの結果をまとめて返す TODO 
                    # （Playerへの通知は既に送信されているが、空を返すとUIで問題が生じる）
                    results = [tr["result"] for tr in execution_tasks if tr["result"]]
                    assistant_message = results[0] if results else "手配を進めています。"

                elif has_confirmation_tools:
                    # 確認系のみの場合は、ループでツール呼び出しを処理
                    assistant_message = self._process_tool_loop(messages, tool_results)
                else:
                    # その他の場合
                    assistant_message = "\n\n".join([tr["result"] for tr in tool_results])
            else:
                assistant_message = "no_tool"
        else:
            assistant_message = response_message.content

        return assistant_message, "supply_manager"

    def handle_system_information(self, source: str, info_data) -> str:
        """情報を受け取り、Playerに報告と指示要請を生成（単一・複数対応）"""
        try:
            client = self.client

            # info_dataが文字列（単一）かリスト（複数）かを判定
            if isinstance(info_data, list):
                # 複数の情報の場合
                info_summary = []
                for info in info_data:
                    info_summary.append(f"・{info.subject}: {info.content}")
                info_text = "\n".join(info_summary)

                prompt = f"""
あなたはsupply_managerです。{source}から複数の情報を受け取りました。

{info_text}

これらの情報をPlayerに報告してください。
- 情報の要点を簡潔に伝える
- 指示要請や対応案は含めない
- 話し言葉で、自然に
"""
            else:
                # 単一の情報の場合（従来通り）
                subject, content = info_data
                prompt = f"""
あなたはsupply_managerです。{source}から以下の情報を受け取りました。

件名: {subject}
内容: {content}

この情報をPlayerに報告してください。
- 情報の要点を簡潔に伝える
- 指示要請や対応案は含めない
- 話し言葉で、自然に
"""

            response = client.chat.completions.create(
                model="gpt-5-mini",
                messages=[{"role": "user", "content": prompt}]
            )

            return response.choices[0].message.content

        except Exception as e:
            return f"{source}から情報を受け取りました。対応について指示をお願いします。"