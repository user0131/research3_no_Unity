import os
import json
from typing import List, Dict
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv

from csv_operations import (
    create_csv_file,
    update_csv_from_knowledge,
)
from rag_search import (
    search_and_summarize,
)
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
        self.knowledge_path = Path("./src/knowledge.txt")
        self.inf_provider = InfProvider()  # タスク管理システムを初期化
        self.in_conversation = False  # 会話中フラグ
        self.away_until_time = None  # 戻り時刻（HH:MM形式）
        self.current_task_description = None  # 現在のタスク内容　ロードや、csv更新や、他のタスクの内容をここに入れる。
        self.document_search_result = None  # 文書検索の結果を保存
        self.pending_search_query = None  # 実行待ちの検索クエリ
        # 時刻管理システムを初期化（callbackで付与情報をチェック） 時間が変更すればこれを実施する
        self.time_manager = TimeManager(start_time="10:30", callback=self.check_scheduled_infos, speed_multiplier=3.0)

    def _build_system_prompt(self) -> str:
        """システムプロンプトを構築"""
        knowledge_content = self.knowledge() # 毎回、新しい内容を読み込んでる
        conv_log = "\n".join([f"{msg['role']}: {msg['content']}" for msg in self.conversation_history[-50:]])  # 最新50件

        return f"""
あなたはUSERと一緒に災害対応の仕事を行う枚方市の災害対応職員（人間）です。
地震を想定した避難訓練をUSERと二人で行っています。あなたは相手の話を聞き、簡潔に返答します。

## 災害対応ルール：
- **会話スタイル**: 同僚との自然な会話を心がける。まずは普通に話す。情報の羅列や箇条書きは禁止。話し言葉で応答。
- **情報の扱い**: 付与された情報と会話履歴のみを基に対応。推測や憶測は避ける。
- **不明な事項**: 手持ちの情報にない場合は、状況に応じて自然に調査を提案する程度。
- **作業依頼**: 明確に何かの作業を頼まれた場合のみ「今○○に行ってきてもいいですか？」と確認し、承認されてから実行。

## 利用可能なツール
- **read_document**: 枚方市の災害対応マニュアルから情報を検索・調査する
- **create_csv_file**: 新しいCSVファイルを作成する（データ管理用）
- **update_csv_from_knowledge**: 既存のCSVファイルを更新する（列追加、行追記、セル更新）
- **other_task**: 上記以外のなタスクを実行する

## 情報付与について
- 訓練中に時間が経過すると、関係機関や避難所から新しい情報が自動的に付与されます。
- 【情報付与】と表示される情報は、リアルタイムで入ってくる災害関連の最新情報です。

## あなたが知っている知識（参考程度）
{knowledge_content}

## これまでの会話履歴
{conv_log}
"""

    def _build_messages_for_api(self, user_message: str = None) -> List[Dict[str, str]]:
        """API用のメッセージリストを構築"""
        messages = []

        # システムプロンプト
        messages.append({"role": "system", "content": self._build_system_prompt()})

        # 過去の会話(role付き)を追加
        messages.extend(self.conversation_history)

        # ユーザーメッセージがあれば(2回目以降)新たに追加
        if user_message:
            messages.append({"role": "user", "content": user_message})

        return messages

    def _create_tool_response(self, tool_name: str, args: Dict = None) -> str:
        """ツール実行結果からレスポンスメッセージを作成"""
        if tool_name == "create_csv_file":
            # CSV作成時は引数全体を辞書として保存
            self.pending_search_query = args if args else {}
            return self.execute_task_with_delay("CSV作成", args)
        elif tool_name == "update_csv_from_knowledge":
            # CSV更新時も引数全体を辞書として保存
            self.pending_search_query = args if args else {}
            return self.execute_task_with_delay("CSV更新", args)
        elif tool_name == "read_document":
            # 文書検索時はクエリを保存
            if args and "query" in args:
                self.pending_search_query = args["query"]
            return self.execute_task_with_delay("資料調査", args)
        elif tool_name == "other_task":
            return self.execute_task_with_delay("その仕事", args)
        else:
            return "未対応のツールが呼ばれました。"

    def execute_task_with_delay(self, task_name: str, args: Dict = None) -> str:
        """タスクを実行し、2分後の戻り時刻を設定"""
        from datetime import datetime, timedelta

        current_time = datetime.strptime(self.time_manager.get_current_time(), "%H:%M")
        return_time = current_time + timedelta(minutes=2)
        self.away_until_time = return_time.strftime("%H:%M")
        self.current_task_description = task_name

        # 引数情報があれば、pending_search_queryは既に設定済み
        # タスク名と引数を組み合わせてメッセージを生成
        return f"{task_name}に行ってきます。{self.away_until_time}頃に戻ります。"

    def add_message(self, role: str, content: str):
        self.conversation_history.append({"role": role, "content": content})

    def clear_history(self):
        self.conversation_history = []

    def get_conversation_history(self) -> List[Dict[str, str]]:
        return self.conversation_history.copy()

    def knowledge(self) -> str:
        try:
            return self.knowledge_path.read_text(encoding='utf-8')
        except Exception as e:
            return f"knowledge読み込みエラー: {e}"

    def add_to_knowledge(self, title: str, content: str):
        try:
            current_knowledge = self.knowledge()
            new_entry = f"\n\n## {title}\n{content}"
            updated_knowledge = current_knowledge + new_entry
            self.knowledge_path.write_text(updated_knowledge, encoding='utf-8')
            print(f"aiエージェントの記憶に次を追加しました: {title}")
        except Exception as e:
            print(f"記憶追加エラー: {e}")

    # --- 枚方市防災計画RAG 検索 ---
    def read_document(self, query: str = "") -> str:
    
        # 検索して要約済みの結果を返す。knowledgeに記憶を追加してもいる。
        return search_and_summarize(
            query=query,
            conversation_history=self.conversation_history,
            knowledge_path=self.knowledge_path
        )

    def get_function_definitions(self) -> List[Dict]:
        # function_calling用
        defs = []

        # CSV作成
        defs.append({
            "type": "function",
            "function": {
                "name": "create_csv_file",
                "description": "columns/rows を指定して CSV を生成し、保存パスを返す。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string", "description": "保存ファイル名。日本語名可", "default": "data.csv"},
                        "columns": {"type": "array", "items": {"type": "string"}, "description": "ヘッダ行"},
                        "rows": {"type": "array", "items": {"type": "array", "items": {}}, "description": "初期データ行（任意）"},
                        "description": {"type": "string", "description": "knowledge.txt 用の説明（任意）"}
                    },
                    "required": ["columns"]
                }
            }
        })

        # CSV更新（列追加/行追記/セル更新）
        defs.append({
            "type": "function",
            "function": {
                "name": "update_csv_from_knowledge",
                "description": "CSVファイルの更新専用ツール。CSVファイルに記録を追加したり更新する場合のみ使用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "instruction": {
                            "type": "string",
                            "description": "自然文の、csvの更新に関する指示。"
                        },
                        "update_spec": {
                            "type": "object",
                            "description": "更新計画（任意）。指定しない場合はinstructionからLLMが自動生成。",
                            "properties": {
                                "filename": {"type": "string", "description": "更新対象CSVファイル名"},
                                "add_columns": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "default": {"description": "既存行の既定値"},
                                            "position": {"type": "string", "enum": ["start", "end"]},
                                            "after": {"type": "string", "description": "この列の直後に挿入"}
                                        },
                                        "required": ["name"]
                                    }
                                },
                                "append_rows": {
                                    "type": "array",
                                    "description": "追加する行データの配列。各要素は必ず {\"objects\": [{行データ1}, {行データ2}, ...]} の形式",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "objects": {
                                                "type": "array",
                                                "description": "実際の行データの配列。例: [{\"配達ID\": \"001\", \"品目\": \"水\"}, ...]",
                                                "items": {"type": "object"}
                                            }
                                        },
                                        "required": ["objects"]
                                    }
                                },
                                "update_cells": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "row_index": {"type": "integer"},
                                            "column": {"type": "string"},
                                            "value": {"description": "書き込む値"}
                                        },
                                        "required": ["row_index", "column", "value"]
                                    }
                                },
                                "save_as": {"type": "string", "description": "別名保存先（任意）。指定しない場合は元ファイルを更新"}
                            }
                        }
                    },
                    "required": []
                }
            }
        })

        # RAG検索
        defs.append({
            "type": "function",
            "function": {
                "name": "read_document",
                "description": "RAG検索。枚方市の地震災害関連ドキュメントから、地震の災害対応のマニュアルを取得する。資料調査",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string", "description": "検索クエリ"}},
                    "required": ["query"]
                }
            }
        })

        # その他のタスク
        defs.append({
            "type": "function",
            "function": {
                "name": "other_task",
                "description": "csv作成・更新、資料調査以外のやる事を実行するtool",
                "parameters": {
                    "type": "object",
                    "properties": {"task_description": {"type": "string", "description": "やる内容を簡潔に"}},
                    "required": ["task_description"]
                }
            }
        })

        return defs

    def send_message(self, user_message: str) -> str:
        # 離席中チェック
        if self.away_until_time:
            current_time = self.time_manager.get_current_time()
            if current_time < self.away_until_time:
                # コンソール表示のみ、会話履歴には追加しない。
                print(f"申し訳ありません、現在別の業務中です。{self.away_until_time}頃に戻る予定です。")
                return "" # returnとして何も返さない

        # 会話中フラグをセット（情報付与を一時停止）
        self.in_conversation = True

        try:
            # ユーザーメッセージを履歴に追加
            self.add_message("user", user_message)

            # API用メッセージを構築
            messages = self._build_messages_for_api()

            # OpenAI APIを呼び出し
            response = self.client.chat.completions.create(
                model="gpt-5-mini",
                messages=messages,
                tools=self.get_function_definitions(),
                tool_choice="auto"
            )

            response_message = response.choices[0].message

            # ツール呼び出しがあれば実行
            if getattr(response_message, "tool_calls", None):
                tool_call = response_message.tool_calls[0]
                fname = tool_call.function.name
                args = json.loads(tool_call.function.arguments or "{}")

                if fname:
                    assistant_message = self._create_tool_response(fname, args) # 〇〇に行ってきます。〇〇分後には戻ります

                else:
                    assistant_message = "no_tool"
            # なければメッセージを
            else:
                assistant_message = response_message.content

            # アシスタントメッセージを履歴に追加
            self.add_message("assistant", assistant_message)

            return assistant_message

        finally:
            # 会話終了後フラグをリセット
            self.in_conversation = False

    def check_scheduled_infos(self):
        """スケジュール情報をチェックして表示"""
        current_time = self.time_manager.get_current_time()

        # 戻り時刻チェック
        if self.away_until_time and current_time >= self.away_until_time:
            task_name = self.current_task_description or "業務"

            # 文書検索の場合は実際に検索を実行してから結果を表示
            if task_name == "資料調査" and self.pending_search_query:
                result = self.read_document(self.pending_search_query)
                return_message = f"{task_name}から戻りました！\n\n{result}"
                print(f"\n{return_message}")
                self.add_message("assistant", return_message)
                self.pending_search_query = None
            elif task_name == "CSV作成" and self.pending_search_query:
                # CSV作成を実行
                if isinstance(self.pending_search_query, dict):
                    create_csv_file(**self.pending_search_query)
                    return_message = f"{task_name}から戻りました！"
                else:
                    return_message = f"{task_name}から戻りました！"
                print(f"\n{return_message}")
                self.add_message("assistant", return_message)
                self.pending_search_query = None
            elif task_name == "CSV更新" and self.pending_search_query:
                # CSV更新を実行
                if isinstance(self.pending_search_query, dict):
                    update_csv_from_knowledge(**self.pending_search_query)
                    return_message = f"{task_name}から戻りました！"
                else:
                    return_message = f"{task_name}から戻りました！"
                print(f"\n{return_message}")
                self.add_message("assistant", return_message)
                self.pending_search_query = None
            else:
                return_message = f"{task_name}から戻りました！"
                print(f"\n{return_message}")
                self.add_message("assistant", return_message)
                self.pending_search_query = None

            self.away_until_time = None
            self.current_task_description = None
            self.document_search_result = None

        # 会話中のみ情報付与を一時停止（離席中は情報付与継続）
        if self.in_conversation:
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
                self.add_message("system", system_message)
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
