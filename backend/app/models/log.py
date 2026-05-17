"""日志数据模型."""

from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional

from .enums import Phase, Role, Team, ActionType
from .action import Action, ActionResult


class ThoughtRecord(BaseModel):
    """Agent 的私有思考记录."""

    round_num: int
    phase: Phase
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class Message(BaseModel):
    """公共消息（发言、系统公告等）."""

    round_num: int
    phase: Phase
    speaker_id: int
    content: str
    msg_type: str = Field(default="speak", description="speak | system | vote | action")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class RoundLog(BaseModel):
    """单轮日志."""

    round_num: int
    phase: Phase
    actions: list[Action] = Field(default_factory=list)
    results: list[ActionResult] = Field(default_factory=list)
    messages: list[Message] = Field(default_factory=list)
    deaths: list[int] = Field(default_factory=list, description="本轮死亡的玩家ID")


class AgentProfile(BaseModel):
    """Agent 自我描述（可演化）."""

    role_description: str = Field(..., description="角色身份与目标")
    strategy_notes: str = Field(default="", description="当前策略描述（可被Agent自己修改）")
    persona: str = Field(default="冷静理性的玩家", description="性格/说话风格")
    version: int = Field(default=1, description="策略版本号")
    agent_profile_id: str = Field(default="", description="稳定身份UUID（非座位号）")
    model_name: str = Field(default="", description="使用的LLM模型")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AgentDecisionLog(BaseModel):
    """单个Agent在单个决策点的完整上下文."""

    agent_id: int
    round_num: int
    phase: Phase
    observation: dict
    llm_prompt: str
    llm_response: str
    action: Action
    result: Optional[ActionResult] = None


class GameLog(BaseModel):
    """整局游戏日志."""

    game_id: str
    config: dict
    players: list[dict] = Field(default_factory=list)
    rounds: list[RoundLog] = Field(default_factory=list)
    agent_decisions: list[AgentDecisionLog] = Field(default_factory=list)
    winner: Optional[Team] = None
    start_time: datetime = Field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None
    total_rounds: int = 0
