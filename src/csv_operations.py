from __future__ import annotations

import os
import re
import csv
import json
from typing import Any, Dict, List, Optional
from pathlib import Path
from pydantic import BaseModel, Field, field_validator, model_validator
from openai import OpenAI


class CSVFormSpec(BaseModel): 
    columns: List[str]
    rows: Optional[List[List[Any]]] = None
    description: Optional[str] = None
    delimiter: str = ","
    quotechar: str = '"'

    @field_validator("columns") # Pydanticのデコレータで、columnsフィールドの値を検証する関数を定義
    @classmethod
    def _columns_not_empty(cls, v):
        if not v:
            raise ValueError("columns は1列以上必要です。")
        return v

    @field_validator("rows")
    @classmethod # クラスメソッドとして定義（Pydanticの要件）
    def _rows_match_columns(cls, rows, info):
        if rows is None:
            return rows  # Noneならそのまま

        cols = info.data.get("columns") or []  # columnsの値を取得
        for r in rows:
            if len(r) != len(cols):  # 各行の要素数がcolumns数と違えばエラー
                raise ValueError(f"初期行の列数が columns と一致しません: {r}")
        return rows


class CSVAddColumn(BaseModel): # CSV更新時の「列追加」する際の設定
    name: str
    default: Optional[Any] = ""
    position: Optional[str] = Field(default="end", description="start/end")
    after: Optional[str] = None

    @field_validator("position")
    @classmethod
    def _pos_ok(cls, v):
        if v is None:
            return "end"
        if v not in ("start", "end"):
            raise ValueError("position は start か end です。")
        return v


class CSVAppendRows(BaseModel):  # 行を追加（オブジェクト形式での追加）
    objects: List[Dict[str, Any]]

    @field_validator("objects")
    @classmethod
    def _objects_ok(cls, v):
        if not v:
            raise ValueError("objects は1件以上必要です。")
        return v


class CSVUpdateCell(BaseModel): # マスを更新
    row_index: int
    column: str
    value: Any


class CSVUpdatePlan(BaseModel): # csv更新時に、「何を」「どのように」更新するかの設計図
    # 対象の特定
    filename: Optional[str] = None
    select_by_description: Optional[str] = None

    # 操作
    add_columns: Optional[List[CSVAddColumn]] = None
    append_rows: Optional[List[CSVAppendRows]] = None
    update_cells: Optional[List[CSVUpdateCell]] = None

    # 出力
    save_as: Optional[str] = None

    @model_validator(mode="after")
    def _at_least_one_operation(self):
        has_add = bool(self.add_columns)
        has_app = bool(self.append_rows)
        has_update = bool(self.update_cells)
        if not (has_add or has_app or has_update):
            raise ValueError("add_columns / append_rows / update_cells のいずれか1つ以上を指定してください。")
        return self



def _ensure_outdir() -> Path:
    outdir = Path("csv")
    outdir.mkdir(parents=True, exist_ok=True)
    return outdir

def _read_knowledge_csvs(knowledge_path: Path) -> List[Dict[str, str]]:
    items = []
    if not knowledge_path.exists():
        return items
    text = knowledge_path.read_text(encoding="utf-8")
    blocks = re.split(r"\n\s*##\s*", text)
    for b in blocks:
        if "【既存CSV】" not in b:
            continue
        title_line = b.splitlines()[0] if b.splitlines() else ""
        m_title = re.search(r"【既存CSV】(.+)", title_line)
        title = m_title.group(1).strip() if m_title else "(不明)"
        m_desc = re.search(r"説明:\s*(.+)", b)
        m_cols = re.search(r"現状のカラム:\s*(.+)", b)

        desc = (m_desc.group(1).strip() if m_desc else "")
        columns = (m_cols.group(1).strip() if m_cols else "")

        if title and title.lower().endswith(".csv"):
            items.append({"title": title, "description": desc, "columns": columns})
    return items


# ------------------------------------------------------------
# CSV新規作成（新規）
# ------------------------------------------------------------
def create_csv_file(
    *,
    filename: str = "data.csv",
    columns: Optional[List[str]] = None,
    rows: Optional[List[List[Any]]] = None,
    description: Optional[str] = None,
) -> str:
    """
    CSVファイルを作成
    columns=[...], rows=[...], description="...", delimiter=",", quotechar="\""
    """
    if not columns:
        raise ValueError("columns が必要です。")

    form_spec = {
        "columns": columns,
        "rows": rows or [],
        "description": description,
    }

    spec = CSVFormSpec.model_validate(form_spec).model_dump()

    outdir = _ensure_outdir()
    path = outdir / filename

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(spec["columns"])
        for row in spec.get("rows", []):
            if len(row) != len(spec["columns"]):
                raise ValueError(f"初期行の列数が columns と一致しません: {row}")
            writer.writerow(row)

    # knowledge に登録
    try:
        knowledge_path = Path("./src/knowledge.txt")
        current = knowledge_path.read_text(encoding="utf-8") if knowledge_path.exists() else ""
        desc = spec.get("description") or "(説明なし)"
        columns_str = ", ".join(spec["columns"])
        new_entry = f"\n\n## 【既存CSV】{filename}\n説明: {desc}\n現状のカラム: {columns_str}"
        knowledge_path.write_text(current + new_entry, encoding="utf-8")
    except Exception:
        pass

    return str(path)


