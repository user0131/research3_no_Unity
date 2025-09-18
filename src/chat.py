import os
import json
from typing import List, Dict
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv

from src.models_forms import (
    create_csv_file,
    update_csv_from_knowledge,
)
from src.rag_search import (
    search_and_summarize,
)
from src.inf_provider import InfProvider

load_dotenv()





# ------------------------------------------------------------
# メイン：チャット（ツール：作成/検索/更新）
# ------------------------------------------------------------
class ChatWithMemory:
    def __init__(self):
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")

        self.client = OpenAI(api_key=api_key)
        self.conversation_history: List[Dict[str, str]] = []
        self.knowledge_path = Path("./src/knowledge.txt")
        self.inf_provider = InfProvider()  # タスク管理システムを初期化

        knowledge_content = self.knowledge()
        self.base_system_content = f"""
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
        # 検索して要約済みの結果を返す
        return search_and_summarize(
            query=query,
            conversation_history=self.conversation_history,
            system_content=self.base_system_content,
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
                "description": "form_spec(JSON: columns/rows) もしくは columns/rows を直接指定して CSV を生成し、保存パスを返す。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string", "description": "保存ファイル名。日本語名可", "default": "data.csv"},
                        "form_spec": {"type": "object", "description": "CSVテンプレのスキーマ（columns/rows/description/delimiter/quotechar）"},
                        "columns": {"type": "array", "items": {"type": "string"}, "description": "ヘッダ行（form_spec の代替）"},
                        "rows": {"type": "array", "items": {"type": "array", "items": {}}, "description": "初期データ行（任意）"},
                        "description": {"type": "string", "description": "knowledge.txt 用の説明（任意）"},
                        "delimiter": {"type": "string", "description": "区切り文字（既定 ,）"},
                        "quotechar": {"type": "string", "description": "クォート文字（既定 \")"}
                    },
                    "required": []
                }
            }
        })

        # CSV更新（列追加/行追記/セル更新）
        defs.append({
            "type": "function",
            "function": {
                "name": "update_csv_from_knowledge",
                "description": "knowledge.txt に記録されたCSVから対象を選び、指示に基づく更新（列追加/行追記/セル更新）を行って保存する。update_spec を直接渡してもよい。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "instruction": {
                            "type": "string",
                            "description": "自然文の指示。例: 『在庫台帳に列「担当者」を追加して、今日の入庫分を1行追記』"
                        },
                        "update_spec": {
                            "type": "object",
                            "description": "更新計画。LLMが自動設計して渡すことを想定。",
                            "properties": {
                                "filename": {"type": "string", "description": "更新対象CSVのフルパス。knowledgeの候補以外は不可。"},
                                "select_by_description": {"type": "string", "description": "説明/タイトルから選ぶキーワード（filenameが無い場合）"},
                                "delimiter": {"type": "string"},
                                "quotechar": {"type": "string"},
                                "add_columns": {
                                    "type": "array",
                                    "description": "列の追加。全既存行に default を埋める。",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "default": {"description": "既存行に入れる既定値", "nullable": True},
                                            "position": {"type": "string", "enum": ["start","end"], "default": "end"},
                                            "after": {"type": "string", "description": "この列の直後に挿入（positionより優先）"}
                                        },
                                        "required": ["name"]
                                    }
                                },
                                "append_rows": {
                                    "type": "array",
                                    "description": "行の追記。headers/rows または objects のいずれか（両方可）。",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "headers": {"type": "array", "items": {"type": "string"}},
                                            "rows": {"type": "array", "items": {"type": "array", "items": {}}},
                                            "objects": {"type": "array", "items": {"type": "object"}}
                                        }
                                    }
                                },
                                "set_cells": {
                                    "type": "array",
                                    "description": "任意セルを書き換え（行インデックス基準）。",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "row_index": {"type": "integer", "description": "0始まりでヘッダーを除いたデータ行のインデックス"},
                                            "column": {"type": "string", "description": "列名"},
                                            "value": {"description": "書き込む値"}
                                        },
                                        "required": ["row_index","column","value"]
                                    }
                                },
                                "save_as": {"type": "string", "description": "別名保存先（任意）"}
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
                "description": "RAG検索。枚方市の地震災害関連ドキュメントから、章・節・ページを含む根拠付きの抜粋を返す。",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string", "description": "検索クエリ"}},
                    "required": ["query"]
                }
            }
        })

        return defs

    def send_message(self, user_message: str) -> str:
        self.add_message("user", user_message)

        # システムプロンプトにタスクを追加
        system_content_with_tasks = self.base_system_content

        system_prompt = {"role": "system", "content": system_content_with_tasks}
        messages = [system_prompt] + self.conversation_history

        response = self.client.chat.completions.create(
            model="gpt-5-mini",
            messages=messages + [
                {"role": "system", "content":
                 "CSVの作成依頼なら create_csv_file、更新依頼なら update_csv_from_knowledge、"
                 "調査許可があるなら read_document を呼び出す。"}
            ],
            tools=self.get_function_definitions(),
            tool_choice="auto"
        )

        response_message = response.choices[0].message

        if getattr(response_message, "tool_calls", None):
            tool_call = response_message.tool_calls[0]
            fname = tool_call.function.name
            args = json.loads(tool_call.function.arguments or "{}")

            if fname == "create_csv_file":
                filepath = create_csv_file(**args)
                assistant_message = f"CSVテンプレートを作成しました。保存先は「{filepath}」です。"

            elif fname == "update_csv_from_knowledge":
                saved = update_csv_from_knowledge(**args)
                assistant_message = f"CSVを更新しました。保存先は「{saved}」です。"

            elif fname == "read_document":
                query = (args.get("query") or "").strip()
                print(f"📚 調べています... (キーワード: {query})")
                # search_and_summarizeが要約済みの結果を返す
                assistant_message = self.read_document(query)

            else:
                assistant_message = "未対応のツールが呼ばれました。"
        else:
            assistant_message = response_message.content

        self.add_message("assistant", assistant_message)

        return assistant_message


# ------------------------------------------------------------
# CLI
# ------------------------------------------------------------
def main():
    print("commanda:")
    print("   /clear   - 会話履歴をクリア")
    print("   /history - 会話履歴を表示")
    print("   /tasks   - 現在のタスクを表示")
    print("   /exit    - 終了")

    try:
        chat = ChatWithMemory()
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
