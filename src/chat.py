import os
import json
from typing import List, Dict
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv

from src.csv_operations import (
    create_csv_file,
    update_csv_from_knowledge,
)
from src.rag_search import (
    search_and_summarize,
)
from src.inf_provider import InfProvider
from src.time_manager import TimeManager

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

        # 時刻管理システムを初期化（コールバックでスケジュール情報をチェック）
        self.time_manager = TimeManager(start_time="10:30", callback=self.check_scheduled_infos)

    def _build_system_prompt(self) -> str:
        """システムプロンプトを構築"""
        knowledge_content = self.knowledge()
        conv_log = "\n".join([f"{msg['role']}: {msg['content']}" for msg in self.conversation_history[-50:]])  # 最新50件

        return f"""
あなたはUSERと一緒に災害対応の仕事を行う枚方市の災害対応職員（人間）です。
地震を想定した避難訓練をUSERと二人で行っています。あなたは相手の話を聞き、簡潔に返答します。

厳格なルール：
- あなたは「あなたが知っている知識」と「これまでの会話履歴」から得た情報以外、災害情報に関する知識は知りません。
- 知らないことは推測せず分かりません。調べましょうか？と確認し、了承が得られた場合のみ `read_document` を使います。
- CSVテンプレ作成は、会話から `form_spec`（JSON：columns/rows）を設計するか、`columns/rows` を直接受け取り、`create_csv_file` を呼びます。
- 追記依頼が来たら、`update_csv_from_knowledge` を呼び、knowledge に保存されたCSVの中から適切なファイルを選び、計画に基づき更新を行います。
- 作成・更新・検索の結果は、knowledge にパスと説明/計画や検索ログを追記します。
- 箇条書き禁止。音声会話を想定した自然な口調で。

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

        # ツール使用のヒントを追加
        messages.append({
            "role": "system",
            "content": "CSVの作成依頼なら create_csv_file、更新依頼なら update_csv_from_knowledge、調査許可があるなら read_document を呼び出す。"
        })

        return messages

    def _create_tool_response(self, tool_name: str, result: any) -> str:
        """ツール実行結果からレスポンスメッセージを作成"""
        if tool_name == "create_csv_file":
            return f"CSVテンプレートを作成しました。保存先は「{result}」です。"
        elif tool_name == "update_csv_from_knowledge":
            return f"CSVを更新しました。保存先は「{result}」です。"
        elif tool_name == "read_document":
            return result  # search_and_summarizeの結果をそのまま返す（ちゃんと会話文になってるはず）
        else:
            return "未対応のツールが呼ばれました。"

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
            print(f"📝 知識ベースに追加しました: {title}")
        except Exception as e:
            print(f"知識ベース追加エラー: {e}")

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
                "description": "knowledge.txt に記録されたCSVから対象を選び、指示に基づく更新（列追加/行追記/セル更新）を行って保存する。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "instruction": {
                            "type": "string",
                            "description": "自然文の指示。例: 『在庫台帳に列「担当者」を追加して、今日の入庫分を1行追記』"
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
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "objects": {"type": "array", "items": {"type": "object"}}
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
                "description": "RAG検索。枚方市の地震災害関連ドキュメントから、地震の災害対応のマニュアルを取得する",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string", "description": "検索クエリ"}},
                    "required": ["query"]
                }
            }
        })

        return defs

    def send_message(self, user_message: str) -> str:
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

            # ツールを実行
            if fname == "create_csv_file":
                result = create_csv_file(**args)
            elif fname == "update_csv_from_knowledge":
                result = update_csv_from_knowledge(**args)
            elif fname == "read_document":
                query = (args.get("query") or "").strip()
                print(f"📚 調べています... (キーワード: {query})")
                result = self.read_document(query)
            else:
                result = None

            # レスポンスメッセージを作成
            assistant_message = self._create_tool_response(fname, result)
        else:
            assistant_message = response_message.content

        # アシスタントメッセージを履歴に追加
        self.add_message("assistant", assistant_message)

        return assistant_message

    def check_scheduled_infos(self):
        """スケジュール情報をチェックして表示"""
        # TimeManagerの時刻をInfProviderに同期
        self.inf_provider.simulation_time = self.time_manager.get_current_time()

        infos = self.inf_provider.check_scheduled_infos()
        if infos:
            for info in infos:
                print(f"\n📢 【{info.source}】{info.subject}")
                print(f"   {info.content}")
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
        print(f"⏰ 災害対応訓練開始 - 現在時刻: {chat.time_manager.get_current_time()}")
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
                    for i, msg in enumerate(history, 1):
                        role = msg["role"].upper()
                        if role != "SYSTEM":
                            print(f"{role}: {msg['content']}")
                else:
                    print("会話履歴はありません")
                print()
                continue
            elif user_input.lower() == "/time":
                current_time = chat.time_manager.get_current_time()
                print(f"⏰ 現在時刻: {current_time}")
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
