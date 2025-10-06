import json
from typing import List, Dict, Optional
from pathlib import Path
from datetime import datetime, timedelta
from openai import OpenAI

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))


class Mayor:
    """市長クラス"""

    def __init__(self, client: OpenAI, time_manager):
        self.client = client
        self.knowledge_path = Path("./src/knowledge/knowledge_mayor.txt")
        self.csv_base_path = Path("./csv/information")
        self.time_manager = time_manager
        self.in_conversation = False
        self.away_until_time = None
        self.current_task_description = None
        self.pending_task_args = None
        self.manager = None  # ChatWithMemoryへの参照

    def build_system_prompt(self) -> str:
        """システムプロンプトを構築"""
        knowledge_content = self.get_knowledge()

        return f"""
あなたは市長です。
地震を想定した避難訓練を"Player"と現在行っています。

# 以下はPlayerに無理に開示しなくて大丈夫な情報です。
## 災害対応ルール：
- **役職と責任**: 職員との自然な会話を心がける。まずは普通に話す。情報の羅列や箇条書きは禁止。話し言葉で応答。あなたは相手の話を聞き、簡潔に返答します。ユーザに聞かれたこと以外は極力返さないように。
- **会話スタイル**: 市長として威厳を持ちつつも、職員やPlayerに対して親身に接します。
- **情報の扱い**: 推測や憶測は避け、事実に基づいた判断を行います。
- **作業依頼**: Playerから明確に、具体的に何かの作業を頼まれた場合のみ、作業を実行してください。それ以外は通常の会話をしてください。
- **重要：ツールの使用**: 実際の作業は必ずツールを使って実行してください。会話（テキスト応答）では作業を実行できません。
  - **市民への広報・避難指示**: public_announcementツールを使用
  - **知事との連絡**: contact_governorツールを使用
  - **府下市町村との連絡**: contact_municipalitiesツールを使用
  - **各部署への一斉連絡**: broadcast_to_departmentsツールを使用。情報管理室・物資管理班・建物・土木対策班に同時に連絡される
  - **CSV内容表示**: show_csv_contentツールを使用（単一または複数ファイル対応、確認系なので許可不要）
  - **CSV一覧表示**: list_all_csv_filesツールを使用（全ファイル一覧、確認系なので許可不要）
  - **必須**: タスクを実行する場合は、必ず適切なツールを呼び出してください。

## 情報付与について
- systemロールにて、【情報付与】と表示されて会話履歴に入る情報は、リアルタイムで入ってくる災害関連の最新情報です。

## 重要
- 自然な会話を心がけてください。選択肢の提示や提案はせず、Playerから言われたことに簡潔に反応してください。
- Playerに聞かれたこと以外は極力返さないように。
- Playerに支持されたこと以外は極力行わないように。

## あなたが知っている知識
{knowledge_content if knowledge_content.strip() else "まだ知識がありません。"}

## これまでの会話履歴
以下に続くメッセージは、Playerとあなた(mayor)のこれまでの会話履歴です。
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
            print(f"市長の記憶に次を追加しました: {title}")
        except Exception as e:
            print(f"記憶追加エラー: {e}")

    def _execute_public_announcement(self, content: str, urgency: str) -> str:
        """市民への広報・避難指示を実行"""
        import pandas as pd

        # CSVファイルパス
        csv_path = self.csv_base_path / "【市長専用】市民への広報記録.csv"

        # 現在時刻を取得
        current_time = self.time_manager.get_current_time()

        # 新しい記録
        new_record = {
            "発信日時": current_time,
            "内容": content,
            "緊急度": urgency,
            "発信者": "市長"
        }

        # 既存CSVに追加
        df = pd.read_csv(csv_path)
        df = pd.concat([df, pd.DataFrame([new_record])], ignore_index=True)
        df.to_csv(csv_path, index=False, encoding='utf-8')

        return f"市民への広報を実施しました。\n内容: {content}\n緊急度: {urgency}"

    def _execute_contact_governor(self, subject: str, content: str) -> str:
        """知事との連絡を実行"""
        import pandas as pd

        # CSVファイルパス
        csv_path = self.csv_base_path / "【市長専用】知事との連絡記録.csv"

        # 現在時刻を取得
        current_time = self.time_manager.get_current_time()

        # 新しい記録
        new_record = {
            "連絡日時": current_time,
            "件名": subject,
            "内容": content,
            "発信者": "市長",
            "宛先": "府知事"
        }

        # 既存CSVに追加
        df = pd.read_csv(csv_path)
        df = pd.concat([df, pd.DataFrame([new_record])], ignore_index=True)
        df.to_csv(csv_path, index=False, encoding='utf-8')

        return f"知事への連絡を実施しました。\n件名: {subject}\n内容: {content}"

    def _execute_contact_municipalities(self, subject: str, content: str, target_municipalities: List[str] = None) -> str:
        """府下市町村との連絡を実行"""
        import pandas as pd

        # CSVファイルパス
        csv_path = self.csv_base_path / "【市長専用】市町村連絡記録.csv"

        # 現在時刻を取得
        current_time = self.time_manager.get_current_time()

        # 対象市町村のデフォルト設定
        if target_municipalities is None:
            target_municipalities = ["全市町村"]

        # 新しい記録
        new_record = {
            "連絡日時": current_time,
            "件名": subject,
            "内容": content,
            "発信者": "市長",
            "宛先": ", ".join(target_municipalities)
        }

        # 既存CSVに追加
        df = pd.read_csv(csv_path)
        df = pd.concat([df, pd.DataFrame([new_record])], ignore_index=True)
        df.to_csv(csv_path, index=False, encoding='utf-8')

        return f"府下市町村への連絡を実施しました。\n宛先: {', '.join(target_municipalities)}\n件名: {subject}\n内容: {content}"

    def _execute_broadcast_to_departments(self, message: str, departments: List[str] = None) -> str:
        """各部署への一斉連絡を実行"""
        # デフォルトの部署設定
        if departments is None:
            departments = ["information_team", "supply_team", "infrastructure_team"]

        # ChatWithMemoryのインスタンスを通じて各部署に連絡
        if self.manager:
            for dept in departments:
                # システムメッセージとして各部署に追加
                system_message = f"【市長からの指示】\n{message}"

                if dept == "information_team":
                    manager_type = "information"
                elif dept == "supply_team":
                    manager_type = "supply"
                elif dept == "infrastructure_team":
                    manager_type = "infrastructure"
                else:
                    continue

                self.manager.add_message("system", "mayor", system_message, manager_type,
                                       from_person="mayor", to_person=dept)

        dept_names_jp = {
            "information_team": "危機管理室",
            "supply_team": "物資管理班",
            "infrastructure_team": "建物・産業・土木対策班"
        }
        dept_names = [dept_names_jp.get(d, d) for d in departments]

        return f"各部署への一斉連絡を実施しました。\n対象: {', '.join(dept_names)}\n内容: {message}"

    def _record_tool_execution(self, tool_name: str, args: Dict = None):
        """ツール実行記録を知識に追加"""
        try:
            current_time = self.time_manager.get_current_time()
            args = args or {}

            # 引数の整形
            if tool_name == "public_announcement":
                content = args.get("content", "")[:50]
                urgency = args.get("urgency", "")
                args_text = f"内容: {content}..., 緊急度: {urgency}"
            elif tool_name == "contact_governor":
                subject = args.get("subject", "")
                args_text = f"件名: {subject}"
            elif tool_name == "contact_municipalities":
                subject = args.get("subject", "")
                municipalities = args.get("target_municipalities", [])
                args_text = f"件名: {subject}, 対象: {len(municipalities)}市町村"
            elif tool_name == "broadcast_to_departments":
                message = args.get("message", "")[:50]
                args_text = f"メッセージ: {message}..."
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
        """CSVファイルの内容を表示"""
        import pandas as pd

        if isinstance(filenames, str):
            filenames = [filenames]

        if not filenames:
            return "チェックするファイルが指定されていません。"

        result = ""

        for i, filename in enumerate(filenames):
            if i > 0:
                result += "\n\n"

            if len(filenames) > 1:
                result += f"## {filename}\n"

            csv_path = self.csv_base_path / filename

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

        csv_dir = self.csv_base_path

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
        """ループでツール呼び出しを処理"""
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

        max_iterations = 5
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            response = self.client.chat.completions.create(
                model="gpt-5-mini",
                messages=messages,
                tools=self.get_function_definitions(),
                tool_choice="auto"
            )

            message = response.choices[0].message

            if not getattr(message, "tool_calls", None):
                return message.content

            tool_results = []
            for tool_call in message.tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments or "{}")

                self._record_tool_execution(function_name, function_args)

                if function_name == "public_announcement":
                    self.pending_task_args = function_args if function_args else {}
                    result = self.execute_task_with_delay("市民への広報", function_args)
                elif function_name == "contact_governor":
                    self.pending_task_args = function_args if function_args else {}
                    result = self.execute_task_with_delay("知事との連絡", function_args)
                elif function_name == "contact_municipalities":
                    self.pending_task_args = function_args if function_args else {}
                    result = self.execute_task_with_delay("市町村連絡", function_args)
                elif function_name == "broadcast_to_departments":
                    # 一斉連絡は即座に実行
                    message = function_args.get("message", "")
                    departments = function_args.get("departments")
                    result = self._execute_broadcast_to_departments(message, departments)
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

        return "最大反復回数に達しました。処理を終了します。"

    def create_tool_response(self, tool_name: str, args: Dict = None) -> str:
        """ツール実行結果からレスポンスメッセージを作成"""
        args = args or {}

        self._record_tool_execution(tool_name, args)

        if tool_name == "public_announcement":
            self.pending_task_args = args if args else {}
            return self.execute_task_with_delay("市民への広報", args)
        elif tool_name == "contact_governor":
            self.pending_task_args = args if args else {}
            return self.execute_task_with_delay("知事との連絡", args)
        elif tool_name == "contact_municipalities":
            self.pending_task_args = args if args else {}
            return self.execute_task_with_delay("市町村連絡", args)
        elif tool_name == "broadcast_to_departments":
            # 一斉連絡は即座に実行
            message = args.get("message", "")
            departments = args.get("departments")
            return self._execute_broadcast_to_departments(message, departments)
        elif tool_name == "show_csv_content":
            filenames = args.get("filenames") or args.get("filename", "")
            return self._show_csv_content(filenames)
        elif tool_name == "list_all_csv_files":
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

            if task_name == "市民への広報" and self.pending_task_args:
                if isinstance(self.pending_task_args, dict):
                    content = self.pending_task_args.get("content", "")
                    urgency = self.pending_task_args.get("urgency", "通常")
                    result = self._execute_public_announcement(content, urgency)
                return_message = f"{task_name}から戻りました！\n{result}"
                self.pending_task_args = None
            elif task_name == "知事との連絡" and self.pending_task_args:
                if isinstance(self.pending_task_args, dict):
                    subject = self.pending_task_args.get("subject", "")
                    content = self.pending_task_args.get("content", "")
                    result = self._execute_contact_governor(subject, content)
                return_message = f"{task_name}から戻りました！\n{result}"
                self.pending_task_args = None
            elif task_name == "市町村連絡" and self.pending_task_args:
                if isinstance(self.pending_task_args, dict):
                    subject = self.pending_task_args.get("subject", "")
                    content = self.pending_task_args.get("content", "")
                    municipalities = self.pending_task_args.get("target_municipalities")
                    result = self._execute_contact_municipalities(subject, content, municipalities)
                return_message = f"{task_name}から戻りました！\n{result}"
                self.pending_task_args = None
            else:
                return_message = f"{task_name}から戻りました！"
                self.pending_task_args = None

            self.away_until_time = None
            self.current_task_description = None

            return return_message

        return None

    def get_function_definitions(self) -> List[Dict]:
        """Function calling用の定義を取得"""
        defs = []

        # 市民への広報・避難指示
        defs.append({
            "type": "function",
            "function": {
                "name": "public_announcement",
                "description": "市民への広報・避難指示を実施する。実施内容はCSVに記録される。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "広報・避難指示の内容"},
                        "urgency": {
                            "type": "string",
                            "description": "緊急度",
                            "enum": ["緊急", "重要", "通常"],
                            "default": "通常"
                        }
                    },
                    "required": ["content"]
                }
            }
        })

        # 知事との連絡
        defs.append({
            "type": "function",
            "function": {
                "name": "contact_governor",
                "description": "府知事との連絡を実施する。連絡内容はCSVに記録される。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "subject": {"type": "string", "description": "連絡の件名"},
                        "content": {"type": "string", "description": "連絡内容"}
                    },
                    "required": ["subject", "content"]
                }
            }
        })

        # 府下市町村との連絡
        defs.append({
            "type": "function",
            "function": {
                "name": "contact_municipalities",
                "description": "府下市町村との連絡を実施する。連絡内容はCSVに記録される。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "subject": {"type": "string", "description": "連絡の件名"},
                        "content": {"type": "string", "description": "連絡内容"},
                        "target_municipalities": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "連絡対象の市町村名リスト（省略時は全市町村）"
                        }
                    },
                    "required": ["subject", "content"]
                }
            }
        })

        # 各部署への一斉連絡
        defs.append({
            "type": "function",
            "function": {
                "name": "broadcast_to_departments",
                "description": "各部署への一斉連絡を実施する。情報管理室、物資管理班、建物・産業・土木対策班に同時に連絡される。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {"type": "string", "description": "連絡内容"},
                        "departments": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": ["information_team", "supply_team", "infrastructure_team"]
                            },
                            "description": "連絡対象の部署（省略時は全部署）"
                        }
                    },
                    "required": ["message"]
                }
            }
        })

        # CSV内容表示
        defs.append({
            "type": "function",
            "function": {
                "name": "show_csv_content",
                "description": "CSVファイルの内容を表示",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filenames": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "表示するCSVファイル名のリスト"
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
                "description": "全ファイル一覧を表示",
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

        if getattr(response_message, "tool_calls", None):
            tool_results = []

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
                confirmation_tools = ["show_csv_content", "list_all_csv_files", "broadcast_to_departments"]
                has_confirmation_tools = any(tr["function_name"] in confirmation_tools for tr in tool_results)

                if has_confirmation_tools:
                    assistant_message = self._process_tool_loop(messages, tool_results)
                else:
                    assistant_message = "\n\n".join([tr["result"] for tr in tool_results])
            else:
                assistant_message = "no_tool"
        else:
            assistant_message = response_message.content

        return assistant_message, "mayor"