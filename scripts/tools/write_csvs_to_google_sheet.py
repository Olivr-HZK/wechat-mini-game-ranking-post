"""
批量将一个目录下的 CSV 文件写入同一个 Google Sheet：
- 每个 CSV 对应一个新的工作表（Sheet）
- 工作表名称默认使用文件名（去掉扩展名），可选加前缀

依赖现有的 Sheets 配置和认证逻辑（复用 write_rankings_to_google_sheet）：
- GOOGLE_SHEET_ID              目标表格 ID 或 URL
- GOOGLE_SHEETS_CREDENTIALS    Sheets 专用凭证 JSON 路径
- GOOGLE_SHEETS_TOKEN          可选，token 保存路径

用法示例（项目根目录）：
  # 将 data/人气榜/2026-1-19~2026-1-25 下所有 csv 写入同一个表
  python -m scripts.tools.write_csvs_to_google_sheet \\
    --dir "data/人气榜/2026-1-19~2026-1-25"

  # 带工作表前缀（例如：周报_）
  python -m scripts.tools.write_csvs_to_google_sheet \\
    --dir "data/人气榜/2026-1-19~2026-1-25" \\
    --sheet-prefix "周报_"
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import List

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402
from scripts.tools import write_rankings_to_google_sheet as base_sheet  # noqa: E402


def _read_csv(csv_path: Path) -> List[List[str]]:
    """读取 CSV 文件为二维数组（包含表头）。自动尝试常见编码。"""
    encodings = ["utf-8-sig", "utf-8", "gbk", "gb2312"]
    last_err: Exception | None = None
    for enc in encodings:
        try:
            with csv_path.open("r", encoding=enc, newline="") as f:
                reader = csv.reader(f)
                rows = list(reader)
            if not rows:
                raise ValueError(f"CSV 为空：{csv_path}")
            return rows
        except Exception as e:  # noqa: BLE001
            last_err = e
            continue
    raise RuntimeError(f"无法读取 CSV：{csv_path}，最后错误：{last_err}")


def _sheet_name_from_path(csv_path: Path, prefix: str = "") -> str:
    """根据文件名生成工作表名称，可选添加前缀。"""
    name = csv_path.stem
    sheet_name = f"{prefix}{name}" if prefix else name
    # Google Sheets 对 sheet 名有长度限制，这里简单截断到 80 字符
    return sheet_name[:80] or "Sheet1"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="将一个或一批 CSV 文件写入同一个 Google Sheet（每个 CSV 一个工作表）"
    )
    ap.add_argument(
        "--dir",
        help="包含 CSV 文件的目录路径（与 --file 二选一，可不填）",
    )
    ap.add_argument(
        "--file",
        help="单个 CSV 文件路径（与 --dir 二选一，可不填）",
    )
    ap.add_argument(
        "--sheet-prefix",
        default="",
        help="为每个工作表名称增加前缀（可选，如：周报_）",
    )
    args = ap.parse_args()

    # 1) 解析 Spreadsheet ID
    raw_id = (config.GOOGLE_SHEET_ID or "").strip()
    if not raw_id:
        print("错误：未配置 GOOGLE_SHEET_ID，请在 .env 中设置")
        return 1
    spreadsheet_id = base_sheet._extract_spreadsheet_id(raw_id)
    print(f"[*] Spreadsheet ID: {spreadsheet_id}")

    # 2) 解析输入：支持目录或单个文件
    dir_arg = (args.dir or "").strip()
    file_arg = (args.file or "").strip()

    if not dir_arg and not file_arg:
        print("错误：请至少提供 --dir 或 --file 其中之一")
        return 1
    if dir_arg and file_arg:
        print("错误：--dir 与 --file 只能二选一，请只填一个")
        return 1

    csv_files: List[Path] = []

    if dir_arg:
        dir_path = Path(dir_arg)
        if not dir_path.exists() or not dir_path.is_dir():
            print(f"错误：CSV 目录不存在：{dir_path}")
            return 1
        csv_files = sorted(dir_path.glob("*.csv"))
        if not csv_files:
            print(f"错误：目录下未找到 CSV：{dir_path}")
            return 1
        print(f"[*] 在目录 {dir_path} 中找到 {len(csv_files)} 个 CSV，将逐个写入工作表")
    else:
        file_path = Path(file_arg)
        if not file_path.exists() or not file_path.is_file():
            print(f"错误：CSV 文件不存在：{file_path}")
            return 1
        csv_files = [file_path]
        print(f"[*] 将处理单个 CSV 文件：{file_path}")

    # 3) 获取 Sheets 凭证与 service
    try:
        creds = base_sheet._get_credentials()
    except FileNotFoundError as e:
        print(f"错误：{e}")
        return 1
    if not creds:
        return 1

    from googleapiclient.discovery import build  # type: ignore

    service = build("sheets", "v4", credentials=creds)

    # 4) 逐个 CSV 写入各自的 Sheet（不清空整表，只清空当前 Sheet 的内容）
    for csv_path in csv_files:
        try:
            print(f"\n[*] 处理 CSV：{csv_path}")
            rows = _read_csv(csv_path)
            print(f"    行数（含表头）：{len(rows)}")

            sheet_name = _sheet_name_from_path(csv_path, prefix=args.sheet_prefix.strip())
            print(f"    目标工作表：{sheet_name}")

            # 确保工作表存在
            base_sheet._get_or_create_sheet(service, spreadsheet_id, sheet_name)
            # 写入数据（先清空该 Sheet）
            ok = base_sheet._write_to_sheet(
                service,
                spreadsheet_id,
                sheet_name,
                rows,
                clear_first=True,
            )
            if not ok:
                print(f"    ✗ 写入 Sheet 失败：{sheet_name}")
            else:
                print(f"    ✓ 写入 Sheet 成功：{sheet_name}")
        except Exception as e:  # noqa: BLE001
            print(f"    ✗ 处理 {csv_path.name} 时出错：{e}")

    sheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
    print("\n✅ 全部 CSV 已处理完毕")
    print(f"   表格链接：{sheet_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

