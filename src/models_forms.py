# -*- coding: utf-8 -*-
# pydantic v2 系を想定
from __future__ import annotations

import os
import re
import csv
import json
from typing import Any, Dict, List, Optional, Union
from pathlib import Path
from pydantic import BaseModel, Field, field_validator, model_validator
from openai import OpenAI


# -----------------------------
# CSV template (form_spec)
# -----------------------------
class CSVFormSpec(BaseModel):
    columns: List[str]
    rows: Optional[List[List[Any]]] = None
    description: Optional[str] = None
    delimiter: str = ","
    quotechar: str = '"'

    @field_validator("columns")
    @classmethod
    def _columns_not_empty(cls, v):
        if not v:
            raise ValueError("columns は1列以上必要です。")
        return v

    @field_validator("rows")
    @classmethod
    def _rows_match_columns(cls, rows, info):
        if rows is None:
            return rows
        cols = info.data.get("columns") or []
        for r in rows:
            if len(r) != len(cols):
                raise ValueError(f"初期行の列数が columns と一致しません: {r}")
        return rows


def parse_csv_form_spec(obj: Any) -> Dict[str, Any]:
    """dict/JSON文字列などを受け取り、正規化した dict を返す"""
    import json
    if obj is None:
        raise ValueError("form_spec が必要です。")
    if isinstance(obj, str):
        data = json.loads(obj)
    elif isinstance(obj, dict):
        data = obj
    else:
        raise ValueError("form_spec は dict か JSON 文字列で渡してください。")
    spec = CSVFormSpec.model_validate(data)
    return spec.model_dump()


# -----------------------------
# CSV update plan
#   - add_columns: 列追加
#   - append_rows: 行追記（headers/rows または objects）
#   - set_cells : セル更新
#   いずれか1つ以上があれば有効
# -----------------------------
class CSVAddColumn(BaseModel):
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


class CSVAppendRowsByHeaders(BaseModel):
    headers: List[str]
    rows: List[List[Any]]

    @field_validator("headers")
    @classmethod
    def _headers_ok(cls, v):
        if not v:
            raise ValueError("headers は1つ以上必要です。")
        return v

    @field_validator("rows")
    @classmethod
    def _rows_ok(cls, v):
        if not v:
            raise ValueError("rows は1行以上必要です。")
        return v


class CSVAppendRowsByObjects(BaseModel):
    objects: List[Dict[str, Any]]

    @field_validator("objects")
    @classmethod
    def _objects_ok(cls, v):
        if not v:
            raise ValueError("objects は1件以上必要です。")
        return v


CSVAppendBatch = Union[CSVAppendRowsByHeaders, CSVAppendRowsByObjects]


class CSVSetCell(BaseModel):
    row_index: int  # 0始まり（ヘッダ除く）
    column: str
    value: Any


class CSVUpdatePlan(BaseModel):
    # 対象の特定
    filename: Optional[str] = None
    select_by_description: Optional[str] = None

    # 書式（任意）
    delimiter: str = ","
    quotechar: str = '"'

    # 操作
    add_columns: Optional[List[CSVAddColumn]] = None
    append_rows: Optional[List[CSVAppendBatch]] = None
    set_cells: Optional[List[CSVSetCell]] = None

    # 出力
    save_as: Optional[str] = None

    @model_validator(mode="after")
    def _at_least_one_operation(self):
        has_add = bool(self.add_columns)
        has_app = bool(self.append_rows)
        has_set = bool(self.set_cells)
        if not (has_add or has_app or has_set):
            raise ValueError("add_columns / append_rows / set_cells のいずれか1つ以上を指定してください。")
        return self


def _coerce_append_batch(obj: Any) -> CSVAppendBatch:
    """headers/rows または objects を含む dict を CSVAppendBatch に変換"""
    if not isinstance(obj, dict):
        raise ValueError("append_rows の各要素は dict である必要があります。")
    if "headers" in obj or "rows" in obj:
        return CSVAppendRowsByHeaders.model_validate(obj)
    if "objects" in obj:
        return CSVAppendRowsByObjects.model_validate(obj)
    raise ValueError("append_rows の要素は 'headers/rows' か 'objects' を含めてください。")


def parse_csv_update_plan(obj: Any) -> Dict[str, Any]:
    """dict/JSON文字列などを受け取り、厳密化した dict を返す（列追加のみ等も許可）"""
    if obj is None:
        raise ValueError("update_spec が必要です。")
    if isinstance(obj, str):
        data = json.loads(obj)
    elif isinstance(obj, dict):
        data = obj
    else:
        raise ValueError("update_spec は dict か JSON 文字列で渡してください。")

    # append_rows を Union モデルに正規化
    if "append_rows" in data and data["append_rows"] is not None:
        data["append_rows"] = [ _coerce_append_batch(x) for x in data["append_rows"] ]

    plan = CSVUpdatePlan.model_validate(data)
    return plan.model_dump()


# ------------------------------------------------------------
# 共通ユーティリティ
# ------------------------------------------------------------
def _ensure_outdir() -> Path:
    outdir = Path("./src/outputs")
    outdir.mkdir(parents=True, exist_ok=True)
    return outdir

