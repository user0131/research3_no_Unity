"""
csv関連の操作を決定するファイル
"""
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
    delimiter: str = "," # delimiterは区切り
    quotechar: str = '"' # quotecharは文章の引用

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

        cols = info.data.get("columns") or [] # columnsの値を取得
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



def _ensure_outdir(filename: str = "") -> Path:
    # ファイル名にディレクトリが含まれている場合はそれを考慮
    if "/" in filename:
        # パスの親ディレクトリを取得
        file_path = Path("csv") / filename
        outdir = file_path.parent
    else:
        outdir = Path("csv")

    outdir.mkdir(parents=True, exist_ok=True)
    return outdir

def _read_knowledge_csvs(knowledge_path: Path) -> List[Dict[str, str]]:
    items = []
    if not knowledge_path.exists():
        return items
    text = knowledge_path.read_text(encoding="utf-8")
    blocks = re.split(r"\n\s*###\s*", text)
    for b in blocks:
        if "【" not in b or "】" not in b:
            continue
        title_line = b.splitlines()[0] if b.splitlines() else ""
        m_title = re.search(r"【(.+?)】", title_line)
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
    column_descriptions: Optional[Dict[str, str]] = None,
    knowledge_path: Optional[str] = None,
    time_manager = None,
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

    # knowledge_pathからCSVディレクトリを自動判定
    # 例: knowledge_information.txt → csv/information/
    #     knowledge_supply.txt → csv/supply/
    csv_dir = None
    if knowledge_path:
        knowledge_name = Path(knowledge_path).stem
        if knowledge_name.startswith("knowledge_"):
            csv_dir = knowledge_name.replace("knowledge_", "")

    # ファイル名にディレクトリが含まれている場合はそのまま使用
    if "/" in filename:
        path = Path("csv") / filename
    elif csv_dir:
        path = Path("csv") / csv_dir / filename
    else:
        outdir = _ensure_outdir(filename)
        path = outdir / filename

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(spec["columns"])
        for row in spec.get("rows", []):
            if len(row) != len(spec["columns"]):
                raise ValueError(f"初期行の列数が columns と一致しません: {row}")
            writer.writerow(row)

    # knowledge に登録　column_descriptions パラメータとして Dict[str, str] 型で受け取り、各カラムの説明を knowledgeファイルに書き込む
    if knowledge_path:
        try:
            knowledge_file = Path(knowledge_path)
            current = knowledge_file.read_text(encoding="utf-8") if knowledge_file.exists() else ""
            desc = spec.get("description") or "(説明なし)"
            columns_str = ", ".join(spec["columns"])

            # カラム説明を追加
            column_desc_lines = []
            for col in spec["columns"]:
                if column_descriptions:
                    col_desc = column_descriptions.get(col, "")
                else:
                    col_desc = ""
                column_desc_lines.append(f"- {col}: {col_desc}")
            column_desc_text = f"\nカラム説明:\n" + "\n".join(column_desc_lines)

            # CSV情報セクションがない場合は作成
            if "# CSV情報" not in current:
                current += "\n\n# CSV情報\n\n## 保有CSV"

            # 新しく作成したCSVとしてタイムスタンプ付きで記録（訓練内時間）
            if time_manager:
                simulation_time = time_manager.get_current_time()
                new_entry = f"\n\n### 【{filename}】 (作成時刻: {simulation_time})\n説明: {desc}\n現状のカラム: {columns_str}{column_desc_text}"
            else:
                new_entry = f"\n\n### 【{filename}】\n説明: {desc}\n現状のカラム: {columns_str}{column_desc_text}"
            knowledge_file.write_text(current + new_entry, encoding="utf-8")
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
    pattern = rf"(### 【{re.escape(filename)}】[\s\S]*?現状のカラム:)\s*([^\n]*)"
    columns_str = ", ".join(new_columns)
    updated_text = re.sub(pattern, rf"\1 {columns_str}", text)
    knowledge_path.write_text(updated_text, encoding="utf-8")

