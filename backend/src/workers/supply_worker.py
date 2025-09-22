import csv
from typing import Dict, Any
from pathlib import Path
from .base_worker import BaseWorker
from openai import OpenAI


class SupplyWorker(BaseWorker):
    """物資管理専門ワーカー（全機能対応）"""

    def __init__(self, worker_name: str, manager, time_manager):
        # 物資管理の全機能を実行可能
        available_functions = [
            "check_inventory",
            "update_inventory",
            "show_inventory",
            "deliver_supplies",
            "show_delivery_log",
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
        self.task_data = None

    def start_task(self, task_description: str, task_data: Dict[str, Any]) -> str:
        self.task_data = task_data
        return super().start_task(task_description, task_data)

    def execute_task(self) -> Dict[str, Any]:
        """物資管理関連タスクを実行"""
        if not self.task_data:
            return {"success": False, "message": "タスクデータがありません"}

        function_name = self.task_data.get("function")

        # 在庫関連
        if function_name == "check_inventory":
            return self._check_inventory()
        elif function_name == "update_inventory":
            return self._update_inventory()
        elif function_name == "show_inventory":
            return self._show_inventory()

        # 配送関連
        elif function_name == "deliver_supplies":
            return self._deliver_supplies()
        elif function_name == "show_delivery_log":
            return self._show_delivery_log()

        # 調達関連
        elif function_name == "procure_supplies":
            return self._procure_supplies()

        else:
            return {"success": False, "message": f"未対応の機能: {function_name}"}

    # 在庫管理機能
    def _check_inventory(self) -> Dict[str, Any]:
        """在庫確認"""
        item_name = self.task_data.get("item_name", "")

        try:
            with open(self.inventory_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if item_name in row['物資名']:
                        stock = int(row['在庫数'])
                        unit = row['単位']
                        return {
                            "success": True,
                            "item_name": row['物資名'],
                            "stock": stock,
                            "unit": unit,
                            "available": stock > 0
                        }

            return {"success": False, "message": f"{item_name}が見つかりません"}
        except Exception as e:
            return {"success": False, "message": f"在庫確認エラー: {e}"}

    def _update_inventory(self) -> Dict[str, Any]:
        """在庫更新"""
        item_name = self.task_data.get("item_name", "")
        quantity = self.task_data.get("quantity", 0)

        try:
            rows = []
            updated = False

            with open(self.inventory_path, 'r', encoding='utf-8') as f:
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
                with open(self.inventory_path, 'w', encoding='utf-8', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)

                return {
                    "success": True,
                    "message": f"{item_name}の在庫を{quantity}減らしました",
                    "item_name": item_name,
                    "quantity_updated": quantity
                }
            else:
                return {"success": False, "message": f"{item_name}が見つかりません"}
        except Exception as e:
            return {"success": False, "message": f"在庫更新エラー: {e}"}

    def _show_inventory(self) -> Dict[str, Any]:
        """在庫一覧表示"""
        try:
            inventory_list = []
            with open(self.inventory_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if int(row['在庫数']) > 0:
                        inventory_list.append({
                            "物資名": row['物資名'],
                            "在庫数": row['在庫数'],
                            "単位": row['単位'],
                            "保管場所": row['保管場所']
                        })

            return {
                "success": True,
                "inventory_list": inventory_list,
                "total_items": len(inventory_list)
            }
        except Exception as e:
            return {"success": False, "message": f"在庫一覧取得エラー: {e}"}

    # 配送機能
    def _deliver_supplies(self) -> Dict[str, Any]:
        """物資配送記録"""
        shelter_name = self.task_data.get("shelter_name", "")
        item_name = self.task_data.get("item_name", "")
        quantity = self.task_data.get("quantity", 0)
        unit = self.task_data.get("unit", "")

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
                    self.worker_name,
                    "避難所要請対応"
                ])

            return {
                "success": True,
                "message": f"{shelter_name}への{item_name} {quantity}{unit}の配送を記録しました",
                "delivery_details": {
                    "time": current_time,
                    "shelter": shelter_name,
                    "item": item_name,
                    "quantity": quantity,
                    "unit": unit
                }
            }
        except Exception as e:
            return {"success": False, "message": f"配送記録エラー: {e}"}

    def _show_delivery_log(self) -> Dict[str, Any]:
        """配送記録表示"""
        try:
            delivery_log = []
            with open(self.delivery_log_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    delivery_log.append(dict(row))

            return {
                "success": True,
                "delivery_log": delivery_log[-10:],  # 最新10件
                "total_deliveries": len(delivery_log)
            }
        except Exception as e:
            return {"success": False, "message": f"配送記録取得エラー: {e}"}

    # 調達機能
    def _procure_supplies(self) -> Dict[str, Any]:
        """物資調達"""
        item_name = self.task_data.get("item_name", "")
        quantity = self.task_data.get("quantity", 0)

        # 実際の調達処理は簡略化（外部業者への発注など）
        return {
            "success": True,
            "message": f"{item_name} {quantity}個の調達手配を完了しました",
            "procurement_details": {
                "item": item_name,
                "quantity": quantity,
                "estimated_arrival": "6時間後",
                "supplier": "災害対応協定業者"
            }
        }

    def complete_task(self) -> Dict[str, Any]:
        """タスクを完了し、結果を返す（BaseWorkerをオーバーライド）"""
        if not self.is_busy:
            return {"success": False, "message": "実行中のタスクがありません"}

        task_result = self.execute_task()

        # LLMで上司への報告を生成
        worker_report = self._generate_report_to_manager(task_result)

        # マネージャーの会話履歴に追加
        if hasattr(self.manager, 'add_message'):
            # supply_manager用の会話履歴に追加
            self.manager.add_message("user", self.worker_name, worker_report, "supply")

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
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": report_prompt}],
                max_tokens=200
            )

            return response.choices[0].message.content

        except Exception as e:
            # LLM呼び出しが失敗した場合のフォールバック
            if task_result.get("success", False):
                return f"{self.worker_name}です。{self.current_task}が完了しました。{task_result.get('message', '')}"
            else:
                return f"{self.worker_name}です。{self.current_task}で問題が発生しました。{task_result.get('message', '')}"