def _read_knowledge_csvs(knowledge_path: Path) -> List[Dict[str, str]]:
    """
    knowledge.txt から CSV テンプレ情報を抽出
    形式（例）:
      ### 【CSVテンプレ】ファイル名.csv
      保存先: ./src/outputs/避難者名簿.csv
      説明: 受付〜名簿の標準テンプレ
    """
    items = []
    if not knowledge_path.exists():
        return items
    text = knowledge_path.read_text(encoding="utf-8")
    blocks = re.split(r"\n\s*###\s*", text)
    for b in blocks:
        if "【CSVテンプレ】" not in b:
            continue
        title_line = b.splitlines()[0] if b.splitlines() else ""
        m_title = re.search(r"【CSVテンプレ】(.+)", title_line)
        title = m_title.group(1).strip() if m_title else "(不明)"
        m_path = re.search(r"保存先:\s*(.+)", b)
        m_desc = re.search(r"説明:\s*(.+)", b)
        path = (m_path.group(1).strip() if m_path else "")
        desc = (m_desc.group(1).strip() if m_desc else "")
        if path and path.lower().endswith(".csv"):
            items.append({"title": title, "path": path, "description": desc})
    return items


# ------------------------------------------------------------
# CSV 作成（新規）
# ------------------------------------------------------------
def create_csv_file(
    *,
    filename: str = "data.csv",
    form_spec: Any = None,
    columns: Optional[List[str]] = None,
    rows: Optional[List[List[Any]]] = None,
    description: Optional[str] = None,
    delimiter: str = ",",
    quotechar: str = '"',
) -> str:
    """
    どちらでもOK:
      A) form_spec={"columns":[...], "rows":[...], "description":"...", "delimiter":",", "quotechar":"\""}
      B) columns=[...], rows=[...], description="...", delimiter=",", quotechar="\""
    """
    if form_spec is None:
        if not columns:
            raise ValueError("form_spec か columns のいずれかが必要です。")
        form_spec = {
            "columns": columns,
            "rows": rows or [],
            "description": description,
            "delimiter": delimiter,
            "quotechar": quotechar,
        }

    spec = parse_csv_form_spec(form_spec)  # バリデーション込み

    outdir = _ensure_outdir()
    path = outdir / filename

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=spec.get("delimiter", ","), quotechar=spec.get("quotechar", '"'))
        writer.writerow(spec["columns"])
        for row in spec.get("rows", []):
            if len(row) != len(spec["columns"]):
                raise ValueError(f"初期行の列数が columns と一致しません: {row}")
            writer.writerow(row)

    # knowledge に登録
    try:
        knowledge_path = Path("./src/functions/knowledge.txt")
        current = knowledge_path.read_text(encoding="utf-8") if knowledge_path.exists() else ""
        desc = spec.get("description") or "(説明なし)"
        new_entry = f"\n\n### 【CSVテンプレ】{filename}\n保存先: {str(path)}\n説明: {desc}"
        knowledge_path.write_text(current + new_entry, encoding="utf-8")
    except Exception:
        pass

    return str(path)


# ------------------------------------------------------------
# CSV 追記・列追加・セル更新：knowledge から対象選定 → 計画に基づき更新・保存
# ------------------------------------------------------------
def _read_csv_all(path: str, delimiter: str = ",", quotechar: str = '"') -> tuple[list[str], list[dict]]:
    rows: list[dict] = []
    header: list[str] = []
    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=delimiter, quotechar=quotechar)
        header = reader.fieldnames or []
        for r in reader:
            rows.append(dict(r))
    return header, rows

def _write_csv_all(path: str, header: list[str], rows: list[dict], delimiter: str = ",", quotechar: str = '"'):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header, delimiter=delimiter, quotechar=quotechar)
        w.writeheader()
        for r in rows:
            w.writerow({h: r.get(h, "") for h in header})

def _insert_col(header: list[str], name: str, *, position: Optional[str] = None, after: Optional[str] = None) -> list[str]:
    if after and after in header:
        i = header.index(after) + 1
        return header[:i] + [name] + header[i:]
    if position == "start":
        return [name] + header
    # default: end
    return header + [name]

def _append_rows_by_headers(header: list[str], rows: list[dict], batch_headers: list[str], values: list[list[Any]]):
    """headersを指定して列名マッピングで追記"""
    index = {h: i for i, h in enumerate(batch_headers)}
    for r in values:
        new = {h: "" for h in header}
        for h in header:
            if h in index and index[h] < len(r):
                new[h] = r[index[h]]
        rows.append(new)

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

