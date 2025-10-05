from typing import Dict, Any
from pathlib import Path
from .base_worker import BaseWorker


class InfrastructureWorker(BaseWorker):
    """建物・産業・土木対策専門ワーカー（全機能対応）"""

    def __init__(self, worker_name: str, manager, time_manager):
        # 建物・産業・土木対策の実行機能（汎用統合ツール）
        available_functions = [
            "execute_infrastructure_task"
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
        """建物・産業・土木対策関連タスクを実行（汎用統合ツール）"""
        if not self.task_data:
            return {"success": False, "message": "タスクデータがありません"}

        # タスクの詳細を取得
        task_type = self.task_data.get("task_type", "作業")
        location = self.task_data.get("location", "")
        details = self.task_data.get("details", "")
        facility_type = self.task_data.get("facility_type", "")

        try:
            # LLMにタスク実行報告を生成してもらう
            prompt = f"""
あなたは土木ワーカー「{self.worker_name}」です。以下のタスクを実施しました。

タスク種別: {task_type}
場所: {location}
{f'施設種別: {facility_type}' if facility_type else ''}
詳細: {details}

タスクの実行結果を報告してください。
- 被害調査の場合: 被害程度（軽微/中程度/重大/倒壊危険）、具体的な被害状況、必要な対応
- 復旧作業の場合: 作業内容、完了状況、残作業
- その他: 実施内容と結果

報告は1-2文で簡潔に、具体的に。
"""
            response = self.manager.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}]
            )

            report = response.choices[0].message.content

            return {
                "success": True,
                "message": report
            }
        except Exception as e:
            return {"success": False, "message": f"タスク実行エラー: {e}"}

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

        # Managerの_process_worker_reportが感謝メッセージとCSV記録を処理する

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

