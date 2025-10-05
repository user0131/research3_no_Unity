import json
import sys
import csv
from typing import List, Dict, Optional, Any
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

        # 知識ファイルのパス
        self.knowledge_path = Path("./src/knowledge/knowledge_infrastructure.txt")

        # 調査ツールを初期化
        self.inspection_tool = InfrastructureInspectionTool(time_manager)

        # 3人のワーカーを初期化
        self.workers = {
            "worker_a": InfrastructureWorker("土木ワーカーA", self, time_manager),
            "worker_b": InfrastructureWorker("土木ワーカーB", self, time_manager),
            "worker_c": InfrastructureWorker("土木ワーカーC", self, time_manager)
        }


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
- **重要：タスク内容の確認**: 作業を依頼された場合、場所や対象が曖昧・不明確な場合は、ツールを実行せずに詳細を確認してください。例：「学校の調査」→どの学校か聞き返す、「道路の確認」→どの道路か聞き返す。具体的な場所が指定されている場合のみツールを実行。
- **重要：現場確認と承認プロセス**:
  - **作業前の必須確認**: 復旧作業を依頼された場合、まず必ずinspect_damageツールで被害状況を確認し、Playerに現在の状況を報告してください
  - **危険箇所の対応**: 危険度が高い場所については、必ずPlayerに報告して対応方針を相談してください
  - **承認後の作業**: Playerから明確な指示を受けた後にのみ、復旧作業ツールを使用してください
