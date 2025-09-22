import json
from typing import List, Dict, Optional
from pathlib import Path
from datetime import datetime, timedelta
from openai import OpenAI

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from csv_operations import create_csv_file, update_csv_from_knowledge
from rag_search import search_and_summarize


class InformationManager:
    """情報管理担当者クラス"""

    def __init__(self, client: OpenAI, time_manager):
        self.client = client
        self.knowledge_path = Path("./src/knowledge/knowledge_information.txt")
        self.csv_base_path = Path("./csv/information")
        self.time_manager = time_manager
        self.in_conversation = False
        self.away_until_time = None
        self.current_task_description = None
        self.document_search_result = None
        self.pending_search_query = None

    def build_system_prompt(self) -> str:
        """システムプロンプトを構築"""
        knowledge_content = self.get_knowledge()

        return f"""
あなたは"Player"と一緒に災害対応の仕事を行う災害対応職員です。あなたは情報管理担当の職員です。あなたは"information_manager"です。
地震を想定した避難訓練をUSERと二人で行っています。

## 災害対応ルール：
- **会話スタイル**: 同僚との自然な会話を心がける。まずは普通に話す。情報の羅列や箇条書きは禁止。話し言葉で応答。あなたは相手の話を聞き、簡潔に返答します。
- **情報の扱い**: あなたの知っている情報は会話履歴と「あなたが知っている知識」に書かれていることのみです。手持ちにない情報の推測や憶測は避けてください
- **作業依頼**: 明確に何かの作業を頼まれた場合のみ、今やっていいか確認し、Playerから承認されてから実行してください。それ以外は通常の会話をしてください。

## 情報付与について
- systemロールにて、【情報付与】と表示されて会話履歴に入る情報は、リアルタイムで入ってくる災害関連の最新情報です。

## あなたが知っている知識
{knowledge_content if knowledge_content.strip() else "まだ知識がありません。"}

## これまでの会話履歴
以下に続くメッセージは、Playerとあなた(information_manager)のこれまでの会話履歴です。
"""

    def get_knowledge(self) -> str:
        """知識を取得"""
        try:
            return self.knowledge_path.read_text(encoding='utf-8')
        except Exception as e:
            return f"knowledge読み込みエラー: {e}"

    def add_to_knowledge(self, title: str, content: str):
        """知識に追加"""
        try:
            current_knowledge = self.get_knowledge()
            new_entry = f"\n\n## {title}\n{content}"
            updated_knowledge = current_knowledge + new_entry
            self.knowledge_path.write_text(updated_knowledge, encoding='utf-8')
            print(f"aiエージェントの記憶に次を追加しました: {title}")
        except Exception as e:
            print(f"記憶追加エラー: {e}")

    def read_document(self, query: str, messages: List[Dict[str, str]]) -> str:
        """防災計画RAG検索"""
        # messagesから会話履歴部分を抽出（systemロール以外）
        conversation_history = [msg for msg in messages if msg.get('role') != 'system']

        return search_and_summarize(
            query=query,
            conversation_history=conversation_history,
            knowledge_path=self.knowledge_path
        )

    def create_tool_response(self, tool_name: str, args: Dict = None) -> str:
        """ツール実行結果からレスポンスメッセージを作成"""
        if tool_name == "create_csv_file":
            self.pending_search_query = args if args else {}
            return self.execute_task_with_delay("CSV作成", args)
        elif tool_name == "update_csv_from_knowledge":
            self.pending_search_query = args if args else {}
            return self.execute_task_with_delay("CSV更新", args)
        elif tool_name == "read_document":
            if args and "query" in args:
                self.pending_search_query = args["query"]
            return self.execute_task_with_delay("資料調査", args)
        else:
            return "未対応のツールが呼ばれました。"

    def execute_task_with_delay(self, task_name: str, args: Dict = None) -> str:
        """タスクを実行し、2分後の戻り時刻を設定"""
        current_time = datetime.strptime(self.time_manager.get_current_time(), "%H:%M")
        return_time = current_time + timedelta(minutes=2)
        self.away_until_time = return_time.strftime("%H:%M")
        self.current_task_description = task_name
        return f"{task_name}に行ってきます。{self.away_until_time}頃に戻ります。"

    def check_if_available(self) -> Optional[str]:
        """利用可能かチェック（離席中の場合はメッセージを返す）"""
        if self.away_until_time:
            current_time = self.time_manager.get_current_time()
            if current_time < self.away_until_time:
                task_name = self.current_task_description or "業務"
                return f"申し訳ありません、現在{task_name}中です。"
        return None

    def handle_return_from_task(self, messages: List[Dict[str, str]] = None) -> Optional[str]:
        """タスクから戻った際の処理"""
        current_time = self.time_manager.get_current_time()

        if self.away_until_time and current_time >= self.away_until_time:
            task_name = self.current_task_description or "業務"

            if task_name == "資料調査" and self.pending_search_query:
                result = self.read_document(self.pending_search_query, messages or [])
                return_message = f"{task_name}から戻りました！\n\n{result}"
                self.pending_search_query = None
            elif task_name == "CSV作成" and self.pending_search_query:
                if isinstance(self.pending_search_query, dict):
                    # CSVの保存先をinformationフォルダに変更
                    if 'filename' in self.pending_search_query:
                        filename = self.pending_search_query['filename']
                        self.pending_search_query['filename'] = f"information/{filename}"
                    create_csv_file(**self.pending_search_query, knowledge_path=str(self.knowledge_path), time_manager=self.time_manager)
                return_message = f"{task_name}から戻りました！"
                self.pending_search_query = None
            elif task_name == "CSV更新" and self.pending_search_query:
                if isinstance(self.pending_search_query, dict):
                    # CSVの更新対象をinformationフォルダに変更
                    if 'update_spec' in self.pending_search_query and 'filename' in self.pending_search_query['update_spec']:
                        filename = self.pending_search_query['update_spec']['filename']
                        self.pending_search_query['update_spec']['filename'] = f"information/{filename}"
                    update_csv_from_knowledge(**self.pending_search_query, knowledge_path=str(self.knowledge_path), time_manager=self.time_manager)
                return_message = f"{task_name}から戻りました！"
                self.pending_search_query = None
            else:
                return_message = f"{task_name}から戻りました！"
                self.pending_search_query = None

            self.away_until_time = None
            self.current_task_description = None
            self.document_search_result = None

            return return_message

        return None

    def get_function_definitions(self) -> List[Dict]:
        """Function calling用の定義を取得"""
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
                        "description": {"type": "string", "description": "CSVファイルの用途説明（どのような時にこのファイルを使うかを説明）"},
                        "column_descriptions": {"type": "object", "description": "各カラムの説明辞書 例: {'カラム名': '説明', ...}"}
                    },
                    "required": ["columns"]
                }
            }
        })

        # CSV更新
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
                "description": "RAG検索。市の地震災害関連ドキュメントから、地震の災害対応のマニュアルを取得する。資料調査",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string", "description": "検索クエリ"}},
                    "required": ["query"]
                }
            }
        })


        return defs

    def process_response(self, messages: List[Dict[str, str]]) -> tuple[str, Optional[str]]:
        """OpenAI APIレスポンスを処理してメッセージとロール名を返す"""
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
                assistant_message = self.create_tool_response(fname, args)
            else:
                assistant_message = "no_tool"
        else:
            assistant_message = response_message.content

        return assistant_message, "information_manager"