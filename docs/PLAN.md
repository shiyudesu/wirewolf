# WireWolf 自进化升级 — 详细实施计划

> 基于 `docs/future.md` 路线图，结合当前代码基线制定的可执行计划。
> 当前基线：Phase 1-4（基础系统）已完成，PostgreSQL + SQLAlchemy async ORM，
> 5 角色独立策略提示，`strategy_notes` 为纯文本字符串。

---

## 目录

- [执行原则](#执行原则)
- [Phase 0：前置准备 — 观测基础设施](#phase-0前置准备--观测基础设施)
- [Phase 1：结构化策略卡片 + Diff 修补](#phase-1结构化策略卡片--diff-修补)
- [Phase 2：统计显著性 + 评估体系加固](#phase-2统计显著性--评估体系加固)
- [Phase 3：策略种群进化](#phase-3策略种群进化)
- [Phase 4：红蓝协同进化](#phase-4红蓝协同进化)
- [Phase 5：过程归因 + 元策略库](#phase-5过程归因--元策略库)
- [里程碑与交付时间表](#里程碑与交付时间表)
- [附录 A：数据库迁移脚本清单](#附录-a数据库迁移脚本清单)
- [附录 B：Feature Flag 设计](#附录-bfeature-flag-设计)
- [附录 C：回滚策略矩阵](#附录-c回滚策略矩阵)

---

## 执行原则

1. **小步快跑**：每个子任务独立可测，避免"大爆炸式"重构。
2. **测试先行**：每改一个模块，先写/补测试，再改实现。
3. **Feature Flag**：新逻辑默认关闭，通过 `EvolutionConfig.use_strategy_cards` 等开关渐进启用。
4. **数据不丢**：所有 Schema 变更通过 Alembic 迁移，旧数据自动兼容。

---

## Phase 0：前置准备 — 观测基础设施

**目标**：为 Phase 3~5 的高复杂度调试提供可观测性，避免"黑盒进化"。
**依赖**：无（可立即开始）
**预估工时**：2~3 天

### 0.1 标准化实验日志格式

**文件**：`backend/app/evolution/experiment_logger.py`（新增）

```python
"""实验追踪 — 每代进化数据持久化到 JSON Lines."""

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class GenerationLog:
    generation: int
    timestamp: str
    game_ids: list[str]
    # 每个被优化 agent 的结果
    results: list[dict]
    # 种群状态（Phase 3+ 使用）
    population_state: Optional[dict] = None
    # 原始 token 消耗估算
    estimated_cost_usd: float = 0.0


class ExperimentLogger:
    """将进化实验数据写入 logs/experiments/{exp_id}.jsonl."""

    def __init__(self, experiment_id: Optional[str] = None) -> None:
        self.exp_id = experiment_id or datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        self.log_dir = Path("logs/experiments")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / f"{self.exp_id}.jsonl"

    def log_generation(self, gen_log: GenerationLog) -> None:
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(gen_log), ensure_ascii=False) + "\n")

    def get_history(self) -> list[GenerationLog]:
        if not self.log_file.exists():
            return []
        logs = []
        with open(self.log_file, "r", encoding="utf-8") as f:
            for line in f:
                logs.append(GenerationLog(**json.loads(line)))
        return logs
```

**集成点**：
- `EvolutionLoop.__init__()` 中初始化 `self.exp_logger = ExperimentLogger()`
- `EvolutionLoop.run()` 每代结束后调用 `self.exp_logger.log_generation()`

### 0.2 后端实时状态端点

**文件**：`backend/app/api/routes.py`（修改）

新增 `/api/evolution/status`：

```python
@router.get("/evolution/status")
async def evolution_status() -> dict:
    """返回当前正在运行的进化实验状态（内存级，非持久化）."""
    # 由 EvolutionLoop 在运行时写入一个全局/单例状态对象
    return getattr(evolution_state, "current", {"running": False})
```

**文件**：`backend/app/evolution/state.py`（新增）

```python
"""全局进化运行状态（线程/协程安全，单进程内使用）."""

import asyncio
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EvolutionRuntimeState:
    running: bool = False
    current_generation: int = 0
    total_generations: int = 0
    current_game: int = 0
    total_games_this_gen: int = 0
    # 关键指标快照
    metrics_snapshot: dict = field(default_factory=dict)
    # 错误信息
    last_error: Optional[str] = None

    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def update(self, **kwargs) -> None:
        async with self._lock:
            for k, v in kwargs.items():
                if hasattr(self, k):
                    setattr(self, k, v)

evolution_state = EvolutionRuntimeState()
```

**集成点**：`EvolutionLoop._run_generation()` 中每完成一局调用 `await evolution_state.update(current_game=i+1)`。

### 0.3 前端实验看板（最小可行版）

**文件**：`frontend/src/pages/EvolutionPage.tsx`（修改）

在现有进化追踪页上方增加一个实时面板：
- 当前运行状态（进行中 / 空闲）
- 代数进度条
- 本代对局进度条
- 最近 10 代的 avg_score 折线图（用 Recharts）

**数据流**：前端轮询 `/api/evolution/status`（每 5 秒），或复用现有 WebSocket 连接推送。

> **注意**：Phase 0 不阻塞后续 Phase，可以独立开发、随时合并。

### 验收标准

- [ ] 运行 3 代进化后，`logs/experiments/` 下生成可读的 `.jsonl` 文件
- [ ] `/api/evolution/status` 能返回当前正在运行的代数和进度
- [ ] 前端 EvolutionPage 能看到实时进度条（即使数据是 mock 的）

---

## Phase 1：结构化策略卡片 + Diff 修补

**目标**：将 `strategy_notes` 文本拆分为可插拔的 `StrategyCard`，实现精准归因和局部更新。
**依赖**：Phase 0（建议但不强制）
**预估工时**：4~5 天

### 1.1 数据模型：StrategyCard + AgentProfile 改造

**文件**：`backend/app/models/log.py`（修改）

```python
class StrategyCard(BaseModel):
    card_id: str = Field(..., description="全局唯一卡片标识，如 night_kill_priority")
    category: str = Field(default="general", description="night | day | meta")
    weight: float = Field(default=1.0, ge=0.0, le=1.0)
    text: str = Field(..., description="策略文本")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("card_id")
    @classmethod
    def _validate_card_id(cls, v: str) -> str:
        if not v or not re.match(r"^[a-z0-9_]+$", v):
            raise ValueError("card_id 只能包含小写字母、数字、下划线")
        return v


class AgentProfile(BaseModel):
    role_description: str
    strategy_notes: str = Field(default="", description="兼容旧数据")
    strategy_cards: list[StrategyCard] = Field(default_factory=list)
    persona: str = "冷静理性的玩家"
    version: int = 1
    agent_profile_id: str = ""
    model_name: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def render_strategy_text(self) -> str:
        """将 strategy_cards 渲染为旧版 strategy_notes 格式（兼容层）."""
        if self.strategy_cards:
            lines = []
            for c in sorted(self.strategy_cards, key=lambda x: (-x.weight, x.card_id)):
                prefix = ""
                if c.weight >= 0.8:
                    prefix = "【核心策略】"
                elif c.weight <= 0.3:
                    prefix = "【参考策略】"
                lines.append(f"- [{c.card_id}] {prefix}(权重{c.weight}): {c.text}")
            return "\n".join(lines)
        return self.strategy_notes or "暂无"
```

**新增验证测试**：`backend/tests/test_strategy_cards.py`

```python
import pytest
from app.models.log import StrategyCard, AgentProfile


def test_strategy_card_validation():
    card = StrategyCard(card_id="night_kill_priority", category="night", weight=0.9, text="优先刀神职")
    assert card.card_id == "night_kill_priority"

    with pytest.raises(ValueError):
        StrategyCard(card_id="Bad ID!", text="invalid")


def test_render_strategy_text():
    profile = AgentProfile(
        role_description="狼人",
        strategy_cards=[
            StrategyCard(card_id="night_kill", weight=0.9, text="优先刀神职"),
            StrategyCard(card_id="day_hide", weight=0.2, text="隐藏身份"),
        ],
    )
    text = profile.render_strategy_text()
    assert "【核心策略】" in text
    assert "【参考策略】" in text
    assert "night_kill" in text
```

### 1.2 预置角色默认卡片模板

**文件**：`backend/app/evolution/strategy_cards.py`（新增）

```python
"""策略卡片模板与工具函数."""

from app.models.log import StrategyCard, AgentProfile
from app.models.enums import Role


# 狼人默认 8 张卡片
WEREWOLF_DEFAULT_CARDS = [
    StrategyCard(card_id="night_kill_priority", category="night", weight=0.9,
                 text="优先刀神职（预言家 > 女巫 > 猎人），避免刀猎人（可能被反杀）"),
    StrategyCard(card_id="night_kill_consensus", category="night", weight=0.8,
                 text="与队友协商时给出明确刀人理由，争取统一意见"),
    StrategyCard(card_id="night_save_awareness", category="night", weight=0.6,
                 text="注意女巫可能有解药，第一晚刀口可能被救"),
    StrategyCard(card_id="day_speech_camouflage", category="day", weight=0.9,
                 text="发言要模仿好人逻辑，避免过度攻击或过度防守"),
    StrategyCard(card_id="day_teammate_sacrifice", category="day", weight=0.5,
                 text="可以适当攻击狼队友做身份，但不要过于明显"),
    StrategyCard(card_id="day_counter_seer", category="day", weight=0.7,
                 text="如果预言家已跳，考虑是否悍跳预言家扰乱局势"),
    StrategyCard(card_id="day_vote_tactics", category="day", weight=0.7,
                 text="投票阶段：狼队友被集火时尝试分散火力，好人被怀疑时推波助澜"),
    StrategyCard(card_id="meta_info_control", category="meta", weight=0.6,
                 text="控制信息披露量，不要一次性暴露太多逻辑"),
]

# 预言家默认 6 张卡片
SEER_DEFAULT_CARDS = [
    StrategyCard(card_id="night_check_priority", category="night", weight=0.9,
                 text="验人优先级：发言最可疑的 > 被多人保护的 > 从未被怀疑的"),
    StrategyCard(card_id="night_check_diversity", category="night", weight=0.6,
                 text="避免连续验同一个人"),
    StrategyCard(card_id="day_reveal_timing", category="day", weight=0.9,
                 text="跳身份时机：已验出狼人且自己可能下一晚被刀时果断跳"),
    StrategyCard(card_id="day_counter_fake_seer", category="day", weight=0.9,
                 text="有狼人悍跳预言家时必须立即对跳"),
    StrategyCard(card_id="day_report_logic", category="day", weight=0.8,
                 text="报查验时给出清晰逻辑链：为什么验这个人 + 结果 + 下一步建议"),
    StrategyCard(card_id="day_protect_future", category="day", weight=0.5,
                 text="不要透露接下来要验谁，避免狼人干扰"),
]

# 女巫 6 张、猎人 4 张、平民 4 张（类似结构，略）
# ...

ROLE_DEFAULT_CARDS: dict[Role, list[StrategyCard]] = {
    Role.WEREWOLF: WEREWOLF_DEFAULT_CARDS,
    Role.SEER: SEER_DEFAULT_CARDS,
    # ...
}


def validate_card_uniqueness(cards: list[StrategyCard]) -> None:
    """确保 cards 中 card_id 唯一."""
    seen = set()
    for c in cards:
        if c.card_id in seen:
            raise ValueError(f"重复的 card_id: {c.card_id}")
        seen.add(c.card_id)


def cards_from_strategy_notes(notes: str, role: Role) -> list[StrategyCard]:
    """将旧版纯文本 strategy_notes 解析为卡片列表（迁移用）."""
    if not notes.strip():
        return [c.model_copy() for c in ROLE_DEFAULT_CARDS.get(role, [])]
    # 简单启发式：按行拆分，每行作为一张卡片
    cards = []
    for i, line in enumerate(notes.strip().split("\n")):
        line = line.strip("- ").strip()
        if line:
            cards.append(StrategyCard(
                card_id=f"legacy_{i}",
                category="general",
                weight=1.0,
                text=line,
            ))
    return cards
```

### 1.3 Prompt 渲染改造

**文件**：`backend/app/agents/base.py`（修改）

```python
def _system_prompt(self) -> str:
    # 优先使用 strategy_cards 渲染
    strategy_text = self.profile.render_strategy_text()

    return (
        f"你是一名狼人杀玩家，你的座位号是 {self.agent_id} 号。\n"
        f"你的角色是: {self.role.value}\n"
        f"角色描述: {self.profile.role_description}\n"
        f"你的性格: {self.profile.persona}\n"
        f"当前策略 (v{self.profile.version}):\n{strategy_text}\n\n"
        "规则提醒:\n"
        "- 狼人杀是推理博弈游戏...\n"
        "- 输出必须是 JSON 格式。"
    )
```

同时修改 `reflect_after_game()`：支持基于 strategy_cards 的反思。

### 1.4 角色 Agent 默认卡片注入

**文件**：`backend/app/agents/roles/werewolf.py`（修改，所有角色文件类似）

```python
from app.evolution.strategy_cards import ROLE_DEFAULT_CARDS

class WerewolfAgent(BaseAgent):
    def _default_profile(self) -> AgentProfile:
        return AgentProfile(
            role_description=self._role_desc(),
            strategy_cards=[c.model_copy() for c in ROLE_DEFAULT_CARDS[Role.WEREWOLF]],
            persona="冷静理性的玩家",
            version=1,
        )

    # get_role_strategy_context 可以保留作为补充，或逐步迁移到卡片
    def get_role_strategy_context(self, observation: Observation) -> str:
        # Phase 1 中保留，但内容可以精简
        return "【额外提示】请严格遵循上述策略卡片中的优先级执行。"
```

> **迁移策略**：`get_role_strategy_context()` 在 Phase 1 不删除，只精简内容，
> 避免一次性改动过大。等 Phase 1 稳定后，Phase 2 再评估是否完全移除。

### 1.5 Optimizer Diff 模式

**文件**：`backend/app/evolution/optimizer.py`（大幅修改）

```python
class StrategyOptimizer:
    # ... __init__ 不变

    async def optimize(
        self,
        agent_id: int,
        role: str,
        current_profile: AgentProfile,
        recent_game_ids: list[str],
        target_metric: str = "win_rate",
        mode: str = "diff",  # 新增参数
    ) -> AgentProfile:
        if mode == "diff":
            return await self._optimize_diff(agent_id, role, current_profile, recent_game_ids, target_metric)
        return await self._optimize_full(agent_id, role, current_profile, recent_game_ids, target_metric)

    async def _optimize_diff(...):
        # 1. 诊断最差卡片（基于规则或历史数据）
        worst_card_id = await self._diagnose_worst_card(current_profile, recent_game_ids)

        # 2. 构建 diff prompt
        prompt = self._build_diff_prompt(current_profile, worst_card_id, performance)

        # 3. 调用 LLM
        try:
            result = await self.llm.chat_json(messages=[...], temperature=0.7)
        except Exception:
            # fallback: 降级为 full 模式
            print("Diff 生成失败，降级为 full 模式")
            return await self._optimize_full(...)

        # 4. 解析并应用 diff
        patches = result.get("patches", [])
        preview = self._apply_diff_preview(current_profile.strategy_cards, patches)

        # 5. 预检
        if not self._validate_diff_preview(preview):
            print("Diff 预检失败，降级为 full 模式")
            return await self._optimize_full(...)

        new_cards = preview
        new_profile = AgentProfile(..., strategy_cards=new_cards, version=current_profile.version + 1)
        return new_profile

    def _build_diff_prompt(self, profile, worst_card_id, performance) -> str:
        cards_json = json.dumps([c.model_dump() for c in profile.strategy_cards], ensure_ascii=False, indent=2)
        return (
            f"【任务】优化以下策略卡片，只修改表现最差的 1~2 张。\n\n"
            f"【当前卡片】\n{cards_json}\n\n"
            f"【表现最差卡片】{worst_card_id}\n"
            f"【最近表现】胜率 {performance['win_rate']:.1%}，评分 {performance['avg_score']:.1f}\n\n"
            f"请输出 JSON diff，示例：\n"
            f'{{"patches": [\n'
            f'  {{"card_id": "xxx", "op": "replace", "text": "新文本"}},\n'
            f'  {{"card_id": "xxx", "op": "adjust_weight", "weight": 0.5}}\n'
            f']}}'
        )

    def _apply_diff_preview(self, cards: list[StrategyCard], patches: list[dict]) -> list[StrategyCard]:
        card_map = {c.card_id: c for c in cards}
        new_cards = [c.model_copy() for c in cards]
        new_map = {c.card_id: c for c in new_cards}

        for p in patches:
            op = p.get("op")
            cid = p.get("card_id")
            if op == "replace" and cid in new_map:
                new_map[cid].text = p.get("text", new_map[cid].text)
            elif op == "adjust_weight" and cid in new_map:
                new_map[cid].weight = max(0.0, min(1.0, p.get("weight", new_map[cid].weight)))
            elif op == "add":
                if cid in new_map:
                    raise ValueError(f"add 失败: {cid} 已存在")
                new_cards.append(StrategyCard(
                    card_id=cid,
                    category=p.get("category", "general"),
                    weight=p.get("weight", 1.0),
                    text=p.get("text", ""),
                ))
            elif op == "delete" and cid in new_map:
                new_cards = [c for c in new_cards if c.card_id != cid]

        validate_card_uniqueness(new_cards)
        return new_cards

    def _validate_diff_preview(self, cards: list[StrategyCard]) -> bool:
        """预检：卡片数合理、总文本长度不异常."""
        if len(cards) < 1 or len(cards) > 50:
            return False
        total_len = sum(len(c.text) for c in cards)
        if total_len > 10000:
            return False
        return True
```

### 1.6 数据库 Schema 迁移

**文件**：`backend/alembic/versions/002_strategy_cards.py`（新增迁移）

```python
"""strategy_cards 表 + agent_profiles 兼容字段."""

from alembic import op
import sqlalchemy as sa

revision = "002_strategy_cards"
down_revision = "001_init_tables"


def upgrade():
    # 1. 新增 strategy_cards 表
    op.create_table(
        "strategy_cards",
        sa.Column("profile_id", sa.String(64), nullable=False),
        sa.Column("card_id", sa.String(64), nullable=False),
        sa.Column("category", sa.String(32), default="general"),
        sa.Column("weight", sa.Float(), default=1.0),
        sa.Column("text", sa.Text(), default=""),
        sa.Column("version", sa.Integer(), default=1),
        sa.Column("created_at", sa.DateTime(), default=sa.func.now()),
        sa.PrimaryKeyConstraint("profile_id", "card_id", "version"),
    )
    op.create_index("idx_sc_profile_version", "strategy_cards", ["profile_id", "version"])

    # 2. agent_profiles 增加 strategy_cards_version（标记当前 profile 是否已迁移到卡片）
    op.add_column("agent_profiles", sa.Column("strategy_cards_version", sa.Integer(), nullable=True))

    # 3. 数据迁移：把现有 strategy_notes 解析为单张 legacy 卡片
    # 注意： Alembic 中不建议做复杂数据迁移，此处只做标记，真正迁移在应用启动时懒加载


def downgrade():
    op.drop_index("idx_sc_profile_version", table_name="strategy_cards")
    op.drop_table("strategy_cards")
    op.drop_column("agent_profiles", "strategy_cards_version")
```

**文件**：`backend/app/db/models.py`（修改）

```python
class StrategyCardModel(Base):
    __tablename__ = "strategy_cards"

    profile_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    card_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(32), default="general")
    weight: Mapped[float] = mapped_column(default=1.0)
    text: Mapped[str] = mapped_column(default="")
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class AgentProfileModel(Base):
    # ... 现有字段不变
    strategy_cards_version: Mapped[Optional[int]] = mapped_column(nullable=True)
```

**文件**：`backend/app/db/database.py`（修改）

新增 `save_profile_cards()` / `load_profile_cards()` 方法：

```python
async def save_profile_cards(self, profile_id: str, version: int, cards: list[StrategyCard]) -> None:
    async with async_session_maker() as session:
        for c in cards:
            session.add(StrategyCardModel(
                profile_id=profile_id,
                card_id=c.card_id,
                version=version,
                category=c.category,
                weight=c.weight,
                text=c.text,
            ))
        await session.commit()

async def load_profile_cards(self, profile_id: str, version: int) -> list[StrategyCard]:
    async with async_session_maker() as session:
        result = await session.execute(
            select(StrategyCardModel).where(
                StrategyCardModel.profile_id == profile_id,
                StrategyCardModel.version == version,
            )
        )
        rows = result.scalars().all()
        return [
            StrategyCard(
                card_id=r.card_id,
                category=r.category,
                weight=r.weight,
                text=r.text,
            )
            for r in rows
        ]
```

### 1.7 Guard 精准回滚支持

**文件**：`backend/app/evolution/guard.py`（修改）

```python
@dataclass
class GuardResult:
    approved: bool
    reason: str
    rollback_recommended: bool = False
    affected_card_ids: list[str] = field(default_factory=list)  # 新增

class DegenerationGuard:
    def check_metrics(self, old_metrics, new_metrics, key_metrics=None, affected_card_ids=None):
        # ... 现有逻辑不变
        result = GuardResult(...)
        if affected_card_ids:
            result.affected_card_ids = affected_card_ids
        return result
```

> **注意**：Phase 1 中 `affected_card_ids` 由 `Optimizer` 在生成 diff 时记录并传入 Guard。
> 如果拒绝新版本，Loop 中只回滚这些卡片，保留其他卡片。

### 1.8 Feature Flag 集成

**文件**：`backend/app/evolution/loop.py`（修改）

```python
@dataclass
class EvolutionConfig:
    # ... 现有字段
    use_strategy_cards: bool = False  # Phase 1 feature flag
    optimizer_mode: str = "full"  # "diff" | "full"，Phase 1 默认 full，稳定后切 diff
```

在 `EvolutionLoop.run()` 中：
```python
if self.evo_config.use_strategy_cards:
    # 新逻辑：按角色加载默认卡片
    for role in ["werewolf", "seer", "witch", "hunter", "villager"]:
        if role not in self.role_profiles:
            self.role_profiles[role] = AgentProfile(
                role_description=role,
                strategy_cards=[c.model_copy() for c in ROLE_DEFAULT_CARDS[Role(role)]],
            )
```

### 验收标准

- [ ] `AgentProfile.render_strategy_text()` 正确渲染核心/参考策略前缀
- [ ] 运行一局 Mock 游戏，Prompt 中策略部分以卡片列表形式出现
- [ ] Optimizer `mode="diff"` 时只修改 1~2 张卡片，失败时自动降级 `mode="full"`
- [ ] Alembic 迁移执行成功，旧数据可加载（懒迁移到卡片）
- [ ] 单元测试：`test_strategy_cards.py` 通过，`test_optimizer_diff.py` 通过
- [ ] Feature flag 关闭时，系统行为与升级前完全一致

---

## Phase 2：统计显著性 + 评估体系加固

**目标**：消除小样本噪声，避免假阳性进化。
**依赖**：Phase 1（需要 strategy_cards 提供结构化数据以便归因）
**预估工时**：3~4 天

### 2.1 新增 scipy 依赖

**文件**：`backend/pyproject.toml`（修改）

```toml
dependencies = [
    # ... 现有依赖
    "scipy>=1.14.0",
]
```

运行 `pip install scipy` 或 `poetry add scipy`。

### 2.2 StatisticalGuard 实现

**文件**：`backend/app/evolution/guard.py`（修改）

```python
from scipy import stats
import numpy as np


class StatisticalGuard:
    def __init__(self, significance_level: float = 0.05, min_effect_size: float = 0.3):
        self.alpha = significance_level
        self.min_effect_size = min_effect_size

    def compare(self, old_scores: list[float], new_scores: list[float]) -> GuardResult:
        if len(old_scores) < 3 or len(new_scores) < 3:
            return GuardResult(approved=False, reason="样本量不足（需 >= 3 局）")

        mean_old = np.mean(old_scores)
        mean_new = np.mean(new_scores)
        std_old = np.std(old_scores, ddof=1) or 1e-6
        std_new = np.std(new_scores, ddof=1) or 1e-6

        # 1. 双向安全检测：如果显著更差，直接拒绝（避免统计上不显著但实际很糟）
        pooled_std = np.sqrt((std_old**2 + std_new**2) / 2)
        cohens_d = (mean_new - mean_old) / pooled_std

        if cohens_d < -0.8:
            return GuardResult(
                approved=False,
                reason=f"退化严重 (Cohen's d={cohens_d:.2f})，无需统计检验",
                rollback_recommended=True,
            )

        # 2. Mann-Whitney U 检验（单边：新策略是否显著更好）
        statistic, pvalue = stats.mannwhitneyu(
            new_scores, old_scores, alternative="greater"
        )

        # 3. 效应量（Cohen's d）
        if mean_new > mean_old and pvalue < self.alpha and cohens_d >= self.min_effect_size:
            return GuardResult(
                approved=True,
                reason=f"显著更优 (p={pvalue:.3f}, d={cohens_d:.2f}, {mean_old:.1f} -> {mean_new:.1f})",
            )

        if mean_new > mean_old and pvalue < self.alpha and cohens_d < self.min_effect_size:
            return GuardResult(
                approved=False,
                reason=f"统计显著但效应量过小 (p={pvalue:.3f}, d={cohens_d:.2f})，不具实际价值",
            )

        return GuardResult(
            approved=False,
            reason=f"未达到显著性 (p={pvalue:.3f}, d={cohens_d:.2f})",
        )
```

### 2.3 评估指标权重配置

**文件**：`backend/app/evaluation/metrics.py`（修改）

```python
from pydantic import BaseModel, Field

class ScoreWeights(BaseModel):
    win_rate: float = 0.30
    survival_rounds: float = 0.15
    speech_quality: float = 0.20
    vote_consistency: float = 0.15
    info_utilization: float = 0.20

    def compute(self, outcome: AgentOutcomeMetrics, process: AgentProcessMetrics) -> float:
        return (
            self.win_rate * outcome.win_rate
            + self.survival_rounds * (outcome.avg_survival_rounds / 10.0)  # 假设最多 10 轮
            + self.speech_quality * (process.avg_speech_quality / 10.0)
            + self.vote_consistency * process.vote_consistency_rate
            + self.info_utilization * process.info_utilization_score
        )


# 角色特化权重
ROLE_WEIGHTS: dict[str, ScoreWeights] = {
    "seer": ScoreWeights(win_rate=0.25, info_utilization=0.30, speech_quality=0.20),
    "witch": ScoreWeights(win_rate=0.25, survival_rounds=0.20, info_utilization=0.25),
    "werewolf": ScoreWeights(win_rate=0.35, speech_quality=0.20, vote_consistency=0.20),
    "hunter": ScoreWeights(win_rate=0.30, survival_rounds=0.15, vote_consistency=0.25),
    "villager": ScoreWeights(win_rate=0.25, speech_quality=0.25, vote_consistency=0.25),
}
```

修改 `MetricsCalculator` / `ReportGenerator` 以支持传入 `ScoreWeights`。

### 2.4 Loop 收集原始分数 + 序贯检验

**文件**：`backend/app/evolution/loop.py`（修改）

```python
@dataclass
class EvolutionConfig:
    # ... 现有字段
    min_games_for_significance: int = 15
    significance_level: float = 0.05
    enable_sequential_testing: bool = True  # 序贯检验开关
    early_termination_threshold: int = 5    # 5 连败/连胜触发提前终止


class EvolutionLoop:
    def __init__(self, ...):
        # ...
        self.stat_guard = StatisticalGuard(significance_level=evo_config.significance_level)
        self._score_buffer: dict[str, list[float]] = {}  # profile_id -> [score, ...]

    async def _run_generation(self, generation: int) -> list[str]:
        game_ids = []
        for i in range(self.evo_config.games_per_generation):
            # ... 运行单局

            # 如果是非基线代且启用了序贯检验，检查是否可以提前终止
            if generation > 0 and self.evo_config.enable_sequential_testing:
                should_stop = self._check_early_termination()
                if should_stop:
                    print(f"  序贯检验触发提前终止，已运行 {i+1}/{self.evo_config.games_per_generation} 局")
                    break
        return game_ids

    def _check_early_termination(self) -> bool:
        """检查最近新策略的得分是否连续极差或极好."""
        for pid, scores in self._score_buffer.items():
            if len(scores) >= self.evo_config.early_termination_threshold:
                recent = scores[-self.evo_config.early_termination_threshold:]
                if all(s < 2.0 for s in recent):  # 连续极低分
                    return True
                # 连续极高分也可以提前接受（可选）
        return False
```

### 2.5 DB 查询支持原始分数列表

**文件**：`backend/app/db/database.py`（修改）

```python
async def get_agent_score_list(self, agent_id: int, game_ids: list[str]) -> list[float]:
    """返回指定对局中该 agent 的 overall_score 列表（用于统计检验）."""
    async with async_session_maker() as session:
        placeholders = ",".join(f":gid{i}" for i in range(len(game_ids)))
        params = {f"gid{i}": gid for i, gid in enumerate(game_ids)}
        params["agent_id"] = agent_id
        result = await session.execute(
            text(f"SELECT overall_score FROM player_stats WHERE agent_id = :agent_id AND game_id IN ({placeholders})"),
            params,
        )
        return [row[0] for row in result.all() if row[0] is not None]
```

### 验收标准

- [ ] 新策略 60% vs 旧 50%，p=0.12 → 被 StatisticalGuard 拒绝
- [ ] 新策略 60% vs 旧 45%，p=0.03，d=0.5 → 被接受
- [ ] 新策略 60% vs 旧 50%，p=0.03，d=0.1 → 被拒绝（效应量不足）
- [ ] 连续 5 局 score < 2.0 → 提前终止，不跑满 15 局
- [ ] 预言家和狼人使用不同权重计算 overall_score
- [ ] 单元测试：`test_statistical_guard.py` 覆盖上述场景

---

## Phase 3：策略种群进化

**目标**：从单策略爬山升级为种群遗传，避免局部最优。
**依赖**：Phase 1（strategy_cards）+ Phase 2（统计检验用于淘汰）
**预估工时**：1.5~2 周

### 3.1 种群管理器

**文件**：`backend/app/evolution/population.py`（新增）

```python
"""策略种群管理 — 每个角色维护一个 StrategyPopulation."""

import math
import random
import copy
from dataclasses import dataclass, field
from typing import Optional

from app.models.log import AgentProfile, StrategyCard
from app.llm.client import LLMClient


@dataclass
class StrategyVariant:
    variant_id: str
    profile: AgentProfile
    elo: float = 1500.0
    games_played: int = 0
    win_count: int = 0
    # TrueSkill 用（推荐替代 Elo）
    trueskill_mu: float = 25.0
    trueskill_sigma: float = 8.333


class StrategyPopulation:
    def __init__(self, role: str, size: int = 5, llm_client: Optional[LLMClient] = None):
        self.role = role
        self.size = size
        self.variants: list[StrategyVariant] = []
        self.llm = llm_client
        self.generation = 0

    async def initialize(self, base_profile: AgentProfile) -> None:
        """初始化种群：基线 + (size-1) 个 LLM 扰动变体."""
        self.variants.append(StrategyVariant("v0", copy.deepcopy(base_profile)))
        for i in range(1, self.size):
            mutated = await self._llm_mutate(base_profile, strength=0.3)
            self.variants.append(StrategyVariant(f"v{i}", mutated))

    async def _llm_mutate(self, profile: AgentProfile, strength: float) -> AgentProfile:
        """让 LLM 对 strategy_cards 做小幅扰动."""
        # 构造 prompt：要求 LLM 修改 1~2 张卡片的 weight 或 text
        prompt = (
            f"【角色】{self.role}\n"
            f"【当前策略卡片】\n"
            f"{json.dumps([c.model_dump() for c in profile.strategy_cards], ensure_ascii=False, indent=2)}\n\n"
            f"请对上述策略做小幅扰动（修改 1~2 张卡片的 text 或 weight，"
            f"strength={strength}），输出完整的卡片列表 JSON。"
        )
        result = await self.llm.chat_json(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7 + strength * 0.5,
        )
        cards = [StrategyCard(**c) for c in result.get("cards", [])]
        return AgentProfile(
            role_description=profile.role_description,
            strategy_cards=cards,
            persona=profile.persona,
            version=profile.version,
        )

    def select_for_game(self, temperature: Optional[float] = None) -> StrategyVariant:
        """按 Elo Softmax 采样，temperature 随代数降低."""
        temp = temperature or max(50, 200 - self.generation * 10)
        weights = [math.exp(v.elo / temp) for v in self.variants]
        total = sum(weights)
        probs = [w / total for w in weights]
        return random.choices(self.variants, weights=probs, k=1)[0]

    def evolve_generation(self) -> None:
        """淘汰 Bottom 20%，Top 40% 交叉变异填充."""
        self.variants.sort(key=lambda v: v.elo, reverse=True)
        survivors = self.variants[:int(self.size * 0.8)]
        needed = self.size - len(survivors)

        top_pool = self.variants[:max(2, int(self.size * 0.4))]
        new_variants = []
        for i in range(needed):
            parent_a = random.choice(top_pool)
            parent_b = random.choice(top_pool)
            child_profile = self._crossover(parent_a.profile, parent_b.profile)
            new_variants.append(StrategyVariant(f"g{self.generation}_v{i}", child_profile))

        self.variants = survivors + new_variants
        self.generation += 1

    def _crossover(self, parent_a: AgentProfile, parent_b: AgentProfile) -> AgentProfile:
        """按 card_id 交叉，支持 weight 混合遗传."""
        cards_a = {c.card_id: c for c in parent_a.strategy_cards}
        cards_b = {c.card_id: c for c in parent_b.strategy_cards}
        all_ids = set(cards_a.keys()) | set(cards_b.keys())

        child_cards = []
        for cid in all_ids:
            ca = cards_a.get(cid)
            cb = cards_b.get(cid)
            if ca and cb:
                # 50% 选择文本，weight 取平均 + 噪声
                if random.random() < 0.5:
                    text = ca.text
                else:
                    text = cb.text
                weight = (ca.weight + cb.weight) / 2 + random.gauss(0, 0.05)
                weight = max(0.0, min(1.0, weight))
                child_cards.append(StrategyCard(
                    card_id=cid, category=ca.category, weight=weight, text=text
                ))
            elif ca:
                child_cards.append(ca.model_copy())
            elif cb:
                child_cards.append(cb.model_copy())

        return AgentProfile(
            role_description=parent_a.role_description,
            strategy_cards=child_cards,
            persona=parent_a.persona,
            version=parent_a.version,
        )

    def diversity_score(self) -> float:
        """计算种群多样性：1 - 平均余弦相似度（简化版用文本重叠度）."""
        if len(self.variants) < 2:
            return 1.0
        # 简化：计算各 variant strategy_cards text 的 Jaccard 相似度
        texts = []
        for v in self.variants:
            text_set = set(c.text[:50] for c in v.profile.strategy_cards)
            texts.append(text_set)
        sims = []
        for i in range(len(texts)):
            for j in range(i + 1, len(texts)):
                inter = len(texts[i] & texts[j])
                union = len(texts[i] | texts[j])
                sims.append(inter / union if union else 0)
        avg_sim = sum(sims) / len(sims) if sims else 0
        return 1.0 - avg_sim
```

### 3.2 TrueSkill 集成（推荐）

**文件**：`backend/app/evolution/trueskill_wrapper.py`（新增）

```python
"""TrueSkill 评分系统包装器."""

try:
    import trueskill
except ImportError:
    trueskill = None


class TrueSkillRating:
    def __init__(self):
        if trueskill is None:
            raise ImportError("trueskill 库未安装，请运行 pip install trueskill")
        self.env = trueskill.TrueSkill(draw_probability=0.05)

    def rate_1v1(self, winner, loser):
        """更新 1v1 对局评分."""
        new_winner, new_loser = self.env.rate_1v1(winner, loser)
        return new_winner, new_loser

    def rate_team_vs_team(self, team_a_ratings, team_b_ratings, ranks):
        """更新队伍对局评分（ranks: [0, 1] 表示 team_a 胜）."""
        return self.env.rate([team_a_ratings, team_b_ratings], ranks=ranks)
```

> **注意**：如果引入 TrueSkill 会增加一个新依赖，也可用 Elo 做 MVP。
> 建议先实现 Elo 版本，用 feature flag `use_trueskill` 控制，验证后再切换。

### 3.3 DB 支持种群持久化

**文件**：`backend/alembic/versions/003_strategy_variants.py`（新增迁移）

```python
from alembic import op
import sqlalchemy as sa

revision = "003_strategy_variants"
down_revision = "002_strategy_cards"

def upgrade():
    op.create_table(
        "strategy_variants",
        sa.Column("variant_id", sa.String(64), primary_key=True),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("population_gen", sa.Integer(), default=0),
        sa.Column("profile_json", sa.JSON(), default=dict),
        sa.Column("elo", sa.Float(), default=1500.0),
        sa.Column("games_played", sa.Integer(), default=0),
        sa.Column("created_at", sa.DateTime(), default=sa.func.now()),
    )
    op.create_index("idx_sv_role_gen", "strategy_variants", ["role", "population_gen"])

def downgrade():
    op.drop_index("idx_sv_role_gen", table_name="strategy_variants")
    op.drop_table("strategy_variants")
```

### 3.4 Loop 改造（种群版）

**文件**：`backend/app/evolution/loop.py`（大幅修改）

核心改动：
- `role_profiles: dict[str, AgentProfile]` → `role_populations: dict[str, StrategyPopulation]`
- `_run_generation()` 每局从种群采样 variant 注入 GameMaster
- 每代结束后更新 variant Elo + 执行 `evolve_generation()`

```python
class EvolutionLoop:
    def __init__(self, ...):
        # ...
        self.role_populations: dict[str, StrategyPopulation] = {}

    async def run(self) -> list[EvolutionResult]:
        # 初始化种群（若未加载）
        for role in ["werewolf", "seer", "witch", "hunter", "villager"]:
            if role not in self.role_populations:
                base = self.role_profiles.get(role, AgentProfile(role_description=role))
                pop = StrategyPopulation(role, size=5, llm_client=self.llm)
                await pop.initialize(base)
                self.role_populations[role] = pop

        # ... 基线对局（使用 v0 变体）
        # 后续每代采样 -> 运行 -> 更新 Elo -> 进化
```

### 3.5 多样性保护

在 `StrategyPopulation.evolve_generation()` 中加入：

```python
def _ensure_diversity(self) -> None:
    """如果 Top2 变体相似度 > 0.9，对其中一个注入随机扰动."""
    if len(self.variants) < 2:
        return
    self.variants.sort(key=lambda v: v.elo, reverse=True)
    top1, top2 = self.variants[0], self.variants[1]
    # 简化相似度：卡片文本重合率
    texts1 = set(c.text[:50] for c in top1.profile.strategy_cards)
    texts2 = set(c.text[:50] for c in top2.profile.strategy_cards)
    inter = len(texts1 & texts2)
    union = len(texts1 | texts2)
    sim = inter / union if union else 0
    if sim > 0.9:
        # 对 top2 做随机扰动
        import asyncio
        asyncio.create_task(self._llm_mutate(top2.profile, strength=0.5))
```

### 验收标准

- [ ] 狼人种群有 5 个变体，每代对局中不同变体被采样
- [ ] 运行 3 代后，Elo 最低变体被淘汰，新变体由 Top2 交叉产生
- [ ] 可观察到"夜间激进刀法"和"白天保守发言"的解耦进化（通过卡片内容对比）
- [ ] 种群数据持久化到 DB，重启后可恢复
- [ ] 种群多样性分数 > 0.1（如果 < 0.1 自动触发扰动）
- [ ] 单元测试：`test_population.py` 覆盖采样、交叉、淘汰逻辑

---

## Phase 4：红蓝协同进化

**目标**：狼人和好人同步进化，找到博弈均衡。
**依赖**：Phase 3（种群管理器）
**预估工时**：2~3 周

### 4.1 按角色分池（核心架构调整）

**文件**：`backend/app/evolution/loop.py`（修改）

不再使用 `wolf_pop` / `good_pop`，直接按角色分池：

```python
class EvolutionLoop:
    def __init__(self, ...):
        # ...
        self.role_populations: dict[str, StrategyPopulation] = {}
        self.roles_to_evolve = ["werewolf", "seer", "witch", "hunter", "villager"]

    async def run(self) -> list[EvolutionResult]:
        # 为每个角色初始化种群
        for role in self.roles_to_evolve:
            base = self.role_profiles.get(role) or self._default_profile_for_role(role)
            pop = StrategyPopulation(role, size=5, llm_client=self.llm)
            await pop.initialize(base)
            self.role_populations[role] = pop
```

### 4.2 非对称采样 + 同局多 Variant

```python
async def _run_generation(self, generation: int) -> list[str]:
    game_ids = []
    for i in range(self.evo_config.games_per_generation):
        gm = GameMaster(config=self.game_config, llm_client=self.llm)
        await gm.setup()

        # 为每个座位独立采样 variant（同一角色可采样不同 variant）
        for pid, agent in gm.agents.items():
            role = agent.role.value
            pop = self.role_populations.get(role)
            if pop:
                # 限制：同一局中同一角色的 variant Elo 差 < 200
                variant = self._sample_variant_constrained(pop, agent.agent_id, gm.agents)
                agent.profile = copy.deepcopy(variant.profile)
                # 记录该 agent 使用了哪个 variant（用于后续更新 Elo）
                self._variant_assignments[gm.game_id][pid] = variant.variant_id

        await gm.run()
        game_ids.append(gm.game_id)

        # 更新各 variant 的 Elo / TrueSkill
        self._update_population_ratings(gm)
    return game_ids


def _sample_variant_constrained(self, pop: StrategyPopulation, agent_id: int, all_agents: dict) -> StrategyVariant:
    """采样 variant，确保同局中同角色 variant Elo 差不太大."""
    # 获取已分配的 variant
    already_assigned = [a.profile for a in all_agents.values() if a.agent_id != agent_id and a.role.value == pop.role]
    if not already_assigned:
        return pop.select_for_game()

    # 简单策略：限制温度，偏向选择与已有 variant Elo 接近的
    candidates = pop.variants
    # 如果已有同角色 agent，优先选择 elo 差距 < 200 的
    return pop.select_for_game(temperature=100)
```

### 4.3 均衡检测

**文件**：`backend/app/evolution/equilibrium.py`（新增）

```python
"""均衡检测 — 判断协同进化是否接近纳什均衡."""

import numpy as np


def check_equilibrium(
    win_rate_history: list[float],
    population_diversities: dict[str, list[float]],
    window: int = 20,
) -> dict:
    """
    返回:
        - is_equilibrium: bool
        - win_rate_stable: bool  # 胜率在 45%~55% 且波动小
        - diversity_sufficient: bool  # 各角色种群多样性充足
        - recommendation: str  # "continue" | "inject_diversity" | "converged"
    """
    recent = win_rate_history[-window:]
    if len(recent) < window:
        return {"is_equilibrium": False, "recommendation": "continue"}

    mean_wr = np.mean(recent)
    std_wr = np.std(recent)
    win_stable = 0.45 <= mean_wr <= 0.55 and std_wr < 0.08

    # 检测循环克制（Rock-Paper-Scissors）
    # 简单方法：胜率序列的自相关系数
    if len(recent) >= 10:
        autocorr = np.corrcoef(recent[:-5], recent[5:])[0, 1]
        cyclic = autocorr < -0.3  # 负自相关暗示循环
    else:
        cyclic = False

    diversity_ok = all(
        divs[-1] > 0.1 if divs else False
        for divs in population_diversities.values()
    )

    if win_stable and diversity_ok and not cyclic:
        return {"is_equilibrium": True, "recommendation": "converged"}
    if cyclic:
        return {"is_equilibrium": False, "recommendation": "inject_diversity"}
    return {"is_equilibrium": False, "recommendation": "continue"}
```

### 4.4 GameMaster Profile 注入优化

**文件**：`backend/app/engine/game_master.py`（修改）

```python
async def inject_profiles(self, role_variant_map: dict[Role, list[AgentProfile]]) -> None:
    """批量注入 profile，同一角色可分配多个不同 variant."""
    role_assignments: dict[Role, list[AgentProfile]] = {r: [] for r in role_variant_map}
    for pid, agent in self.agents.items():
        role = agent.role
        if role in role_variant_map:
            variants = role_variant_map[role]
            # 轮询分配，确保同一角色不同 agent 可能获得不同 variant
            idx = len(role_assignments[role]) % len(variants)
            agent.profile = copy.deepcopy(variants[idx])
            role_assignments[role].append(agent.profile)
```

### 验收标准

- [ ] 运行 5 代后，狼人胜率从过拟合的 70% 回落到 50%~55%
- [ ] 好人种群演化出"反悍跳"策略，狼人种群演化出"深水狼"策略
- [ ] 前端/命令行可可视化各角色 Elo 变化曲线
- [ ] 移除一方种群后，另一方胜率偏离 50%（证明是博弈结果）
- [ ] 按角色分池：预言家/女巫/猎人各自独立进化
- [ ] 同一局内不同狼人可采样不同 variant
- [ ] 种群 Elo 标准差 < 50 时自动注入多样性

---

## Phase 5：过程归因 + 元策略库

**目标**：从结果驱动进化为因果驱动。
**依赖**：Phase 1（strategy_cards 用于归因到具体卡片）+ Phase 3/4（可选）
**预估工时**：2~3 周

### 5.1 决策日志精简记录

**文件**：`backend/app/agents/base.py`（修改 `act()`）

```python
async def act(self, observation: Observation) -> tuple[Action, list[dict], dict]:
    # ... 现有逻辑

    # 只记录关键决策点
    is_critical = observation.phase in ["night_werewolf", "day_vote", "day_execution"]
    if is_critical and hasattr(self, "game_master") and self.game_master:
        from app.models.log import AgentDecisionLog
        self.game_master.log.agent_decisions.append(
            AgentDecisionLog(
                agent_id=self.agent_id,
                round_num=observation.round_num,
                phase=Phase(observation.phase),
                observation=observation.model_dump(),
                llm_prompt="",  # 不存原始 prompt，只存摘要（避免膨胀）
                llm_response=json.dumps({"reasoning": result.get("reasoning", "")}, ensure_ascii=False),
                action=action,
            )
        )
    return action, messages, result
```

> **注意**：`Agent` 需要持有 `game_master` 引用。当前架构中 `BaseAgent` 没有反向引用，
> 可以通过 `GameMaster.setup()` 中设置 `agent.game_master = self` 注入。

### 5.2 归因 Judge

**文件**：`backend/app/evolution/attribution.py`（新增）

```python
"""策略归因 Judge — 诊断决策违反了哪些策略卡片."""

from app.models.log import AgentDecisionLog, AgentProfile, StrategyCard
from app.llm.client import LLMClient


class StrategyAttributionJudge:
    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    async def judge_decision(
        self,
        decision_log: AgentDecisionLog,
        profile: AgentProfile,
        known_info_only: bool = True,  # 关键：只给 Judge 看 Agent 当时的已知信息
    ) -> dict:
        # 构造 observation 摘要（脱敏：移除隐藏信息）
        obs = decision_log.observation.copy()
        if known_info_only:
            obs.pop("true_roles", None)
            obs.pop("werewolf_teammates", None)

        cards_text = "\n".join(
            f"- [{c.card_id}] (权重{c.weight}): {c.text}"
            for c in profile.strategy_cards
        ) if profile.strategy_cards else profile.strategy_notes

        prompt = (
            f"【Agent 策略卡片】\n{cards_text}\n\n"
            f"【决策场景】第{decision_log.round_num}轮 {decision_log.phase.value}\n"
            f"【Agent 已知信息】{json.dumps(obs, ensure_ascii=False)}\n"
            f"【Agent 选择】{decision_log.action.model_dump()}\n\n"
            f"请评估该决策：\n"
            f'{{"score": 1-10, "violated_cards": ["card_id"], "reason": "...", "suggestion": "..."}}'
        )

        return await self.llm.chat_json(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
```

### 5.3 失败案例库

**文件**：`backend/app/evolution/case_library.py`（新增）

```python
"""失败案例库 — 基于 RAG 检索历史失败决策."""

import json
import hashlib
from pathlib import Path
from typing import Optional


class FailureCaseLibrary:
    def __init__(self, storage_dir: str = "logs/case_library"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.index: dict[str, list[dict]] = {}  # key -> cases
        self._load_index()

    def _hash_scenario(self, observation: dict) -> str:
        # 粗粒度 hash：role + phase + 存活人数
        alive_count = sum(1 for p in observation.get("players_status", []) if p.get("alive"))
        key_str = f"{observation.get('phase')}_{alive_count}"
        return hashlib.md5(key_str.encode()).hexdigest()[:8]

    def add(self, decision_log, judgement: dict, min_score: float = 3.0) -> None:
        """只收录 Judge 评分 <= min_score 的明确失败案例."""
        if judgement.get("score", 10) > min_score:
            return
        key = self._hash_scenario(decision_log.observation)
        case = {
            "role": decision_log.observation.get("role"),
            "phase": decision_log.phase.value,
            "scenario_summary": self._summarize_observation(decision_log.observation),
            "action": decision_log.action.model_dump(),
            "violated_cards": judgement.get("violated_cards", []),
            "suggestion": judgement.get("suggestion", ""),
        }
        self.index.setdefault(key, []).append(case)
        self._save_index()

    def retrieve(self, role: str, observation: dict, k: int = 3) -> list[dict]:
        key = self._hash_scenario(observation)
        candidates = self.index.get(key, [])
        # 简单过滤：只取同角色的
        same_role = [c for c in candidates if c["role"] == role]
        return same_role[:k]

    def _summarize_observation(self, observation: dict) -> str:
        # 用 LLM 或规则生成场景摘要（Phase 5 MVP 用简化版）
        return f"第{observation.get('round_num')}轮，存活{sum(1 for p in observation.get('players_status', []) if p.get('alive'))}人"

    def _save_index(self) -> None:
        with open(self.storage_dir / "index.json", "w", encoding="utf-8") as f:
            json.dump(self.index, f, ensure_ascii=False, indent=2)

    def _load_index(self) -> None:
        idx_path = self.storage_dir / "index.json"
        if idx_path.exists():
            with open(idx_path, "r", encoding="utf-8") as f:
                self.index = json.load(f)
```

### 5.4 Optimizer CBR 集成

**文件**：`backend/app/evolution/optimizer.py`（修改 `_build_optimization_prompt`）

```python
def _build_optimization_prompt(self, ..., case_library: Optional[FailureCaseLibrary] = None):
    prompt = "..."  # 现有 prompt 前半部分

    # Phase 5 新增：检索失败案例
    if case_library:
        cases = case_library.retrieve(role, recent_observation, k=3)
        if cases:
            prompt += (
                "\n【历史失败案例】\n"
                f"以下是与当前场景相似的历史失败决策，请确保新策略能避免这些错误：\n"
            )
            for i, case in enumerate(cases, 1):
                prompt += (
                    f"{i}. 场景: {case['scenario_summary']}\n"
                    f"   错误决策: {case['action']}\n"
                    f"   违反卡片: {case['violated_cards']}\n"
                    f"   改进建议: {case['suggestion']}\n"
                )

    prompt += "\n## 输出要求\n..."
    return prompt
```

### 5.5 前端归因展示

**文件**：`frontend/src/pages/EvolutionPage.tsx`（修改）

新增面板：
- "最常被违反的策略卡片"：按角色统计 `violated_cards` 频率
- "失败案例时间线"：展示最近 10 个入库的失败案例

后端新增 `/api/evolution/{agent_id}/attribution`：

```python
@router.get("/evolution/{agent_id}/attribution")
async def get_agent_attribution(agent_id: int) -> dict:
    # 从 case_library.index 中聚合该 agent 的数据
    return {"most_violated_cards": [...], "recent_cases": [...]}
```

### 验收标准

- [ ] 狼人第一晚刀猎人被反杀，Judge 正确指出 `night_kill_priority` 执行错误
- [ ] Optimizer 生成新策略时明确引用历史失败案例
- [ ] 运行 10 代后，Judge 评分与人工标注的 Pearson 相关性 > 0.6
- [ ] 每局 Judge 调用次数 < 10（仅关键决策）
- [ ] Judge 输入中不暴露隐藏信息（如真实身份）
- [ ] 失败案例库支持按 (role, phase, 存活人数) 检索

---

## 里程碑与交付时间表

| 周次 | 里程碑 | 交付物 | 关键验收 |
|------|--------|--------|----------|
| W1 | **Phase 0 完成** | 实验日志、状态端点、前端看板 | `/api/evolution/status` 正常，前端有进度条 |
| W1~W2 | **Phase 1 完成** | StrategyCard 模型、Diff Optimizer、DB 迁移 | Mock 游戏 Prompt 中出现卡片列表，diff 降级工作 |
| W2~W3 | **Phase 2 完成** | StatisticalGuard、ScoreWeights、序贯检验 | p=0.12 被拒绝，p=0.03+d=0.5 被接受 |
| W3~W5 | **Phase 3 完成** | StrategyPopulation、交叉算子、DB 持久化 | 5 变体采样、3 代后淘汰、多样性 > 0.1 |
| W5~W8 | **Phase 4 完成** | 按角色分池、同局多 variant、均衡检测 | 胜率 50%~55%、反悍跳/深水狼策略出现 |
| W8~W11 | **Phase 5 完成** | Judge、CaseLibrary、CBR Optimizer | 刀猎人被正确归因、案例被引用 |
| W11+ | 系统联调 & 文档 | 完整端到端测试、README 更新 | 一键运行 10 代进化并生成报告 |

> **注**：人力按 1~2 人全职计算。Phase 3~5 可以部分并行（如 Phase 5 的 Judge 可与 Phase 4 同时开发）。

---

## 附录 A：数据库迁移脚本清单

| 迁移文件 | 说明 | 依赖 |
|----------|------|------|
| `001_init_tables.py` | 现有：games, player_stats, agent_profiles | 基线 |
| `002_strategy_cards.py` | 新增 strategy_cards 表 + agent_profiles.strategy_cards_version | 001 |
| `003_strategy_variants.py` | 新增 strategy_variants 表（种群持久化） | 002 |
| `004_agent_decisions.py` | 新增 agent_decisions 表（结构化存储决策日志，可选） | 003 |

---

## 附录 B：Feature Flag 设计

所有新功能通过 `EvolutionConfig` 中的布尔/枚举字段控制：

```python
@dataclass
class EvolutionConfig:
    # Phase 1
    use_strategy_cards: bool = False        # 是否启用结构化卡片
    optimizer_mode: str = "full"            # "full" | "diff"

    # Phase 2
    use_statistical_guard: bool = False     # 是否启用统计检验
    enable_sequential_testing: bool = False # 是否启用序贯检验

    # Phase 3
    use_population: bool = False            # 是否启用种群进化
    use_trueskill: bool = False             # TrueSkill vs Elo

    # Phase 4
    role_separate_pools: bool = False       # 按角色分池 vs 狼/好人二分池
    multi_variant_per_game: bool = False    # 同局同角色多 variant

    # Phase 5
    enable_attribution: bool = False        # 是否启用归因 Judge
    enable_case_library: bool = False       # 是否启用失败案例库
```

> 渐进启用策略：Phase 1 完成后 `use_strategy_cards=True`；Phase 2 完成后 `use_statistical_guard=True`；以此类推。随时可以回滚到旧模式。

---

## 附录 C：回滚策略矩阵

| 阶段 | 回滚粒度 | 回滚目标 | 触发条件 |
|------|----------|----------|----------|
| Phase 1~2 | 卡片级 | 上一 version 的 strategy_cards | Guard 拒绝 + affected_card_ids 非空 |
| Phase 3 | 变体级 | 删除退化变体，恢复父本 | 变体 Elo 连续下降 2 代 |
| Phase 3 | 种群级 | 恢复上一代 `StrategyPopulation` 快照 | 种群多样性 < 0.05 且胜率异常 |
| Phase 4 | 种群级 | 恢复上一 generation 的所有角色种群 | 均衡检测触发 "inject_diversity" 无效 |
| Phase 5 | 案例级 | 清空本周期新增的失败案例 | CBR 导致连续 3 代策略退化 |

> 种群快照实现：`EvolutionLoop` 每代结束后将 `self.role_populations` 序列化为 JSON 存入 `logs/population_snapshots/gen_{n}.json`。
