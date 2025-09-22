import io
import os
import re
import sys
import requests
from collections import Counter
from dataclasses import dataclass, field
from typing import List, Optional

from dotenv import load_dotenv
from pypdf import PdfReader

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.schema import Document

load_dotenv()

# =========================
# 基本ユーティリティ
# =========================

def download_pdf(url: str) -> bytes:
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.content

def pdf_pages(pdf_bytes: bytes):
    """(page_index, normalized_text) を返すジェネレータ"""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    for i, p in enumerate(reader.pages):
        text = p.extract_text() or ""
        norm = re.sub(r"[ \u3000]+", " ", text)  # 全角空白などを統一
        yield i, norm

def _page_to_lines(text: str) -> List[str]:
    lines = [re.sub(r"[ \u3000]+", " ", ln).strip() for ln in text.splitlines()]
    return [ln for ln in lines if ln]

def _build_header_footer_blacklist(all_pages_texts: List[str], freq_threshold=0.50) -> set:
    """
    多数ページで繰返し出る行をヘッダー／フッターとみなし除去対象に。
    既定はページ数の50%以上に出現する行。
    """
    page_count = len(all_pages_texts)
    if page_count == 0:
        return set()
    line_in_pages = Counter()
    for t in all_pages_texts:
        uniq = set(_page_to_lines(t))
        for ln in uniq:
            line_in_pages[ln] += 1
    return {ln for ln, c in line_in_pages.items() if (c / page_count) >= freq_threshold}

def _strip_blacklisted_lines(text: str, blacklist: set) -> str:
    if not text:
        return ""
    kept = [ln for ln in _page_to_lines(text) if ln not in blacklist]
    return "\n".join(kept)

# =========================
# 見出し・目次検出（誤分割対策込み）
# =========================

DOT_LEADER_RE = re.compile(r"(…{2,}|\.{3,})")
PAGE_NUM_TAIL = re.compile(r"[ \t　\.…]*\d{1,4}\s*$")

def _looks_like_toc(text_head: str) -> bool:
    """目次っぽい先頭ブロックなら True"""
    if "目次" in text_head[:40]:
        return True
    lines = text_head.splitlines()
    if not lines:
        return False
    dot_like = sum(1 for ln in lines if DOT_LEADER_RE.search(ln))
    page_tail = sum(1 for ln in lines if PAGE_NUM_TAIL.search(ln) and DOT_LEADER_RE.search(ln))
    return (dot_like >= 2) or (page_tail >= 2)

KANJI_NUM = "〇一二三四五六七八九十百千"
CHAP_RE   = re.compile(rf"^(第[{KANJI_NUM}\d]+章)[ 　]?[^\n]{{0,60}}$", re.M)
SECT_RE   = re.compile(rf"^(第[{KANJI_NUM}\d]+節)[ 　]?[^\n]{{0,60}}$", re.M)
ITEM_RE   = re.compile(rf"^(第[{KANJI_NUM}\d]+項)[ 　]?[^\n]{{0,60}}$", re.M)

def _find_heading_candidates(text_head: str):
    """ページ先頭テキストから 章/節/項 見出し候補を拾う。ドットリーダー行は除外。"""
    head_wo_dots = "\n".join([ln for ln in text_head.splitlines() if not DOT_LEADER_RE.search(ln)])
    chap = CHAP_RE.search(head_wo_dots)
    sect = SECT_RE.search(head_wo_dots)
    item = ITEM_RE.search(head_wo_dots)
    return (
        chap.group(0) if chap else None,
        sect.group(0) if sect else None,
        item.group(0) if item else None
    )

# 応急対策編の開始マーカー（ゆるめ）＋ 第1章タイトルのフォールバック
START_OPS_RE   = re.compile(r"〔?\s*地\s*震\s*災\s*害\s*応\s*急\s*対\s*策\s*〕?")
CHAP1_TITLE_RE = re.compile(r"^第[０-９\d]+章[ 　]*組織動員体制", re.M)

