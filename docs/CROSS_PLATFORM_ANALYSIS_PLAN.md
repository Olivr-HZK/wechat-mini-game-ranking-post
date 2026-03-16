# 跨平台游戏异动检测方案

## 📋 方案概述

将市场监测系统（iOS/Android Puzzle品类）的**起量分析**和**榜单异动**功能，与**微信小游戏榜单**和**抖音小游戏榜单**进行交叉分析，实现多平台新游戏异动检测。

---

## 🎯 核心目标

1. **跨平台异动检测**：识别同时在多个平台（iOS/Android + 微信/抖音）出现异动的游戏
2. **新游戏发现**：通过交叉验证，提高新游戏发现的准确性和及时性
3. **趋势预测**：基于多平台数据，预测游戏起量趋势

---

## 📊 数据源分析

### 1. 市场监测系统（market_monitor_v1.6.js）
- **平台**：iOS、Android
- **品类**：Puzzle 游戏
- **数据**：
  - 榜单排名（Top Charts）
  - 排名变化（本周 vs 上周）
  - 下载量数据（用于起量分析）
- **异动类型**：
  - 🆕 新进榜单（首次进入 Top 50）
  - 🚀 排名飙升（周环比上升 ≥ 20 位）
  - 📈 排名上升（周环比上升 ≥ 10 位）
  - 📉 排名下跌（周环比下跌 ≥ 20 位）

### 2. 微信/抖音小游戏榜单
- **平台**：微信小游戏、抖音小游戏
- **数据字段**：
  - 排名、游戏名称、游戏类型、标签
  - 热度指数、平台、来源、榜单
  - 监控日期、发布时间、开发公司
  - **排名变化**（已有字段，但需要历史数据对比）

---

## 🔄 交叉分析方案

### 方案一：基于游戏名称的模糊匹配（推荐）

#### 1.1 数据准备阶段

**步骤1：建立游戏名称标准化库**
```
功能：将不同平台的游戏名称进行标准化处理
- 去除特殊字符、空格、标点
- 统一大小写
- 提取关键词（去除"游戏"、"小游戏"等通用词）
- 建立同义词库（处理不同平台的命名差异）
```

**步骤2：历史数据存储**
```
数据库表结构：
- games_history
  - game_name_normalized (标准化名称)
  - game_name_original (原始名称)
  - platform (平台：ios/android/wechat/douyin)
  - rank (排名)
  - rank_change (排名变化)
  - monitor_date (监控日期)
  - company (开发公司)
  - category (游戏类型)
  - heat_index (热度指数，仅小游戏)
  - download_estimate (下载量估算，仅iOS/Android)
```

#### 1.2 榜单异动分析

**功能：analyzeCrossPlatformRankChanges()**

```python
输入：
- iOS/Android 榜单异动数据（来自 market_monitor）
- 微信小游戏榜单（当前周）
- 抖音小游戏榜单（当前周）
- 历史榜单数据（上周/上上周）

处理逻辑：
1. 提取各平台异动游戏
   - iOS/Android: 新进榜单、排名飙升（≥20位）
   - 微信/抖音: 排名变化显著（需要定义阈值，如上升≥15位）

2. 游戏名称匹配
   - 标准化所有游戏名称
   - 模糊匹配（相似度 > 0.8）
   - 公司名称辅助匹配（如果游戏名匹配度低，用开发公司验证）

3. 交叉验证
   - 识别同时在2个以上平台出现异动的游戏
   - 标记为"高优先级异动"

4. 生成异动报告
   - 跨平台异动游戏列表
   - 单平台异动游戏列表
   - 异动趋势分析
```

**输出格式：**
```
工作表：📊 跨平台异动分析

列：
- 信号（🔴高优先级 / 🟡中优先级 / 🟢低优先级）
- 游戏名称（标准化）
- 匹配平台（iOS/Android/微信/抖音，多选）
- iOS排名/变化
- Android排名/变化
- 微信排名/变化
- 抖音排名/变化
- 开发公司
- 异动类型（新进/飙升/上升）
- 首次异动日期
- 异动强度评分（基于多平台异动程度）
```