# ------------------------------------------------------------
# CSV 追記・列追加・セル更新：knowledge から対象選定 → 計画に基づき更新・保存
# ------------------------------------------------------------
def _read_csv_all(path: str) -> tuple[list[str], list[dict]]:
    rows: list[dict] = []
    header: list[str] = []
    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        for r in reader:
            rows.append(dict(r))
    return header, rows

def _write_csv_all(path: str, header: list[str], rows: list[dict]):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        for r in rows:
            w.writerow({h: r.get(h, "") for h in header})

# 列を挿入
def _insert_col(header: list[str], name: str, *, position: Optional[str] = None, after: Optional[str] = None) -> list[str]:
    if after and after in header:
        i = header.index(after) + 1
        return header[:i] + [name] + header[i:]
    if position == "start":
        return [name] + header
    # default: end
    return header + [name]

def _append_rows_by_objects(header: list[str], rows: list[dict], objects: list[dict]):
    for obj in objects:
        # 未知カラムは末尾に追加
        for k in obj.keys():
            if k not in header:
                header.append(k)
                for rr in rows:
                    rr[k] = rr.get(k, "")
        new = {h: "" for h in header}
        for h in header:
            if h in obj:
                new[h] = obj[h]
        rows.append(new)

def _update_knowledge_columns(knowledge_path: Path, filename: str, new_columns: List[str]):
    """knowledgeのカラム情報を更新"""
    if not knowledge_path.exists():
        return

    text = knowledge_path.read_text(encoding="utf-8")
    pattern = rf"(## 【既存CSV】{re.escape(filename)}[\s\S]*?現状のカラム:)\s*([^\n]*)"
    columns_str = ", ".join(new_columns)
    updated_text = re.sub(pattern, rf"\1 {columns_str}", text)
    knowledge_path.write_text(updated_text, encoding="utf-8")


def _apply_update_plan_csv_full(path: str, plan: Dict[str, Any]) -> str:
    # 空ファイルは作らない前提（knowledge登録CSVを更新）。無ければエラー
    p = Path(path)
    if not p.exists() or p.stat().st_size == 0:
        raise FileNotFoundError(f"CSVが空か存在しません: {path}")

    header, rows = _read_csv_all(path)
    if not header:
        raise ValueError("CSVのヘッダ行が見つかりません。")

    # 1) 列追加
    for col in plan.get("add_columns", []) or []:
        name = col.get("name")
        if not name:
            continue
        if name in header:
            # 既存列には default だけ適用
            default = col.get("default", "")
            for r in rows:
                if r.get(name) in (None, ""):
                    r[name] = default
            continue
        header = _insert_col(header, name, position=col.get("position"), after=col.get("after"))
        default = col.get("default", "")
        for r in rows:
            r[name] = default

    # 2) 行追記
    for b in plan.get("append_rows", []) or []:
        objects_spec = b.get("objects")
        if objects_spec:
            _append_rows_by_objects(header, rows, objects_spec)

    # 3) セル更新（行インデックスはデータ行の0始まり。DictReader基準）
    for sc in plan.get("update_cells", []) or []:
        idx = sc.get("row_index")
        col = sc.get("column")
        val = sc.get("value")
        if idx is None or col is None:
            continue
        if col not in header:
            header.append(col)
            for r in rows:
                r[col] = r.get(col, "")
        if 0 <= idx < len(rows):
            rows[idx][col] = val

    # 保存
    save_as = plan.get("save_as")
    if save_as:
        # 別名保存の場合は元ファイルを変更せず、新しいパスに保存
        Path(save_as).parent.mkdir(parents=True, exist_ok=True)
        _write_csv_all(save_as, header, rows)
        out_path = save_as
    else:
        # 通常の場合は元ファイルを更新
        _write_csv_all(path, header, rows)
        out_path = path

    # knowledgeのカラム情報を更新
    filename = Path(path).name
    knowledge_path = Path("./src/knowledge.txt")
    _update_knowledge_columns(knowledge_path, filename, header)

    return out_path


def update_csv_from_knowledge(
    *,
    instruction: Optional[str] = None,
    update_spec: Optional[Any] = None
) -> str:
    """CSV更新: 自然文指示またはupdate_specでCSVを更新"""
    # CSV一覧取得
    knowledge_path = Path("./src/knowledge.txt")
    items = _read_knowledge_csvs(knowledge_path)
    if not items:
        raise RuntimeError("CSV記録がありません")

    # 計画取得（LLMまたは直接指定）
    if update_spec:
        plan = CSVUpdatePlan.model_validate(update_spec)
    else:
        if not instruction:
            raise ValueError("instructionが必要です")
        plan = _generate_plan_with_llm(items, instruction)

    # 対象ファイル決定
    target_path = f"csv/{plan.filename or items[0]['title']}"

    # 実行
    save_path = _apply_update_plan_csv_full(target_path, plan.model_dump())

    return save_path


def _generate_plan_with_llm(items: List[Dict[str, str]], instruction: str) -> CSVUpdatePlan:
    """LLMでCSV更新計画を生成"""
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    summary = "\n".join([
        f"- ファイル名: {it['title']}\n  説明: {it['description']}\n  カラム: {it['columns']}"
        for it in items
    ])

    resp = client.beta.chat.completions.parse(
        model="gpt-5-mini",
        messages=[
            {"role": "system", "content": "CSV更新プランナーです。指示に従ってJSON形式で更新計画を返してください。"},
            {"role": "user", "content": f"【CSV一覧】\n{summary}\n\n【指示】\n{instruction}"}
        ],
        response_format=CSVUpdatePlan,
    )

    return resp.choices[0].message.parsed
