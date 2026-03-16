#!/usr/bin/env bash
#
# 每周运行一次：爬取引力引擎（微信/抖音人气周榜）。
# 输出目录：data/人气榜/{周范围}/（如 2026-1-19~2026-1-25）
# 生成文件：wx_full.csv、wx_anomalies.csv、dy_full.csv、dy_anomalies.csv
#
# 用法：
#   ./scripts/scrapers/weekly_scrape_anomalies.sh
#   ./scripts/scrapers/weekly_scrape_anomalies.sh 2026-02-03   # 指定监控日期
#
# 定时（crontab 示例，每周一早上 8 点）：
#   0 8 * * 1 /path/to/wechat-mini-game-ranking-post/scripts/scrapers/weekly_scrape_anomalies.sh >> /path/to/logs/weekly_scrape.log 2>&1
#

# 不 set -e，以便某一步失败后继续执行后续步骤并汇总失败状态

# 监控日期，默认今天（YYYY-MM-DD）
MONITOR_DATE="${1:-}"

# 脚本所在目录 -> 项目根目录（scripts/scrapers 的上级的上级）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

# 若存在虚拟环境则激活（支持 .venv / venv / env）
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

echo "============================================================"
echo "每周异动数据爬取 - $(date '+%Y-%m-%d %H:%M:%S')"
echo "项目目录: $PROJECT_ROOT"
echo "监控日期: ${MONITOR_DATE:-（默认今天）}"
echo "============================================================"

FAILED=0

# ---------- 引力引擎 - 四份榜单（wx/dy 完整休闲榜 + 异动榜） ----------
echo ""
echo "引力引擎 - 微信/抖音 完整榜 + 异动榜（共 4 个 CSV）"
if [ -n "$MONITOR_DATE" ]; then
    python scripts/scrapers/scrape_weekly_popularity.py --platform all --monitor-date "$MONITOR_DATE" || FAILED=1
else
    python scripts/scrapers/scrape_weekly_popularity.py --platform all || FAILED=1
fi

echo ""
echo "============================================================"
if [ $FAILED -eq 0 ]; then
    echo "全部完成 - $(date '+%Y-%m-%d %H:%M:%S')"
else
    echo "部分任务失败，请检查上方输出 - $(date '+%Y-%m-%d %H:%M:%S')"
fi
echo "============================================================"

exit $FAILED
