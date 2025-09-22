from abc import ABC, abstractmethod
from typing import Dict, Any, List, Callable
from datetime import datetime, timedelta


class BaseWorker(ABC):
    """Worker基底クラス"""

    def __init__(self, worker_name: str, manager, available_functions: List[str], time_manager):
        self.worker_name = worker_name
        self.manager = manager  # 上司のマネージャー
        self.available_functions = available_functions  # 実行可能な機能リスト
        self.time_manager = time_manager

        # タスク管理
        self.current_task = None
        self.task_start_time = None
        self.task_end_time = None
        self.is_busy = False

    def can_execute_function(self, function_name: str) -> bool:
        """指定された機能を実行可能かチェック"""
        return function_name in self.available_functions

    def start_task(self, task_description: str, task_data: Dict[str, Any]) -> str:
        """タスクを開始"""
        if self.is_busy:
            current_task_name = self.current_task or "作業"
            return f"{self.worker_name}は現在{current_task_name}中です。"

        self.is_busy = True
        self.current_task = task_description

        # タスク完了時刻を設定（2分後）
        current_time = datetime.strptime(self.time_manager.get_current_time(), "%H:%M")
        self.task_end_time = current_time + timedelta(minutes=2)

        return f"{self.worker_name}が{task_description}を開始しました。{self.task_end_time.strftime('%H:%M')}頃に完了予定です。"

    def check_task_completion(self) -> bool:
        """タスクが完了したかチェック"""
        if not self.is_busy or not self.task_end_time:
            return False

        current_time = datetime.strptime(self.time_manager.get_current_time(), "%H:%M")
        return current_time >= self.task_end_time

    def complete_task(self) -> Dict[str, Any]:
        """タスクを完了し、結果を返す"""
        if not self.is_busy:
            return {"success": False, "message": "実行中のタスクがありません"}

        task_result = self.execute_task()

        # タスク状態をリセット
        self.is_busy = False
        self.current_task = None
        self.task_end_time = None

        return {
            "success": True,
            "worker_name": self.worker_name,
            "task": self.current_task,
            "result": task_result
        }

    @abstractmethod
    def execute_task(self) -> Dict[str, Any]:
        """実際のタスク実行（サブクラスで実装）"""
        pass

    def get_status(self) -> Dict[str, Any]:
        """ワーカーの現在状況を返す"""
        return {
            "worker_name": self.worker_name,
            "is_busy": self.is_busy,
            "current_task": self.current_task,
            "available_functions": self.available_functions,
            "task_end_time": self.task_end_time.strftime("%H:%M") if self.task_end_time else None
        }