"""
将游戏排行榜数据写入 Google Sheets。

- 从 CSV 读取（默认：data/人气榜 下最新文件），或 --from-db 从数据库 games 表读取
- Sheet ID、凭证路径均从 .env 加载（config），不复用现有 Drive 凭证

env：
  GOOGLE_SHEET_ID      目标表格 ID 或完整 URL（必填）
  GOOGLE_SHEETS_CREDENTIALS  OAuth2/服务账号凭证 JSON 路径（必填）
  GOOGLE_SHEETS_TOKEN  token 保存路径（可选，仅 OAuth2 时用）

用法：
  python write_rankings_to_google_sheet.py
  python write_rankings_to_google_sheet.py --from-db
  python write_rankings_to_google_sheet.py --csv "data/人气榜/2026-1-12~2026-1-18.csv" --sheet-name "周榜"
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from __future__ import annotations

import argparse
import csv
import json
import os
import re
from pathlib import Path
from typing import Any, List, Optional

import config

try:
    from google.oauth2.credentials import Credentials
    from google.oauth2 import service_account
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_SHEETS_AVAILABLE = True
except ImportError:
    GOOGLE_SHEETS_AVAILABLE = False
    print("警告：未安装Google Sheets API库，请运行: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")


SCOPES = ['https://www.googleapis.com/auth/spreadsheets']


def _is_service_account(credentials_file: str) -> bool:
    """检测凭证文件是否为服务账号类型"""
    try:
        import json
        with open(credentials_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('type') == 'service_account'
    except Exception:
        return False


def _get_credentials():
    """从 env 指定的独立 JSON 获取凭证，支持服务账号和 OAuth2 两种类型。"""
    if not GOOGLE_SHEETS_AVAILABLE:
        return None

    credentials_file = (config.GOOGLE_SHEETS_CREDENTIALS or "").strip()
    if not credentials_file or not os.path.exists(credentials_file):
        raise FileNotFoundError(
            "未配置或找不到 Google Sheets 凭证文件。\n"
            "在 .env 中设置 GOOGLE_SHEETS_CREDENTIALS=path/to/your/sheets_credentials.json\n"
            "（单独配置，不复用 Drive 的 credentials.json）"
        )

    # 检测是否为服务账号
    if _is_service_account(credentials_file):
        # 服务账号：直接使用，无需 OAuth 流程
        print("[*] 检测到服务账号凭证，直接使用")
        creds = service_account.Credentials.from_service_account_file(
            credentials_file,
            scopes=SCOPES
        )
        return creds

    # OAuth2 客户端凭证：需要 OAuth 流程
    print("[*] 检测到 OAuth2 客户端凭证，使用 OAuth 流程")
    token_file = (config.GOOGLE_SHEETS_TOKEN or "").strip()
    if not token_file:
        token_file = str(Path(credentials_file).parent / "token_sheets.json")

    creds = None
    if os.path.exists(token_file):
        try:
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)
        except Exception as e:
            print(f"加载 token 时出错：{e}")

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"刷新 token 时出错：{e}")
                creds = None

        if not creds:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)

        Path(token_file).parent.mkdir(parents=True, exist_ok=True)
        with open(token_file, "w") as f:
            f.write(creds.to_json())

    return creds


def _extract_spreadsheet_id(url_or_id: str) -> str:
    """从 Google Sheets URL 或直接 ID 提取 spreadsheet_id"""
    s = (url_or_id or "").strip()
    if not s:
        raise ValueError("spreadsheet_id 或 URL 不能为空")

    # 如果是 URL，提取 ID
    m = re.search(r'/spreadsheets/d/([a-zA-Z0-9_-]+)', s)
    if m:
        return m.group(1)

    # 如果看起来就是 ID（只包含字母数字和 -_），直接返回
    if re.match(r'^[a-zA-Z0-9_-]+$', s):
        return s

    raise ValueError(f"无法从输入中提取 spreadsheet_id: {s}")


def _read_csv_to_rows(csv_path: Path) -> List[List[str]]:
    """读取 CSV 文件，返回行列表（每行是一个字符串列表）"""
    rows: List[List[str]] = []
    encodings = ['utf-8-sig', 'utf-8', 'gbk', 'gb2312']

    for enc in encodings:
        try:
            with csv_path.open('r', encoding=enc, newline='') as f:
                reader = csv.reader(f)
                rows = list(reader)
                break
        except UnicodeDecodeError:
            continue
        except Exception as e:
            print(f"读取CSV失败（{enc}）：{e}")
            continue

    if not rows:
        raise ValueError(f"无法读取CSV文件：{csv_path}")

    return rows


def _get_games_table_columns(db_path: str) -> List[str]:
    """从数据库 PRAGMA table_info(games) 获取 games 表所有列名（按表定义顺序）。"""
    import sqlite3

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(games)")
    rows = cursor.fetchall()
    conn.close()
    # sqlite3 PRAGMA: (cid, name, type, notnull, dflt_value, pk)
    return [r[1] for r in rows]


def _best_video_link(g: dict) -> str:
    """优先 share_url > gdrive_url > original_video_url > video_url。"""
    for key in ("share_url", "gdrive_url", "original_video_url", "video_url"):
        v = (g.get(key) or "").strip()
        if v:
            return v
    return ""


def _enrich_games_with_play_and_link(games: List[dict]) -> None:
    """原地为每条 game 添加 视频链接、玩法，便于导出。"""
    for g in games:
        g["视频链接"] = _best_video_link(g)
        g["玩法"] = g.get("gameplay_analysis") or ""


def _games_to_rows(games: List[dict], columns: Optional[List[str]] = None) -> List[List[str]]:
    """将 games 表数据转为 Sheet 行（表头 + 数据行），含 gameplay_analysis 等全部列。"""
    if not games:
        return []

    if columns is None:
        # 兜底：取所有行出现过的 key，首行键顺序优先
        seen = set()
        cols = []
        for g in games:
            for k in g.keys():
                if k not in seen:
                    seen.add(k)
                    cols.append(k)
    else:
        cols = columns

    def _cell(v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, (list, dict)):
            return json.dumps(v, ensure_ascii=False)
        return str(v).strip() if isinstance(v, str) else str(v)

    header = cols
    data = [[_cell(g.get(c)) for c in cols] for g in games]
    return [header] + data


def _get_or_create_sheet(service, spreadsheet_id: str, sheet_name: str) -> int:
    """获取或创建工作表，返回 sheet_id"""
    try:
        spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheets = spreadsheet.get('sheets', [])

        for sheet in sheets:
            props = sheet.get('properties', {})
            if props.get('title') == sheet_name:
                return props.get('sheetId')

        # 不存在则创建
        body = {
            'requests': [{
                'addSheet': {
                    'properties': {
                        'title': sheet_name
                    }
                }
            }]
        }
        result = service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body=body
        ).execute()
        new_sheet_id = result.get('replies', [{}])[0].get('addSheet', {}).get('properties', {}).get('sheetId')
        if new_sheet_id:
            print(f"  ✓ 已创建工作表：{sheet_name} (ID: {new_sheet_id})")
            return new_sheet_id

        raise RuntimeError("创建工作表失败")
    except HttpError as e:
        raise RuntimeError(f"获取/创建工作表失败：{e}")


def _write_to_sheet(
    service,
    spreadsheet_id: str,
    sheet_name: str,
    rows: List[List[str]],
    clear_first: bool = True,
) -> bool:
    """将数据写入 Google Sheet"""
    try:
        range_name = f"{sheet_name}!A1"

        if clear_first:
            # 先清空现有数据（可选）；列多时用 A:ZZ 覆盖 games 全表+玩法/视频链接
            service.spreadsheets().values().clear(
                spreadsheetId=spreadsheet_id,
                range=f"{sheet_name}!A:ZZ"
            ).execute()

        # 写入数据
        body = {
            'values': rows
        }
        result = service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption='USER_ENTERED',  # 自动识别数字/日期等格式
            body=body
        ).execute()

        updated_cells = result.get('updatedCells', 0)
        print(f"  ✓ 已写入 {updated_cells} 个单元格到工作表：{sheet_name}")

        # 可选：格式化表头（加粗）
        if len(rows) > 0:
            try:
                sheet_id = _get_or_create_sheet(service, spreadsheet_id, sheet_name)
                format_body = {
                    'requests': [{
                        'repeatCell': {
                            'range': {
                                'sheetId': sheet_id,
                                'startRowIndex': 0,
                                'endRowIndex': 1,
                            },
                            'cell': {
                                'userEnteredFormat': {
                                    'textFormat': {
                                        'bold': True
                                    }
                                }
                            },
                            'fields': 'userEnteredFormat.textFormat.bold'
                        }
                    }]
                }
                service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body=format_body
                ).execute()
            except Exception:
                pass  # 格式化失败不影响主流程

        return True
    except HttpError as e:
        print(f"写入 Google Sheet 失败：{e}")
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="将游戏排行榜写入 Google Sheets（Sheet ID、凭证从 .env 加载）")
    ap.add_argument("--from-db", action="store_true", help="从数据库 games 表读取并上传（忽略 --csv）")
    ap.add_argument("--csv", default="", help="CSV 路径（默认：data/人气榜 下最新）；--from-db 时无效")
    ap.add_argument("--sheet-name", default="", help="工作表名称（默认：排行榜；--from-db 时为 games）")
    ap.add_argument("--clear", action="store_true", help="写入前清空该工作表")
    ap.add_argument("--limit", type=int, default=0, help="--from-db 时最多导出条数（0=全部）")
    args = ap.parse_args()

    if not GOOGLE_SHEETS_AVAILABLE:
        print("错误：未安装 Google Sheets API 库")
        print("请运行: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")
        return 1

    # 1) Spreadsheet ID 从 env 加载
    raw_id = (config.GOOGLE_SHEET_ID or "").strip()
    if not raw_id:
        print("错误：未配置 GOOGLE_SHEET_ID，请在 .env 中设置")
        return 1
    spreadsheet_id = _extract_spreadsheet_id(raw_id)
    print(f"[*] Spreadsheet ID: {spreadsheet_id}")

    # 2) 数据来源：数据库 games 表 或 CSV
    if args.from_db:
        from modules.database import VideoDatabase

        db = VideoDatabase()
        games = db.get_all_games(limit=args.limit if args.limit else None)
        if not games:
            print("错误：games 表为空")
            return 1
        _enrich_games_with_play_and_link(games)
        columns = _get_games_table_columns(db.db_path)
        extra = ["视频链接", "玩法"]
        for c in extra:
            if c not in columns:
                columns = list(columns) + [c]
        rows = _games_to_rows(games, columns=columns)
        sheet_name = (args.sheet_name or "games").strip()
        print(f"[*] 已从数据库读取 games：{len(games)} 条，{len(columns)} 列（含 玩法、视频链接）")
    else:
        csv_path: Optional[Path] = None
        if args.csv and args.csv.strip():
            csv_path = Path(args.csv.strip())
        else:
            data_dir = Path("data") / "人气榜"
            if data_dir.exists():
                csv_files = list(data_dir.glob("*.csv"))
                if csv_files:
                    csv_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                    csv_path = csv_files[0]
                    print(f"[*] 自动选择最新 CSV：{csv_path}")

        if not csv_path or not csv_path.exists():
            print("错误：未找到 CSV（用 --csv 指定，或确保 data/人气榜 下有 CSV）；或使用 --from-db 从数据库上传")
            return 1

        rows = _read_csv_to_rows(csv_path)
        sheet_name = (args.sheet_name or "排行榜").strip()
        print(f"[*] 已读取 CSV：{len(rows)} 行（含表头）")

    # 3) 认证（独立凭证，从 env）
    try:
        creds = _get_credentials()
    except FileNotFoundError as e:
        print(f"错误：{e}")
        return 1
    if not creds:
        return 1

    service = build("sheets", "v4", credentials=creds)
    _get_or_create_sheet(service, spreadsheet_id, sheet_name)

    success = _write_to_sheet(service, spreadsheet_id, sheet_name, rows, clear_first=bool(args.clear))

    if success:
        sheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid=0"
        print(f"\n✅ 写入完成")
        print(f"   Sheet URL: {sheet_url}")
        return 0
    else:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
