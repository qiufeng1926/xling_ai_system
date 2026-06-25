"""飞书云文档正文导出（docx / sheet / bitable 等 → 纯文本快照）"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from config.config import feishu_api_base
from integrations.feishu.errors import FeishuError
from integrations.feishu.file_types import build_file_url


def _headers(user_access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {user_access_token}"}


def _check(data: dict[str, Any], *, action: str) -> dict[str, Any]:
    if data.get("code", 0) != 0:
        raise FeishuError(
            int(data.get("code", -1)),
            str(data.get("msg") or f"{action}失败"),
        )
    return data.get("data") or {}


def _col_letter(col_count: int) -> str:
    """列数 → Excel 列名（1→A, 26→Z, 27→AA）"""
    n = max(col_count, 1)
    letters = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _cell_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(_cell_str(v) for v in value)
    if isinstance(value, dict):
        return str(value.get("text") or value.get("name") or value)
    return str(value).replace("\t", " ").replace("\n", " ")


def _rows_to_tsv(values: list[list[Any]]) -> str:
    lines: list[str] = []
    for row in values:
        if not isinstance(row, list):
            continue
        lines.append("\t".join(_cell_str(c) for c in row))
    return "\n".join(lines)


def _export_docx(user_access_token: str, document_id: str) -> dict[str, str]:
    base = feishu_api_base.rstrip("/")
    meta_url = f"{base}/open-apis/docx/v1/documents/{document_id}"
    raw_url = f"{base}/open-apis/docx/v1/documents/{document_id}/raw_content"

    with httpx.Client(timeout=30.0) as client:
        meta_resp = client.get(meta_url, headers=_headers(user_access_token))
        meta = _check(meta_resp.json(), action="获取文档元数据")
        document = meta.get("document") or {}
        title = (document.get("title") or "").strip()
        url = (document.get("url") or "").strip() or build_file_url("docx", document_id)

        raw_resp = client.get(raw_url, headers=_headers(user_access_token), params={"lang": 0})
        raw = _check(raw_resp.json(), action="导出文档正文")
        content = (raw.get("content") or "").strip()

    return {"title": title, "content": content, "url": url}


def _export_sheet(user_access_token: str, spreadsheet_token: str) -> dict[str, str]:
    base = feishu_api_base.rstrip("/")
    meta_url = f"{base}/open-apis/sheets/v3/spreadsheets/{spreadsheet_token}"
    sheets_url = f"{base}/open-apis/sheets/v3/spreadsheets/{spreadsheet_token}/sheets/query"

    with httpx.Client(timeout=45.0) as client:
        meta_resp = client.get(meta_url, headers=_headers(user_access_token))
        meta = _check(meta_resp.json(), action="获取表格元数据")
        spreadsheet = meta.get("spreadsheet") or {}
        title = (spreadsheet.get("title") or "").strip()
        url = build_file_url("sheet", spreadsheet_token)

        sheets_resp = client.get(sheets_url, headers=_headers(user_access_token))
        sheets_data = _check(sheets_resp.json(), action="获取工作表列表")
        sheets = sheets_data.get("sheets") or []

        parts: list[str] = []
        for sheet in sheets[:20]:
            if not isinstance(sheet, dict):
                continue
            sheet_id = (sheet.get("sheet_id") or "").strip()
            sheet_title = (sheet.get("title") or sheet_id or "工作表").strip()
            if not sheet_id:
                continue
            grid = sheet.get("grid_properties") or {}
            row_count = min(int(grid.get("row_count") or 200), 500)
            col_count = min(int(grid.get("column_count") or 26), 52)
            end_col = _col_letter(col_count)
            range_str = f"{sheet_id}!A1:{end_col}{row_count}"
            range_encoded = quote(range_str, safe="")
            values_url = (
                f"{base}/open-apis/sheets/v2/spreadsheets/{spreadsheet_token}/values/{range_encoded}"
            )
            val_resp = client.get(
                values_url,
                headers=_headers(user_access_token),
                params={"valueRenderOption": "ToString"},
            )
            val_data = _check(val_resp.json(), action=f"读取工作表 {sheet_title}")
            value_range = val_data.get("valueRange") or {}
            values = value_range.get("values") or []
            tsv = _rows_to_tsv(values)
            if tsv.strip():
                parts.append(f"## {sheet_title}\n{tsv}")

    content = "\n\n".join(parts).strip()
    return {"title": title, "content": content, "url": url}


def _export_bitable(user_access_token: str, app_token: str) -> dict[str, str]:
    base = feishu_api_base.rstrip("/")
    app_url = f"{base}/open-apis/bitable/v1/apps/{app_token}"
    tables_url = f"{base}/open-apis/bitable/v1/apps/{app_token}/tables"

    with httpx.Client(timeout=45.0) as client:
        app_resp = client.get(app_url, headers=_headers(user_access_token))
        app_data = _check(app_resp.json(), action="获取多维表格元数据")
        app_info = app_data.get("app") or {}
        title = (app_info.get("name") or "").strip()
        url = build_file_url("bitable", app_token)

        tables_resp = client.get(tables_url, headers=_headers(user_access_token), params={"page_size": 20})
        tables_data = _check(tables_resp.json(), action="获取数据表列表")
        tables = tables_data.get("items") or []

        parts: list[str] = []
        for table in tables[:10]:
            if not isinstance(table, dict):
                continue
            table_id = (table.get("table_id") or "").strip()
            table_name = (table.get("name") or table_id or "数据表").strip()
            if not table_id:
                continue
            records_url = (
                f"{base}/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records"
            )
            rec_resp = client.get(
                records_url,
                headers=_headers(user_access_token),
                params={"page_size": 100},
            )
            rec_data = _check(rec_resp.json(), action=f"读取数据表 {table_name}")
            records = rec_data.get("items") or []
            if not records:
                continue
            parts.append(f"## {table_name}")
            for rec in records[:100]:
                if not isinstance(rec, dict):
                    continue
                fields = rec.get("fields") or {}
                if not isinstance(fields, dict):
                    continue
                row_parts = [f"{k}: {_cell_str(v)}" for k, v in fields.items()]
                if row_parts:
                    parts.append(" | ".join(row_parts))

    content = "\n".join(parts).strip()
    return {"title": title, "content": content, "url": url}


def _export_unsupported(file_type: str, token: str, *, hint: str) -> dict[str, str]:
    return {
        "title": "",
        "content": hint,
        "url": build_file_url(file_type, token),
    }


def export_document_text(user_access_token: str, *, token: str, file_type: str) -> dict[str, str]:
    """按类型导出可读文本快照。"""
    normalized = (file_type or "docx").strip().lower()
    doc_token = (token or "").strip()
    if not doc_token:
        raise ValueError("缺少文档 token")

    if normalized in {"docx", "doc"}:
        return _export_docx(user_access_token, doc_token)
    if normalized == "sheet":
        return _export_sheet(user_access_token, doc_token)
    if normalized == "bitable":
        return _export_bitable(user_access_token, doc_token)
    if normalized in {"slides", "mindnote"}:
        return _export_unsupported(
            normalized,
            doc_token,
            hint=f"（{normalized} 类型暂不支持正文快照，请在飞书中查看完整内容）",
        )
    return _export_unsupported(normalized, doc_token, hint="（该文件类型暂不支持正文快照）")
