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
        """物資配送記録と在庫更新（単一・複数物資対応）"""
        shelter_name = self.task_data.get("shelter_name", "")
        items = self.task_data.get("items", [])


        if not items:
            return {"success": False, "message": "配送する物資が指定されていません"}

        try:
            # 複数物資の在庫チェックと配送処理
            inventory_data = []
            failed_items = []
            processed_items = []

            # 在庫情報を読み込み
            with open(self.inventory_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                inventory_data = list(reader)

            # 各物資の在庫確認
            for item in items:
                item_name = item.get("item_name", "")
                quantity = item.get("quantity", 0)

                row_index = None
                current_stock = 0
                unit = ""
                item_found = False

                for idx, row in enumerate(inventory_data):
                    if item_name in row['物資名']:
                        row_index = idx
                        current_stock = int(row['在庫数'])
                        unit = row['単位']
                        item_found = True
                        break

                # 物資が見つからない場合
                if not item_found:
                    failed_items.append({
                        "item": item_name,
                        "reason": f"{item_name}は在庫リストに存在しません",
                        "type": "item_not_found"
                    })
                    continue

                # 在庫不足チェック
                if current_stock < quantity:
                    shortage_amount = quantity - current_stock
                    if current_stock == 0:
                        failed_items.append({
                            "item": item_name,
                            "reason": f"{item_name}の在庫が完全にありません（要請: {quantity}{unit}）",
                            "type": "no_stock"
                        })
                    else:
                        failed_items.append({
                            "item": item_name,
                            "reason": f"{item_name}の在庫が{current_stock}{unit}しかありません（要請: {quantity}{unit}、不足: {shortage_amount}{unit}）",
                            "type": "insufficient_stock"
                        })
                    continue

                # 在庫が十分にある場合
                processed_items.append({
                    "item_name": item_name,
                    "quantity": quantity,
                    "unit": unit,
                    "row_index": row_index,
                    "current_stock": current_stock
                })

            # 一つでも失敗があれば全体を失敗とする
            if failed_items:
                failed_reasons = [f"・{item['reason']}" for item in failed_items]
                return {
                    "success": False,
                    "message": f"在庫不足により配送できません:\n" + "\n".join(failed_reasons),
                    "shortage_type": "multiple_issues",
                    "failed_items": failed_items
                }

            # 全ての物資が配送可能な場合、在庫を更新
            update_cells = []
            for item in processed_items:
                new_stock = item["current_stock"] - item["quantity"]
                update_cells.append({
                    "row_index": item["row_index"],
                    "column": "在庫数",
                    "value": str(new_stock)
                })

            # 在庫を一括更新
            if update_cells:
                update_csv_from_knowledge(
                    update_spec={
                        "filename": "物資在庫情報.csv",
                        "update_cells": update_cells
                    },
                    knowledge_path=str(self.knowledge_path),
                    time_manager=self.time_manager
                )

            # 配送記録を一括追加
            delivery_objects = []
            for item in processed_items:
                delivery_objects.append({
                    "避難所名": shelter_name,
                    "物資名": item["item_name"],
                    "数量": str(item["quantity"]),
                    "単位": item["unit"],
                    "備考": "避難所要請対応"
                })

            update_csv_from_knowledge(
                update_spec={
                    "filename": "物資配送記録.csv",
                    "append_rows": [{"objects": delivery_objects}]
                },
                knowledge_path=str(self.knowledge_path),
                time_manager=self.time_manager
            )

            # 成功メッセージを作成
            delivered_items = [f"{item['item_name']} {item['quantity']}{item['unit']}" for item in processed_items]
            items_text = "、".join(delivered_items)

            return {
                "success": True,
                "message": f"{shelter_name}への{items_text}の配送を完了し、在庫を更新しました",
                "delivery_details": {
                    "shelter": shelter_name,
                    "items": processed_items,
                    "total_items": len(processed_items)
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

            # 在庫不足の場合は特別な報告を生成
            shortage_type = task_result.get("shortage_type")
            if shortage_type:
                if shortage_type == "no_stock":
                    requested = task_result.get("requested", {})
                    return f"班長、申し訳ありません。{requested.get('item', '')}の在庫が完全にありません。{self.current_task}を実行できませんでした。"
                elif shortage_type == "insufficient_stock":
                    requested = task_result.get("requested", {})
                    available = task_result.get("available", {})
                    shortage = task_result.get("shortage", {})
                    return f"班長、{requested.get('item', '')}の在庫が{available.get('quantity', 0)}{available.get('unit', '')}しかありません。要請の{requested.get('quantity', 0)}{requested.get('unit', '')}に対して{shortage.get('quantity', 0)}{shortage.get('unit', '')}不足しています。配送できませんでした。"
                elif shortage_type == "item_not_found":
                    requested = task_result.get("requested", {})
                    return f"班長、{requested.get('item', '')}という物資が在庫リストに見つかりません。配送できませんでした。"

            report_prompt = f"""
あなたは{self.worker_name}です。上司のsupply_managerに作業完了の報告をしてください。

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

        except Exception:
            # LLM呼び出しが失敗した場合のフォールバック
            if task_result.get("success", False):
                return f"{self.worker_name}です。{self.current_task}が完了しました。{task_result.get('message', '')}"
            else:
                return f"{self.worker_name}です。{self.current_task}で問題が発生しました。{task_result.get('message', '')}"