#### 1.3 起量分析

**功能：analyzeCrossPlatformRising()**

```python
输入：
- iOS/Android 起量产品数据（日均下载 > 5000）
- 微信/抖音小游戏榜单（当前 + 历史）

处理逻辑：
1. 提取起量产品
   - iOS/Android: 日均下载超过阈值的产品
   - 微信/抖音: 热度指数显著上升的产品（需要定义阈值）

2. 时间序列分析
   - 对比各平台起量时间点
   - 识别起量顺序（哪个平台先起量）
   - 分析起量传播路径（iOS → 微信 → 抖音？）

3. 交叉验证
   - 如果iOS/Android起量，检查是否在微信/抖音也有异动
   - 如果微信/抖音起量，检查是否在iOS/Android也有异动
   - 标记"跨平台起量"产品

4. 预测模型
   - 基于历史数据，预测小游戏平台可能的起量时间
   - 提供"预警"功能（iOS/Android已起量，小游戏平台可能即将起量）
```

**输出格式：**
```
工作表：🚀 跨平台起量分析

列：
- 游戏名称
- 开发公司
- iOS起量日期/峰值下载
- Android起量日期/峰值下载
- 微信起量日期/峰值热度
- 抖音起量日期/峰值热度
- 起量顺序（如：iOS → 微信 → 抖音）
- 起量强度（综合评分）
- 预测小游戏起量时间（如果尚未起量）
```

---

### 方案二：基于开发公司的关联分析

#### 2.1 公司维度分析

**功能：analyzeCompanyCrossPlatform()**

```python
逻辑：
1. 识别在多个平台都有产品的公司
2. 分析公司产品矩阵
   - 哪些公司在iOS/Android有产品
   - 哪些公司在微信/抖音有产品
   - 哪些公司同时在多个平台有产品

3. 公司异动监控
   - 如果某公司在iOS/Android有产品起量
   - 检查该公司在微信/抖音是否有新产品或异动
   - 预测该公司可能在小游戏平台的动作
```

**输出：**
```
工作表：🏢 公司跨平台分析

列：
- 公司名称
- 平台覆盖（iOS/Android/微信/抖音）
- iOS产品数/异动数
- Android产品数/异动数
- 微信产品数/异动数
- 抖音产品数/异动数
- 跨平台产品关联度
- 公司异动评分
```

---

## 🛠️ 技术实现方案

### 阶段一：数据集成模块

#### 1.1 创建跨平台分析模块

**文件：`modules/cross_platform_analyzer.py`**

```python
class CrossPlatformAnalyzer:
    """跨平台游戏异动分析器"""
    
    def __init__(self):
        self.name_normalizer = GameNameNormalizer()
        self.db = CrossPlatformDatabase()
    
    def analyze_rank_changes(self, 
                            ios_data: List[Dict],
                            android_data: List[Dict],
                            wechat_data: List[Dict],
                            douyin_data: List[Dict]) -> Dict:
        """分析跨平台榜单异动"""
        pass
    
    def analyze_rising_apps(self,
                           ios_rising: List[Dict],
                           android_rising: List[Dict],
                           wechat_data: List[Dict],
                           douyin_data: List[Dict]) -> Dict:
        """分析跨平台起量产品"""
        pass
    
    def match_games_across_platforms(self, 
                                    game_name: str,
                                    platform: str) -> List[Dict]:
        """跨平台游戏名称匹配"""
        pass
```

#### 1.2 游戏名称标准化器

**文件：`modules/game_name_normalizer.py`**

```python
class GameNameNormalizer:
    """游戏名称标准化处理"""
    
    def normalize(self, name: str) -> str:
        """标准化游戏名称"""
        # 1. 去除特殊字符
        # 2. 统一大小写
        # 3. 提取关键词
        # 4. 处理同义词
        pass
    
    def similarity(self, name1: str, name2: str) -> float:
        """计算名称相似度（0-1）"""
        # 使用编辑距离、Jaccard相似度等
        pass
```

#### 1.3 跨平台数据库

**文件：`modules/cross_platform_database.py`**

