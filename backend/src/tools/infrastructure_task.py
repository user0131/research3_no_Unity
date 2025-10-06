import csv
from typing import Dict, Any, List, Optional
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).parent.parent))
from csv_operations import update_csv_from_knowledge


class InfrastructureInspectionTool:
    """建物・土木施設の被害調査ツール"""

    def __init__(self, time_manager=None):
        self.damage_report_path = Path("./csv/infrastructure/被害調査報告.csv")
        self.knowledge_path = Path("./src/knowledge/knowledge_infrastructure.txt")
        self.time_manager = time_manager

    def inspect_damage(
        self,
        location: str,
        facility_type: str,
        severity: str = "未確認",
        details: str = ""
    ) -> Dict[str, Any]:
        """
        被害状況を調査し記録する

        Args:
            location: 調査場所
            facility_type: 施設種別（道路、橋梁、公園、河川等）
            severity: 被害程度（大、中、小、なし、未確認）
            details: 被害詳細

        Returns:
            調査結果
        """
        try:
            # 被害調査記録を追加
            update_spec = {
                "filename": "被害調査報告.csv",
                "append_rows": [
                    {
                        "objects": [
                            {
                                "調査日時": self.time_manager.get_current_time() if self.time_manager else "",
                                "場所": location,
                                "施設種別": facility_type,
                                "被害程度": severity,
                                "被害詳細": details,
                                "調査者": "infrastructure_manager",
                                "対応状況": "調査完了",
                                "備考": "要対応判断"
                            }
                        ]
                    }
                ]
            }

            update_csv_from_knowledge(
                update_spec=update_spec,
                knowledge_path=str(self.knowledge_path),
                time_manager=self.time_manager
            )

            return {
                "success": True,
                "message": f"{location}の{facility_type}の被害調査を完了しました。",
                "details": {
                    "location": location,
                    "facility_type": facility_type,
                    "severity": severity,
                    "details": details
                }
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"被害調査エラー: {str(e)}"
            }

    def get_damage_reports(
        self,
        location: Optional[str] = None,
        facility_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        被害調査報告を取得する

        Args:
            location: 場所でフィルタ（オプション）
            facility_type: 施設種別でフィルタ（オプション）

        Returns:
            被害調査報告のリスト
        """
        try:
            if not self.damage_report_path.exists():
                return {
                    "success": True,
                    "reports": [],
                    "message": "被害調査報告はまだありません。"
                }

            reports = []
            with open(self.damage_report_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # フィルタリング
                    if location and row.get('場所') != location:
                        continue
                    if facility_type and row.get('施設種別') != facility_type:
                        continue
                    reports.append(row)

            return {
                "success": True,
                "reports": reports,
                "total_count": len(reports)
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"報告取得エラー: {str(e)}"
            }

    def prioritize_damage(self) -> Dict[str, Any]:
        """
        被害の優先度を判定する

        Returns:
            優先度順の被害リスト
        """
        try:
            result = self.get_damage_reports()
            if not result["success"]:
                return result

            reports = result["reports"]

            # 被害程度で優先度をつける
            severity_order = {"大": 1, "中": 2, "小": 3, "なし": 4, "未確認": 5}

            # 施設種別の重要度
            facility_priority = {
                "道路": 1,
                "橋梁": 1,
                "病院": 1,
                "避難所": 1,
                "河川": 2,
                "公園": 3,
                "その他": 4
            }

            # ソート
            sorted_reports = sorted(
                reports,
                key=lambda x: (
                    severity_order.get(x.get("被害程度", "未確認"), 5),
                    facility_priority.get(x.get("施設種別", "その他"), 4)
                )
            )

            # 優先対応が必要な施設を抽出
            high_priority = [
                r for r in sorted_reports
                if r.get("被害程度") in ["大", "中"]
            ]

            return {
                "success": True,
                "high_priority": high_priority,
                "all_reports": sorted_reports,
                "message": f"優先対応が必要な施設: {len(high_priority)}件"
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"優先度判定エラー: {str(e)}"
            }


class InfrastructureRestorationTool:
    """復旧作業管理ツール"""

    def __init__(self, time_manager=None):
        self.restoration_log_path = Path("./csv/infrastructure/復旧作業記録.csv")
        self.knowledge_path = Path("./src/knowledge/knowledge_infrastructure.txt")
        self.time_manager = time_manager

    def get_restoration_status(
        self,
        location: Optional[str] = None,
        work_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        復旧作業の状況を取得する

        Args:
            location: 場所でフィルタ（オプション）
            work_type: 作業種別でフィルタ（オプション）

        Returns:
            復旧作業の状況
        """
        try:
            if not self.restoration_log_path.exists():
                return {
                    "success": True,
                    "logs": [],
                    "message": "復旧作業記録はまだありません。"
                }

            logs = []
            with open(self.restoration_log_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # フィルタリング
                    if location and row.get('場所') != location:
                        continue
                    if work_type and row.get('作業種別') != work_type:
                        continue
                    logs.append(row)

            # 作業統計
            completed = [l for l in logs if l.get('完了状況') == '完了']
            in_progress = [l for l in logs if l.get('完了状況') == '作業中']

            return {
                "success": True,
                "logs": logs,
                "statistics": {
                    "total": len(logs),
                    "completed": len(completed),
                    "in_progress": len(in_progress)
                }
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"状況取得エラー: {str(e)}"
            }

    def estimate_resources(
        self,
        work_type: str,
        scale: str = "中規模"
    ) -> Dict[str, Any]:
        """
        復旧作業に必要なリソースを見積もる

        Args:
            work_type: 作業種別
            scale: 作業規模（小規模、中規模、大規模）

        Returns:
            必要リソースの見積もり
        """
        # リソース見積もりテンプレート
        resource_templates = {
            "道路啓開": {
                "小規模": {"作業員": 3, "重機": 1, "時間": "2時間"},
                "中規模": {"作業員": 5, "重機": 2, "時間": "4時間"},
                "大規模": {"作業員": 10, "重機": 3, "時間": "8時間"}
            },
            "応急復旧": {
                "小規模": {"作業員": 2, "資材": "少量", "時間": "1時間"},
                "中規模": {"作業員": 4, "資材": "中量", "時間": "3時間"},
                "大規模": {"作業員": 8, "資材": "大量", "時間": "6時間"}
            },
            "廃棄物処理": {
                "小規模": {"作業員": 2, "トラック": 1, "時間": "2時間"},
                "中規模": {"作業員": 4, "トラック": 2, "時間": "4時間"},
                "大規模": {"作業員": 6, "トラック": 3, "時間": "6時間"}
            }
        }

        template = resource_templates.get(work_type, {})
        resources = template.get(scale, {})

        if resources:
            return {
                "success": True,
                "work_type": work_type,
                "scale": scale,
                "resources": resources,
                "message": f"{work_type}（{scale}）のリソース見積もりを作成しました。"
            }
        else:
            return {
                "success": False,
                "message": f"作業種別 '{work_type}' の見積もりテンプレートがありません。"
            }