def _add_update_record_to_knowledge(knowledge_path: Path, filename: str, plan: Dict[str, Any], time_manager = None, cell_changes = None):
    """CSV更新記録をknowledgeに追加"""
    if not knowledge_path.exists():
        return

    try:
        # 訓練内時刻を取得
        if time_manager:
            current_time = time_manager.get_current_time()
        else:
            from datetime import datetime
            current_time = datetime.now().strftime("%H:%M")

        # 更新記録の作成
        update_records = []

        # カラム追加記録
        if plan.get("add_columns"):
            for col in plan["add_columns"]:
                col_name = col.get("name")
                update_records.append(f"- カラム追加: '{col_name}'")

        # 行追加記録（具体的なデータ内容を記録）
        if plan.get("append_rows"):
            for row_block in plan["append_rows"]:
                objects = row_block.get("objects", [])
                for obj in objects:
                    # オブジェクトの内容を文字列化
                    data_summary = ", ".join([f"{k}: {v}" for k, v in obj.items() if v])
                    update_records.append(f"- データ追加: {data_summary}")

        # セル更新記録（変更前の値も記録）
        if cell_changes:
            for change in cell_changes:
                column = change["column"]
                new_value = change["new_value"]
                old_value = change["old_value"]
                identifier = change["identifier"]

                if identifier:
                    update_records.append(f"- ({identifier})の{column}の値を'{old_value}'から'{new_value}'に変更")
                else:
                    update_records.append(f"- {column}の値を'{old_value}'から'{new_value}'に変更")

        if not update_records:
            return

        # 更新記録をknowledgeに追加
        text = knowledge_path.read_text(encoding="utf-8")

        # CSV更新記録セクションがない場合は作成
        if "## CSV更新記録" not in text:
            if "# CSV情報" in text:
                # CSV情報セクションの後に更新記録セクションを追加
                text = text.replace("# CSV情報", "# CSV情報\n\n## 保有CSV\n\n## CSV更新記録")
            else:
                # CSV情報セクション自体がない場合
                text += "\n\n# CSV情報\n\n## 保有CSV\n\n## CSV更新記録"

        # 更新記録を追加
        update_record_text = f"\n### {current_time} - {filename}\n" + "\n".join(update_records)

        # CSV更新記録セクションの後に追加
        pattern = r"(## CSV更新記録)"
        updated_text = re.sub(pattern, rf"\1{update_record_text}\n", text)
        knowledge_path.write_text(updated_text, encoding="utf-8")

    except Exception as e:
        print(f"更新記録追加エラー: {e}")


def _apply_update_plan_csv_full(path: str, plan: Dict[str, Any], knowledge_file: Path, time_manager = None) -> str:
    # 空ファイルは作らない前提（knowledge登録CSVを更新）。無ければエラー
    p = Path(path)
    if not p.exists() or p.stat().st_size == 0:
        raise FileNotFoundError(f"CSVが空か存在しません: {path}")

    header, rows = _read_csv_all(path)
    if not header:
        raise ValueError("CSVのヘッダ行が見つかりません。")

    # セル更新の変更前値を事前に記録
    cell_changes = []
    for sc in plan.get("update_cells", []) or []:
        idx = sc.get("row_index")
        col = sc.get("column")
        val = sc.get("value")
        if idx is not None and col is not None and 0 <= idx < len(rows):
            old_value = rows[idx].get(col, "") if col in rows[idx] else ""

            # 冒頭のフィールドから最小限で識別できるフィールドを取得
            row_data = rows[idx]
            identifier_fields = []

            # 冒頭のフィールドから順番に確認
            for field_idx, key in enumerate(header):
                if key == col:  # 更新対象のカラムはスキップ
                    continue
                value = row_data.get(key, "")
                if value:  # 値があるフィールドのみ
                    identifier_fields.append(f"{key}: {value}")

                    # 現在までのフィールドで他の行と区別できるかチェック
                    current_identifier = ", ".join(identifier_fields)
                    is_unique = True
                    for other_idx, other_row in enumerate(rows):
                        if other_idx == idx:
                            continue
                        # 他の行との比較
                        other_fields = []
                        for check_key in header[:field_idx+1]:
                            if check_key == col:
                                continue
                            other_value = other_row.get(check_key, "")
                            if other_value:
                                other_fields.append(f"{check_key}: {other_value}")
                        other_identifier = ", ".join(other_fields)
                        if current_identifier == other_identifier:
                            is_unique = False
                            break

                    if is_unique:
                        break

            cell_changes.append({
                "row_index": idx,
                "column": col,
                "new_value": val,
                "old_value": old_value,
                "identifier": ", ".join(identifier_fields) if identifier_fields else f"行{idx+1}"
            })

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

    # knowledgeのカラム情報を更新（csvディレクトリからの相対パス）
    csv_relative_path = Path(path).relative_to(Path("csv")) if Path(path).is_relative_to(Path("csv")) else Path(path).name
    _update_knowledge_columns(knowledge_file, str(csv_relative_path), header)

    # CSV更新記録をknowledgeに追加
    _add_update_record_to_knowledge(knowledge_file, str(csv_relative_path), plan, time_manager, cell_changes)

    return out_path


def update_csv_from_knowledge(
    *,
    instruction: Optional[str] = None,
    update_spec: Optional[Any] = None,
    knowledge_path: Optional[str] = None,
    time_manager = None
) -> str:
    """CSV更新: 自然文指示またはupdate_specでCSVを更新"""
    # CSV一覧取得
    if not knowledge_path:
        return "knowledge_pathが必要です"
    knowledge_file = Path(knowledge_path)
    items = _read_knowledge_csvs(knowledge_file)
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
    filename = plan.filename or items[0]['title']

    # knowledge_pathからCSVディレクトリを自動判定
    csv_dir = None
    knowledge_name = knowledge_file.stem
    if knowledge_name.startswith("knowledge_"):
        csv_dir = knowledge_name.replace("knowledge_", "")

    # ディレクトリ情報を考慮してパスを構築
    if "/" in filename:
        target_path = f"csv/{filename}"
    elif csv_dir:
        target_path = f"csv/{csv_dir}/{filename}"
    else:
        target_path = f"csv/{filename}"

    # 実行
    save_path = _apply_update_plan_csv_full(target_path, plan.model_dump(), knowledge_file, time_manager)

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