```python
class CrossPlatformDatabase:
    """跨平台游戏数据库"""
    
    def save_ranking_snapshot(self, platform: str, data: List[Dict]):
        """保存榜单快照"""
        pass
    
    def get_rank_history(self, game_name: str, platform: str) -> List[Dict]:
        """获取游戏历史排名"""
        pass
    
    def find_cross_platform_matches(self, game_name: str) -> List[Dict]:
        """查找跨平台匹配的游戏"""
        pass
```

### 阶段二：数据采集增强

#### 2.1 扩展市场监测数据采集

**修改：`market_monitor_v1.6.js` 或创建 Python 版本**

```javascript
// 新增函数：导出异动数据为 JSON/CSV
function exportRankChangesToJSON() {
  // 导出榜单异动数据
}

function exportRisingAppsToJSON() {
  // 导出起量产品数据
}
```

#### 2.2 小游戏榜单历史数据管理

**文件：`scripts/tools/manage_ranking_history.py`**

```python
def save_weekly_snapshot(platform: str):
    """保存周榜快照到数据库"""
    pass

def compare_rankings(current_csv: str, previous_csv: str) -> List[Dict]:
    """对比两周榜单，计算排名变化"""
    pass
```

### 阶段三：分析报告生成

#### 3.1 跨平台异动报告生成器

**文件：`modules/cross_platform_report_generator.py`**

```python
class CrossPlatformReportGenerator:
    """跨平台异动报告生成器"""
    
    def generate_rank_changes_report(self, analysis_result: Dict) -> str:
        """生成榜单异动报告"""
        pass
    
    def generate_rising_apps_report(self, analysis_result: Dict) -> str:
        """生成起量产品报告"""
        pass
    
    def export_to_sheets(self, report_data: Dict, sheet_name: str):
        """导出到Google Sheets"""
        pass
```

---

## 📈 工作流程设计

### 日常运行流程

```
1. 数据采集阶段（每周一）
   ├── 运行 market_monitor 获取 iOS/Android 榜单异动
   ├── 运行 scrape_weekly_popularity 获取微信/抖音周榜
   └── 保存历史快照到数据库

2. 数据分析阶段（每周一，采集后）
   ├── 运行 analyzeCrossPlatformRankChanges()
   ├── 运行 analyzeCrossPlatformRising()
   └── 生成跨平台异动报告

3. 报告输出阶段
   ├── 生成 Google Sheets 报告
   ├── 生成飞书/企业微信通知
   └── 标记高优先级异动游戏
```

### 实时监控流程（可选）

```
1. 每日数据更新
   ├── 检查 iOS/Android 榜单异动（API）
   ├── 检查微信/抖音榜单变化（爬虫）
   └── 增量更新数据库

2. 实时异动检测
   ├── 检测跨平台异动
   ├── 发送高优先级异动通知
   └── 更新异动评分
```

---

## 🎯 关键指标定义

### 异动强度评分

```
综合评分 = (
    iOS异动权重 × iOS异动分数 +
    Android异动权重 × Android异动分数 +
    微信异动权重 × 微信异动分数 +
    抖音异动权重 × 抖音异动分数
) / 总权重

异动分数计算：
- 新进榜单：100分
- 排名飙升（≥20位）：80分
- 排名上升（≥10位）：40分
- 排名下跌（≥20位）：-20分
```

### 起量强度评分

```
起量评分 = (
    下载量评分（iOS/Android）+
    热度指数评分（微信/抖音）+
    跨平台一致性加分
)

下载量评分：
- > 10000/天：100分
- 5000-10000/天：70分
- 2000-5000/天：40分

热度指数评分：
- 需要根据实际数据定义阈值
```

---

## 📊 输出报告格式

### 1. 跨平台异动报告（Google Sheets）

**工作表：📊 跨平台异动分析**

| 信号 | 游戏名称 | 匹配平台 | iOS排名/变化 | Android排名/变化 | 微信排名/变化 | 抖音排名/变化 | 开发公司 | 异动类型 | 异动强度 | 首次异动日期 |
|------|---------|---------|-------------|----------------|-------------|-------------|---------|---------|---------|------------|
| 🔴 | 羊了个羊 | iOS+微信 | #15 ↑20 | - | #3 ↑5 | - | 简游科技 | 新进+飙升 | 85 | 2026-01-20 |

