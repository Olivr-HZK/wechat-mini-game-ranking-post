from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from modules.database import VideoDatabase


class WeeklyReportItem(BaseModel):
    week_range: str
    platform: str
    change_type: str
    rank: Optional[str] = None
    rank_change: Optional[str] = None
    summary: Optional[str] = None
    created_at: Optional[str] = None


class GameWeeklyReportResponse(BaseModel):
    game_name: str
    game_company: Optional[str] = None
    # 各平台最新排名（来自 games 表聚合字段）
    rank_wx: Optional[str] = None
    rank_dy: Optional[str] = None
    rank_ios: Optional[str] = None
    rank_android: Optional[str] = None
    # 最近一次记录的榜单元信息（平台/来源/榜单名/监控日期等，方便周报对齐）
    platform: Optional[str] = None
    source: Optional[str] = None
    board_name: Optional[str] = None
    monitor_date: Optional[str] = None
    rank_change: Optional[str] = None
    # 玩法分析相关
    gameplay_analysis: Optional[str] = None
    analysis_model: Optional[str] = None
    analyzed_at: Optional[str] = None
    # 周报简表中的多周记录
    weekly_reports: List[WeeklyReportItem]
    # 原始数据库行（可选，给调试/兜底用）
    raw_game_row: Dict[str, Any]


app = FastAPI(
    title="Mini Game Weekly Report API",
    description="通过游戏名查询与玩法周报相关的数据（排名、排名变化、平台、来源、玩法分析等）",
    version="1.0.0",
)

# 允许本地前端或其他服务跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 如需更安全可改为具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = VideoDatabase()


@app.get("/api/game-weekly-report", response_model=GameWeeklyReportResponse)
def get_game_weekly_report(game_name: str):
    """
    通过游戏名获取该游戏在数据库中的玩法周报相关数据：
    - games 表：玩法分析、各平台排名、来源/平台/榜单名/监控日期等元信息
    - weekly_report_simple 表：该游戏在不同周、不同平台的周报记录（排名、排名变化、变动类型、摘要等）

    使用示例：
    GET /api/game-weekly-report?game_name=点线落
    """
    game = db.get_game(game_name)
    if not game:
        raise HTTPException(status_code=404, detail=f"未找到游戏：{game_name}")

    weekly_rows = db.get_weekly_report_simple_by_game(game_name)

    weekly_items: List[WeeklyReportItem] = []
    for row in weekly_rows:
        weekly_items.append(
            WeeklyReportItem(
                week_range=row.get("week_range") or "",
                platform=row.get("platform") or "",
                change_type=row.get("change_type") or "",
                rank=(row.get("rank") or "") or None,
                rank_change=(row.get("rank_change") or "") or None,
                summary=(row.get("summary") or "") or None,
                created_at=(row.get("created_at") or "") or None,
            )
        )

    resp = GameWeeklyReportResponse(
        game_name=game.get("game_name") or game_name,
        game_company=game.get("game_company"),
        rank_wx=game.get("rank_wx") or game.get("game_rank"),  # 兼容旧字段
        rank_dy=game.get("rank_dy"),
        rank_ios=game.get("rank_ios"),
        rank_android=game.get("rank_android"),
        platform=game.get("platform"),
        source=game.get("source"),
        board_name=game.get("board_name"),
        monitor_date=game.get("monitor_date"),
        rank_change=game.get("rank_change"),
        gameplay_analysis=game.get("gameplay_analysis"),
        analysis_model=game.get("analysis_model"),
        analyzed_at=game.get("analyzed_at"),
        weekly_reports=weekly_items,
        raw_game_row=game,
    )
    return resp


@app.get("/health")
def health_check():
    """简单健康检查接口。"""
    return {"status": "ok"}

