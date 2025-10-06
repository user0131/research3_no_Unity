import os
import json
from typing import List, Dict
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv

from managers.information_manager import InformationManager
from managers.supply_manager import SupplyManager
from managers.infrastructure_manager import InfrastructureManager
from managers.mayor_manager import MayorManager
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
        self.infrastructure_manager = InfrastructureManager(self.client, self.time_manager)
        self.mayor_manager = MayorManager(self.client, self.time_manager)

        # マネージャーにChatWithMemoryへの参照を設定
        self.info_manager.manager = self
        self.supply_manager.manager = self
        self.infrastructure_manager.manager = self
        self.mayor_manager.manager = self

        # 会話履歴を分離（マネージャータイプ別）
        self.info_conversation_history: List[Dict[str, str]] = []
        self.supply_conversation_history: List[Dict[str, str]] = []
        self.infrastructure_conversation_history: List[Dict[str, str]] = []
        self.mayor_conversation_history: List[Dict[str, str]] = []

        # 各人物ごとの会話履歴ボックス
        self.person_histories = {
            "Player": [],
            "information_manager": [],
            "mayor_manager": [],
            "supply_manager": [],
            "infrastructure_manager": [],
            "ワーカーA": [],
            "ワーカーB": [],
            "ワーカーC": [],
            "土木ワーカーA": [],
            "土木ワーカーB": [],
            "土木ワーカーC": []
        }



    def _build_messages_for_api(self, user_message: str = None, manager_type: str = "information") -> List[Dict[str, str]]:
        """API用のメッセージリストを構築"""
        messages = []

        if manager_type == "information":
            # システムプロンプト（InformationManagerから取得）
            messages.append({"role": "system", "content": self.info_manager.build_system_prompt()})
            # 過去の会話(role付き)を追加
            messages.extend(self.info_conversation_history)
        elif manager_type == "mayor":
            # システムプロンプト（MayorManagerから取得）
            messages.append({"role": "system", "content": self.mayor_manager.build_system_prompt()})
            # 過去の会話(role付き)を追加
            messages.extend(self.mayor_conversation_history)
        elif manager_type == "supply":
            # システムプロンプト（SupplyManagerから取得）
            messages.append({"role": "system", "content": self.supply_manager.build_system_prompt()})
            # 過去の会話(role付き)を追加
            messages.extend(self.supply_conversation_history)
        else:  # infrastructure
            # システムプロンプト（InfrastructureManagerから取得）
            messages.append({"role": "system", "content": self.infrastructure_manager.build_system_prompt()})
            # 過去の会話(role付き)を追加
            messages.extend(self.infrastructure_conversation_history)

        # ユーザーメッセージがあれば(2回目以降)新たに追加
        if user_message:
            messages.append({"role": "user", "name": "Player" ,"content": user_message})

        return messages


    def add_message(self, role: str, name: str, content: str, manager_type: str = "information", from_person: str = None, to_person: str = None):
        # from_personとto_personが指定されていない場合はnameから推測
        if from_person is None:
            from_person = name
        if to_person is None:
            # デフォルトの宛先を推測
            if name == "Player":
                if manager_type == "supply":
                    to_person = "supply_manager"
                elif manager_type == "infrastructure":
                    to_person = "infrastructure_manager"
                elif manager_type == "mayor":
                    to_person = "mayor_manager"
                else:
                    to_person = "information_manager"
            elif "ワーカー" in name:
                if manager_type == "supply":
                    to_person = "supply_manager"
                elif manager_type == "infrastructure":
                    to_person = "infrastructure_manager"
                else:
                    to_person = "information_manager"
            elif name in ["supply_manager", "information_manager", "infrastructure_manager", "mayor_manager"]:
                to_person = "Player"  # デフォルトはPlayerに報告
            else:
                to_person = "Player"

        # 現在時刻を取得
        current_time = self.time_manager.get_current_time()

        message = {
            "role": role,
            "name": name,
            "content": content,
            "from": from_person,
            "to": to_person,
            "timestamp": current_time
        }

        if manager_type == "information":
            self.info_conversation_history.append(message)
        elif manager_type == "mayor":
            self.mayor_conversation_history.append(message)
        elif manager_type == "supply":
            self.supply_conversation_history.append(message)
        else:  # infrastructure
            self.infrastructure_conversation_history.append(message)

        # 全体の履歴にも追加（情報付与用）
        self.conversation_history.append(message)

        # 各人物の会話ボックスに追加
        # 発信者のボックスに追加
        if from_person in self.person_histories:
            self.person_histories[from_person].append(message)

        # 特別な宛先処理（チーム全体への通知）
        if to_person == "information_team":
            # 情報管理室全体（Player, Information Manager, Mayor）に追加
            if "Player" in self.person_histories:
                self.person_histories["Player"].append(message)
            if "information_manager" in self.person_histories:
                self.person_histories["information_manager"].append(message)
            if "mayor_manager" in self.person_histories:
                self.person_histories["mayor_manager"].append(message)
        elif to_person == "supply_team":
            # 物資管理班全体（supply_manager, ワーカーA/B/C）に追加
            supply_team_members = ["supply_manager", "ワーカーA", "ワーカーB", "ワーカーC"]
            for member in supply_team_members:
                if member in self.person_histories and member != from_person:
                    self.person_histories[member].append(message)
        elif to_person == "infrastructure_team":
            # 建物・産業・土木対策班全体（infrastructure_manager, 土木ワーカーA/B/C）に追加
            infrastructure_team_members = ["infrastructure_manager", "土木ワーカーA", "土木ワーカーB", "土木ワーカーC"]
            for member in infrastructure_team_members:
                if member in self.person_histories and member != from_person:
                    self.person_histories[member].append(message)
        elif to_person != from_person and to_person in self.person_histories:
            # 通常の宛先のボックスに追加（発信者と宛先が異なる場合のみ）
            self.person_histories[to_person].append(message)

    def clear_history(self):
        self.conversation_history = []
        self.info_conversation_history = []
        self.mayor_conversation_history = []
        self.supply_conversation_history = []
        self.infrastructure_conversation_history = []
        # 各人物の会話履歴もクリア
        for person in self.person_histories:
            self.person_histories[person] = []

    def get_conversation_history(self, manager_type: str = "all") -> List[Dict[str, str]]:
        if manager_type == "information":
            return self.info_conversation_history.copy()
        elif manager_type == "mayor":
            return self.mayor_conversation_history.copy()
        elif manager_type == "supply":
            return self.supply_conversation_history.copy()
        elif manager_type == "infrastructure":
            return self.infrastructure_conversation_history.copy()
        else:
            return self.conversation_history.copy()

    def get_person_history(self, person: str) -> List[Dict[str, str]]:
        """特定の人物の会話履歴を取得"""
        if person in self.person_histories:
            return self.person_histories[person].copy()
        return []

    def get_all_person_histories(self) -> Dict[str, List[Dict[str, str]]]:
        """全ての人物の会話履歴を取得"""
        return {person: history.copy() for person, history in self.person_histories.items()}


    def send_message(self, user_message: str) -> str:
        # マネージャー選択の判定
        manager_type = "information"  # デフォルトでは、情報管理（同じ部屋）の人と話すように
        actual_message = user_message

        if user_message.startswith("/information_manager/"):
            manager_type = "information"
            actual_message = user_message[len("/information_manager/"):]
        elif user_message.startswith("/mayor/"):
            manager_type = "mayor"
            actual_message = user_message[len("/mayor/"):]
        elif user_message.startswith("/supply_manager/"):
            manager_type = "supply"
            actual_message = user_message[len("/supply_manager/"):]
        elif user_message.startswith("/infrastructure_manager/"):
            manager_type = "infrastructure"
            actual_message = user_message[len("/infrastructure_manager/"):]

        # 対応するマネージャーを選択
        if manager_type == "information":
            current_manager = self.info_manager
        elif manager_type == "mayor":
            current_manager = self.mayor_manager
        elif manager_type == "supply":
            current_manager = self.supply_manager
        else:
            current_manager = self.infrastructure_manager

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
            if isinstance(info_return_message, dict):
                message = info_return_message.get("message", "")
                to_person = info_return_message.get("to", "Player")
            else:
                message = info_return_message
                to_person = "Player"
            print(f"\n{message}")
            self.add_message("user", "information_manager", message, "information", from_person="information_manager", to_person=to_person)

        supply_return_message = self.supply_manager.handle_return_from_task()
        if supply_return_message:
            if isinstance(supply_return_message, dict):
                message = supply_return_message.get("message", "")
                to_person = supply_return_message.get("to", "Player")
            else:
                message = supply_return_message
                to_person = "Player"
            print(f"\n{message}")
            self.add_message("user", "supply_manager", message, "supply", from_person="supply_manager", to_person=to_person)

        infrastructure_return_message = self.infrastructure_manager.handle_return_from_task()
        if infrastructure_return_message:
            if isinstance(infrastructure_return_message, dict):
                message = infrastructure_return_message.get("message", "")
                to_person = infrastructure_return_message.get("to", "Player")
            else:
                message = infrastructure_return_message
                to_person = "Player"
            print(f"\n{message}")
            self.add_message("user", "infrastructure_manager", message, "infrastructure", from_person="infrastructure_manager", to_person=to_person)

        # 会話中のみ情報付与を一時停止（離席中は情報付与継続）
        if self.info_manager.in_conversation or self.mayor_manager.in_conversation or self.supply_manager.in_conversation or self.infrastructure_manager.in_conversation:
            return False

        # TimeManagerの時刻をInfProviderに同期
        self.inf_provider.simulation_time = current_time

        infos = self.inf_provider.check_scheduled_infos()
        if infos:
            # 付与先とソース別にグループ化
            from collections import defaultdict
            grouped_infos = defaultdict(list)

            for info in infos:
                print(f"\n【情報付与】付与元: {info.source} | 件名: {info.subject} | 付与先: {info.target_team}")
                print(f"   {info.content}")

                # 会話ログにsystemメッセージとして追加
                system_message = f"【情報付与】{info.source}: {info.subject}\n{info.content}"

                # 付与先に応じて適切なマネージャータイプと宛先を決定
                if info.target_team == "supply_team":
                    manager_type = "supply"
                    to_person = "supply_manager"
                elif info.target_team == "infrastructure_team":
                    manager_type = "infrastructure"
                    to_person = "infrastructure_manager"
                else:  # information_team or default
                    manager_type = "information"
                    to_person = "information_team"

                self.add_message("system", "System", system_message, manager_type, from_person="System", to_person=to_person)

                # 付与先とソース別にグループ化（Playerへの報告用）
                if info.target_team in ["supply_team", "infrastructure_team"]:
                    key = (info.target_team, info.source)
                    grouped_infos[key].append(info)

            # グループ化された情報をまとめてPlayerに報告
            for (target_team, source), info_list in grouped_infos.items():
                if target_team == "supply_team":
                    # 複数の場合はリスト、単一の場合はタプルで渡す
                    if len(info_list) > 1:
                        manager_response = self.supply_manager.handle_system_information(source, info_list)
                    else:
                        info = info_list[0]
                        manager_response = self.supply_manager.handle_system_information(source, (info.subject, info.content))
                    self.add_message("assistant", "supply_manager", manager_response, "supply", from_person="supply_manager", to_person="Player")
                elif target_team == "infrastructure_team":
                    # 複数の場合はリスト、単一の場合はタプルで渡す
                    if len(info_list) > 1:
                        manager_response = self.infrastructure_manager.handle_system_information(source, info_list)
                    else:
                        info = info_list[0]
                        manager_response = self.infrastructure_manager.handle_system_information(source, (info.subject, info.content))
                    self.add_message("assistant", "infrastructure_manager", manager_response, "infrastructure", from_person="infrastructure_manager", to_person="Player")

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
