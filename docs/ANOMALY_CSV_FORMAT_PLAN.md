# 榜单异动CSV格式统一方案

## 📋 需求概述

1. **参考 market_monitor_v1.6.js 的榜单异动分析**，获取每周新进榜和排名飙升（>10）的游戏
2. **统一CSV格式**，整合引力引擎和 SensorTower 的数据
3. **修改爬取脚本**，只爬取异动游戏（排名飙升>10 或 新进榜）

---

## 📊 新的CSV格式

### 字段定义

```
排名,游戏名称,游戏类型,平台,来源,榜单,监控日期,发布时间,开发公司,排名变化,地区
```

### 字段说明

| 字段 | 说明 | 示例 |
|------|------|------|
| 排名 | 当前排名 | 1 |
| 游戏名称 | 游戏名称 | 羊了个羊 |
| 游戏类型 | 游戏类型 | 休闲 / puzzle |
| 平台 | 平台名称 | iOS / Android / 微信小游戏 / 抖音小游戏 |
| 来源 | 数据来源 | SensorTower / 引力引擎 |
| 榜单 | 榜单名称 | iOS Top Charts / 微信小游戏人气周榜 |
| 监控日期 | 监控日期 | 2026-01-26 |
| 发布时间 | 发布时间 | 周平均排名:3.0 / -- |
| 开发公司 | 开发公司 | 北京简游科技有限公司 |
| 排名变化 | 排名变化 | 新进榜 / ↑25 / ↓10 |
| 地区 | 地区 | 中国 / 美国 / 日本 |

### 格式变化

**删除的字段：**
- ❌ 热度指数
- ❌ 标签

**新增的字段：**
- ✅ 地区

**保留的字段：**
- ✅ 排名、游戏名称、游戏类型、平台、来源、榜单、监控日期、发布时间、开发公司、排名变化

---

## 🛠️ 实现方案

### 1. SensorTower 榜单异动分析脚本

**文件：`scripts/scrapers/fetch_sensortower_anomalies.py`**

```python
"""
从 SensorTower API 获取榜单异动数据（新进榜 + 排名飙升>10）
参考 market_monitor_v1.6.js 的 analyzeRankChanges 逻辑
"""

功能：
1. 调用 SensorTower API 获取本周和上周的榜单数据
2. 对比排名，识别：
   - 新进榜（上周不在 Top 50，本周在 Top 50）
   - 排名飙升（排名上升 > 10 位）
3. 获取应用名称
4. 写入统一格式的 CSV
```

### 2. 修改微信爬取脚本

**文件：`scripts/scrapers/scrape_weekly_popularity.py`**

修改点：
1. **添加异动过滤逻辑**：
   - 读取上周的 CSV 文件
   - 对比排名变化
   - 只保留：新进榜 或 排名飙升（>10）的游戏

2. **修改 CSV 写入格式**：
   - 删除热度指数列
   - 删除标签列
   - 增加地区列（固定为"中国"）

### 3. 修改抖音爬取脚本

**文件：`scripts/scrapers/scrape_weekly_popularity.py`**（同一个脚本，通过 --platform 参数区分）

修改点：
- 同微信爬取脚本

### 4. 数据汇总脚本

**文件：`scripts/tools/aggregate_anomaly_rankings.py`**

```python
"""
汇总所有平台的异动数据到统一 CSV
整合：
- 引力引擎（微信/抖音）
- SensorTower（iOS/Android）
"""

功能：
1. 读取各平台的异动 CSV
2. 统一格式
3. 合并写入到一个 CSV 文件
```

---

## 📝 具体实现细节

### SensorTower 异动检测逻辑

```python
# 参考 market_monitor_v1.6.js 的逻辑

def detect_sensortower_anomalies(platform, country, current_date, last_week_date):
    """
    检测 SensorTower 榜单异动
    
    Args:
        platform: 'ios' or 'android'
        country: 'US', 'JP', 'GB', 'DE', 'IN'
        current_date: 当前日期 YYYY-MM-DD
        last_week_date: 上周日期 YYYY-MM-DD
    
    Returns:
        异动游戏列表
    """
    # 1. 获取本周榜单
    current_ranking = get_ranking(platform, country, current_date)
    
    # 2. 获取上周榜单
    last_week_ranking = get_ranking(platform, country, last_week_date)
    
    # 3. 构建上周排名映射
    last_week_map = {}
    for idx, app_id in enumerate(last_week_ranking[:50], 1):
        last_week_map[app_id] = idx
    
    # 4. 检测异动
    anomalies = []
    for idx, app_id in enumerate(current_ranking[:50], 1):
        current_rank = idx
        last_week_rank = last_week_map.get(app_id)
        
        if not last_week_rank:
            # 新进榜
            anomalies.append({
                'app_id': app_id,
                'current_rank': current_rank,
                'last_week_rank': None,
                'rank_change': '新进榜',
                'anomaly_type': '新进榜'
            })
        else:
            # 排名变化
            change = last_week_rank - current_rank
            if change > 10:  # 排名飙升
                anomalies.append({
                    'app_id': app_id,
                    'current_rank': current_rank,
                    'last_week_rank': last_week_rank,
                    'rank_change': f'↑{change}',
                    'anomaly_type': '排名飙升'
                })
    
    return anomalies
```

### 微信/抖音异动过滤逻辑

