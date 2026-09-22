from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone
from typing import Any, Sequence

import gspread
import psycopg2
from google.oauth2.service_account import Credentials

from app.config import DATABASE_DSN

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
TABLES = ("users", "test_progress", "referrals")
BATCH_ROWS = 20_000


def _google_client() -> gspread.Client:
    credentials_b64 = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_B64", "").strip()
    credentials_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON", "").strip()
    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()

    if credentials_b64:
        try:
            decoded = base64.b64decode(credentials_b64, validate=True).decode("utf-8")
            info = json.loads(decoded)
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeError(
                "GOOGLE_APPLICATION_CREDENTIALS_B64 содержит некорректный "
                "Base64 или JSON"
            ) from error
        credentials = Credentials.from_service_account_info(info, scopes=SCOPES)
    elif credentials_json:
        info = json.loads(credentials_json)
        credentials = Credentials.from_service_account_info(info, scopes=SCOPES)
    elif credentials_path:
        credentials = Credentials.from_service_account_file(
            credentials_path,
            scopes=SCOPES,
        )
    else:
        raise RuntimeError(
            "Для Google Sheets задайте GOOGLE_APPLICATION_CREDENTIALS_B64, "
            "GOOGLE_APPLICATION_CREDENTIALS_JSON или "
            "GOOGLE_APPLICATION_CREDENTIALS"
        )

    return gspread.authorize(credentials)


def _format_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _chunks(sequence: Sequence[list[str]], size: int):
    for index in range(0, len(sequence), size):
        yield sequence[index : index + size]


def _ensure_worksheet(
    spreadsheet: gspread.Spreadsheet,
    title: str,
    columns: int,
) -> gspread.Worksheet:
    try:
        worksheet = spreadsheet.worksheet(title)
        if worksheet.col_count < columns:
            worksheet.add_cols(columns - worksheet.col_count)
        return worksheet
    except gspread.exceptions.WorksheetNotFound:
        return spreadsheet.add_worksheet(
            title=title,
            rows=100,
            cols=max(columns, 1),
        )


def _replace_worksheet(
    worksheet: gspread.Worksheet,
    headers: list[str],
    rows: list[list[str]],
) -> None:
    worksheet.clear()

    if len(rows) <= BATCH_ROWS:
        worksheet.update([headers, *rows], value_input_option="RAW")
    else:
        worksheet.update([headers], value_input_option="RAW")
        for chunk in _chunks(rows, BATCH_ROWS):
            worksheet.append_rows(chunk, value_input_option="RAW")

    try:
        worksheet.format("1:1", {"textFormat": {"bold": True}})
        worksheet.freeze(rows=1)
    except Exception:
        pass


def sync_full(spreadsheet_id: str) -> None:
    client = _google_client()
    spreadsheet = client.open_by_key(spreadsheet_id)

    with psycopg2.connect(DATABASE_DSN) as connection:
        with connection.cursor() as cursor:
            for table_name in TABLES:
                cursor.execute(f'SELECT * FROM "{table_name}"')
                records = cursor.fetchall()
                headers = [description[0] for description in cursor.description]
                rows = [[_format_cell(value) for value in row] for row in records]
                worksheet = _ensure_worksheet(
                    spreadsheet,
                    table_name,
                    len(headers),
                )
                _replace_worksheet(worksheet, headers, rows)
