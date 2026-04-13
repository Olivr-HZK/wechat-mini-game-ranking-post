# 定时任务：每周一 10:00 爬取上一周榜单、入库并推送周报

## 一键脚本（手动跑一次）

在项目根目录执行：

```bash
./scripts/weekly_scrape_and_import.sh
```

- 会先爬取「上一周」的 **微信 + 抖音 × 人气榜 / 畅销榜 / 畅玩榜**：每个榜单各输出一份完整榜与一份异动榜（`wx_full.csv` / `wx_anomalies.csv` / `dy_full.csv` / `dy_anomalies.csv`），共 **12 个 CSV**，分别落在 `data/人气榜/`、`data/畅销榜/`、`data/畅玩榜/` 下**同一周区间子目录**。
- 再自动根据 **最新一周**（在 `data/人气榜/` 下按修改时间选取）的周区间，把上述三个子目录里该周的 CSV 一并导入数据库表 `top20_ranking`、`rank_changes`（`platform_key` 为 `wx`/`dy`，`chart_key` 区分榜单类型；同一 `(week_range, platform_key, chart_key)` 先删后插）。
- 最后执行 `scripts/senders/send_wechat_douyin_weekly_push.py`，从 `data/wechatdouyin.db` 推送「微信/抖音小游戏周报」到飞书 / 企业微信（需在项目根配置 `.env` 中的 `FEISHU_WEBHOOK_URL`、`WECOM_WEBHOOK_URL` 等）。
- 若在周一运行且不传参数，则「上一周」= 刚结束的周一～周日。
- 可选：`./scripts/weekly_scrape_and_import.sh 2026-02-24` 指定监控日期。
- 若只想爬取+入库、**不推送**：`SKIP_WEEKLY_PUSH=1 ./scripts/weekly_scrape_and_import.sh`

---

## 方式一：macOS launchd（推荐，每周一 10:00）

1. **复制并修改 plist（把项目路径换成你的）**

   ```bash
   cd /Users/oliver/guru/wechat-mini-game-ranking-post
   PROJECT_ROOT=$(pwd)
   mkdir -p logs
   sed "s|__PROJECT_ROOT__|$PROJECT_ROOT|g" scripts/schedule/com.wechat.minigame.weekly_scrape.plist > /tmp/com.wechat.minigame.weekly_scrape.plist
   ```

2. **安装到当前用户 LaunchAgents**

   ```bash
   cp /tmp/com.wechat.minigame.weekly_scrape.plist ~/Library/LaunchAgents/
   launchctl load ~/Library/LaunchAgents/com.wechat.minigame.weekly_scrape.plist
   ```

3. **查看是否已加载**

   ```bash
   launchctl list | grep com.wechat.minigame.weekly_scrape
   ```

4. **卸载**

   ```bash
   launchctl unload ~/Library/LaunchAgents/com.wechat.minigame.weekly_scrape.plist
   rm ~/Library/LaunchAgents/com.wechat.minigame.weekly_scrape.plist
   ```

- 日志：`项目根目录/logs/weekly_scrape_import.log`、`weekly_scrape_import.err.log`。
- 执行时间：**每周一 10:00**（StartCalendarInterval: Weekday=1, Hour=10, Minute=0）。

---

## 方式二：crontab（Linux / macOS 通用）

1. 建日志目录（若还没有）：

   ```bash
   mkdir -p /Users/oliver/guru/wechat-mini-game-ranking-post/logs
   ```

2. 编辑 crontab：

   ```bash
   crontab -e
   ```

3. 加入一行（路径按你的项目改）：

   ```cron
   0 10 * * 1 /Users/oliver/guru/wechat-mini-game-ranking-post/scripts/weekly_scrape_and_import.sh >> /Users/oliver/guru/wechat-mini-game-ranking-post/logs/weekly_scrape_import.log 2>&1
   ```

即：每周一 10:00 执行一次，输出追加到 `logs/weekly_scrape_import.log`。
