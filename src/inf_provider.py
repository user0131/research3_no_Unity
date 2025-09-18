"""
タスクキュー管理システム
災害対応訓練中に定期的にタスクが発生し、動的に管理される
"""

import json
import random
import time
import csv
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from openai import OpenAI
from pydantic import BaseModel, Field


class Task(BaseModel):
    """タスク定義"""
    content: str
    created_at: str
    completed: bool = False
    completed_at: Optional[str] = None


class ScheduledInfo(BaseModel):
    """スケジュール情報"""
    time_str: str  # HH:MM形式
    source: str  # 付与元
    subject: str  # 件名
    content: str  # 付与内容
    delivered: bool = False  # 配信済みフラグ


class TaskQueue(BaseModel):
    """タスクキュー"""
    tasks: List[Task] = []
    scheduled_infos: List[ScheduledInfo] = []  # スケジュール情報リスト
    last_scheduled_check: Optional[str] = None  # 最後にチェックした時刻


class TaskManager:
    """タスク管理システム"""

    def __init__(self, csv_file: str = "./config/push_tasks/付与情報.csv"):
        self.csv_file = Path(task_file)
        self.task_file.parent.mkdir(parents=True, exist_ok=True)
        self.queue = self._load_queue()
        self.client = None
        api_key = None
        try:
            import os
            api_key = os.environ.get('OPENAI_API_KEY')
        except:
            pass
        if api_key:
            self.client = OpenAI(api_key=api_key)

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
                        # 既存のスケジュール情報と重複しないか確認
                        exists = any(
                            s.time_str == info.time_str and
                            s.source == info.source and
                            s.subject == info.subject
                            for s in self.queue.scheduled_infos
                        )
                        if not exists:
                            self.queue.scheduled_infos.append(info)
            self._save_queue()
        except Exception as e:
            print(f"スケジュール情報の読み込みエラー: {e}")

    def check_scheduled_infos(self) -> List[ScheduledInfo]:
        """
        現在時刻をチェックして、配信すべきスケジュール情報を取得

        Returns:
            配信すべき情報のリスト
        """
        current_time = datetime.now()
        current_time_str = current_time.strftime("%H:%M")
        delivered_infos = []

        for info in self.queue.scheduled_infos:
            if not info.delivered and info.time_str <= current_time_str:
                # 時刻が過ぎていて未配信の情報を配信
                delivered_infos.append(info)
                info.delivered = True

        if delivered_infos:
            self._save_queue()

        return delivered_infos