import os
import sys
from typing import List, Dict, Any, Optional
from pathlib import Path
from openai import OpenAI


# ドキュメントを読む
def rag_read(query: str) -> str:
    try:
        sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
        from rag_db_maker import load_retriever
        from config.constants import VECTOR_DB_PATH, HIRAKATA_JISIN_VECTOR # TODO 全てのpathを、統合してconfigで管理できるようにする

        db_path = os.path.join(VECTOR_DB_PATH, HIRAKATA_JISIN_VECTOR)
        if not os.path.exists(db_path):
            return "ベクトルデータベースが見つかりません。先に rag_db_maker.py を実行して作成してください。"

        if not query.strip():
            query = "災害対応の基本情報"

        retriever, _ = load_retriever(db_path)
        results = retriever.invoke(query)

        blocks = []
        for i, doc in enumerate(results[:5], 1):  # 上位5件 # TODO 調べた内容を記憶に入れる時にも何かしら考慮
            m = getattr(doc, "metadata", {}) or {}
            chapter = m.get('chapter') or ''
            section = m.get('section') or ''
            page_s = m.get('page_start', '?')
            page_e = m.get('page_end', '?')
            head = " / ".join([x for x in [chapter, section] if x]).strip()
            text = (doc.page_content or "").replace("\n", " ")
            snippet = text
            blocks.append(f"#{i} [{head}] p.{page_s}-{page_e}\n{snippet}")

        if not blocks:
            return f"該当なし: {query}"

        return f"Query: {query}\n\n" + "\n\n".join(blocks) # ragの内容を出力

    except Exception as e:
        return f"ベクトル検索エラー: {str(e)}"


# knowledge.txtに、調べた結果を要約してマニュアルの知識として入れる
def add_search_to_knowledge(query: str, search_result: str, knowledge_path: Optional[Path] = None) -> bool:
    try:
        if knowledge_path is None:
            knowledge_path = Path("./src/knowledge.txt")

        # OpenAI APIで検索結果を要約・整形
        client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

        summary_prompt = f"""
以下の防災マニュアルの検索結果を要約し、実務で使える知識として整理してください。

【検索クエリ】{query}

【検索結果】
{search_result}

【整形の指針】
1. 見出しは「### {query}」の形式で開始
2. 内容は段落で適切に区切る
3. 具体的な数値や基準は必ず含める
4. 実務手順は順序立てて記載
5. 重要ポイントは段落を分けて明確化

【出力形式】
### {query}
[概要の段落]

[詳細内容の段落1]

[詳細内容の段落2]

...このような形式で整理してください。

## 重要
- 検索結果に書かれていないことを勝手に追加しないでください。
- 一般的な知識や推測は含めないでください。検索結果に基づく内容のみを記載してください。
"""

        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {"role": "system", "content": "あなたは防災マニュアルの要約専門家です。検索結果を段落で構造化し、実務で即座に参照できる形に整理してください。"},
                {"role": "user", "content": summary_prompt}
            ]
        )

        summarized_content = response.choices[0].message.content

        current_knowledge = ""
        if knowledge_path.exists():
            current_knowledge = knowledge_path.read_text(encoding='utf-8')

        # 【マニュアルからの知識】セクションが既に存在するか確認
        manual_section_marker = "## 【マニュアルからの知識】"
        if manual_section_marker in current_knowledge:
            # 既存のセクションに追加
            updated_knowledge = current_knowledge + f"\n\n{summarized_content}"
        else:
            # 新規セクション作成
            updated_knowledge = current_knowledge + f"\n\n{manual_section_marker}\n\n{summarized_content}"

        knowledge_path.write_text(updated_knowledge, encoding='utf-8')

        # print(f"aiエージェントの記憶に追加しました: 【マニュアル】{query}")
        return True

    except Exception as e:
        print(f"記憶追加エラー: {e}")
        return False



def search_and_summarize(
    query: str,
    conversation_history: List[Dict[str, str]] = None,
    knowledge_path: Optional[Path] = None
) -> str:
    import threading

    # 検索実行
    doc_content = rag_read(query)

    # 知識ベースへの保存を非同期で実行
    if knowledge_path:
        # バックグラウンドで知識保存を実行
        save_thread = threading.Thread(
            target=add_search_to_knowledge,
            args=(query, doc_content, knowledge_path)
        )
        save_thread.daemon = True
        save_thread.start()

    # OpenAI APIで要約（ユーザーへの応答生成）
    try:
        client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

        if not conversation_history:
            conversation_history = []

        system_content = """
あなたはUSERと一緒に災害対応の仕事を行う枚方市の災害対応職員（人間）です。あなたは情報管理担当の職員です。あなたは"information_manager"です。
地震を想定した避難訓練をUSERと二人で行っています。
検索結果を根拠に、会話文で簡潔に答えてください。
"""

        messages = [
            {"role": "system", "content": system_content},
            *conversation_history,
            {"role": "user", "name":"information_manager", "content": f"今、『{query}』について資料を検索しました。"},
            {"role": "system", "content": "以下の検索結果を根拠に、会話文で簡潔に答えてください。" + "\n\n【検索結果】\n" + doc_content}
        ]

        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=messages
        )

        return response.choices[0].message.content

    except Exception as e:
        # エラー時は検索結果をそのまま返す
        print(f"要約エラー: {e}")
        return doc_content