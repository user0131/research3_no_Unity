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
地震を想定した避難訓練をPlayerと行っています。

## 災害対応ルール：
- **会話スタイル**: 同僚との自然な会話を心がける。まずは普通に話す。情報の羅列や箇条書きは禁止。話し言葉で応答。あなたは相手の話を聞き、簡潔に返答します。ユーザに聞かれたこと以外は極力返さないように。
- **情報の扱い**: あなたの知っている情報は会話履歴と「あなたが知っている知識」のみです。手持ちにない情報の推測や憶測は避けてください
- **作業依頼**: Playerから明確に、具体的に何かの作業を頼まれた場合のみ、作業を実行してください。それ以外は通常の会話をしてください。
- **重要：ツールの使用**: 実際の作業は必ずツールを使って実行してください。会話（テキスト応答）では作業を実行できません。
  - **ツール以外では実行不可**: 会話で「調査します」「作成しました」と言っても実際の作業は実行されません
  - **資料調査**: read_documentツールを使用
  - **CSV作成**: create_csv_fileツールを使用
  - **CSV更新**: update_csv_from_knowledgeツールを使用
  - **CSV内容表示**: show_csv_contentツールを使用（単一または複数ファイル対応、確認系なので許可不要）
  - **CSV一覧表示**: list_all_csv_filesツールを使用（全ファイル一覧、確認系なので許可不要）
  - **必須**: タスクを実行する場合は、必ず適切なツールを呼び出してください。JSON形式の情報やCSV内容を会話で返すことは禁止です。

## 情報付与について
- systemロールにて、【情報付与】と表示されて会話履歴に入る情報は、リアルタイムで入ってくる災害関連の最新情報です。

