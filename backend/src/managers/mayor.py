import json
from typing import List, Dict, Optional
from pathlib import Path
from datetime import datetime
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

    def _execute_public_announcement(self, context: List[Dict]) -> str:
        """市民への広報・避難指示を実行"""
        import pandas as pd

        # Playerへの了解メッセージを送信
        acknowledgment = self._generate_acknowledgment_message(context, "市民への広報")
        if self.manager:
            self.manager.add_message("assistant", "mayor", acknowledgment, "information",
                                   from_person="mayor", to_person="Player")

        # 別LLMで市民向けメッセージを作成（会話履歴から判断）
        citizen_message = self._generate_citizen_message_from_context(context)

        # 市民への広報メッセージを送信
        if self.manager:
            self.manager.add_message("system", "mayor", citizen_message, "information",
                                   from_person="mayor", to_person="市民")

        # 発信後にCSV記録用の内容を別LLMで生成
        csv_content = self._generate_csv_content_for_announcement(citizen_message)

        # CSVファイルパス
        csv_path = self.csv_base_path / "【市長専用】市民への広報記録.csv"

        # 現在時刻を取得
        current_time = self.time_manager.get_current_time()

        # 新しい記録
        new_record = {
            "発信日時": current_time,
            "内容": csv_content,
            "発信者": "市長"
        }

        # 既存CSVに追加
        df = pd.read_csv(csv_path)
        df = pd.concat([df, pd.DataFrame([new_record])], ignore_index=True)
        df.to_csv(csv_path, index=False, encoding='utf-8')

        return f"市民への広報を実施しました。\n内容: {csv_content}"

    def _execute_contact_governor(self, context: List[Dict]) -> str:
        """知事との連絡を実行"""
        import pandas as pd

        # Playerへの了解メッセージを送信
        acknowledgment = self._generate_acknowledgment_message(context, "府知事への連絡")
        if self.manager:
            self.manager.add_message("assistant", "mayor", acknowledgment, "information",
                                   from_person="mayor", to_person="Player")

        # 別LLMで府知事向けメッセージを作成（会話履歴から判断）
        governor_message = self._generate_governor_message_from_context(context)

        # 府知事への連絡メッセージを送信
        if self.manager:
            self.manager.add_message("system", "mayor", governor_message, "information",
                                   from_person="mayor", to_person="府知事")

            # 府知事からの了解返信を生成・送信
            governor_reply = self._generate_governor_reply(governor_message)
            self.manager.add_message("system", "府知事", governor_reply, "information",
                                   from_person="府知事", to_person="mayor")

        # 発信後にCSV記録用の内容を別LLMで生成
        subject, content = self._generate_csv_content_for_governor(governor_message)

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

    def _execute_contact_municipalities(self, context: List[Dict], target_municipalities: List[str] = None) -> str:
        """府下市町村との連絡を実行"""
        import pandas as pd

        # 対象市町村のデフォルト設定
        if target_municipalities is None:
            target_municipalities = ["全市町村"]

        # Playerへの了解メッセージを送信
        acknowledgment = self._generate_acknowledgment_message(context, "市町村への連絡")
        if self.manager:
            self.manager.add_message("assistant", "mayor", acknowledgment, "information",
                                   from_person="mayor", to_person="Player")

        # 別LLMで市町村向けメッセージを作成（会話履歴から判断）
        municipality_message = self._generate_municipality_message_from_context(context, target_municipalities)

        # 市町村への連絡メッセージを送信
        if self.manager:
            for municipality in target_municipalities:
                self.manager.add_message("system", "mayor", municipality_message, "information",
                                       from_person="市長", to_person=municipality)

                # 各市町村からの了解返信を生成・送信
                municipality_reply = self._generate_municipality_reply(municipality_message, municipality)
                self.manager.add_message("system", municipality, municipality_reply, "information",
                                       from_person=municipality, to_person="市長")

        # 発信後にCSV記録用の内容を別LLMで生成
        subject, content = self._generate_csv_content_for_municipalities(municipality_message, target_municipalities)

        # CSVファイルパス
        csv_path = self.csv_base_path / "【市長専用】市町村連絡記録.csv"

        # 現在時刻を取得
        current_time = self.time_manager.get_current_time()

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

    def _execute_broadcast_to_departments(self, context: List[Dict], departments: List[str] = None) -> str:
        """各部署への一斉連絡を実行"""
        # デフォルトの部署設定
        if departments is None:
            departments = ["information_team", "supply_team", "infrastructure_team"]

        # Playerへの了解メッセージを送信
        acknowledgment = self._generate_acknowledgment_message(context, "各部署への一斉連絡")
        if self.manager:
            self.manager.add_message("assistant", "mayor", acknowledgment, "information",
                                   from_person="mayor", to_person="Player")

        # ChatWithMemoryのインスタンスを通じて各部署に連綄
        if self.manager:
            # 別LLMで各部署向けメッセージを作成（会話履歴から判断）
            dept_message = self._generate_department_message(context)

            for dept in departments:
                if dept == "information_team":
                    manager_type = "information"
                elif dept == "supply_team":
                    manager_type = "supply"
                elif dept == "infrastructure_team":
                    manager_type = "infrastructure"
                else:
                    continue

                self.manager.add_message("system", "mayor", dept_message, manager_type,
                                       from_person="mayor", to_person=dept)

        dept_names_jp = {
            "information_team": "危機管理室",
            "supply_team": "物資管理班",
            "infrastructure_team": "建物・産業・土木対策班"
        }
        dept_names = [dept_names_jp.get(d, d) for d in departments]

        return f"各部署への一斉連絡を実施しました。\n対象: {', '.join(dept_names)}"

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
                    result = self._execute_public_announcement(messages)
                elif function_name == "contact_governor":
                    result = self._execute_contact_governor(messages)
                elif function_name == "contact_municipalities":
                    municipalities = function_args.get("target_municipalities")
                    result = self._execute_contact_municipalities(messages, municipalities)
                elif function_name == "broadcast_to_departments":
                    # 一斉連絡は即座に実行（会話履歴を渡す）
                    departments = function_args.get("departments")
                    result = self._execute_broadcast_to_departments(messages, departments)
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

    def _generate_citizen_message_from_context(self, context: List[Dict]) -> str:
        """別LLMで市民向けメッセージを生成（会話履歴から判断）"""
        try:
            # 最新の会話履歴から文脈を抽出
            recent_messages = context[-5:] if len(context) > 5 else context
            context_str = "\n".join([f"{msg.get('role', '')}: {msg.get('content', '')}" for msg in recent_messages])

            prompt = f"""
あなたは市長です。以下の会話履歴を踏まえて、市民への広報内容を決定し、わかりやすいメッセージを作成してください。

会話履歴:
{context_str}

要件:
- 市民にとってわかりやすい言葉で
- 状況に応じた適切な表現で
- 具体的で実用的な内容で
- 200文字以内で

市民向けメッセージ:
"""

            response = self.client.chat.completions.create(
                model="gpt-5-mini",
                messages=[{"role": "user", "content": prompt}]
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            print(f"市民向けメッセージ生成エラー: {e}")
            return "市民の皆様へ重要なお知らせがあります。"

    def _generate_csv_content_for_announcement(self, sent_message: str) -> str:
        """市民への広報発信後にCSV記録用の内容を生成"""
        try:
            prompt = f"""
以下の市民へ発信したメッセージをCSV記録用に要約してください。

発信メッセージ: {sent_message}

要約:
"""

            response = self.client.chat.completions.create(
                model="gpt-5-mini",
                messages=[{"role": "user", "content": prompt}]
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            print(f"CSV内容生成エラー: {e}")
            return "市民への広報を実施"

    def _generate_governor_message_from_context(self, context: List[Dict]) -> str:
        """別LLMで府知事向けメッセージを生成（会話履歴から判断）"""
        try:
            recent_messages = context[-5:] if len(context) > 5 else context
            context_str = "\n".join([f"{msg.get('role', '')}: {msg.get('content', '')}" for msg in recent_messages])

            prompt = f"""
あなたは市長です。以下の会話履歴を踏まえて、府知事への公式メッセージを作成してください。

会話履歴:
{context_str}

要件:
- 公式な文書として適切な敬語で
- 簡潔で要点を明確に
- 具体的な状況や要請があれば明記
- 300文字以内で

府知事向けメッセージ:
"""

            response = self.client.chat.completions.create(
                model="gpt-5-mini",
                messages=[{"role": "user", "content": prompt}]
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            print(f"府知事向けメッセージ生成エラー: {e}")
            return "府知事への緊急連絡です。"

    def _generate_csv_content_for_governor(self, sent_message: str) -> tuple[str, str]:
        """知事への連絡発信後にCSV記録用の内容を生成"""
        try:
            prompt = f"""
以下の府知事へ発信したメッセージからCSV記録用の件名と内容を抽出してください。

発信メッセージ: {sent_message}

出力形式:
件名: （件名50文字以内）
CSV内容: （内容）
"""

            response = self.client.chat.completions.create(
                model="gpt-5-mini",
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = response.choices[0].message.content.strip()
            lines = response_text.split('\n')
            subject = "緊急連絡"
            content = "府知事への連絡"

            for line in lines:
                if line.startswith("件名:"):
                    subject = line.replace("件名:", "").strip()
                elif line.startswith("CSV内容:"):
                    content = line.replace("CSV内容:", "").strip()

            return subject, content

        except Exception as e:
            print(f"CSV内容生成エラー: {e}")
            return "緊急連絡", "府知事への連絡"

    def _generate_municipality_message_from_context(self, context: List[Dict], target_municipalities: List[str]) -> str:
        """別LLMで市町村向けメッセージを生成（会話履歴から判断）"""
        try:
            municipalities_str = "、".join(target_municipalities)
            recent_messages = context[-5:] if len(context) > 5 else context
            context_str = "\n".join([f"{msg.get('role', '')}: {msg.get('content', '')}" for msg in recent_messages])

            prompt = f"""
あなたは市長です。以下の会話履歴を踏まえて、府下市町村（{municipalities_str}）へのメッセージを作成してください。

会話履歴:
{context_str}

対象: {municipalities_str}

要件:
- 自治体間の連携を意識した表現で
- 協力要請や情報共有の目的を明確に
- 具体的で実用的な内容で
- 簡潔に

市町村向けメッセージ:
"""

            response = self.client.chat.completions.create(
                model="gpt-5-mini",
                messages=[{"role": "user", "content": prompt}]
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            print(f"市町村向けメッセージ生成エラー: {e}")
            return "各市町村への重要な連絡です。"

    def _generate_csv_content_for_municipalities(self, sent_message: str, target_municipalities: List[str]) -> tuple[str, str]:
        """市町村への連絡発信後にCSV記隂用の内容を生成"""
        try:
            municipalities_str = "、".join(target_municipalities)
            prompt = f"""
以下の市町村（{municipalities_str}）へ発信したメッセージからCSV記録用の件名と内容を抽出してください。

発信メッセージ: {sent_message}

出力形式:
件名: （件名50文字以内）
CSV内容: （内容）
"""

            response = self.client.chat.completions.create(
                model="gpt-5-mini",
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = response.choices[0].message.content.strip()
            lines = response_text.split('\n')
            subject = "各市町村への連絡"
            content = "市町村への連絡"

            for line in lines:
                if line.startswith("件名:"):
                    subject = line.replace("件名:", "").strip()
                elif line.startswith("CSV内容:"):
                    content = line.replace("CSV内容:", "").strip()

            return subject, content

        except Exception as e:
            print(f"CSV内容生成エラー: {e}")
            return "各市町村への連絡", "市町村への連絡"

    def _generate_acknowledgment_message(self, context: List[Dict], task_type: str) -> str:
        """Playerへの了解メッセージを生成"""
        try:
            # 最新の会話履歴から文脈を抽出
            recent_messages = context[-3:] if len(context) > 3 else context
            context_str = "\n".join([f"{msg.get('role', '')}: {msg.get('content', '')}" for msg in recent_messages])

            prompt = f"""
あなたは市長です。以下の会話履歴を踏まえて、Playerに対して「了解しました、{task_type}を実行します」という旨の自然なメッセージを作成してください。

会話履歴:
{context_str}

作業内容: {task_type}

要件:
- 市長として威厳を持ちつつも親身な表現で
- Playerの指示を理解したことを示す
- これから実行することを明確に伝える
- 50文字以内で簡潔に

了解メッセージ:
"""

            response = self.client.chat.completions.create(
                model="gpt-5-mini",
                messages=[{"role": "user", "content": prompt}]
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            print(f"了解メッセージ生成エラー: {e}")
            return f"了解いたしました。{task_type}を実行いたします。"

    def _generate_governor_reply(self, sent_message: str) -> str:
        """府知事からの了解返信メッセージを生成"""
        try:
            prompt = f"""
あなたは府知事です。以下の市長からのメッセージを受けて、了解した旨の返信を作成してください。

市長からのメッセージ: {sent_message}

要件:
- 府知事として適切な敬語と表現で
- 市長への感謝と協力の意志を示す
- 必要に応じて具体的な対応や支援を言及
- 100文字以内で簡潔に

府知事からの返信:
"""

            response = self.client.chat.completions.create(
                model="gpt-5-mini",
                messages=[{"role": "user", "content": prompt}]
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            print(f"府知事返信生成エラー: {e}")
            return "市長のご連絡、承知いたしました。府としても全力で協力いたします。"

    def _generate_municipality_reply(self, sent_message: str, municipality_name: str) -> str:
        """市町村からの了解返信メッセージを生成"""
        try:
            prompt = f"""
あなたは{municipality_name}の担当者です。以下の市長からのメッセージを受けて、了解した旨の返信を作成してください。

市長からのメッセージ: {sent_message}
自治体名: {municipality_name}

要件:
- 自治体職員として適切な敬語と表現で
- 市長への感謝と協力の意志を示す
- 必要に応じて具体的な対応や連携を言及
- 80文字以内で簡潔に

{municipality_name}からの返信:
"""

            response = self.client.chat.completions.create(
                model="gpt-5-mini",
                messages=[{"role": "user", "content": prompt}]
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            print(f"市町村返信生成エラー: {e}")
            return f"{municipality_name}です。市長のご指示、承知いたしました。連携して対応いたします。"

    def _generate_department_message(self, context: List[Dict]) -> str:
        """別LLMで各部署向けメッセージを生成（会話履歴から判断）"""
        try:
            # 最新の会話履歴から文脈を抽出
            recent_messages = context[-5:] if len(context) > 5 else context
            context_str = "\n".join([f"{msg.get('role', '')}: {msg.get('content', '')}" for msg in recent_messages])

            prompt = f"""
あなたは市長です。以下の会話履歴を踏まえて、各部署（危機管理室、物資管理班、建物・土木対策班）への一斉連絡メッセージを作成してください。

会話履歴:
{context_str}

要件:
- 市長からの重要な指示であることを明確に
- 各部署の全職員（Manager、Worker全員）に向けた内容
- 会話の文脈から判断して、各部署が取るべき行動を具体的に指示
- 緊急度や優先順位があれば明記
- 部署間の連携が必要な場合はその旨を記載
- 300文字以内で

各部署の全職員向けメッセージ:
"""

            response = self.client.chat.completions.create(
                model="gpt-5-mini",
                messages=[{"role": "user", "content": prompt}]
            )

            return f"【市長からの全職員への指示】\n{response.choices[0].message.content.strip()}"

        except Exception as e:
            print(f"各部署向けメッセージ生成エラー: {e}")
            return "【市長からの全職員への指示】\n各部署は現在の状況に応じて適切に対応してください。"

    def create_tool_response(self, tool_name: str, args: Dict = None) -> str:
        """ツール実行結果からレスポンスメッセージを作成"""
        args = args or {}

        self._record_tool_execution(tool_name, args)

        if tool_name == "public_announcement":
            context = getattr(self, 'current_conversation_context', [])
            return self._execute_public_announcement(context)
        elif tool_name == "contact_governor":
            context = getattr(self, 'current_conversation_context', [])
            return self._execute_contact_governor(context)
        elif tool_name == "contact_municipalities":
            municipalities = args.get("target_municipalities")
            context = getattr(self, 'current_conversation_context', [])
            return self._execute_contact_municipalities(context, municipalities)
        elif tool_name == "broadcast_to_departments":
            # 一斉連絡は即座に実行（会話履歴を渡す）
            departments = args.get("departments")
            # 保存された会話履歴を使用
            context = getattr(self, 'current_conversation_context', [])
            return self._execute_broadcast_to_departments(context, departments)
        elif tool_name == "show_csv_content":
            filenames = args.get("filenames") or args.get("filename", "")
            return self._show_csv_content(filenames)
        elif tool_name == "list_all_csv_files":
            return self._list_all_csv_files()
        else:
            return "未対応のツールが呼ばれました。"


    def check_if_available(self) -> Optional[str]:
        """利用可能かチェック（離席中の場合はメッセージを返す）"""
        if self.away_until_time:
            current_time = self.time_manager.get_current_time()
            if current_time < self.away_until_time:
                task_name = self.current_task_description or "業務"
                return f"申し訳ありません、現在{task_name}中です。"
        return None

    def handle_return_from_task(self) -> Optional[str]:
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
                "description": "市民への広報・避難指示を実施する。会話の文脈から内容を判断して広報する。",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        })

        # 知事との連絡
        defs.append({
            "type": "function",
            "function": {
                "name": "contact_governor",
                "description": "府知事との連絡を実施する。会話の文脈から内容を判断して連絡する。",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        })

        # 府下市町村との連絡
        defs.append({
            "type": "function",
            "function": {
                "name": "contact_municipalities",
                "description": "府下市町村との連絡を実施する。会話の文脈から内容を判断して連絡する。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target_municipalities": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "連絡対象の市町村名リスト（省略時は全市町村）"
                        }
                    },
                    "required": []
                }
            }
        })

        # 各部署への一斉連絡
        defs.append({
            "type": "function",
            "function": {
                "name": "broadcast_to_departments",
                "description": "各部署への一斉連絡を実施する。情報管理室、物資管理班、建物・産業・土木対策班に同時に連絡される。会話の文脈から内容を判断して連絡する。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "departments": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": ["information_team", "supply_team", "infrastructure_team"]
                            },
                            "description": "連絡対象の部署（省略時は全部署）"
                        }
                    },
                    "required": []
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
        # 会話履歴を保存（broadcast_to_departments用）
        self.current_conversation_context = messages

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