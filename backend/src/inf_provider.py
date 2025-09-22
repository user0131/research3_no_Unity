import csv
from typing import List
from pathlib import Path
from pydantic import BaseModel


class ScheduledInfo(BaseModel):
    """スケジュール情報"""
    time_str: str  # HH:MM形式
    source: str  # 付与元
    subject: str  # 件名
    content: str  # 付与内容
    delivered: bool = False  # 配信済みフラグ


class InfoQueue(BaseModel):
    """情報キュー"""
    scheduled_infos: List[ScheduledInfo] = []  # スケジュール情報リスト


class InfProvider:
    """情報付与システム"""

    def __init__(self):
        self.queue = InfoQueue()
        # スケジュール情報をCSVから読み込み
        self._load_scheduled_infos()


    def _load_scheduled_infos(self):
        """CSVファイルからスケジュール情報を読み込み"""
        csv_path = Path("./config/push_tasks/付与情報.csv")
        if not csv_path.exists():
            print(f"付与情報CSVファイルが見つかりません: {csv_path}")
            return

        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('付与時間') and row.get('付与元') and row.get('件名') and row.get('付与内容'):
                        info = ScheduledInfo(
                            time_str=row['付与時間'],
                            source=row['付与元'],
                            subject=row['件名'],
                            content=row['付与内容']
                        )
                        # 既存の付与内容と重複しないか確認
                        exists = any(
                            s.time_str == info.time_str and
                            s.source == info.source and
                            s.subject == info.subject
                            for s in self.queue.scheduled_infos
                        )
                        if not exists:
                            self.queue.scheduled_infos.append(info)
        except Exception as e:
            print(f"付与内容情報の読み込みエラー: {e}")

    def check_scheduled_infos(self) -> List[ScheduledInfo]:
        """
        現在時刻をチェックして、配信すべきスケジュール情報を取得

        Returns:
            配信すべき情報のリスト
        """
        # 災害対応訓練用の模擬時刻を使用
        current_time_str = self.simulation_time
        delivered_infos = []

        for info in self.queue.scheduled_infos:
            if not info.delivered and info.time_str <= current_time_str:
                # 時刻が過ぎていて未配信の情報を配信
                delivered_infos.append(info)
                info.delivered = True

        return delivered_infos