## 重要
- ユーザに聞かれたこと以外は極力返さないように。

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

    def _record_tool_execution(self, tool_name: str, args: Dict = None):
        """ツール実行記録を知識に追加"""
        try:
            current_time = self.time_manager.get_current_time()
            args = args or {}

            # 引数の整形
            if tool_name == "create_csv_file":
                filename = args.get("filename", "")
                columns = args.get("columns", [])
                args_text = f"ファイル名: {filename}, カラム数: {len(columns)}"
            elif tool_name == "update_csv_from_knowledge":
                instruction = args.get("instruction", "")[:50]
                args_text = f"更新指示: {instruction}..."
            elif tool_name == "read_document":
                query = args.get("query", "")
                args_text = f"検索クエリ: {query}"
            elif tool_name == "show_csv_content":
                filenames = args.get("filenames", [])
                if isinstance(filenames, str):
                    filenames = [filenames]
                args_text = f"ファイル数: {len(filenames)}, ファイル: {', '.join(filenames[:3])}{'...' if len(filenames) > 3 else ''}"
            elif tool_name == "list_all_csv_files":
                args_text = "引数なし"
            else:
                args_text = str(args) if args else "引数なし"

            # 現在のknowledge内容を読み取り
            try:
                current_content = self.knowledge_path.read_text(encoding='utf-8')
            except FileNotFoundError:
                current_content = ""

            # ツール実行記録セクションを探すか作成
            lines = current_content.split('\n')
            tool_section_start = -1

            for i, line in enumerate(lines):
                if line.strip() == "## ツール実行記録":
                    tool_section_start = i
                    break

            # 新しい記録エントリ
            new_entry = f"### {current_time} - {tool_name}\n- {args_text}\n"

            if tool_section_start >= 0:
                # 既存のセクションに追加
                lines.insert(tool_section_start + 1, new_entry)
            else:
                # 新しいセクションを作成
                lines.extend([
                    "",
                    "## ツール実行記録",
                    new_entry
                ])

            # ファイルに書き戻し
            updated_content = '\n'.join(lines)
            self.knowledge_path.write_text(updated_content, encoding='utf-8')

        except Exception as e:
            print(f"ツール実行記録エラー: {e}")

    def _show_csv_content(self, filenames) -> str:
        """CSVファイルの内容を表示（単一または複数対応、information/ディレクトリのみ）"""
        import pandas as pd

        # 文字列が渡された場合はリストに変換
        if isinstance(filenames, str):
            filenames = [filenames]

        if not filenames:
            return "チェックするファイルが指定されていません。"

        result = ""

        for i, filename in enumerate(filenames):
            if i > 0:
                result += "\n\n"

            # 複数ファイルの場合のみヘッダーを付ける
            if len(filenames) > 1:
                result += f"## {filename}\n"

            csv_path = Path(f"./csv/information/{filename}")

            if not csv_path.exists():
                error_msg = "今はCSVファイルを保有していません"
                if len(filenames) == 1:
                    return f"'{filename}' は{error_msg}。"
                else:
                    result += error_msg
                continue

            try:
                df = pd.read_csv(csv_path)

                if len(df) > 0:
                    result += df.to_string(index=False)
                else:
                    result += "データがありません"

            except Exception as e:
                result += f"読み込みエラー: {str(e)}"

        return result

    def _list_all_csv_files(self) -> str:
        """information/ディレクトリ内の全CSVファイル一覧を表示"""
        import os

        csv_dir = Path("./csv/information/")

        if not csv_dir.exists():
            return "information/ディレクトリが存在しません。"

        csv_files = [f for f in os.listdir(csv_dir) if f.endswith('.csv')]

        if not csv_files:
            return "現在、CSVファイルを保有していません。"

        result = "## 保有CSVファイル一覧\n\n"
        for i, filename in enumerate(sorted(csv_files), 1):
            result += f"{i}. {filename}\n"

        return result

    def _process_tool_loop(self, messages: List[Dict], initial_tool_results: List[Dict]) -> str:
        """ループでツール呼び出しを処理（2回目以降対応）"""
        # 最初のツール結果を会話履歴に追加
        messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [tr["tool_call"].model_dump() for tr in initial_tool_results]
        })

        for tr in initial_tool_results:
            messages.append({
                "role": "tool",
                "tool_call_id": tr["tool_call"].id,
                "name": tr["function_name"],
                "content": tr["result"]
            })

        # ループでツール呼び出しを処理
        max_iterations = 5  # 無限ループを防ぐため
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            # LLMに結果を解釈させ、必要に応じて追加ツールを実行
            response = self.client.chat.completions.create(
                model="gpt-5-mini",
                messages=messages,
                tools=self.get_function_definitions(),
                tool_choice="auto"
            )

            message = response.choices[0].message

            # ツール呼び出しがない場合は終了
            if not getattr(message, "tool_calls", None):
                return message.content

            # 追加のツール呼び出しを処理
            tool_results = []
            for tool_call in message.tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments or "{}")

                # ツール実行を記録
                self._record_tool_execution(function_name, function_args)

                # ツール実行
                if function_name == "create_csv_file":
                    self.pending_search_query = function_args if function_args else {}
                    result = self.execute_task_with_delay("CSV作成", function_args)
                elif function_name == "update_csv_from_knowledge":
                    self.pending_search_query = function_args if function_args else {}
                    result = self.execute_task_with_delay("CSV更新", function_args)
                elif function_name == "read_document":
                    if function_args and "query" in function_args:
                        self.pending_search_query = function_args["query"]
                    result = self.execute_task_with_delay("資料調査", function_args)
                elif function_name == "show_csv_content":
                    filenames = function_args.get("filenames") or function_args.get("filename", "")
                    result = self._show_csv_content(filenames)
                elif function_name == "list_all_csv_files":
                    result = self._list_all_csv_files()
                else:
                    result = "未対応のツールが呼ばれました。"

                tool_results.append({
                    "tool_call": tool_call,
                    "function_name": function_name,
                    "result": result
                })

            # 結果を会話履歴に追加
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [tr["tool_call"].model_dump() for tr in tool_results]
            })

            for tr in tool_results:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tr["tool_call"].id,
                    "name": tr["function_name"],
                    "content": tr["result"]
                })

        # 最大反復回数に達した場合
        return "最大反復回数に達しました。処理を終了します。"

    def create_tool_response(self, tool_name: str, args: Dict = None) -> str:
        """ツール実行結果からレスポンスメッセージを作成"""
        args = args or {}

        # ツール実行を記録
        self._record_tool_execution(tool_name, args)

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
        elif tool_name == "show_csv_content":
            # 確認系は即座に実行
            filenames = args.get("filenames") or args.get("filename", "")
            return self._show_csv_content(filenames)
        elif tool_name == "list_all_csv_files":
            # 確認系は即座に実行
            return self._list_all_csv_files()
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
                    create_csv_file(**self.pending_search_query, knowledge_path=str(self.knowledge_path), time_manager=self.time_manager)
                return_message = f"{task_name}から戻りました！"
                self.pending_search_query = None
            elif task_name == "CSV更新" and self.pending_search_query:
                if isinstance(self.pending_search_query, dict):
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
                "description": "CSV ファイルを新規作成する。descriptionにはファイル全体の説明のみ記入し、各カラムの説明は必ずcolumn_descriptionsに記入すること。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string", "description": "保存ファイル名。日本語名可", "default": "data.csv"},
                        "columns": {"type": "array", "items": {"type": "string"}, "description": "ヘッダ行。例: ['氏名', '年齢', '住所', '連絡先']"},
                        "rows": {"type": "array", "items": {"type": "array", "items": {}}, "description": "初期データ行（任意）"},
                        "description": {"type": "string", "description": "CSVファイル全体の用途・目的の説明。カラムの説明はここには書かずcolumn_descriptionsに記入。例: '避難者の管理用名簿'"},
                        "column_descriptions": {"type": "object", "description": "【必須】各カラムの詳細説明。キーはカラム名、値は説明文。例: {'氏名': '避難者の氏名を記入', '年齢': '避難者の年齢を数値で記入', '住所': '避難者の現住所を記入', '連絡先': '電話番号やメールアドレス等の連絡先'}"}
                    },
                    "required": ["columns", "description", "column_descriptions"]
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

        # CSV内容表示（単一または複数対応）
        defs.append({
            "type": "function",
            "function": {
                "name": "show_csv_content",
                "description": "指定されたCSVファイルの内容を表示する。単一ファイルまたは複数ファイルに対応。ファイルが存在しない場合はエラーメッセージを返す。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filenames": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "表示するCSVファイル名のリスト（拡張子含む）"
                        }
                    },
                    "required": ["filenames"]
                }
            }
        })

        # 全CSV一覧表示
        defs.append({
            "type": "function",
            "function": {
                "name": "list_all_csv_files",
                "description": "全ファイル一覧を表示する。",
                "parameters": {
                    "type": "object",
                    "properties": {}
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

        # ツール呼び出しがあれば実行（複数対応）
        if getattr(response_message, "tool_calls", None):
            tool_results = []

            # 各ツールを実行
            for tool_call in response_message.tool_calls:
                fname = tool_call.function.name
                args = json.loads(tool_call.function.arguments or "{}")

                if fname:
                    result = self.create_tool_response(fname, args)
                    tool_results.append({
                        "tool_call": tool_call,
                        "function_name": fname,
                        "result": result
                    })

            if tool_results:
                # 確認系ツールかどうかをチェック
                confirmation_tools = ["show_csv_content", "list_all_csv_files"]
                has_confirmation_tools = any(tr["function_name"] in confirmation_tools for tr in tool_results)

                if has_confirmation_tools:
                    # 確認系のみの場合は、ループでツール呼び出しを処理
                    assistant_message = self._process_tool_loop(messages, tool_results)
                else:
                    # その他の場合（実行系ツール）
                    assistant_message = "\n\n".join([tr["result"] for tr in tool_results])
            else:
                assistant_message = "no_tool"
        else:
            assistant_message = response_message.content

        return assistant_message, "information_manager"