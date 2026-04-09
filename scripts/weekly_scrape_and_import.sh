#!/usr/bin/env bash
#
# 每周执行：爬取上一周「两平台 × 三榜」共 6 组 CSV（人气/畅销/畅玩 × wx/dy）并导入数据库。
# 建议在每周一早上运行，此时“今天”对应的上一周即为刚结束的周一到周日。
#
# 用法：
#   ./scripts/weekly_scrape_and_import.sh              # 使用默认“今天”为参考日期（周一跑即上一周）
#   ./scripts/weekly_scrape_and_import.sh 2026-02-24   # 指定监控日期
#
# 定时任务：见 scripts/schedule/README.md（每周一 10:00）
#

set -e

MONITOR_DATE="${1:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# 虚拟环境
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
echo "每周榜单爬取 + 入库 - $(date '+%Y-%m-%d %H:%M:%S')"
echo "项目目录: $PROJECT_ROOT"
echo "监控日期: ${MONITOR_DATE:-（默认今天，上一周）}"
echo "============================================================"

# ---------- 1. 爬虫：两平台 × 人气/畅销/畅玩（各 full + 异动） ----------
echo ""
echo "[1/2] 爬取引力引擎 - 微信/抖音 × 人气榜/畅销榜/畅玩榜"
if [ -n "$MONITOR_DATE" ]; then
    python scripts/scrapers/scrape_weekly_popularity.py --chart all --platform all --monitor-date "$MONITOR_DATE" || exit 1
else
    python scripts/scrapers/scrape_weekly_popularity.py --chart all --platform all || exit 1
fi

# ---------- 2. 入库：将刚生成的 CSV 导入 top20_ranking、rank_changes ----------
echo ""
echo "[2/2] 导入数据库（最新一周目录）"
python scripts/tools/import_ranking_csv_to_tables.py || exit 1

echo ""
echo "============================================================"
echo "全部完成 - $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"
