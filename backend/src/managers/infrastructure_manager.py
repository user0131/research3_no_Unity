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
from workers.infrastructure_worker import InfrastructureWorker
from tools.infrastructure_task import InfrastructureInspectionTool


class InfrastructureManager:
    """建物・産業・土木対策担当者クラス"""

    def __init__(self, client: OpenAI, time_manager):
        self.client = client
        self.knowledge_path = Path("./src/knowledge/knowledge_infrastructure.txt")
        self.time_manager = time_manager
        self.in_conversation = False
        self.away_until_time = None
        self.current_task_description = None
        self.pending_inspection = None
        self.pending_restoration = None

        # CSVファイルのパス（infrastructureフォルダ内）
        self.damage_report_path = Path("./csv/infrastructure/被害調査報告.csv")
        self.restoration_log_path = Path("./csv/infrastructure/復旧作業記録.csv")

        # 初期化時にCSVを作成
        self._initialize_infrastructure()

        # 調査ツールを初期化
        self.inspection_tool = InfrastructureInspectionTool(time_manager)

        # 3人のワーカーを初期化
        self.workers = {
            "worker_a": InfrastructureWorker("土木ワーカーA", self, time_manager),
            "worker_b": InfrastructureWorker("土木ワーカーB", self, time_manager),
            "worker_c": InfrastructureWorker("土木ワーカーC", self, time_manager)
        }

    def _initialize_infrastructure(self):
        """初期CSVデータを作成"""
        # csvディレクトリが存在しない場合は作成
        self.damage_report_path.parent.mkdir(parents=True, exist_ok=True)

        # 被害調査報告CSVが存在しない場合は作成
        if not self.damage_report_path.exists():
            with open(self.damage_report_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['施設種別', '被害程度', '被害詳細', '対応状況', '備考'])
            print(f"被害調査報告.csvを作成しました")

        # 復旧作業記録CSVが存在しない場合は作成
        if not self.restoration_log_path.exists():
            with open(self.restoration_log_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['作業種別', '作業内容', '完了状況', '備考'])
            print(f"復旧作業記録.csvを作成しました")

    def build_system_prompt(self) -> str:
        """システムプロンプトを構築"""
        knowledge_content = self.get_knowledge()
        workers_status = self._get_workers_status()

        return f"""
あなたは"Player"と一緒に災害対応の仕事を行う災害対応職員です。あなたは建物・産業・土木対策担当の職員です。あなたは"infrastructure_manager"です。
地震を想定した避難訓練を"Player"と行っています。

## 災害対応ルール：
- **会話スタイル**: 同僚との自然な会話を心がける。まずは普通に話す。情報の羅列や箇条書きは禁止。話し言葉で応答。あなたは相手の話を聞き、簡潔に返答します。ユーザに聞かれたこと以外は極力返さないように。
- **情報の扱い**: あなたの知っている情報は会話履歴と「あなたが知っている知識」のみです。手持ちにない情報の推測や憶測は避けてください
- **作業依頼**: Playerから明確に、具体的に何かの作業を頼まれた場合のみ、作業を実行してください。それ以外は通常の会話をしてください。
- **重要：現場確認と承認プロセス**:
  - **作業前の必須確認**: 復旧作業を依頼された場合、まず必ずinspect_damageツールで被害状況を確認し、Playerに現在の状況を報告してください
  - **危険箇所の対応**: 危険度が高い場所については、必ずPlayerに報告して対応方針を相談してください
  - **承認後の作業**: Playerから明確な指示を受けた後にのみ、復旧作業ツールを使用してください
- **重要：ツールの使用**: 実際の作業は必ずツールを使って実行してください。会話（テキスト応答）では作業を実行できません。
  - **現場確認**: inspect_damageツールを使用（道路、橋、公園、河川等の調査）
  - **道路確保**: secure_roadツールを使用（道路啓開・確保作業）
  - **応急復旧**: emergency_restorationツールを使用（応急復旧作業）
  - **廃棄物処理**: handle_debrisツールを使用（災害廃棄物等処理）
  - **調査記録確認**: show_damage_reportツールを使用（被害調査記録の確認）
  - **復旧記録確認**: show_restoration_logツールを使用（復旧作業記録の確認）
- **ワーカー情報の非開示**: ワーカーA、ワーカーB、ワーカーCといった具体的なワーカー名や、誰が作業をするかの詳細をPlayerに伝える必要はありません。あなたが内部的に判断して「手配します」「対応します」のように伝えてください。

## 重要
- 極力あなた(infrastructure_manager)自身が作業を行うことは避けてください。workerの手が空いていない場合は、Playerにそのことを伝え、それでもやってほしいと頼まれた場合にあなた自身が作業をしてください。
- ユーザに聞かれたこと以外は極力返さないように。

## Playerに無理に開示しなくて大丈夫な情報：
以下の情報は、あなたが内部的に判断するために使用します。Playerに対しては詳細を説明する必要はありません。

### 現在のワーカー(部下の)状況（この情報はPlayerに伝えない）
{workers_status}

Playerに対しては「手配します」「対応します」のように、ワーカー名を出さずに伝えてください。

## あなたが知っている知識
{knowledge_content if knowledge_content.strip() else "まだ知識がありません。"}

## これまでの会話履歴
以下に続くメッセージは、Playerとあなた(infrastructure_manager)のこれまでの会話履歴です。
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
        """ツール実行をknowledge_infrastructure.txtに記録"""
        try:
            current_time = self.time_manager.get_current_time()

            # 引数を整理して記録用テキストを作成
            args_text = ""
            if tool_name == "inspect_damage":
                location = args.get("location", "")
                facility_type = args.get("facility_type", "")
                args_text = f"場所: {location}, 施設種別: {facility_type}"
            elif tool_name == "secure_road":
                location = args.get("location", "")
                worker = args.get("assigned_worker", "")
                args_text = f"場所: {location}, 担当: {worker}"
            elif tool_name == "emergency_restoration":
                location = args.get("location", "")
                work_type = args.get("work_type", "")
                worker = args.get("assigned_worker", "")
                args_text = f"場所: {location}, 作業: {work_type}, 担当: {worker}"
            elif tool_name == "handle_debris":
                location = args.get("location", "")
                debris_type = args.get("debris_type", "")
                worker = args.get("assigned_worker", "")
                args_text = f"場所: {location}, 種別: {debris_type}, 担当: {worker}"
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
        if tool_name == "show_damage_report":
            return self._execute_manager_task("show_damage_report", args)

        elif tool_name == "show_restoration_log":
            return self._execute_manager_task("show_restoration_log", args)

        # 実行系（ワーカー指定可能）
        elif tool_name == "inspect_damage":
            return self._handle_task_assignment("inspect_damage", args)

        elif tool_name == "secure_road":
            return self._handle_task_assignment("secure_road", args)

        elif tool_name == "emergency_restoration":
            return self._handle_task_assignment("emergency_restoration", args)

        elif tool_name == "handle_debris":
            return self._handle_task_assignment("handle_debris", args)

        else:
            return "未対応のツールが呼ばれました。"

    def _handle_task_assignment(self, function_name: str, args: Dict) -> str:
        """タスク割り当てを処理"""
        assigned_worker = args.get("assigned_worker")

        if assigned_worker == "マネージャー自身":
            return self._execute_manager_task(function_name, args)
        else:
            return self._assign_specific_worker_task(assigned_worker, function_name, args)

    def _assign_specific_worker_task(self, worker_name: str, function_name: str, args: Dict) -> str:
        """指定されたワーカーにタスクを依頼"""
        worker_key_map = {
            "土木ワーカーA": "worker_a",
            "土木ワーカーB": "worker_b",
            "土木ワーカーC": "worker_c"
        }

        worker_key = worker_key_map.get(worker_name)
        if not worker_key or worker_key not in self.workers:
            return f"{worker_name}が見つかりません。"

        worker = self.workers[worker_key]

        if worker.is_busy:
            return f"{worker_name}は現在作業中です。他のワーカーを選択するか、マネージャー自身で実行してください。"

        # マネージャーからワーカーへの指示を会話履歴に追加
        task_instruction = self._generate_task_instruction(worker_name, function_name, args)
        if hasattr(self, 'manager') and hasattr(self.manager, 'add_message'):
            self.manager.add_message("user", "infrastructure_manager", task_instruction, "infrastructure",
                                   from_person="infrastructure_manager", to_person=worker_name)

        # ワーカーからマネージャーへの承諾を会話履歴に追加
        task_acceptance = self._generate_task_acceptance(worker_name, function_name, args)
        if hasattr(self, 'manager') and hasattr(self.manager, 'add_message'):
            self.manager.add_message("user", worker_name, task_acceptance, "infrastructure",
                                   from_person=worker_name, to_person="infrastructure_manager")

        # ワーカーにタスクを依頼
        args["function"] = function_name
        worker_response = worker.start_task(f"{function_name}の実行", args)

        return self._convert_to_natural_response(function_name, args, worker_response)

    def _convert_to_natural_response(self, function_name: str, args: Dict, worker_response: str) -> str:
        """ワーカーの応答をPlayerに伝える自然な表現に変換"""
        try:
            client = self.client

            conversion_prompt = f"""
