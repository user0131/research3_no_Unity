import os
import json
from typing import List, Dict
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv

from managers.information_manager import InformationManager
from managers.supply_manager import SupplyManager
from inf_provider import InfProvider
from time_manager import TimeManager

load_dotenv()


class ChatWithMemory:
    def __init__(self):
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")

        self.client = OpenAI(api_key=api_key)
        self.conversation_history: List[Dict[str, str]] = []
        self.inf_provider = InfProvider()  # タスク管理システムを初期化
        # 時刻管理システムを初期化（callbackで付与情報をチェック） 時間が変更すればこれを実施する
        self.time_manager = TimeManager(start_time="10:30", callback=self.check_scheduled_infos, speed_multiplier=3.0)
        # 各マネージャーを初期化
        self.info_manager = InformationManager(self.client, self.time_manager)
        self.supply_manager = SupplyManager(self.client, self.time_manager)

        # 会話履歴を分離
        self.info_conversation_history: List[Dict[str, str]] = []
        self.supply_conversation_history: List[Dict[str, str]] = []



    def _build_messages_for_api(self, user_message: str = None, manager_type: str = "information") -> List[Dict[str, str]]:
        """API用のメッセージリストを構築"""
        messages = []

        if manager_type == "information":
            # システムプロンプト（InformationManagerから取得）
            messages.append({"role": "system", "content": self.info_manager.build_system_prompt()})
            # 過去の会話(role付き)を追加
            messages.extend(self.info_conversation_history)
        else:  # supply
            # システムプロンプト（SupplyManagerから取得）
            messages.append({"role": "system", "content": self.supply_manager.build_system_prompt()})
            # 過去の会話(role付き)を追加
            messages.extend(self.supply_conversation_history)

        # ユーザーメッセージがあれば(2回目以降)新たに追加
        if user_message:
            messages.append({"role": "user", "name": "Player" ,"content": user_message})

        return messages


    def add_message(self, role: str, name: str, content: str, manager_type: str = "information"):
        message = {"role": role, "name": name, "content": content}

        if manager_type == "information":
            self.info_conversation_history.append(message)
        else:  # supply
            self.supply_conversation_history.append(message)

        # 全体の履歴にも追加（情報付与用）
        self.conversation_history.append(message)

    def clear_history(self):
        self.conversation_history = []
        self.info_conversation_history = []
        self.supply_conversation_history = []

    def get_conversation_history(self, manager_type: str = "all") -> List[Dict[str, str]]:
        if manager_type == "information":
            return self.info_conversation_history.copy()
        elif manager_type == "supply":
            return self.supply_conversation_history.copy()
        else:
            return self.conversation_history.copy()


    def send_message(self, user_message: str) -> str:
        # マネージャー選択の判定
        manager_type = "information"  # デフォルトでは、情報管理（同じ部屋）の人と話すように
        actual_message = user_message

        if user_message.startswith("/information_manager/"):
            manager_type = "information"
            actual_message = user_message[len("/information_manager/"):]
        elif user_message.startswith("/supply_manager/"):
            manager_type = "supply"
            actual_message = user_message[len("/supply_manager/"):]

        # 対応するマネージャーを選択
        if manager_type == "information":
            current_manager = self.info_manager
        else:
            current_manager = self.supply_manager

        # 離席中チェック
        unavailable_msg = current_manager.check_if_available()
        if unavailable_msg:
            print(unavailable_msg)
            return ""

        # 会話中フラグをセット（情報付与を一時停止）
        current_manager.in_conversation = True

        try:
            # ユーザーメッセージを履歴に追加
            self.add_message("user", "Player", actual_message, manager_type)

            # API用メッセージを構築
            messages = self._build_messages_for_api(actual_message, manager_type)

            # 選択されたマネージャーでレスポンスを処理
            assistant_message, role_name = current_manager.process_response(messages)

            # アシスタントメッセージを履歴に追加
            self.add_message("user", role_name, assistant_message, manager_type)

            return assistant_message

        finally:
            # 会話終了後フラグをリセット
            current_manager.in_conversation = False

    def check_scheduled_infos(self):
        """スケジュール情報をチェックして表示"""
        current_time = self.time_manager.get_current_time()

        # 両方のマネージャーのタスク戻りを処理
        info_return_message = self.info_manager.handle_return_from_task()
        if info_return_message:
            print(f"\n{info_return_message}")
            self.add_message("user", "information_manager", info_return_message, "information")

        supply_return_message = self.supply_manager.handle_return_from_task()
        if supply_return_message:
            print(f"\n{supply_return_message}")
            self.add_message("user", "supply_manager", supply_return_message, "supply")

        # 会話中のみ情報付与を一時停止（離席中は情報付与継続）
        # information_managerのみが情報付与を受け取る
        if self.info_manager.in_conversation or self.supply_manager.in_conversation:
            return False

        # TimeManagerの時刻をInfProviderに同期
        self.inf_provider.simulation_time = current_time

        infos = self.inf_provider.check_scheduled_infos()
        if infos:
            for info in infos:
                print(f"\n【情報付与】付与元: {info.source} | 件名: {info.subject}")
                print(f"   {info.content}")

                # 会話ログにsystemメッセージとして追加
                system_message = f"【情報付与】{info.source}: {info.subject}\n{info.content}"
                self.add_message("system", "System", system_message)
            print()
        return len(infos) > 0


def main():
    print("command:")
    print("   /clear   - 会話履歴をクリア")
    print("   /history - 会話履歴を表示")
    print("   /time    - 現在時刻を表示")
    print("   /exit    - 終了")
    try:
        chat = ChatWithMemory()
        print(f"災害対応訓練開始 - 現在時刻: {chat.time_manager.get_current_time()}")
    except Exception as e:
        print(f"error: {e}")
        return

    while True:
        try:
            user_input = input("You: ").strip()

            if user_input.lower() == "/exit":
                print("bie")
                break
            elif user_input.lower() == "/clear":
                chat.clear_history()
                print("🧹 会話履歴をクリアしました")
                continue
            elif user_input.lower() == "/history":
                history = chat.get_conversation_history()
                if history:
                    print("\nこれまでの会話:")
                    # 最初のsystemプロンプトをスキップ、2回目以降のsystemは表示
                    first_system_skipped = False
                    for i, msg in enumerate(history, 1):
                        role = msg["role"].upper()
                        if role == "SYSTEM" and not first_system_skipped:
                            first_system_skipped = True
                            continue
                        print(f"{role}: {msg['content']}")
                else:
                    print("会話履歴はありません")
                print()
                continue
            elif user_input.lower() == "/time":
                current_time = chat.time_manager.get_current_time()
                print(f"現在時刻: {current_time}")
                continue

            elif user_input:
                print("assitant ", end="", flush=True)
                response = chat.send_message(user_input)
                print(response)
                print()

        except KeyboardInterrupt:
            print("\nbie")
            break
        except Exception as e:
            print(f"error: {e}")


if __name__ == "__main__":
    main()
