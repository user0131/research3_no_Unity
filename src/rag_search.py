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
        from config.constants import VECTOR_DB_PATH, HIRAKATA_JISIN_VECTOR

        db_path = os.path.join(VECTOR_DB_PATH, HIRAKATA_JISIN_VECTOR)
        if not os.path.exists(db_path):
            return "ベクトルデータベースが見つかりません。先に rag_db_maker.py を実行して作成してください。"

        if not query.strip():
            query = "災害対応の基本情報"

        retriever, _ = load_retriever(db_path)
        results = retriever.invoke(query)

        blocks = []
        for i, doc in enumerate(results[:5], 1):  # 上位5件
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

        return f"Query: {query}\n\n" + "\n\n".join(blocks)

    except Exception as e:
        return f"ベクトル検索エラー: {str(e)}"


# knowledge.txtに、調べた結果を入れる。これにより、もう知っていることを以降は調べなくても良くなる
def add_search_to_knowledge(query: str, search_result: str, knowledge_path: Optional[Path] = None) -> bool:
    try:
        if knowledge_path is None:
            knowledge_path = Path("./src/knowledge.txt")

        current_knowledge = ""
        if knowledge_path.exists():
            current_knowledge = knowledge_path.read_text(encoding='utf-8')

        new_entry = f"\n\n## 【検索内容】{query}\n{search_result}"
        updated_knowledge = current_knowledge + new_entry
        knowledge_path.write_text(updated_knowledge, encoding='utf-8')

        # print(f"aiエージェントの記憶に追加しました: 【検索】{query}")
        return True

    except Exception as e:
        print(f"記憶追加エラー: {e}")
        return False



def search_and_summarize(
    query: str,
    conversation_history: List[Dict[str, str]] = None,
    knowledge_path: Optional[Path] = None
) -> str:
    # 検索実行
    doc_content = rag_read(query)

    # 知識ベースに保存
    if knowledge_path:
        add_search_to_knowledge(query, doc_content, knowledge_path)

    # OpenAI APIで要約
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