```python
def filter_anomalies_only(items, previous_csv_path):
    """
    只保留异动游戏（新进榜或排名飙升>10）
    
    Args:
        items: 当前周的游戏列表
        previous_csv_path: 上周 CSV 文件路径
    
    Returns:
        过滤后的游戏列表
    """
    if not previous_csv_path or not Path(previous_csv_path).exists():
        # 如果没有上周数据，所有游戏都算新进榜
        return [item for item in items if _is_new_entry(item)]
    
    # 读取上周数据
    previous_games = read_previous_csv(previous_csv_path)
    previous_map = {game['游戏名称']: int(game['排名']) for game in previous_games}
    
    anomalies = []
    for item in items:
        game_name = item.name
        current_rank = item.rank
        previous_rank = previous_map.get(game_name)
        
        if previous_rank is None:
            # 新进榜
            anomalies.append(item)
        else:
            # 排名变化
            change = previous_rank - current_rank
            if change > 10:  # 排名飙升
                anomalies.append(item)
    
    return anomalies
```

### 统一CSV写入格式

```python
def write_unified_csv(items, output_csv, platform, source, country, monitor_date):
    """
    写入统一格式的 CSV
    
    Args:
        items: 游戏列表
        output_csv: 输出文件路径
        platform: 平台（iOS/Android/微信小游戏/抖音小游戏）
        source: 来源（SensorTower/引力引擎）
        country: 地区（中国/美国/日本等）
        monitor_date: 监控日期
    """
    fieldnames = [
        "排名",
        "游戏名称",
        "游戏类型",
        "平台",
        "来源",
        "榜单",
        "监控日期",
        "发布时间",
        "开发公司",
        "排名变化",
        "地区",
    ]
    
    with output_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for item in items:
            w.writerow({
                "排名": str(item.rank),
                "游戏名称": item.name,
                "游戏类型": item.game_type or ("puzzle" if source == "SensorTower" else item.game_type),
                "平台": platform,
                "来源": source,
                "榜单": item.board_name or "",
                "监控日期": monitor_date,
                "发布时间": item.publish_time or "--",
                "开发公司": item.company or "--",
                "排名变化": item.rank_change or "--",
                "地区": country,
            })
```

---

## 🔄 工作流程

### 完整流程

```
1. 爬取微信小游戏周榜（只保留异动游戏）
   └── 输出：wechat_anomalies_YYYY-MM-DD~YYYY-MM-DD.csv

2. 爬取抖音小游戏周榜（只保留异动游戏）
   └── 输出：dy_anomalies_YYYY-MM-DD~YYYY-MM-DD.csv

3. 获取 SensorTower 榜单异动（iOS + Android，多国家）
   └── 输出：sensortower_anomalies_YYYY-MM-DD.csv

4. 汇总所有异动数据
   └── 输出：all_anomalies_YYYY-MM-DD.csv
```

---

## 📝 实施步骤

### Phase 1: 创建 SensorTower 异动分析脚本（1-2天）
1. ✅ 创建 `scripts/scrapers/fetch_sensortower_anomalies.py`
2. ✅ 实现 SensorTower API 调用
3. ✅ 实现异动检测逻辑
4. ✅ 实现 CSV 写入（统一格式）

### Phase 2: 修改微信/抖音爬取脚本（1-2天）
1. ✅ 添加读取上周 CSV 的逻辑
2. ✅ 添加异动过滤功能
3. ✅ 修改 CSV 写入格式（删除热度指数、标签，增加地区）

### Phase 3: 创建数据汇总脚本（1天）
1. ✅ 创建 `scripts/tools/aggregate_anomaly_rankings.py`
2. ✅ 实现多平台数据汇总
3. ✅ 统一格式输出

### Phase 4: 测试和优化（1天）
1. ✅ 测试完整流程
2. ✅ 验证数据准确性
3. ✅ 优化性能

---

## ⚙️ 配置参数

### config.py 新增配置

```python
# 榜单异动分析配置
RANKING_ANOMALY_CONFIG = {
    # 排名飙升阈值
    'rank_surge_threshold': 10,  # 排名上升超过10位算飙升
    
    # SensorTower 配置
    'sensortower': {
        'api_token': os.getenv("SENSORTOWER_API_TOKEN", ""),
        'base_url': "https://api.sensortower.com/v1",
        'category_ios': "7012",  # Puzzle
        'category_android': "game_puzzle",
        'countries': ["US", "JP", "GB", "DE", "IN"],
        'new_entry_top_n': 50,  # 新进榜 Top N
    },
    
    # 地区映射
    'country_mapping': {
        '微信小游戏': '中国',
        '抖音小游戏': '中国',
        'US': '美国',
        'JP': '日本',
        'GB': '英国',
        'DE': '德国',
        'IN': '印度',
    }
}
```

---

## 📊 输出示例

### 统一格式 CSV 示例

```csv
排名,游戏名称,游戏类型,平台,来源,榜单,监控日期,发布时间,开发公司,排名变化,地区
1,羊了个羊,休闲,微信小游戏,引力引擎,微信小游戏人气周榜,2026-01-26,周平均排名:3.0,北京简游科技有限公司,新进榜,中国
15,Game A,puzzle,iOS,SensorTower,iOS Top Charts,2026-01-26,--,Company A,↑25,美国
8,Game B,puzzle,Android,SensorTower,Android Top Charts,2026-01-26,--,Company B,新进榜,日本
```

---

## ⚠️ 注意事项

1. **历史数据依赖**：
   - 微信/抖音需要上周的 CSV 文件才能判断异动
   - 首次运行或没有历史数据时，所有游戏都算新进榜

2. **排名变化计算**：
   - 需要确保排名是数字格式
   - 处理"新进榜"等特殊值

3. **地区字段**：
   - 微信/抖音固定为"中国"
   - SensorTower 根据 API 返回的国家代码映射

4. **游戏类型**：
   - SensorTower 自动设置为"puzzle"
   - 微信/抖音保持原有游戏类型

5. **文件命名**：
   - 建议使用统一命名规则，便于后续汇总
   - 例如：`{platform}_anomalies_{date_range}.csv`