- **重要：ツールの使用**: 実際の作業は必ずツールを使って実行してください。会話（テキスト応答）では作業を実行できません。
  - **現場確認**: inspect_damageツールを使用（道路、橋、公園、河川等の調査）
  - **道路確保**: secure_roadツールを使用（道路啓開・確保作業）
  - **応急復旧**: emergency_restorationツールを使用（応急復旧作業）
  - **廃棄物処理**: handle_debrisツールを使用（災害廃棄物等処理）
  - **調査記録確認**: show_damage_reportツールを使用（被害調査記録の確認、確認系なので即座に実行）
  - **復旧記録確認**: show_restoration_logツールを使用（復旧作業記録の確認、確認系なので即座に実行）
  - **CSV更新**: update_csv_from_knowledgeツールを使用（CSVファイルの更新、確認系なので即座に実行）
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

        # 実行系（汎用統合ツール）
        elif tool_name == "execute_infrastructure_task":
            return self._handle_task_assignment("execute_infrastructure_task", args)

        # CSV更新（マネージャー専用）
        elif tool_name == "update_csv_from_knowledge":
            return self._execute_manager_task("update_csv_from_knowledge", args)

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

        # Playerにタスク依頼前のメッセージを送信
        player_notification = self._generate_player_notification(worker_name, function_name, args)
        if hasattr(self, 'manager') and hasattr(self.manager, 'add_message'):
            self.manager.add_message("assistant", "infrastructure_manager", player_notification, "infrastructure",
                                   from_person="infrastructure_manager", to_person="Player")

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

    def _generate_player_notification(self, worker_name: str, function_name: str, args: Dict) -> str:
        """ワーカーにタスクを依頼する前にPlayerに送るメッセージを生成"""
        try:
            client = self.client

            notification_prompt = f"""
あなたはinfrastructure_managerです。Playerから{function_name}の依頼を受けました。

タスク: {function_name}
場所: {args.get('location', '')}

Playerに対して、依頼を受諾することを簡潔に返答してください。
- 「承知しました」「了解しました」「手配します」のような簡潔な受諾の返事
- 話し言葉で、短く簡潔に
"""

            response = client.chat.completions.create(
                model="gpt-5-mini",
                messages=[{"role": "user", "content": notification_prompt}]
            )

            return response.choices[0].message.content

        except Exception:
            return "部下に作業を依頼します。"

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
        if function_name == "execute_infrastructure_task":
            task_type = args.get("task_type", "作業")
            self.pending_task = args
            return self.execute_task_with_delay(task_type, args)

        elif function_name == "show_damage_report":
            return self._show_damage_report()

        elif function_name == "show_restoration_log":
            return self._show_restoration_log()

        elif function_name == "update_csv_from_knowledge":
            # information_managerと同じ処理
            from src.csv_operations import update_csv_from_knowledge
            result = update_csv_from_knowledge(
                **args,
                knowledge_path=str(self.knowledge_path),
                time_manager=self.time_manager
            )
            return "CSVを更新しました。"

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
        """タスクを実行し、10分後の戻り時刻を設定"""
        # Playerにタスク開始前のメッセージを送信
        if hasattr(self, 'manager') and hasattr(self.manager, 'add_message'):
            player_notification = f"{task_name}に行ってきます。"
            self.manager.add_message("assistant", "infrastructure_manager", player_notification, "infrastructure",
                                   from_person="infrastructure_manager", to_person="Player")

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
        """Workerの完了報告を処理（感謝→CSV記録→Player報告）"""
        try:
            client = self.client

            # 1. ワーカーへの感謝メッセージ生成
            thanks_prompt = f"""
あなたはinfrastructure_managerです。{worker_name}から作業完了の報告を受けました。

報告内容: {worker_report}

{worker_name}に対して、感謝の気持ちを表す短いメッセージを作成してください。
「お疲れ様」「ありがとう」のような簡潔な感謝の言葉で。
"""
            thanks_response = client.chat.completions.create(
                model="gpt-5-mini",
                messages=[{"role": "user", "content": thanks_prompt}]
            )
            thanks_message = thanks_response.choices[0].message.content

            # ワーカーへの感謝を会話履歴に追加
            if hasattr(self, 'manager') and hasattr(self.manager, 'add_message'):
                self.manager.add_message("assistant", "infrastructure_manager", thanks_message, "infrastructure", from_person="infrastructure_manager", to_person=worker_name)

            # 2. CSV記録用のデータ生成とCSV振り分け（LLMで判定）
            csv_prompt = f"""
以下のワーカー報告から、適切なCSVファイルに記録すべき情報を判定してください。

報告内容: {worker_report}
報告者: {worker_name}
現在時刻: {self.time_manager.get_current_time()}

# 振り分けルール:
- 道路、橋梁、トンネルの被害 → 道路被害状況.csv
- 電気、ガス、水道、通信の被害 → ライフライン被害状況.csv
- 学校、公園、公共建物などの公共施設の被害調査 → 公共施設被害状況.csv
- 実際の復旧作業、応急処置、撤去作業 → 復旧作業記録.csv（被害調査は含まない）
- 鉄道、バスの運行状況 → 交通機関運行状況.csv

以下のJSON形式で出力してください（JSONのみ、説明不要）：
{{
  "csv_type": "道路被害状況|ライフライン被害状況|公共施設被害状況|復旧作業記録|交通機関運行状況",
  "data": {{
    // csv_typeに応じた適切なフィールド
  }}
}}

例:
道路被害状況の場合: {{"場所": "...", "道路名": "...", "被害内容": "...", "規制状況": "...", "報告者": "{worker_name}", "報告日時": "{self.time_manager.get_current_time()}", "備考": "..."}}
ライフライン被害状況の場合: {{"種別": "...", "地域": "...", "被害内容": "...", "対応状況": "...", "復旧予定": "...", "報告者": "{worker_name}", "報告日時": "{self.time_manager.get_current_time()}", "備考": "..."}}
公共施設被害状況の場合: {{"施設名": "...", "施設種別": "...", "被害内容": "...", "被害程度": "...", "対応状況": "...", "調査者": "{worker_name}", "調査日時": "{self.time_manager.get_current_time()}", "備考": "..."}}
復旧作業記録の場合: {{"作業種別": "...", "作業内容": "...", "完了状況": "...", "報告者": "{worker_name}", "報告日時": "{self.time_manager.get_current_time()}", "備考": "..."}}
交通機関運行状況の場合: {{"交通機関": "...", "路線名": "...", "運行状況": "...", "影響区間": "...", "報告者": "{worker_name}", "報告日時": "{self.time_manager.get_current_time()}", "備考": "..."}}
"""
            csv_response = client.chat.completions.create(
                model="gpt-5-mini",
                messages=[{"role": "user", "content": csv_prompt}]
            )

            # CSV記録を実行
            try:
                import json
                csv_data = json.loads(csv_response.choices[0].message.content)
                csv_type = csv_data.get("csv_type")
                data = csv_data.get("data", {})

                # CSVファイル名のマッピング
                csv_mapping = {
                    "道路被害状況": "道路被害状況.csv",
                    "ライフライン被害状況": "ライフライン被害状況.csv",
                    "公共施設被害状況": "公共施設被害状況.csv",
                    "復旧作業記録": "復旧作業記録.csv",
                    "交通機関運行状況": "交通機関運行状況.csv"
                }

                if csv_type in csv_mapping:
                    from src.csv_operations import update_csv_from_knowledge
                    update_spec = {
                        "filename": csv_mapping[csv_type],
                        "append_rows": [{
                            "objects": [data]
                        }]
                    }

                    update_csv_from_knowledge(
                        instruction=f"{worker_name}の作業完了を記録",
                        update_spec=update_spec,
                        knowledge_path=str(self.knowledge_path),
                        time_manager=self.time_manager
                    )
            except Exception as e:
                print(f"CSV記録エラー: {e}")

            # 3. Playerへの報告メッセージ生成
            player_prompt = f"""
あなたはinfrastructure_managerです。{worker_name}から作業完了の報告を受けました。

報告内容: {worker_report}

Playerに対して、この作業完了を報告する簡潔なメッセージを作成してください。
話し言葉で、短く簡潔に。
"""
            player_response = client.chat.completions.create(
                model="gpt-5-mini",
                messages=[{"role": "user", "content": player_prompt}]
            )

            return player_response.choices[0].message.content

        except Exception:
            return f"{worker_name}の作業が完了しました。"

    def get_function_definitions(self) -> List[Dict]:
        """Function calling用の定義を取得"""
        defs = []

        # 土木作業実施（汎用統合ツール）
        defs.append({
            "type": "function",
            "function": {
                "name": "execute_infrastructure_task",
                "description": "土木インフラ関連の作業全般を実施する汎用ツール。被害調査、道路確保、応急復旧、廃棄物処理、その他の土木作業を実施。会話履歴から空いているワーカーを判断してタスクを依頼する。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_type": {"type": "string", "description": "作業種別（例：被害調査、道路確保、応急復旧、廃棄物処理、通行規制、安全確認、パトロール等）"},
                        "location": {"type": "string", "description": "作業場所"},
                        "details": {"type": "string", "description": "作業の詳細内容（施設種別、具体的な作業内容、対象物等）"},
                        "assigned_worker": {
                            "type": "string",
                            "description": "タスクを依頼するワーカー名（会話履歴から空いているワーカーを選択）",
                            "enum": ["土木ワーカーA", "土木ワーカーB", "土木ワーカーC", "マネージャー自身"]
                        }
                    },
                    "required": ["task_type", "location", "assigned_worker"]
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

        # CSV更新
        defs.append({
            "type": "function",
            "function": {
                "name": "update_csv_from_knowledge",
                "description": "CSVファイルの更新専用ツール。CSVファイルに記録を追加したり更新する場合のみ使用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "instruction": {
                            "type": "string",
                            "description": "自然文の、csvの更新に関する指示。"
                        },
                        "update_spec": {
                            "type": "object",
                            "description": "更新計画（任意）。指定しない場合はinstructionからLLMが自動生成。",
                            "properties": {
                                "filename": {"type": "string", "description": "更新対象CSVファイル名"},
                                "append_rows": {
                                    "type": "array",
                                    "description": "追加する行データの配列",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "objects": {
                                                "type": "array",
                                                "description": "実際の行データの配列",
                                                "items": {"type": "object"}
                                            }
                                        },
                                        "required": ["objects"]
                                    }
                                },
                                "update_cells": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "row_index": {"type": "integer"},
                                            "column": {"type": "string"},
                                            "value": {"description": "書き込む値"}
                                        },
                                        "required": ["row_index", "column", "value"]
                                    }
                                }
                            }
                        }
                    },
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
                has_confirmation_tools = any(tr["function_name"] in ["show_damage_report", "show_restoration_log", "update_csv_from_knowledge"] for tr in tool_results)
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

        # Playerからの重要な情報をCSVに記録するかチェック
        player_message = None
        for msg in messages:
            if msg.get("role") == "user" and msg.get("name") == "Player":
                player_message = msg.get("content", "")
                break

        if player_message:
            self._check_and_record_player_info(player_message)

        return assistant_message, "infrastructure_manager"

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
                    # 各情報をCSVに記録
                    self._record_system_info_to_csv(info.subject, info.content, source)
                info_text = "\n".join(info_summary)

                prompt = f"""
あなたはinfrastructure_managerです。{source}から複数の情報を受け取りました。

{info_text}

これらの情報をPlayerに報告してください。
- 情報の要点を簡潔に伝える
- 指示要請や対応案は含めない
- 話し言葉で、自然に
"""
            else:
                # 単一の情報の場合（従来通り）
                subject, content = info_data
                # システム情報をCSVに記録
                self._record_system_info_to_csv(subject, content, source)
                prompt = f"""
あなたはinfrastructure_managerです。{source}から以下の情報を受け取りました。

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

    def _record_system_info_to_csv(self, subject: str, content: str, source: str):
        """systemからの情報をCSVに記録"""
        try:
            client = self.client
            # LLMでCSV振り分けを判定
            csv_prompt = f"""
