# 定时任务：每周一 10:00 爬取上一周榜单并入库

## 一键脚本（手动跑一次）

在项目根目录执行：

```bash
./scripts/weekly_scrape_and_import.sh
```

- 会先爬取「上一周」的微信/抖音完整榜和异动榜（4 个 CSV），再自动把**最新一周目录**下的 CSV 导入到数据库表 `top20_ranking`、`rank_changes`。
- 若在周一运行且不传参数，则「上一周」= 刚结束的周一～周日。
- 可选：`./scripts/weekly_scrape_and_import.sh 2026-02-24` 指定监控日期。

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
