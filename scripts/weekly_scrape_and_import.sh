#!/usr/bin/env bash
#
# 每周执行：爬取上一周「微信+抖音 × 人气榜+畅销榜」（scrape_weekly_popularity.py 仅支持 --chart both，无畅玩）并入库。
# 建议在每周一早上运行，此时“今天”对应的上一周即为刚结束的周一到周日。
#
# 用法：
#   ./scripts/weekly_scrape_and_import.sh              # 爬取 + 入库 + 推送周报（飞书/企微，需 .env）
#   ./scripts/weekly_scrape_and_import.sh 2026-02-24   # 指定监控日期（同上）
#   SKIP_WEEKLY_PUSH=1 ./scripts/weekly_scrape_and_import.sh   # 只爬取+入库，不推送
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
echo "每周榜单爬取 + 入库 + 推送 - $(date '+%Y-%m-%d %H:%M:%S')"
echo "项目目录: $PROJECT_ROOT"
echo "监控日期: ${MONITOR_DATE:-（默认今天，上一周）}"
if [ -n "${SKIP_WEEKLY_PUSH:-}" ]; then
    echo "推送: 已设置 SKIP_WEEKLY_PUSH，将跳过"
else
    echo "推送: 入库后将执行 scripts/senders/send_wechat_douyin_weekly_push.py"
fi
echo "============================================================"

# ---------- 1. 爬虫：两平台 × 人气+畅销（各 full + 异动；--chart 仅支持 most_played|bestseller|both） ----------
echo ""
echo "[1/3] 爬取引力引擎 - 微信/抖音 × 人气榜 + 畅销榜"
if [ -n "$MONITOR_DATE" ]; then
    python scripts/scrapers/scrape_weekly_popularity.py --chart both --platform all --monitor-date "$MONITOR_DATE" || exit 1
else
    python scripts/scrapers/scrape_weekly_popularity.py --chart both --platform all || exit 1
fi

# ---------- 2. 入库：将刚生成的 CSV 导入 top20_ranking、rank_changes ----------
echo ""
echo "[2/3] 导入数据库（最新一周目录）"
python scripts/tools/import_ranking_csv_to_tables.py || exit 1

# ---------- 3. 推送：从 data/wechatdouyin.db 发微信/抖音小游戏周报 ----------
echo ""
if [ -n "${SKIP_WEEKLY_PUSH:-}" ]; then
    echo "[3/3] 跳过推送（SKIP_WEEKLY_PUSH 已设置）"
else
    echo "[3/3] 推送微信/抖音小游戏周报（飞书 / 企业微信，依赖项目根 .env）"
    python scripts/senders/send_wechat_douyin_weekly_push.py || exit 1
fi

echo ""
echo "============================================================"
echo "全部完成 - $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"
