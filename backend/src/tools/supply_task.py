import csv
from typing import Tuple
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent))
from csv_operations import update_csv_from_knowledge


class SupplyInventoryTool:
    """物資在庫管理ツールクラス"""

    def __init__(self, knowledge_path: Path, time_manager):
        self.knowledge_path = knowledge_path
        self.time_manager = time_manager
        self.inventory_csv_path = Path("./csv/supply/物資在庫情報.csv")
        self.delivery_log_path = Path("./csv/supply/物資配送記録.csv")

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
                return "主な在庫:\n" + "\n".join(summary)
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
            row_index = None
            current_stock = 0

            with open(self.inventory_csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for idx, row in enumerate(reader):
                    if item_name in row['物資名']:
                        row_index = idx
                        current_stock = int(row['在庫数'])
                        break

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
                return True
            return False
        except Exception as e:
            print(f"在庫更新エラー: {e}")
            return False

    def add_inventory(self, item_name: str, quantity: int) -> bool:
        """在庫を追加（調達により増加）"""
        try:
            row_index = None
            current_stock = 0

            with open(self.inventory_csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for idx, row in enumerate(reader):
                    if item_name in row['物資名']:
                        row_index = idx
                        current_stock = int(row['在庫数'])
                        break

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
                return True
            return False
        except Exception as e:
            print(f"在庫追加エラー: {e}")
            return False

    def record_delivery(self, shelter_name: str, item_name: str, quantity: int, unit: str):
        """配送記録を追加"""
        try:
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
        except Exception as e:
            print(f"配送記録エラー: {e}")