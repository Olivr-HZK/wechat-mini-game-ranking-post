#!/usr/bin/env bash
#
# 独立版：每周执行爬虫 + 入库（引力引擎 wx/dy 四份 CSV → SQLite）。
# 目录结构假设为：
#   agent-skill-ranking-scrape-and-import/
#     ├── scripts/
#     │   ├── weekly_scrape_and_import.sh
#     │   ├── scrapers/scrape_weekly_popularity.py
#     │   └── tools/import_ranking_csv_to_tables.py
#     └── data/人气榜/...
#
# 用法（在 Skill 根目录运行）：
#   cd agent-skill-ranking-scrape-and-import
#   ./scripts/weekly_scrape_and_import.sh
#   ./scripts/weekly_scrape_and_import.sh 2026-02-24   # 指定监控日期
#

set -e

MONITOR_DATE="${1:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# 虚拟环境（如果存在就自动激活）
if [ -d "$PROJECT_ROOT/.venv" ] && [ -f "$PROJECT_ROOT/.venv/bin/activate" ]; then
    source "$PROJECT_ROOT/.venv/bin/activate"
    echo "[*] 已激活虚拟环境: .venv"
elif [ -d "$PROJECT_ROOT/venv" ] && [ -f "$PROJECT_ROOT/venv/bin/activate" ]; then
    source "$PROJECT_ROOT/venv/bin/activate"
    echo "[*] 已激活虚拟环境: venv"
elif [ -d "$PROJECT_ROOT/env" ] && [ -f "$PROJECT_ROOT/env/bin/activate" ]; then
    source "$PROJECT_ROOT/env/bin/activate"
    echo "[*] 已激活虚拟环境: env"
fi

LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"

echo "============================================================"
echo "独立 Skill - 每周榜单爬取 + 入库 - $(date '+%Y-%m-%d %H:%M:%S')"
echo "Skill 根目录: $PROJECT_ROOT"
echo "监控日期: ${MONITOR_DATE:-（默认今天，上一周）}"
echo "============================================================"

# ---------- 1. 爬虫：上一周 wx/dy 完整榜 + 异动榜（4 个 CSV） ----------
echo ""
echo "[1/2] 爬取引力引擎 - 微信/抖音 完整榜 + 异动榜"
if [ -n "$MONITOR_DATE" ]; then
    python scripts/scrapers/scrape_weekly_popularity.py --platform all --monitor-date "$MONITOR_DATE" || exit 1
else
    python scripts/scrapers/scrape_weekly_popularity.py --platform all || exit 1
fi

# ---------- 2. 入库：将刚生成的 CSV 导入 top20_ranking、rank_changes ----------
echo ""
echo "[2/2] 导入 SQLite 数据库（最新一周目录）"
python scripts/tools/import_ranking_csv_to_tables.py || exit 1

echo ""
echo "============================================================"
echo "全部完成 - $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"