def _apply_update_plan_csv_full(path: str, plan: Dict[str, Any]) -> str:
    delimiter = plan.get("delimiter", ",")
    quotechar = plan.get("quotechar", '"')

    # 空ファイルは作らない前提（knowledge登録CSVを更新）。無ければエラー
    p = Path(path)
    if not p.exists() or p.stat().st_size == 0:
        raise FileNotFoundError(f"CSVが空か存在しません: {path}")

    header, rows = _read_csv_all(path, delimiter=delimiter, quotechar=quotechar)
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
        headers_spec = b.get("headers")
        objects_spec = b.get("objects")
        values = b.get("rows", [])

        if headers_spec:
            # 未知カラムが headers に含まれるなら追加してからマッピング
            for h in headers_spec:
                if h not in header:
                    header.append(h)
                    for rr in rows:
                        rr[h] = rr.get(h, "")
            _append_rows_by_headers(header, rows, headers_spec, values)
        if objects_spec:
            _append_rows_by_objects(header, rows, objects_spec)

    # 3) セル更新（行インデックスはデータ行の0始まり。DictReader基準）
    for sc in plan.get("set_cells", []) or []:
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
    _write_csv_all(path, header, rows, delimiter=delimiter, quotechar=quotechar)

    # save_as（別名保存）オプション
    save_as = plan.get("save_as")
    out_path = path if not save_as else save_as
    if save_as and save_as != path:
        data = Path(path).read_bytes()
        Path(save_as).parent.mkdir(parents=True, exist_ok=True)
        Path(save_as).write_bytes(data)
        out_path = save_as

    return out_path


def update_csv_from_knowledge(
    *,
    instruction: Optional[str] = None,
    update_spec: Optional[Any] = None
) -> str:
    """
    knowledge.txt を読み、対象CSVを選び、指示に基づいて更新（列追加/行追記/セル更新）を実行。
    - instruction: 自然文。LLMで更新計画(JSON)を合成（update_spec が無い場合のみ）
    - update_spec: 直接JSON計画を渡す場合（CSVUpdatePlan）
    返り値: 保存パス
    """
    knowledge_path = Path("./src/functions/knowledge.txt")
    items = _read_knowledge_csvs(knowledge_path)
    if not items:
        raise RuntimeError("knowledge.txt に CSV テンプレの記録がありません。")

    # 計画を決定
    if update_spec:
        plan = parse_csv_update_plan(update_spec)
    else:
        if not instruction:
            raise ValueError("instruction か update_spec のいずれかが必要です。")

        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        sys_prompt = (
            "あなたはCSV更新プランナーです。与えられた候補一覧と指示から、"
            "どのファイルを更新し、どの操作（列追加/行追記/セル更新）を行うかを厳密なJSONで返してください。"
            "JSONスキーマ例:\n"
            "{\n"
            '  "filename": "<候補の path 文字列>",\n'
            '  "select_by_description": "<説明キーワード（省略可）>",\n'
            '  "add_columns": [\n'
            '     {"name":"担当者","default":"","position":"end","after":"在庫数"}\n'
            '  ],\n'
            '  "append_rows": [\n'
            '     {"headers":["品目","数量"], "rows":[["水",10]]},\n'
            '     {"objects":[{"品目":"毛布","数量":5,"担当者":"A"}]}\n'
            '  ],\n'
            '  "set_cells": [\n'
            '     {"row_index":0,"column":"数量","value":15}\n'
            '  ],\n'
            '  "delimiter": ",",\n'
            '  "quotechar": "\\""\n'
            "}\n"
            "注意: 候補以外のパスを出さないこと。headers を使う場合は既存CSVのカラム名に合わせること。"
        )
        summary = "\n".join(
            [f"- path: {it['path']}\n  title: {it['title']}\n  desc: {it['description']}" for it in items]
        )
        user_prompt = (
            "【候補一覧】\n" + summary + "\n\n"
            "【指示】\n" + instruction + "\n\n"
            "制約: 曖昧なら説明やタイトルで最も一致するものを選んでください。"
        )
        resp = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
        try:
            plan = json.loads(resp.choices[0].message.content)
        except Exception:
            plan = parse_csv_update_plan(resp.choices[0].message.content)

    # 対象パスを resolve
    target_path = None
    if plan.get("filename"):
        target_path = plan["filename"]
    else:
        key = (plan.get("select_by_description") or "").strip()
        if key:
            matches = [it for it in items if key in (it["description"] or "") or key in (it["title"] or "")]
            if matches:
                target_path = matches[0]["path"]
    if not target_path:
        target_path = items[-1]["path"]

    # パスが相対パスの場合、絶対パスに変換（src/outputs/... → ./src/outputs/...）
    if not os.path.isabs(target_path) and not target_path.startswith('./'):
        target_path = './' + target_path

    # 計画のバリデーション（ゆるめに通しつつ、必須型は確認）
    plan_norm = parse_csv_update_plan(plan)

    # 実適用
    save_path = _apply_update_plan_csv_full(target_path, plan_norm)

    # knowledge にログ追記
    try:
        log = f"更新対象: {target_path}\n保存先: {save_path}\n計画: {json.dumps(plan_norm, ensure_ascii=False)}"
        current = knowledge_path.read_text(encoding="utf-8") if knowledge_path.exists() else ""
        new_entry = f"\n\n### 【CSV更新】{Path(save_path).name}\n{log}"
        (knowledge_path).write_text(current + new_entry, encoding="utf-8")
    except Exception:
        pass

    return save_path