あなたはinfrastructure_managerです。部下に作業を依頼したところ、以下の応答がありました。

タスク: {function_name}
引数: {args}
ワーカーの応答: {worker_response}

この応答をPlayerに伝える際、以下の点に注意してください：
- 技術的な用語を使わず、自然な日本語に変換
- JSON形式の情報は一切含めない
- ワーカー名は含めない（「部下が」「担当者が」などで表現）
- 作業の詳細情報は簡潔にまとめる

短く簡潔に、話し言葉で返してください。
"""

            response = client.chat.completions.create(
                model="gpt-5-mini",
                messages=[{"role": "user", "content": conversion_prompt}]
            )

            return response.choices[0].message.content

        except Exception as e:
            print(f"_convert_to_natural_response エラー: {e}")
            return worker_response

    def _generate_task_instruction(self, worker_name: str, function_name: str, args: Dict) -> str:
        """マネージャーからワーカーへのタスク指示を生成"""
        try:
            client = self.client

            instruction_prompt = f"""
あなたはinfrastructure_managerです。{worker_name}に以下のタスクを依頼してください。

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

        except Exception:
            return f"{worker_name}、{function_name}をお願いします。"

    def _generate_task_acceptance(self, worker_name: str, function_name: str, args: Dict) -> str:
        """ワーカーからマネージャーへのタスク承諾を生成"""
        try:
            client = self.client

            acceptance_prompt = f"""
あなたは{worker_name}です。班長のinfrastructure_managerから以下のタスクを依頼されました。

タスク: {function_name}
引数: {args}

上司に対して、タスクを承諾し、実施することを伝える短いメッセージを作成してください。
部下が上司に返事をする感じで、短く簡潔に、話し言葉で。
"""

            response = client.chat.completions.create(
                model="gpt-5-mini",
                messages=[{"role": "user", "content": acceptance_prompt}]
            )

            return response.choices[0].message.content

        except Exception:
            return f"承知しました。{function_name}を実施します。"

    def _execute_manager_task(self, function_name: str, args: Dict) -> str:
        """マネージャー自身がタスクを実行"""
        if function_name == "inspect_damage":
            self.pending_inspection = args
            return self.execute_task_with_delay("被害調査", args)

        elif function_name == "show_damage_report":
            return self._show_damage_report()

        elif function_name == "show_restoration_log":
            return self._show_restoration_log()

        elif function_name == "secure_road":
            self.pending_inspection = args
            return self.execute_task_with_delay("道路確保作業", args)

        elif function_name == "emergency_restoration":
            self.pending_restoration = args
            return self.execute_task_with_delay("応急復旧作業", args)

        elif function_name == "handle_debris":
            self.pending_restoration = args
            return self.execute_task_with_delay("廃棄物処理作業", args)

        return "マネージャーが実行できないタスクです。"

    def _show_damage_report(self) -> str:
        """被害調査報告を表示"""
        try:
            reports = []
            with open(self.damage_report_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    reports.append(f"{row.get('場所', '')}: {row.get('施設種別', '')} - {row.get('被害状況', '')} (危険度: {row.get('危険度', '')})")

            if reports:
                return f"（マネージャー自身で確認）被害調査報告:\n" + "\n".join(reports[-10:])
            else:
                return f"（マネージャー自身で確認）被害調査報告がまだありません。"
        except Exception:
            return f"（マネージャー自身で確認）被害調査報告の読み込みに失敗しました。"

    def _show_restoration_log(self) -> str:
        """復旧作業記録を表示"""
        try:
            logs = []
            with open(self.restoration_log_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    logs.append(f"{row.get('場所', '')}: {row.get('作業種別', '')} - {row.get('完了状況', '')}")

            if logs:
                return f"（マネージャー自身で確認）復旧作業記録:\n" + "\n".join(logs[-10:])
            else:
                return f"（マネージャー自身で確認）復旧作業記録がまだありません。"
        except Exception:
            return f"（マネージャー自身で確認）復旧作業記録の読み込みに失敗しました。"

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
        """タスクから戻った際の処理"""
        # ワーカーのタスク完了チェック
        completed_workers = self._check_worker_completions()
        if completed_workers:
            for worker_result in completed_workers:
                worker_name = worker_result["worker_name"]
                worker_report = worker_result["report"]

                # マネージャーがWorkerの報告を見て、Playerに報告
                manager_response = self._process_worker_report(worker_name, worker_report)

                return {"message": manager_response, "to": "Player"}

        return None

    def _check_worker_completions(self) -> List[Dict[str, Any]]:
        """ワーカーのタスク完了をチェック"""
        completed_results = []

        for worker in self.workers.values():
            if worker.check_task_completion():
                result = worker.complete_task()
                if result["success"]:
                    completed_results.append(result)

        return completed_results

    def _generate_manager_completion_message(self, task_name: str, task_result: Dict[str, Any]) -> str:
        """マネージャー自身のタスク完了時のつぶやきメッセージを生成"""
        try:
            client = self.client

            completion_prompt = f"""
あなたはinfrastructure_managerです。自分で以下のタスクを完了しました。

完了したタスク: {task_name}
結果: {task_result.get('message', '完了')}
成功: {task_result.get('success', True)}

自分がタスクを完了した時の自然なつぶやきメッセージを作成してください。
「よし、～完了」や「～が終わった」のような感じで、短くて自然に。
"""

            response = client.chat.completions.create(
                model="gpt-5-mini",
                messages=[{"role": "user", "content": completion_prompt}]
            )

            return response.choices[0].message.content

        except Exception:
            return f"よし、私の{task_name}完了。"

    def _process_worker_report(self, worker_name: str, worker_report: str) -> str:
        """Workerの完了報告を処理"""
        try:
            client = self.client

            process_prompt = f"""
あなたはinfrastructure_managerです。{worker_name}から作業完了の報告を受けました。

報告内容: {worker_report}

Playerに対して、この作業完了を報告する簡潔なメッセージを作成してください。
話し言葉で、短く簡潔に。
"""

            response = client.chat.completions.create(
                model="gpt-5-mini",
                messages=[{"role": "user", "content": process_prompt}]
            )

            return response.choices[0].message.content

        except Exception:
            return f"{worker_name}の作業が完了しました。"

    def get_function_definitions(self) -> List[Dict]:
        """Function calling用の定義を取得"""
        defs = []

        # 現場確認（ワーカー指定可能）
        defs.append({
            "type": "function",
            "function": {
                "name": "inspect_damage",
                "description": "道路、橋りょう、公園、河川等の土木施設の被害調査を行う。会話履歴から空いているワーカーを判断してタスクを依頼する。全員忙しい場合はマネージャー自身が実行。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "調査場所"},
                        "facility_type": {"type": "string", "description": "施設種別（道路、橋、公園、河川、土砂災害危険箇所等）"},
                        "assigned_worker": {"type": "string", "description": "タスクを依頼するワーカー名（会話履歴から空いているワーカーを選択）", "enum": ["土木ワーカーA", "土木ワーカーB", "土木ワーカーC", "マネージャー自身"]}
                    },
                    "required": ["location", "facility_type", "assigned_worker"]
                }
            }
        })

        # 道路確保（ワーカー指定可能）
        defs.append({
            "type": "function",
            "function": {
                "name": "secure_road",
                "description": "道路啓開・確保作業を実施する。重要：現場確認後にのみ使用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "作業場所"},
                        "assigned_worker": {"type": "string", "description": "タスクを依頼するワーカー名（会話履歴から空いているワーカーを選択）", "enum": ["土木ワーカーA", "土木ワーカーB", "土木ワーカーC", "マネージャー自身"]}
                    },
                    "required": ["location", "assigned_worker"]
                }
            }
        })

        # 応急復旧（ワーカー指定可能）
        defs.append({
            "type": "function",
            "function": {
                "name": "emergency_restoration",
                "description": "土木施設の応急復旧作業を実施する。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "作業場所"},
                        "work_type": {"type": "string", "description": "作業種別（道路補修、橋梁応急処置、河川護岸補修等）"},
                        "assigned_worker": {"type": "string", "description": "タスクを依頼するワーカー名（会話履歴から空いているワーカーを選択）", "enum": ["土木ワーカーA", "土木ワーカーB", "土木ワーカーC", "マネージャー自身"]}
                    },
                    "required": ["location", "work_type", "assigned_worker"]
                }
            }
        })

        # 廃棄物処理（ワーカー指定可能）
        defs.append({
            "type": "function",
            "function": {
                "name": "handle_debris",
                "description": "災害廃棄物等の処理作業を実施する。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "作業場所"},
                        "debris_type": {"type": "string", "description": "廃棄物種別（がれき、土砂、倒木等）"},
                        "assigned_worker": {"type": "string", "description": "タスクを依頼するワーカー名（会話履歴から空いているワーカーを選択）", "enum": ["土木ワーカーA", "土木ワーカーB", "土木ワーカーC", "マネージャー自身"]}
                    },
                    "required": ["location", "debris_type", "assigned_worker"]
                }
            }
        })

        # 被害調査報告確認（マネージャー専用）
        defs.append({
            "type": "function",
            "function": {
                "name": "show_damage_report",
                "description": "被害調査報告を確認する。マネージャー自身が実行。",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        })

        # 復旧作業記録確認（マネージャー専用）
        defs.append({
            "type": "function",
            "function": {
                "name": "show_restoration_log",
                "description": "復旧作業記録を確認する。マネージャー自身が実行。",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        })

        return defs

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
                return message.content if message.content else ""

            # 実行系ツールがある場合は先にPlayerに一括通知
            execution_tool_calls = [tc for tc in message.tool_calls
                                   if tc.function.name in ["inspect_damage", "secure_road", "emergency_restoration", "handle_debris"]]
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
                    self.manager.add_message("assistant", "infrastructure_manager", combined_notification, "infrastructure", from_person="infrastructure_manager", to_person="Player")

            # ツールを実行
            tool_results = []
            for tool_call in message.tool_calls:
                fname = tool_call.function.name
                args = json.loads(tool_call.function.arguments or "{}")

                tool_result = self.create_tool_response(fname, args)
                tool_results.append(tool_result)

            # 実行系ツールがある場合は完了メッセージを返して終了
            if any(tc.function.name in ["inspect_damage", "secure_road", "emergency_restoration", "handle_debris"] for tc in message.tool_calls):
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

                if tool_call.function.name == "inspect_damage":
                    location = args.get("location", "場所")
                    facility_type = args.get("facility_type", "施設")
                    tasks_info.append(f"{location}の{facility_type}調査")
                elif tool_call.function.name == "secure_road":
                    location = args.get("location", "場所")
                    tasks_info.append(f"{location}の道路確保")
                elif tool_call.function.name == "emergency_restoration":
                    location = args.get("location", "場所")
                    work_type = args.get("work_type", "作業")
                    tasks_info.append(f"{location}の{work_type}")
                elif tool_call.function.name == "handle_debris":
                    location = args.get("location", "場所")
                    debris_type = args.get("debris_type", "廃棄物")
                    tasks_info.append(f"{location}の{debris_type}処理")

            notification_prompt = f"""
あなたはinfrastructure_managerです。以下の複数のタスクを部下に依頼することになり、それをPlayerに報告することになりました。

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

    def _generate_completion_summary(self, tool_calls) -> str:
        """実行されたツールの内容をまとめた完了メッセージを生成"""
        try:
            client = self.client

            # ツール実行内容をまとめる
            tasks_summary = []
            for tool_call in tool_calls:
                if tool_call.function.name in ["inspect_damage", "secure_road", "emergency_restoration", "handle_debris"]:
                    args = json.loads(tool_call.function.arguments or "{}")

                    if tool_call.function.name == "inspect_damage":
                        location = args.get("location", "場所")
                        facility_type = args.get("facility_type", "施設")
                        tasks_summary.append(f"{location}の{facility_type}調査")
                    elif tool_call.function.name == "secure_road":
                        location = args.get("location", "場所")
                        tasks_summary.append(f"{location}の道路確保")
                    elif tool_call.function.name == "emergency_restoration":
                        location = args.get("location", "場所")
                        work_type = args.get("work_type", "作業")
                        tasks_summary.append(f"{location}の{work_type}")
                    elif tool_call.function.name == "handle_debris":
                        location = args.get("location", "場所")
                        debris_type = args.get("debris_type", "廃棄物")
                        tasks_summary.append(f"{location}の{debris_type}処理")

            summary_prompt = f"""
あなたはinfrastructure_managerです。以下のタスクを完了しました。

実行したタスク:
{chr(10).join(f"- {task}" for task in tasks_summary)}

Playerに対して、これらのタスクの手配が完了したことを報告する自然な会話メッセージを作成してください。
- 「～の手配が完了しました」のような形で
- 簡潔で話し言葉で作成してください
"""

            response = client.chat.completions.create(
                model="gpt-5-mini",
                messages=[{"role": "user", "content": summary_prompt}]
            )

            return response.choices[0].message.content

        except Exception:
            return "手配が完了しました。"

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

            # 実行系ツールがある場合は先にPlayerに一括通知
            execution_tool_calls = [tc for tc in response_message.tool_calls
                                   if tc.function.name in ["inspect_damage", "secure_road", "emergency_restoration", "handle_debris"]]
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
                    self.manager.add_message("assistant", "infrastructure_manager", combined_notification, "infrastructure", from_person="infrastructure_manager", to_person="Player")

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
                has_confirmation_tools = any(tr["function_name"] in ["show_damage_report", "show_restoration_log"] for tr in tool_results)
                has_execution_tools = any(tr["function_name"] in ["inspect_damage", "secure_road", "emergency_restoration", "handle_debris"] for tr in tool_results)

                if has_execution_tools:
                    # 実行系ツールがある場合
                    execution_tasks = [tr for tr in tool_results if tr["function_name"] in ["inspect_damage", "secure_road", "emergency_restoration", "handle_debris"]]

                    # 実行系ツールの結果をまとめて返す
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
            # 通常の会話応答
            assistant_message = response_message.content if response_message.content else ""

        return assistant_message, "infrastructure_manager"