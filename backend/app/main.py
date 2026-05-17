"""FastAPI 入口."""

from __future__ import annotations

import os
import asyncio
from contextlib import asynccontextmanager

from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router, active_games
from app.websocket.manager import watch_manager
from app.llm.client import LLMClient
from app.llm.mock_client import MockLLMClient
from app.models.game import GameConfig
from app.engine.game_master import GameMaster
from app.evaluation.leaderboard import LeaderboardDB
from app.evaluation.metrics import MetricsCalculator
from app.evaluation.report import ReportGenerator


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理."""
    print("WireWolf 服务启动...")
    yield
    print("WireWolf 服务关闭。")


app = FastAPI(
    title="WireWolf API",
    description="狼人杀多 Agent 协作系统",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 路由
app.include_router(api_router)


@app.post("/api/game/start")
async def start_game(config: dict) -> dict:
    """创建并开始一局游戏（支持观战）."""
    game_config = GameConfig(
        player_count=config.get("player_count", 9),
        werewolf_count=config.get("werewolf_count", 3),
        seer_count=config.get("seer_count", 1),
        witch_count=config.get("witch_count", 1),
        hunter_count=config.get("hunter_count", 1),
    )

    use_mock = config.get("use_mock", False)
    # 模型可由前端指定，兜底从 .env 读取
    model = config.get("model") or os.getenv("LLM_MODEL", "gpt-4o-mini")

    if use_mock:
        llm = MockLLMClient()
    else:
        try:
            llm = LLMClient(model=model)
        except RuntimeError as e:
            raise HTTPException(status_code=400, detail=str(e))

    gm = GameMaster(
        config=game_config,
        llm_client=llm,
        watch_manager=watch_manager,
    )

    # 标记人类玩家座位
    human_seats = config.get("human_seats", [])
    gm.human_seats = set(human_seats)

    # 存储活跃游戏
    active_games[gm.game_id] = gm

    # 在后台运行对局
    async def _run_game():
        try:
            await gm.run()

            # 对局结束后持久化到数据库
            db = LeaderboardDB()
            winner = gm.game_state.winner
            await db.record_game(
                game_id=gm.game_id,
                config=game_config.model_dump(),
                winner=winner.value if winner else None,
                total_rounds=gm.game_state.round_num,
            )

            # 计算指标并入库
            calculator = MetricsCalculator(gm.log_file)
            outcome_metrics = calculator.compute_outcome_metrics()
            process_metrics = calculator.compute_process_metrics()
            report_gen = ReportGenerator(gm.log_file)
            report = report_gen.generate()

            for pid, om in outcome_metrics.items():
                pm = process_metrics.get(pid)
                score = report.player_scores.get(pid, 0.0)
                agent = gm.agents.get(pid)
                version = agent.profile.version if agent else 1
                model_name = agent.profile.model_name if agent else ""
                await db.record_player_stats(
                    game_id=gm.game_id,
                    outcome=om,
                    process=pm,
                    overall_score=score,
                    strategy_version=version,
                    model_name=model_name,
                )

            # 触发局后反思
            try:
                await gm.post_game_reflection()
            except Exception as e:
                print(f"[Game {gm.game_id}] 局后反思失败: {e}")

            print(f"[Game {gm.game_id}] 数据已持久化到数据库")

        except Exception as e:
            import traceback
            print(f"[Game {gm.game_id}] 运行异常: {e}")
            traceback.print_exc()

    task = asyncio.create_task(_run_game())
    await asyncio.sleep(0.1)

    return {
        "game_id": gm.game_id,
        "status": "running",
        "config": game_config.model_dump(),
        "human_seats": list(gm.human_seats),
    }


@app.websocket("/ws/watch/{game_id}")
async def watch_game(websocket: WebSocket, game_id: str):
    """观战 WebSocket — 接收对局实时事件."""
    await watch_manager.connect(websocket, game_id)
    try:
        while True:
            # 接收客户端消息（心跳或人类玩家操作）
            data = await websocket.receive_text()
            try:
                msg = __import__("json").loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_text(__import__("json").dumps({"type": "pong"}))
            except Exception:
                pass
    except WebSocketDisconnect:
        await watch_manager.disconnect(websocket, game_id)


# 静态文件（前端构建产物）
frontend_dist = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
if os.path.exists(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
