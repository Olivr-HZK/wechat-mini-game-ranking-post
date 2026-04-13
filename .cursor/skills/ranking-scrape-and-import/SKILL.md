---
name: ranking-scrape-and-import
description: Encapsulates the gravity-engine ranking crawler and DB import workflow. Covers weekly_scrape_and_import script, scrape_weekly_popularity, import_ranking_csv_to_tables, top20_ranking/rank_changes tables, and schedule. Use when the user asks about or needs to modify crawler, import, scheduled task, 人气榜 CSV, or anomaly (异动) logic.
---

**独立技能已迁至个人目录**：完整自洽的「人气榜爬虫与入库」skill（含 reference、脚本说明）位于 `~/.cursor/skills/ranking-scrape-and-import/`，独立于项目，可跨项目使用。本文件仅作项目内快捷入口，详细内容以该目录为准。

---

# 人气榜爬虫与入库（项目内入口）

本技能描述「引力引擎人气榜爬取 + 入库」的脚本、依赖与用法。修改或排查相关逻辑时请先查阅本技能。

## 一键流程（推荐）

**脚本**: `scripts/weekly_scrape_and_import.sh`

- 步骤 1：爬取上一周 wx/dy × 人气+畅销（`scrape_weekly_popularity.py --chart both --platform all`；脚本仅支持 `most_played`/`bestseller`/`both`，无 `all`、无畅玩），CSV 写入 `data/人气榜|畅销榜/{周范围}/`
- 步骤 2：将同一周三个目录下的 CSV 导入 `top20_ranking`、`rank_changes`（`platform_key` 为 `wx`/`dy`，`chart_key` 区分人气/畅销/畅玩；抖音「畅玩」目录对应新游榜，入库为 `chart_key=new_games`；同一 `(week_range, platform_key, chart_key)` 先删后插）
- 步骤 3：运行 `scripts/senders/send_wechat_douyin_weekly_push.py`，从 `data/wechatdouyin.db` 推送微信/抖音小游戏周报到飞书/企微（依赖项目根 `.env` Webhook）。若只要爬取+入库：设置 `SKIP_WEEKLY_PUSH=1`。

**运行**（项目根目录）:
```bash
./scripts/weekly_scrape_and_import.sh
# 或指定监控日期
./scripts/weekly_scrape_and_import.sh 2026-02-24
# 只爬取+入库，不推送
SKIP_WEEKLY_PUSH=1 ./scripts/weekly_scrape_and_import.sh
```

**依赖**: 需在项目根执行；若有 `.venv`/`venv`/`env`，脚本会先激活再跑 Python。推送步骤需配置 `.env`（如 `FEISHU_WEBHOOK_URL`、`WECOM_WEBHOOK_URL`）。

---

## 爬虫

**脚本**: `scripts/scrapers/scrape_weekly_popularity.py`  
**目标**: https://web.gravity-engine.com/#/manage/rank （需登录）

- 输出目录: `data/人气榜|畅销榜|畅玩榜/{周范围}/`，周范围格式 `YYYY-MM-DD~YYYY-MM-DD`（月日补零）
- 输出文件: 各目录 `wx_full.csv`, `wx_anomalies.csv`, `dy_full.csv`, `dy_anomalies.csv`
- 抖音侧「榜单」列：人气→热门周榜、畅玩→新游周榜（与产品文案一致）
- 异动规则: **新进榜** 或 **上升>10** 或 **下降>10**（阈值 `--rank-surge-threshold`，默认 10）
- 排名变化: 从页面标签 + SVG 图标识别方向，写入 `↑N` / `↓N` / `新进榜`

**常用命令**:
```bash
python scripts/scrapers/scrape_weekly_popularity.py --platform all
python scripts/scrapers/scrape_weekly_popularity.py --platform wechat --monitor-date 2026-02-24
python scripts/scrapers/scrape_weekly_popularity.py --platform douyin --limit 50
```

**依赖**: Playwright（Chromium）、`data/pw_user_data` 可复用登录态；无头运行。

---

## 入库

**脚本**: `scripts/tools/import_ranking_csv_to_tables.py`

- 从 `data/人气榜|畅销榜|畅玩榜/{同一周范围}/` 读取各 4 个 CSV，写入 `top20_ranking`（full）、`rank_changes`（anomalies）
- 表字段 **`platform_key`**（`wx`/`dy`）与 **`chart_key`**（`popularity`/`bestseller`/`casual_play`/`new_games`）分列存储；微信第三榜为 `casual_play`（畅玩），抖音第三榜为 `new_games`（新游）；同一 `(week_range, platform_key, chart_key)` **先 DELETE 再 INSERT**
- CSV 11 列与表字段一一对应（排名、游戏名称、游戏类型、平台、来源、榜单、监控日期、发布时间、开发公司、排名变化、地区）

**运行**:
```bash
python scripts/tools/import_ranking_csv_to_tables.py
python scripts/tools/import_ranking_csv_to_tables.py "data/人气榜/2026-02-16~2026-02-22"
python scripts/tools/import_ranking_csv_to_tables.py --week-dir "data/人气榜/2026-02-16~2026-02-22"
```

**依赖**: `modules.database.VideoDatabase`（`insert_top20_ranking`, `insert_rank_changes`）、`config.RANKINGS_CSV_PATH`、项目根为当前工作目录。

---

## 数据库表

- **top20_ranking**: 每周 full 榜，字段含 `week_range`, `platform_key`（wx/dy）, `chart_key`（榜单类型）, `rank`, `game_name`, …, `board_name`（CSV「榜单」长名称）, `rank_change`, `region`
- **rank_changes**: 每周异动榜，字段同上；`rank_change` 存原文（含 `↑`/`↓`）

表结构在 `modules/database.py` 的 `_init_database` 中创建；插入逻辑在同一文件的 `insert_top20_ranking`、`insert_rank_changes`，内含「先删后插」避免重复。

---

## 定时任务

- **配置**: `scripts/schedule/`（launchd plist + README）
- **执行内容**: 每周一 10:00 运行 `scripts/weekly_scrape_and_import.sh`
- **说明**: 见 `scripts/schedule/README.md`（launchd 与 crontab 两种方式）

---

## 相关文件速查

| 用途           | 路径 |
|----------------|------|
| 一键爬虫+入库  | `scripts/weekly_scrape_and_import.sh` |
| 人气榜爬虫     | `scripts/scrapers/scrape_weekly_popularity.py` |
| CSV 入库       | `scripts/tools/import_ranking_csv_to_tables.py` |
| 表与插入       | `modules/database.py`（top20_ranking, rank_changes） |
| 周范围补零迁移 | `scripts/tools/migrate_week_range_zero_pad.py` |
| 定时说明       | `scripts/schedule/README.md` |

修改爬虫逻辑（异动规则、排名变化解析、平台）时改 `scrape_weekly_popularity.py`；修改入库或表结构时改 `database.py` 与 `import_ranking_csv_to_tables.py`。
