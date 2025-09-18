import threading
import time
from datetime import datetime, timedelta
from typing import Callable, Optional


class TimeManager:
    """災害対応訓練用の時刻管理システム"""

    def __init__(self, start_time: str = "10:30", callback: Optional[Callable] = None):
        """
        初期化
        Args:
            start_time: 開始時刻 (HH:MM形式)
            callback: 時刻が進んだ時に呼び出す関数
        """
        self.simulation_time = start_time
        self.running = True
        self.callback = callback

        # 自動時刻進行スレッドを開始
        self.time_thread = threading.Thread(target=self._auto_advance_time, daemon=True)
        self.time_thread.start()

    def _auto_advance_time(self):
        """バックグラウンドで自動的に時刻を進める"""
        while self.running:
            time.sleep(30)  # 30秒ごと
            if self.running:
                self.advance_time(1)
                if self.callback:
                    self.callback()

    def advance_time(self, minutes: int = 1):
        """訓練用の模擬時刻を進める"""
        current = datetime.strptime(self.simulation_time, "%H:%M")
        new_time = current + timedelta(minutes=minutes)
        self.simulation_time = new_time.strftime("%H:%M")

    def get_current_time(self) -> str:
        """現在の模擬時刻を取得"""
        return self.simulation_time

    def stop(self):
        """時刻進行を停止"""
        self.running = False