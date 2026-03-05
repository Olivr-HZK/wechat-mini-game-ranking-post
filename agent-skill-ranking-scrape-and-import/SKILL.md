---
name: ranking-scrape-and-import-agent
description: 独立封装引力引擎人气榜爬虫与入库的通用 Skill，包含一键脚本 weekly_scrape_and_import、scrape_weekly_popularity 爬虫、import_ranking_csv_to_tables 入库脚本和 SQLite 表结构。任何 Agent / 项目只要复制整个目录即可直接使用该工作流。
---

# 人气榜爬虫与入库（独立 Skill）

本目录是一个**完全独立于项目**的 Skill，打包后交给其它 Agent / 仓库即可使用，无需依赖你当前的 Python 项目代码。

- 不依赖现有项目的 `config.py`、`modules.database` 等模块
- 自带 SQLite 建表逻辑与 CSV → DB 入库逻辑
- 只依赖：Python 3、Playwright（Chromium）、bash

> 建议把整个 `agent-skill-ranking-scrape-and-import/` 目录打包（如 zip）发给其它 Agent 使用。

---

## 目录结构

```text
agent-skill-ranking-scrape-and-import/
├── SKILL.md                        # 本文件：Skill 说明
├── requirements.txt                # Python 依赖（主要是 playwright）
├── scripts/
│   ├── weekly_scrape_and_import.sh # 一键：爬虫 + 入库
│   ├── scrapers/
│   │   └── scrape_weekly_popularity.py
│   └── tools/
│       └── import_ranking_csv_to_tables.py
└── data/                           # 运行时生成：人气榜 CSV、SQLite 数据库等
    └── 人气榜/
        └── YYYY-MM-DD~YYYY-MM-DD/  # 按周划分的目录（脚本自动创建）
```

所有脚本都以 **Skill 根目录** 为基准路径，可以单独移动到任意位置使用。

---

## 一键执行流程

在 `agent-skill-ranking-scrape-and-import/` 目录内：

```bash
cd agent-skill-ranking-scrape-and-import
./scripts/weekly_scrape_and_import.sh
# 或指定监控日期（用于计算“上一周”）
./scripts/weekly_scrape_and_import.sh 2026-02-24
```

一键脚本会完成：

1. **爬虫**：通过 Playwright 打开引力引擎人气榜，爬取上一周的微信/抖音完整榜和异动榜
2. **写 CSV**：在 `data/人气榜/{周范围}/` 下生成：
   - `wx_full.csv`, `wx_anomalies.csv`
   - `dy_full.csv`, `dy_anomalies.csv`
3. **入库**：将上述 4 个 CSV 导入同级目录下的 `data/videos.db` 中的两张表：
   - `top20_ranking`（完整榜）
   - `rank_changes`（异动榜）

---

## 爬虫脚本

- 路径：`scripts/scrapers/scrape_weekly_popularity.py`
- 目标页面：`https://web.gravity-engine.com/#/manage/rank`
- 使用 Playwright（Chromium）+ 已登录的用户数据目录（默认 `data/pw_user_data`）

**输出目录 & 文件：**

- 目录：`data/人气榜/{YYYY-MM-DD~YYYY-MM-DD}/`
- 文件：
  - `wx_full.csv` / `wx_anomalies.csv`
  - `dy_full.csv` / `dy_anomalies.csv`

**CSV 列（11 列统一格式）：**

```text
排名,游戏名称,游戏类型,平台,来源,榜单,监控日期,发布时间,开发公司,排名变化,地区
```

**关键点：**

- 微信：只保留【休闲】类，排名取「休闲:X名」中的 X
- 抖音：直接按列表序号
- `发布时间` 字段统一写入「周平均排名:xx」
- `排名变化` 从 SVG 图标 + 文案解析成 `↑N` / `↓N` / `新进榜` / `--`
- `地区` 固定为「中国」

**常用 CLI：**

```bash
python scripts/scrapers/scrape_weekly_popularity.py --platform all
python scripts/scrapers/scrape_weekly_popularity.py --platform wechat --monitor-date 2026-02-24
python scripts/scrapers/scrape_weekly_popularity.py --platform douyin --limit 50
```

---

## 入库脚本（独立版）

- 路径：`scripts/tools/import_ranking_csv_to_tables.py`
- 特点：不依赖任何外部模块，内部通过 `sqlite3` 自行：
  - 建表（`top20_ranking`、`rank_changes`）
  - 删除同周同平台旧数据
  - 插入 CSV 数据

**默认行为：**

- `data/videos.db` 为数据库文件（若不存在会自动创建）
- 人气榜根目录：`data/人气榜`
- 未指定周目录时，会在 `data/人气榜` 下选择**最近修改时间**的包含 `~` 的目录

**CLI：**

```bash
python scripts/tools/import_ranking_csv_to_tables.py
python scripts/tools/import_ranking_csv_to_tables.py "data/人气榜/2026-02-16~2026-02-22"
python scripts/tools/import_ranking_csv_to_tables.py --week-dir "data/人气榜/2026-02-16~2026-02-22"
```

---

## 数据库结构（内置）

脚本会在 `data/videos.db` 中自动创建如下两张表：

```sql
CREATE TABLE IF NOT EXISTS top20_ranking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_range TEXT NOT NULL,
    platform_key TEXT NOT NULL, -- wx / dy
    rank TEXT,
    game_name TEXT,
    game_type TEXT,
    platform TEXT,
    source TEXT,
    board_name TEXT,
    monitor_date TEXT,
    publish_time TEXT,
    company TEXT,
    rank_change TEXT,
    region TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_top20_week_platform
ON top20_ranking(week_range, platform_key);

CREATE TABLE IF NOT EXISTS rank_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_range TEXT NOT NULL,
    platform_key TEXT NOT NULL,
    rank TEXT,
    game_name TEXT,
    game_type TEXT,
    platform TEXT,
    source TEXT,
    board_name TEXT,
    monitor_date TEXT,
    publish_time TEXT,
    company TEXT,
    rank_change TEXT,
    region TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_rank_changes_week_platform
ON rank_changes(week_range, platform_key);
```

> CSV 11 列与表字段一一对应（外加 `week_range`、`platform_key` 两个逻辑主键）。

---

## 依赖与安装

在 Skill 根目录：

```bash
python -m venv .venv
source .venv/bin/activate  # Windows 使用 .venv\\Scripts\\activate
pip install -r requirements.txt

# Playwright 浏览器安装
python -m playwright install chromium
```

首次使用时需要在浏览器里登录引力引擎一次，以便后续复用登录态：

```bash
python -m playwright codegen https://web.gravity-engine.com/#/manage/rank --user-data-dir=data/pw_user_data
```

---

## 给其它 Agent 使用的方式

- 直接把 `agent-skill-ranking-scrape-and-import/` 整个目录打包发送（例如 zip）
- 在目标环境解压后：
  1. 安装依赖（见上节）
  2. 运行 `./scripts/weekly_scrape_and_import.sh` 完成爬虫 + 入库
  3. 其它 Agent 可以根据 `data/videos.db` / CSV 继续做分析、生成报告等工作

