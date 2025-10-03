import csv
from typing import Dict, Any
from pathlib import Path
from .base_worker import BaseWorker
from openai import OpenAI
import sys
sys.path.append(str(Path(__file__).parent.parent))
from csv_operations import update_csv_from_knowledge


class InfrastructureWorker(BaseWorker):
    """建物・産業・土木対策専門ワーカー（全機能対応）"""

    def __init__(self, worker_name: str, manager, time_manager):
        # 建物・産業・土木対策の実行機能
        available_functions = [
            "inspect_damage",
            "secure_road",
            "emergency_restoration",
            "handle_debris"
        ]

        super().__init__(
            worker_name=worker_name,
            manager=manager,
            available_functions=available_functions,
            time_manager=time_manager
        )

        self.damage_report_path = Path("./csv/infrastructure/被害調査報告.csv")
        self.restoration_log_path = Path("./csv/infrastructure/復旧作業記録.csv")
        self.knowledge_path = Path("./src/knowledge/knowledge_infrastructure.txt")
        self.task_data = None

    def start_task(self, task_description: str, task_data: Dict[str, Any]) -> str:
        self.task_data = task_data
        return super().start_task(task_description, task_data)

    def execute_task(self) -> Dict[str, Any]:
        """建物・産業・土木対策関連タスクを実行"""
        if not self.task_data:
            return {"success": False, "message": "タスクデータがありません"}

        function_name = self.task_data.get("function")

        # 被害調査
        if function_name == "inspect_damage":
            return self._inspect_damage()

        # 道路確保作業
        elif function_name == "secure_road":
            return self._secure_road()

        # 応急復旧作業
        elif function_name == "emergency_restoration":
            return self._emergency_restoration()

        # 廃棄物処理作業
        elif function_name == "handle_debris":
            return self._handle_debris()

        else:
            return {"success": False, "message": f"未対応の機能: {function_name}"}

    def _inspect_damage(self) -> Dict[str, Any]:
        """被害調査を実行"""
        location = self.task_data.get("location", "")
        facility_type = self.task_data.get("facility_type", "")

        try:
            # 調査結果をシミュレート
            import random
            damage_levels = ["軽微", "中程度", "重大", "倒壊危険"]
            damage_level = random.choice(damage_levels)

            # 調査記録を追加
            update_csv_from_knowledge(
                update_spec={
                    "filename": "被害調査報告.csv",
                    "append_rows": [
                        {
                            "objects": [
                                {
                                    "調査日時": self.time_manager.get_current_time(),
                                    "場所": location,
                                    "施設種別": facility_type,
                                    "被害程度": damage_level,
                                    "被害詳細": f"{facility_type}の被害状況を確認",
                                    "調査者": self.worker_name,
                                    "対応状況": "調査完了",
                                    "備考": "詳細評価実施済み"
                                }
                            ]
                        }
                    ]
                },
                knowledge_path=str(self.knowledge_path),
                time_manager=self.time_manager
            )

            return {
                "success": True,
                "message": f"{location}の{facility_type}調査が完了しました。被害程度: {damage_level}",
                "details": {
                    "location": location,
                    "facility_type": facility_type,
                    "damage_level": damage_level,
                    "status": "調査完了"
                }
            }
        except Exception as e:
            return {"success": False, "message": f"被害調査エラー: {e}"}

    def _secure_road(self) -> Dict[str, Any]:
        """道路確保作業を実行"""
        location = self.task_data.get("location", "")

        try:
            # 作業記録を追加
            update_csv_from_knowledge(
                update_spec={
                    "filename": "復旧作業記録.csv",
                    "append_rows": [
                        {
                            "objects": [
                                {
                                    "作業日時": self.time_manager.get_current_time(),
                                    "場所": location,
                                    "作業種別": "道路啓開",
                                    "作業内容": "がれき撤去・道路確保",
                                    "作業者": self.worker_name,
                                    "完了状況": "完了",
                                    "備考": "緊急車両通行可能"
                                }
                            ]
                        }
                    ]
                },
                knowledge_path=str(self.knowledge_path),
                time_manager=self.time_manager
            )

            return {
                "success": True,
                "message": f"{location}の道路確保作業が完了しました。緊急車両の通行が可能になりました。",
                "details": {
                    "location": location,
                    "work_type": "道路啓開",
                    "status": "完了"
                }
            }
        except Exception as e:
            return {"success": False, "message": f"道路確保作業エラー: {e}"}

    def _emergency_restoration(self) -> Dict[str, Any]:
        """応急復旧作業を実行"""
        location = self.task_data.get("location", "")
        work_type = self.task_data.get("work_type", "")

        try:
            # 作業記録を追加
            update_csv_from_knowledge(
                update_spec={
                    "filename": "復旧作業記録.csv",
                    "append_rows": [
                        {
                            "objects": [
                                {
                                    "作業日時": self.time_manager.get_current_time(),
                                    "場所": location,
                                    "作業種別": "応急復旧",
                                    "作業内容": work_type,
                                    "作業者": self.worker_name,
                                    "完了状況": "完了",
                                    "備考": "応急措置済み"
                                }
                            ]
                        }
                    ]
                },
                knowledge_path=str(self.knowledge_path),
                time_manager=self.time_manager
            )

            return {
                "success": True,
                "message": f"{location}の{work_type}応急復旧作業が完了しました。",
                "details": {
                    "location": location,
                    "work_type": work_type,
                    "status": "応急措置完了"
                }
            }
        except Exception as e:
            return {"success": False, "message": f"応急復旧作業エラー: {e}"}

    def _handle_debris(self) -> Dict[str, Any]:
        """廃棄物処理作業を実行"""
        location = self.task_data.get("location", "")
        debris_type = self.task_data.get("debris_type", "")

        try:
            # 作業記録を追加
            update_csv_from_knowledge(
                update_spec={
                    "filename": "復旧作業記録.csv",
                    "append_rows": [
                        {
                            "objects": [
                                {
                                    "作業日時": self.time_manager.get_current_time(),
                                    "場所": location,
                                    "作業種別": "廃棄物処理",
                                    "作業内容": f"{debris_type}の撤去・処理",
                                    "作業者": self.worker_name,
                                    "完了状況": "完了",
                                    "備考": "一時集積場へ搬送"
                                }
                            ]
                        }
                    ]
                },
                knowledge_path=str(self.knowledge_path),
                time_manager=self.time_manager
            )

            return {
                "success": True,
                "message": f"{location}の{debris_type}処理が完了しました。一時集積場へ搬送しました。",
                "details": {
                    "location": location,
                    "debris_type": debris_type,
                    "status": "処理完了"
                }
            }
        except Exception as e:
            return {"success": False, "message": f"廃棄物処理作業エラー: {e}"}

    def complete_task(self) -> Dict[str, Any]:
        """タスクを完了し、結果を返す（BaseWorkerをオーバーライド）"""
        if not self.is_busy:
            return {"success": False, "message": "実行中のタスクがありません"}

        task_result = self.execute_task()

        # LLMで上司への報告を生成
        worker_report = self._generate_report_to_manager(task_result)

        # マネージャーの会話履歴に追加
        if hasattr(self.manager, 'manager') and hasattr(self.manager.manager, 'add_message'):
            self.manager.manager.add_message("user", self.worker_name, worker_report, "infrastructure",
                                            from_person=self.worker_name, to_person="infrastructure_manager")

        # マネージャーから感謝メッセージを生成して追加
        if hasattr(self.manager, '_generate_thank_you_message'):
            thank_you_message = self.manager._generate_thank_you_message(self.worker_name, worker_report)
            if hasattr(self.manager, 'manager') and hasattr(self.manager.manager, 'add_message'):
                self.manager.manager.add_message("assistant", "infrastructure_manager", thank_you_message, "infrastructure",
                                                from_person="infrastructure_manager", to_person=self.worker_name)

        # タスク状態をリセット
        self.is_busy = False
        current_task = self.current_task
        self.current_task = None
        self.task_end_time = None

        return {
            "success": True,
            "worker_name": self.worker_name,
            "task": current_task,
            "result": task_result,
            "report": worker_report
        }

    def _generate_report_to_manager(self, task_result: Dict[str, Any]) -> str:
        """作業結果からマネージャーへの報告を生成"""
        try:
            # マネージャーのOpenAIクライアントを使用
            client = self.manager.client

            report_prompt = f"""
あなたは{self.worker_name}です。上司のinfrastructure_managerに作業完了の報告をしてください。

実行したタスク: {self.current_task}
作業結果: {task_result}

上記の作業結果を元に、上司への簡潔な報告を作成してください。
- 作業が成功した場合は完了報告と要点を報告
- 失敗した場合は問題点と対応が必要な事項を報告
- 話し言葉で、同僚への報告として自然な形で報告してください
- 長すぎず、要点を簡潔にまとめてください。短く簡潔に、話し言葉で報告のみを。余計な提案はせずに。
"""

            response = client.chat.completions.create(
                model="gpt-5-mini",
                messages=[{"role": "user", "content": report_prompt}]
            )

            return response.choices[0].message.content

        except Exception as e:
            # LLM呼び出しが失敗した場合のフォールバック
            if task_result.get("success", False):
                return f"{self.worker_name}です。{self.current_task}が完了しました。{task_result.get('message', '')}"
            else:
                return f"{self.worker_name}です。{self.current_task}で問題が発生しました。{task_result.get('message', '')}"

    def _generate_thank_you_message(self, worker_name: str, worker_report: str) -> str:
        """ワーカーの完了報告に対するマネージャーの感謝メッセージを生成"""
        try:
            client = self.manager.client

            thank_you_prompt = f"""
あなたはinfrastructure_managerです。{worker_name}から以下の完了報告を受けました。

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

        except Exception:
            return f"{worker_name}、お疲れ様でした。ありがとう。"