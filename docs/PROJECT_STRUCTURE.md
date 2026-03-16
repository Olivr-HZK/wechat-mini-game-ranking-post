# 项目结构说明

本文档说明项目的目录结构和组织方式。

## 目录结构

```
.
├── main.py                    # 主程序入口（工作流）
├── config.py                  # 配置文件
├── requirements.txt           # Python依赖
├── README.md                  # 主文档
├── env_example.txt            # 环境变量示例
│
├── modules/                   # 核心功能模块
│   ├── rank_extractor.py      # 排行提取
│   ├── video_searcher.py      # 视频搜索下载
│   ├── video_analyzer.py      # 视频分析
│   ├── report_generator.py    # 日报生成
│   ├── feishu_sender.py       # 飞书发送
│   ├── wecom_sender.py        # 企业微信发送
│   ├── database.py            # 数据库操作
│   ├── gdrive_uploader.py     # Google Drive上传
│   ├── GravityScraper.py      # 引力引擎爬虫
│   └── DEScraper.py           # DataEye爬虫
│
├── scripts/                   # 脚本目录
│   ├── scrapers/              # 爬取脚本
│   │   ├── scrape_weekly_popularity.py    # 爬取周榜
│   │   ├── scrape_gravity.py              # 爬取引力引擎
│   │   └── ...
│   │
│   ├── tools/                 # 工具脚本
│   │   ├── search_videos.py                # 视频搜索工具
│   │   ├── upload_existing_videos_to_gdrive.py
│   │   └── ...
│   │
│   ├── tests/                 # 测试脚本
│   │   ├── test_download.py
│   │   └── ...
│   │
│   ├── utils/                 # 工具/清理脚本
│   │   ├── clear_database.py
│   │   └── ...
│   │
│   └── senders/               # 发送脚本
│       ├── send_single_game_to_feishu.py
│       └── ...
│
├── docs/                      # 文档目录
│   ├── WORKFLOW_GUIDE.md      # 工作流指南
│   ├── GOOGLE_DRIVE_SETUP.md  # Google Drive设置
│   └── ...
│
└── data/                      # 数据目录
    ├── 人气榜/                 # 排行榜CSV文件
    ├── videos/                # 视频文件目录
    └── videos.db              # SQLite数据库
```

## 目录说明

### 根目录

- `main.py`: 主工作流程序，执行完整的分析流程
- `config.py`: 项目配置文件，包含API密钥、路径等配置
- `requirements.txt`: Python依赖包列表
- `README.md`: 项目主文档

### modules/ - 核心模块

包含所有可复用的核心功能模块，这些模块被主程序和脚本调用。

### scripts/ - 脚本目录

所有独立脚本按功能分类：

- **scrapers/**: 爬取相关脚本，用于从网站爬取排行榜数据
- **tools/**: 工具脚本，如视频搜索、数据上传等
- **tests/**: 测试脚本，用于测试各个功能模块
- **utils/**: 工具/清理脚本，如数据库清理、数据删除等
- **senders/**: 发送脚本，用于单独发送消息到飞书/企业微信

### docs/ - 文档目录

包含所有项目文档，如工作流指南、API设置说明等。

### data/ - 数据目录

存储所有数据文件：
- `人气榜/`: 排行榜CSV文件
- `videos/`: 下载的视频文件
- `videos.db`: SQLite数据库

## 脚本导入路径

所有 `scripts/` 目录下的脚本都已配置为自动添加项目根目录到Python路径，因此可以直接使用：

```python
from modules.xxx import ...
import config
```

无需手动修改 `sys.path`。

## 使用建议

1. **开发新功能**: 在 `modules/` 目录下创建新的模块
2. **添加新脚本**: 根据脚本功能放入对应的 `scripts/` 子目录
3. **编写文档**: 将文档放入 `docs/` 目录
4. **测试代码**: 使用 `scripts/tests/` 目录下的测试脚本
