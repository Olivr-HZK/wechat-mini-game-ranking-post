"""
配置文件
"""
import os
from dotenv import load_dotenv

load_dotenv()

# OpenRouter API配置
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
# 推荐使用支持视频的多模态模型，如Gemini 2.5 Pro、GPT-4o或Claude 3.5 Sonnet
# Gemini 2.5 Pro 模型名称：google/gemini-pro-2.0 或 google/gemini-2.0-flash-exp
VIDEO_ANALYSIS_MODEL = os.getenv("VIDEO_ANALYSIS_MODEL", "google/gemini-pro-2.0")

# 飞书机器人配置
FEISHU_WEBHOOK_URL = os.getenv("FEISHU_WEBHOOK_URL", "")
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")

# 企业微信机器人配置（群机器人 Webhook）
WECOM_WEBHOOK_URL = os.getenv("WECOM_WEBHOOK_URL", "")
WECOM_WEBHOOK_URL_REAL = os.getenv("WECOM_WEBHOOK_URL_REAL", "")

# 抖音搜索API配置
DOUYIN_API_BASE_URL = "https://api.tikhub.io"
DOUYIN_API_TOKEN = os.getenv("DOUYIN_API_TOKEN", "")
DOUYIN_SEARCH_ENDPOINT = "/api/v1/douyin/search/fetch_general_search_v3"

# 抖音下载API配置（可选，如果使用专门的下载API）
DOUYIN_DOWNLOAD_ENDPOINT = os.getenv("DOUYIN_DOWNLOAD_ENDPOINT", "")  # 下载API端点，如 "/api/v1/douyin/video/download"
USE_DOWNLOAD_API = os.getenv("USE_DOWNLOAD_API", "false").lower() == "true"  # 是否使用专门的下载API

# 抖音最高画质API配置（付费API，0.005$一次）
DOUYIN_HIGH_QUALITY_ENDPOINT = "/api/v1/douyin/app/v3/fetch_video_high_quality_play_url"
USE_HIGH_QUALITY_API_FALLBACK = os.getenv("USE_HIGH_QUALITY_API_FALLBACK", "true").lower() == "true"  # 普通URL失败时是否使用付费API

# 文件路径配置
RANKINGS_CSV_PATH = "data/game_rankings.csv"
VIDEOS_DIR = "data/videos"
VIDEO_INFO_DIR = "data/video_info"  # 保存视频URL和ID的目录

# 工作流配置
MAX_GAMES_TO_PROCESS = int(os.getenv("MAX_GAMES_TO_PROCESS", "5"))  # 每次处理的最大游戏数量

# API请求配置
API_REQUEST_DELAY = float(os.getenv("API_REQUEST_DELAY", "1.0"))  # 请求间隔（秒），避免频率过高
API_MAX_RETRIES = int(os.getenv("API_MAX_RETRIES", "3"))  # 最大重试次数（针对502等临时错误）
API_RETRY_DELAY = float(os.getenv("API_RETRY_DELAY", "2.0"))  # 重试延迟（秒）