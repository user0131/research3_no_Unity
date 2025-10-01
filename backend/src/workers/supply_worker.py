import csv
from typing import Dict, Any
from pathlib import Path
from .base_worker import BaseWorker
from openai import OpenAI
import sys
sys.path.append(str(Path(__file__).parent.parent))
from csv_operations import update_csv_from_knowledge


class SupplyWorker(BaseWorker):
    """物資管理専門ワーカー（全機能対応）"""

    def __init__(self, worker_name: str, manager, time_manager):
        # 物資管理の配送と調達機能を実行可能
        available_functions = [
            "deliver_supplies",
            "procure_supplies"
        ]

        super().__init__(
            worker_name=worker_name,
            manager=manager,
            available_functions=available_functions,
            time_manager=time_manager
        )

        self.inventory_path = Path("./csv/supply/物資在庫情報.csv")
        self.delivery_log_path = Path("./csv/supply/物資配送記録.csv")
        self.knowledge_path = Path("./src/knowledge/knowledge_supply.txt")
        self.task_data = None

    def start_task(self, task_description: str, task_data: Dict[str, Any]) -> str:
        self.task_data = task_data
        return super().start_task(task_description, task_data)

    def execute_task(self) -> Dict[str, Any]:
        """物資管理関連タスクを実行"""
        if not self.task_data:
            return {"success": False, "message": "タスクデータがありません"}

        function_name = self.task_data.get("function")

        # 配送関連
        if function_name == "deliver_supplies":
            return self._deliver_supplies()

        # 調達関連
        elif function_name == "procure_supplies":
            return self._procure_supplies()

        else:
            return {"success": False, "message": f"未対応の機能: {function_name}"}

    # 配送機能
    def _deliver_supplies(self) -> Dict[str, Any]:
        """物資配送記録と在庫更新"""
        shelter_name = self.task_data.get("shelter_name", "")
        item_name = self.task_data.get("item_name", "")
        quantity = self.task_data.get("quantity", 0)
        unit = self.task_data.get("unit", "")

        try:
            # 在庫情報を取得
            row_index = None
            current_stock = 0

            with open(self.inventory_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for idx, row in enumerate(reader):
                    if item_name in row['物資名']:
                        row_index = idx
                        current_stock = int(row['在庫数'])
                        if not unit:
                            unit = row['単位']
                        break

            # 在庫を減らす
            if row_index is not None:
                new_stock = max(0, current_stock - quantity)
                update_csv_from_knowledge(
                    update_spec={
                        "filename": "物資在庫情報.csv",
                        "update_cells": [
                            {"row_index": row_index, "column": "在庫数", "value": str(new_stock)}
                        ]
                    },
                    knowledge_path=str(self.knowledge_path),
                    time_manager=self.time_manager
                )

            # 配送記録を追加
            update_csv_from_knowledge(
                update_spec={
                    "filename": "物資配送記録.csv",
                    "append_rows": [
                        {
                            "objects": [
                                {
                                    "避難所名": shelter_name,
                                    "物資名": item_name,
                                    "数量": str(quantity),
                                    "単位": unit,
                                    "備考": "避難所要請対応"
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
                "message": f"{shelter_name}への{item_name} {quantity}{unit}の配送を完了し、在庫を更新しました",
                "delivery_details": {
                    "shelter": shelter_name,
                    "item": item_name,
                    "quantity": quantity,
                    "unit": unit
                }
            }
        except Exception as e:
            return {"success": False, "message": f"配送記録エラー: {e}"}

    # 調達機能
    def _procure_supplies(self) -> Dict[str, Any]:
        """物資調達と在庫追加"""
        item_name = self.task_data.get("item_name", "")
        quantity = self.task_data.get("quantity", 0)

        try:
            # 在庫情報を取得
            row_index = None
            current_stock = 0
            unit = ""

            with open(self.inventory_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for idx, row in enumerate(reader):
                    if item_name in row['物資名']:
                        row_index = idx
                        current_stock = int(row['在庫数'])
                        unit = row['単位']
                        break

            # 在庫を増やす
            if row_index is not None:
                new_stock = current_stock + quantity
                update_csv_from_knowledge(
                    update_spec={
                        "filename": "物資在庫情報.csv",
                        "update_cells": [
                            {"row_index": row_index, "column": "在庫数", "value": str(new_stock)}
                        ]
                    },
                    knowledge_path=str(self.knowledge_path),
                    time_manager=self.time_manager
                )

                return {
                    "success": True,
                    "message": f"{item_name} {quantity}{unit}の調達が完了し、在庫に追加しました",
                    "procurement_details": {
                        "item": item_name,
                        "quantity": quantity,
                        "unit": unit,
                        "supplier": "災害対応協定業者"
                    }
                }
            else:
                return {"success": False, "message": f"{item_name}が在庫リストに見つかりません"}

        except Exception as e:
            return {"success": False, "message": f"調達処理エラー: {e}"}

    def complete_task(self) -> Dict[str, Any]:
        """タスクを完了し、結果を返す（BaseWorkerをオーバーライド）"""
        if not self.is_busy:
            return {"success": False, "message": "実行中のタスクがありません"}

        task_result = self.execute_task()

        # LLMで上司への報告を生成
        worker_report = self._generate_report_to_manager(task_result)

        # マネージャーの会話履歴に追加（ChatWithMemory経由）
        if hasattr(self.manager, 'manager') and hasattr(self.manager.manager, 'add_message'):
            self.manager.manager.add_message("user", self.worker_name, worker_report, "supply", from_person=self.worker_name, to_person="supply_manager")

        # マネージャーから感謝メッセージを生成して追加
        if hasattr(self.manager, '_generate_thank_you_message'):
            thank_you_message = self.manager._generate_thank_you_message(self.worker_name, worker_report)
            if hasattr(self.manager, 'manager') and hasattr(self.manager.manager, 'add_message'):
                self.manager.manager.add_message("assistant", "supply_manager", thank_you_message, "supply", from_person="supply_manager", to_person=self.worker_name)

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
あなたは{self.worker_name}です。上司のsupply_managerに作業完了の報告をしてください。

実行したタスク: {self.current_task}
作業結果: {task_result}

上記の作業結果を元に、上司への簡潔な報告を作成してください。
- 作業が成功した場合は完了報告と要点を報告
- 失敗した場合は問題点と対応が必要な事項を報告
- 話し言葉で、同僚への報告として自然な形で報告してください
- 長すぎず、要点を簡潔にまとめてください
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