以下のシステム情報から、適切なCSVファイルに記録すべき情報を判定してください。
件名: {subject}
内容: {content}
情報源: {source}
現在時刻: {self.time_manager.get_current_time()}

# 振り分けルール:
- 道路、橋梁、トンネルの被害 → 道路被害状況.csv
- 電気、ガス、水道、通信の被害 → ライフライン被害状況.csv
- 学校、公園、公共建物などの公共施設の被害調査 → 公共施設被害状況.csv
- 実際の復旧作業、応急処置、撤去作業 → 復旧作業記録.csv（被害調査は含まない）
- 鉄道、バスの運行状況 → 交通機関運行状況.csv

以下のJSON形式で出力してください（JSONのみ、説明不要）：
{{
  "csv_type": "道路被害状況|ライフライン被害状況|公共施設被害状況|復旧作業記録|交通機関運行状況",
  "data": {{
    // csv_typeに応じた適切なフィールド
  }}
}}

例:
道路被害状況の場合: {{"場所": "...", "道路名": "...", "被害内容": "...", "規制状況": "...", "報告者": "{source}", "報告日時": "{self.time_manager.get_current_time()}", "備考": "..."}}
ライフライン被害状況の場合: {{"種別": "...", "地域": "...", "被害内容": "...", "対応状況": "...", "復旧予定": "...", "報告者": "{source}", "報告日時": "{self.time_manager.get_current_time()}", "備考": "..."}}
公共施設被害状況の場合: {{"施設名": "...", "施設種別": "...", "被害内容": "...", "被害程度": "...", "対応状況": "...", "調査者": "{source}", "調査日時": "{self.time_manager.get_current_time()}", "備考": "..."}}
復旧作業記録の場合: {{"作業種別": "...", "作業内容": "...", "完了状況": "...", "報告者": "{source}", "報告日時": "{self.time_manager.get_current_time()}", "備考": "..."}}
交通機関運行状況の場合: {{"交通機関": "...", "路線名": "...", "運行状況": "...", "影響区間": "...", "報告者": "{source}", "報告日時": "{self.time_manager.get_current_time()}", "備考": "..."}}
"""
            csv_response = client.chat.completions.create(
                model="gpt-5-mini",
                messages=[{"role": "user", "content": csv_prompt}]
            )

            # CSV記録を実行
            try:
                import json
                csv_data = json.loads(csv_response.choices[0].message.content)
                csv_type = csv_data.get("csv_type")
                data = csv_data.get("data", {})

                # CSVファイル名のマッピング
                csv_mapping = {
                    "道路被害状況": "道路被害状況.csv",
                    "ライフライン被害状況": "ライフライン被害状況.csv",
                    "公共施設被害状況": "公共施設被害状況.csv",
                    "復旧作業記録": "復旧作業記録.csv",
                    "交通機関運行状況": "交通機関運行状況.csv"
                }

                if csv_type in csv_mapping:
                    from src.csv_operations import update_csv_from_knowledge
                    update_spec = {
                        "filename": csv_mapping[csv_type],
                        "append_rows": [{
                            "objects": [data]
                        }]
                    }
                    update_csv_from_knowledge(
                        instruction=f"{source}からのシステム情報を記録",
                        update_spec=update_spec,
                        knowledge_path=str(self.knowledge_path),
                        time_manager=self.time_manager
                    )
            except Exception as e:
                # CSV記録でエラーが発生しても処理を継続
                pass

        except Exception as e:
            # システム情報のCSV記録でエラーが発生しても処理を継続
            pass

    def _check_and_record_player_info(self, player_message: str):
        """Playerからの情報でCSVに記録すべきものがあるかチェックして記録"""
        try:
            client = self.client
            # LLMでPlayerの情報がCSVに記録すべきかを判定
            check_prompt = f"""
Playerから以下の情報を受け取りました：
「{player_message}」

この情報が以下のいずれかに該当し、CSVに記録すべきかを判定してください：
- 道路、橋梁、トンネルの被害情報
- 電気、ガス、水道、通信の被害情報
- 学校、公園、公共建物などの公共施設の被害情報
- 復旧作業、応急処置、撤去作業の情報
- 鉄道、バスの運行状況情報

記録すべき場合は「YES」、そうでなければ「NO」のみで回答してください。
"""
            check_response = client.chat.completions.create(
                model="gpt-5-mini",
                messages=[{"role": "user", "content": check_prompt}]
            )

            should_record = check_response.choices[0].message.content.strip().upper()

            if should_record == "YES":
                # CSV記録を実行
                self._record_system_info_to_csv("Player報告", player_message, "Player")

        except Exception:
            # Playerメッセージのチェック・記録でエラーが発生しても処理を継続
            pass