### 2. 跨平台起量报告（Google Sheets）

**工作表：🚀 跨平台起量分析**

| 游戏名称 | 开发公司 | iOS起量日/峰值 | Android起量日/峰值 | 微信起量日/峰值 | 抖音起量日/峰值 | 起量顺序 | 起量强度 | 预测小游戏起量 |
|---------|---------|--------------|------------------|---------------|---------------|---------|---------|--------------|
| 游戏A | 公司A | 2026-01-15/12000 | 2026-01-18/8000 | 2026-01-20/95 | - | iOS→Android→微信 | 92 | 抖音可能1-2周内起量 |

### 3. 飞书/企业微信通知格式

```
🔴 高优先级跨平台异动

游戏：羊了个羊
开发公司：简游科技
异动平台：iOS + 微信小游戏

异动详情：
- iOS：新进榜单 #15（飙升20位）
- 微信：排名上升至 #3（上升5位）

异动强度：85/100
建议：重点关注，可能即将在抖音起量
```

---

## 🔧 配置参数

### config.py 新增配置

```python
# 跨平台分析配置
CROSS_PLATFORM_ANALYSIS = {
    # 异动阈值
    "rank_change_threshold": {
        "ios": 20,
        "android": 20,
        "wechat": 15,  # 微信小游戏阈值
        "douyin": 15   # 抖音小游戏阈值
    },
    
    # 起量阈值
    "rising_threshold": {
        "ios": 5000,      # 日均下载
        "android": 5000,
        "wechat": 80,     # 热度指数（需根据实际数据调整）
        "douyin": 80
    },
    
    # 名称匹配相似度阈值
    "name_similarity_threshold": 0.8,
    
    # 跨平台异动优先级
    "cross_platform_priority": {
        "high": 3,    # 3个以上平台异动
        "medium": 2,  # 2个平台异动
        "low": 1      # 1个平台异动
    }
}
```

---

## 🚀 实施步骤建议

### Phase 1: 基础功能（2-3周）
1. ✅ 创建跨平台数据库表结构
2. ✅ 实现游戏名称标准化器
3. ✅ 实现历史数据存储功能
4. ✅ 实现基础的跨平台匹配功能

### Phase 2: 分析功能（2-3周）
1. ✅ 实现榜单异动分析
2. ✅ 实现起量分析
3. ✅ 实现异动强度评分
4. ✅ 测试和优化匹配算法

### Phase 3: 报告和集成（1-2周）
1. ✅ 生成Google Sheets报告
2. ✅ 集成到现有工作流
3. ✅ 添加飞书/企业微信通知
4. ✅ 文档和测试

### Phase 4: 优化和扩展（持续）
1. ✅ 优化匹配准确率
2. ✅ 添加预测模型
3. ✅ 实时监控功能
4. ✅ 可视化 dashboard

---

## ⚠️ 注意事项

1. **数据质量**：
   - 游戏名称在不同平台可能差异很大，需要建立完善的标准化和匹配机制
   - 建议人工审核匹配结果，建立反馈机制

2. **API限制**：
   - SensorTower API 有调用频率限制
   - 需要合理设计数据采集频率

3. **数据存储**：
   - 历史数据会快速增长，需要设计合理的数据归档策略
   - 考虑使用时间序列数据库优化查询性能

4. **匹配准确率**：
   - 初期匹配准确率可能不高，需要持续优化
   - 建议建立人工审核流程

5. **阈值调整**：
   - 微信/抖音的"热度指数"阈值需要根据实际数据调整
   - 不同平台的异动阈值可能需要差异化设置

---

## 📝 总结

这个方案将市场监测系统和小游戏榜单系统有机结合，通过：
- **跨平台匹配**：识别同一游戏在不同平台的异动
- **交叉验证**：提高异动检测的准确性
- **趋势预测**：基于多平台数据预测起量趋势

实现更全面、更准确的新游戏异动检测能力。
