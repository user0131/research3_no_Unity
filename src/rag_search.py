# -*- coding: utf-8 -*-
"""
RAG検索機能モジュール
FAISSベクトルデータベースから災害対応情報を検索
"""

import os
import sys
from typing import List, Dict, Any, Optional
from pathlib import Path
from openai import OpenAI


def rag_read(query: str) -> str:
    """
    rag_db_maker.load_retriever を用い、config.constants の
    VECTOR_DB_PATH / HIRAKATA_JISIN_VECTOR を参照して検索。
    戻り値は整形済みテキスト（章・節・ページ＋抜粋）。
    """
    try:
        # パス解決と import
        sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
        from src.rag_db_maker import load_retriever
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


def add_search_to_knowledge(query: str, search_result: str, knowledge_path: Optional[Path] = None) -> bool:
    """
    検索結果を知識ベース(knowledge.txt)に追記

    Args:
        query: 検索クエリ
        search_result: 検索結果のテキスト
        knowledge_path: knowledge.txtのパス（省略時はデフォルト）

    Returns:
        bool: 追記成功時True
    """
    try:
        if knowledge_path is None:
            knowledge_path = Path("./src/functions/knowledge.txt")

        current_knowledge = ""
        if knowledge_path.exists():
            current_knowledge = knowledge_path.read_text(encoding='utf-8')

        new_entry = f"\n\n### 【検索】{query}\n{search_result}"
        updated_knowledge = current_knowledge + new_entry
        knowledge_path.write_text(updated_knowledge, encoding='utf-8')

        print(f"📝 知識ベースに追加しました: 【検索】{query}")
        return True

    except Exception as e:
        print(f"知識ベース追加エラー: {e}")
        return False


def search_and_save(query: str, knowledge_path: Optional[Path] = None) -> str:
    """
    RAG検索を実行し、結果を知識ベースに保存

    Args:
        query: 検索クエリ
        knowledge_path: knowledge.txtのパス（省略時はデフォルト）

    Returns:
        str: 検索結果
    """
    result = rag_read(query)
    add_search_to_knowledge(query, result, knowledge_path)
    return result


def search_and_summarize(
    query: str,
    conversation_history: List[Dict[str, str]] = None,
    system_content: str = None,
    knowledge_path: Optional[Path] = None
) -> str:
    """
    RAG検索を実行し、結果を自然な会話形式で要約して返す

    Args:
        query: 検索クエリ
        conversation_history: 会話履歴
        system_content: システムプロンプト
        knowledge_path: knowledge.txtのパス（省略時はデフォルト）

    Returns:
        str: 要約された検索結果
    """
    # 検索実行
    doc_content = rag_read(query)

    # 知識ベースに保存
    if knowledge_path or Path("./src/functions/knowledge.txt").exists():
        add_search_to_knowledge(query, doc_content, knowledge_path)

    # OpenAI APIで要約
    try:
        client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

        if not conversation_history:
            conversation_history = []

        if not system_content:
            system_content = """
あなたはUSERと一緒に災害対応の仕事を行う枚方市の災害対応職員（人間）です。
地震を想定した避難訓練をUSERと二人で行っています。
検索結果を根拠に、会話文で簡潔に答えてください。
"""

        synth = "以下の検索結果を根拠に、会話文で簡潔に答えてください。"
        messages = [
            {"role": "system", "content": system_content},
            *conversation_history,
            {"role": "assistant", "content": f"今、『{query}』について資料を検索しました。"},
            {"role": "system", "content": synth + "\n\n【検索結果】\n" + doc_content}
        ]

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages
        )

        return response.choices[0].message.content

    except Exception as e:
        # エラー時は検索結果をそのまま返す
        print(f"要約エラー: {e}")
        return doc_content


def get_available_databases() -> List[Dict[str, str]]:
    """
    利用可能なベクトルデータベースの一覧を取得

    Returns:
        List[Dict[str, str]]: データベース情報のリスト
    """
    try:
        sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
        from config.constants import VECTOR_DB_PATH

        db_path = Path(VECTOR_DB_PATH)
        if not db_path.exists():
            return []

        databases = []
        for item in db_path.iterdir():
            if item.is_dir():
                # FAISSインデックスファイルの存在確認
                if (item / "index.faiss").exists():
                    databases.append({
                        "name": item.name,
                        "path": str(item),
                        "type": "FAISS"
                    })

        return databases

    except Exception as e:
        print(f"データベース一覧取得エラー: {e}")
        return []