def _find_ops_start_index(pages: List[str], head_chars: int = 800) -> Optional[int]:
    """応急対策編の開始インデックスを返す。編見出し or 第1章タイトルのどちらかで検出。"""
    for idx, t in enumerate(pages):
        if not t:
            continue
        head = t[:head_chars]
        if START_OPS_RE.search(head) or CHAP1_TITLE_RE.search(head):
            return idx
    return None

@dataclass
class _Buf:
    chapter: Optional[str] = None
    section: Optional[str] = None
    item: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    texts: List[str] = field(default_factory=list)

    def flush(self, out_docs: List[Document]):
        if not self.texts:
            return
        meta = {
            "chapter": self.chapter,
            "section": self.section,
            "item": self.item,
            "page_start": self.page_start,
            "page_end": self.page_end,
        }
        content = "\n".join(self.texts).strip()
        if content:
            out_docs.append(Document(page_content=content, metadata=meta))
        self.texts.clear()

# =========================
# 章・節ベースで構造化 → サイズ再分割
# =========================

def read_document_structured_by_sections(
    url: str,
    *,
    granularity: str = "section",   # "chapter" | "section" | "item"
    min_page_chars: int = 50,
    head_chars: int = 800,          # 見出し検出はページ先頭のこの文字数に限定
    inner_chunk_size: int = 900,
    inner_chunk_overlap: int = 200,
    start_after_ops: bool = True,   # 応急対策編が出るまでスキップ
) -> List[Document]:
    """
    1) 全ページ取得→頻出行（ヘッダ/フッタ）を除去
    2) 章・節（・項）単位で論理チャンク化
    3) 各まとまりをサイズ基準で再分割
    """
    pdf_bytes = download_pdf(url)

    # 全ページの生テキスト
    raw_pages: List[str] = []
    for _, raw in pdf_pages(pdf_bytes):
        raw_pages.append(raw if (raw and len(raw.strip()) >= min_page_chars) else "")

    # ヘッダ/フッタ除去（保守的に 0.50）
    blacklist = _build_header_footer_blacklist(raw_pages, freq_threshold=0.50)
    cleaned_pages = [_strip_blacklisted_lines(t, blacklist) if t else "" for t in raw_pages]

    # 応急対策編の開始ページを特定し、そこまで前付を一括スキップ
    if start_after_ops:
        start_idx = _find_ops_start_index(cleaned_pages, head_chars=head_chars)
        if start_idx is not None:
            cleaned_pages = cleaned_pages[start_idx:]

    # 章・節バッファリング
    out_docs_lvl: List[Document] = []
    buf = _Buf()
    last_page = None

    for pageno, t in enumerate(cleaned_pages):
        if not t:
            continue

        head = t[:head_chars]

        # 目次っぽい先頭なら見出しトリガー無効化
        is_toc = _looks_like_toc(head)

        new_chap = new_sect = new_item = None
        if not is_toc:
            new_chap, new_sect, new_item = _find_heading_candidates(head)

        # 切替条件
        new_unit = False
        if granularity == "chapter":
            if new_chap and new_chap != buf.chapter:
                new_unit = True
        elif granularity == "section":
            if (new_chap and new_chap != buf.chapter) or (new_sect and new_sect != buf.section):
                new_unit = True
        elif granularity == "item":
            if (new_chap and new_chap != buf.chapter) or (new_sect and new_sect != buf.section) or (new_item and new_item != buf.item):
                new_unit = True
        else:
            raise ValueError("granularity must be 'chapter' | 'section' | 'item'")

        if new_unit and buf.texts:
            buf.page_end = last_page
            buf.flush(out_docs_lvl)
            buf = _Buf()

        if buf.page_start is None:
            buf.page_start = pageno

        if new_chap: buf.chapter = new_chap
        if new_sect: buf.section = new_sect
        if new_item: buf.item = new_item

        buf.texts.append(t)
        last_page = pageno

    if buf.texts:
        buf.page_end = last_page
        buf.flush(out_docs_lvl)

    # 節まとまりをサイズ再分割
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=inner_chunk_size,
        chunk_overlap=inner_chunk_overlap,
        separators=["\n", "。", "、", " "],
    )
    final_docs: List[Document] = []
    for d in out_docs_lvl:
        parts = splitter.split_text(d.page_content)
        if len(parts) == 1:
            final_docs.append(d)
        else:
            for i, part in enumerate(parts, 1):
                meta = dict(d.metadata)
                meta["section_chunk_index"] = i
                final_docs.append(Document(page_content=part, metadata=meta))

    # 念のため：章名が付いていない（= 前付の取りこぼしなど）を落とす
    final_docs = [d for d in final_docs if d.metadata.get("chapter")]

    return final_docs

