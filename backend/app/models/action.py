"""动作与观察数据模型."""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional, Any

from .enums import ActionType, Role


class Observation(BaseModel):
    """Agent 在某一时刻接收到的观察信息."""

    phase: str = Field(..., description="当前阶段")
    round_num: int = Field(..., description="当前轮次")
    available_actions: list[str] = Field(default_factory=list)
    # 根据角色不同，可见信息不同
    public_info: str = Field(default="", description="公共可见信息")
    private_info: str = Field(default="", description="仅该Agent可见的私有信息")
    players_status: list[dict] = Field(
        default_factory=list, description="存活玩家列表（不含角色信息）"
    )


class Action(BaseModel):
    """Agent 执行的动作."""

    agent_id: int = Field(..., description="执行者ID")
    action_type: ActionType = Field(..., description="动作类型")
    target_id: Optional[int] = Field(default=None, description="目标玩家ID")
    content: Optional[str] = Field(default=None, description="发言内容等文本信息")
    reasoning: str = Field(default="", description="Agent的推理过程")


class ActionResult(BaseModel):
    """动作执行结果."""

    action: Action
    success: bool = Field(default=True)
    message: str = Field(default="")
    side_effects: list[dict] = Field(default_factory=list)
