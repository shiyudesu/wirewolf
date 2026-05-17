"""FastAPI REST API 路由."""

from __future__ import annotations

import json
import os
from typing import Any

from fastapi import APIRouter, HTTPException

from app.evaluation.leaderboard import LeaderboardDB
from app.evaluation.metrics import MetricsCalculator
from app.evaluation.report import ReportGenerator

router = APIRouter(prefix="/api")

# 项目根目录
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs", "games")

# 全局 DB 实例
db = LeaderboardDB()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "wirewolf"}


@router.get("/config")
async def get_config() -> dict[str, str]:
    """获取服务端公开配置（如默认 LLM 模型）."""
    import os
    return {
        "llm_model": os.getenv("LLM_MODEL", "gpt-4o-mini"),
        "llm_base_url": os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
    }


@router.get("/leaderboard")
async def get_leaderboard(role: str | None = None, model_name: str | None = None, limit: int = 20) -> list[dict]:
    """获取排行榜."""
    return await db.get_leaderboard(role=role, model_name=model_name, min_games=1, limit=limit)


@router.get("/games")
async def list_games(limit: int = 50) -> list[dict]:
    """列出最近的游戏."""
    return await db.list_games(limit=limit)


@router.get("/games/{game_id}")
async def get_game(game_id: str) -> dict[str, Any]:
    """获取单局游戏详情."""
    log_path = os.path.join(LOGS_DIR, f"{game_id}.jsonl")
    if not os.path.exists(log_path):
        raise HTTPException(status_code=404, detail="Game not found")

    with open(log_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    if not lines:
        raise HTTPException(status_code=404, detail="Empty log file")

    meta = json.loads(lines[0])
    rounds = [json.loads(line) for line in lines[1:]]

    return {
        "meta": meta,
        "rounds": rounds,
    }


@router.get("/games/{game_id}/report")
async def get_game_report(game_id: str) -> dict[str, Any]:
    """获取单局复盘报告."""
    log_path = os.path.join(LOGS_DIR, f"{game_id}.jsonl")
    if not os.path.exists(log_path):
        raise HTTPException(status_code=404, detail="Game not found")

    generator = ReportGenerator(log_path)
    report = generator.generate()
    return report.to_dict()


@router.get("/games/{game_id}/metrics")
async def get_game_metrics(game_id: str) -> dict[str, Any]:
    """获取单局评测指标."""
    log_path = os.path.join(LOGS_DIR, f"{game_id}.jsonl")
    if not os.path.exists(log_path):
        raise HTTPException(status_code=404, detail="Game not found")

    calculator = MetricsCalculator(log_path)
    outcome = calculator.compute_outcome_metrics()
    process = calculator.compute_process_metrics()

    return {
        "outcome": {pid: {
            "role": m.role.value,
            "win_rate": m.win_rate,
            "survival_rounds": m.avg_survival_rounds,
            "voted_out_count": m.voted_out_count,
            "vote_out_rate": m.vote_out_rate,
            "seer_check_accuracy": m.seer_check_accuracy,
            "witch_save_rate": m.witch_save_success_rate,
            "witch_saves_total": m.witch_saves_total,
            "witch_poison_accuracy": m.witch_poison_accuracy,
            "witch_poison_total": m.witch_poison_total,
            "first_night_kill_accuracy": m.first_night_kill_accuracy,
        } for pid, m in outcome.items()},
        "process": {pid: {
            "avg_speech_quality": m.avg_speech_quality,
            "speech_quality_scores": m.speech_quality_scores,
            "vote_consistency_rate": m.vote_consistency_rate,
            "info_utilization_score": m.info_utilization_score,
            "defense_quality": m.defense_quality,
        } for pid, m in process.items()},
    }


@router.get("/evolution/{agent_id}")
async def get_agent_evolution(agent_id: int) -> list[dict]:
    """获取 Agent 策略演进历史."""
    return await db.get_agent_evolution(agent_id)


# 活跃的游戏实例（简化：内存存储，生产环境应使用 Redis）
active_games: dict[str, GameMaster] = {}


@router.post("/game/{game_id}/action")
async def submit_action(game_id: str, action: dict) -> dict:
    """人类玩家提交操作."""
    from app.models.enums import ActionType
    from app.models.action import Action

    gm = active_games.get(game_id)
    if not gm:
        raise HTTPException(status_code=404, detail="Game not found or already ended")

    agent_id = action.get("agent_id")
    if agent_id not in gm.human_seats:
        raise HTTPException(status_code=400, detail="Not a human player seat")

    try:
        act = Action(
            agent_id=agent_id,
            action_type=ActionType(action.get("action_type", "pass")),
            target_id=action.get("target_id"),
            content=action.get("content", ""),
            reasoning=action.get("reasoning", "人类玩家操作"),
        )
    except ValueError:
        act = Action(agent_id=agent_id, action_type=ActionType.PASS)

    is_valid, error_msg = gm.validate_human_action(agent_id, act)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    await gm.submit_human_action(agent_id, act)
    return {"status": "ok", "agent_id": agent_id, "action": act.action_type.value}


@router.post("/batch/run")
async def run_batch(config: dict) -> dict:
    """批量运行对局（异步任务，立即返回任务ID）."""
    import asyncio
    from app.models.game import GameConfig
    from app.batch.runner import BatchRunner

    game_config = GameConfig(
        player_count=config.get("player_count", 9),
        werewolf_count=config.get("werewolf_count", 3),
        seer_count=config.get("seer_count", 1),
        witch_count=config.get("witch_count", 1),
        hunter_count=config.get("hunter_count", 1),
    )

    use_mock = config.get("use_mock", False)
    # 模型可由请求指定，兜底从 .env 读取
    import os
    model = config.get("model") or os.getenv("LLM_MODEL", "gpt-4o-mini")

    llm = None
    if not use_mock:
        from app.llm.client import LLMClient
        try:
            llm = LLMClient(model=model)
        except RuntimeError as e:
            raise HTTPException(status_code=400, detail=str(e))

    runner = BatchRunner(
        config=game_config,
        games=config.get("games", 10),
        use_mock=use_mock,
        llm_client=llm,
    )

    # 在后台运行
    asyncio.create_task(runner.run())

    return {
        "status": "started",
        "games": config.get("games", 10),
        "config": game_config.model_dump(),
    }


@router.get("/batch/status")
async def batch_status() -> dict:
    """获取批量对局状态（简化版，从数据库推断）."""
    return await db.get_game_stats()