# =========================
# ページ単位（参考として残す）
# =========================

def read_document_all_pages(url: str, *, chunk_size: int = 900, chunk_overlap: int = 200):
    pdf_bytes = download_pdf(url)
    docs = []
    for pageno, text in pdf_pages(pdf_bytes):
        if text.strip() and len(text.strip()) > 50:
            docs.append(Document(page_content=text, metadata={"page": pageno}))
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap, separators=["\n", "。", "、", " "]
    )
    return splitter.split_documents(docs)

# =========================
# ベクタDB（FAISS）
# =========================

def build_retriever(docs, save_path=None):
    embeddings = OpenAIEmbeddings(model="text-embedding-3-large")  # 日本語◎
    vs = FAISS.from_documents(docs, embeddings)
    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        vs.save_local(save_path)
        print(f"ベクトルデータベースを保存しました: {save_path}")
    retriever = vs.as_retriever(search_kwargs={"k": 5})
    return retriever, vs

def load_retriever(load_path):
    if not os.path.exists(load_path):
        raise FileNotFoundError(f"ベクトルデータベースが見つかりません: {load_path}")
    embeddings = OpenAIEmbeddings(model="text-embedding-3-large")
    vs = FAISS.load_local(load_path, embeddings, allow_dangerous_deserialization=True)
    retriever = vs.as_retriever(search_kwargs={"k": 5})
    return retriever, vs

# =========================
# 実行例
# =========================

if __name__ == "__main__":
    # config.constants があれば使う／なければデフォルトにフォールバック
    try:
        sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
        from config.constants import VECTOR_DB_PATH, HIRAKATA_JISIN_VECTOR
        default_save_path = os.path.join(VECTOR_DB_PATH, HIRAKATA_JISIN_VECTOR)
    except Exception:
        default_save_path = "../config/vector_db/hirakata_jisin_vector"

    url = "https://www.city.hirakata.osaka.jp/cmsfiles/contents/0000028/28183/jisin.pdf"
    save_path = default_save_path

    print("章・節ベースでドキュメントを構造化中...")
    docs = read_document_structured_by_sections(
        url=url,
        granularity="section",      # "chapter" or "item" も可
        head_chars=800,
        inner_chunk_size=900,
        inner_chunk_overlap=200,
        start_after_ops=True,       # 応急対策編から開始
    )
    print(f"チャンク数: {len(docs)}")
    for d in docs[:3]:
        print(d.metadata)

    print("ベクトルデータベースを構築中...")
    retriever, vs = build_retriever(docs, save_path)

    # LangChain 0.1.46+ の推奨API: invoke
    query = "災害対策本部の設置基準は？"
    print(f"\nクエリ: {query}\n検索結果:")
    hits = retriever.invoke(query)
    for i, d in enumerate(hits, 1):
        meta = d.metadata
        loc = f"{meta.get('chapter') or ''} / {meta.get('section') or ''} p.{meta.get('page_start')}-{meta.get('page_end')}"
        text_head = d.page_content[:120].replace("\n", " ")
        print(f"{i}. {loc} : {text_head} ...")
