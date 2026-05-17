# WireWolf 自进化升级路线图

## 总体原则

- **不破坏现有接口**：`BaseAgent.act()`、`GameMaster.run()`、`/api/*` 保持兼容
- **向后兼容**：`strategy_notes` 逐步迁移到 `strategy_cards`，旧数据可自动转换
- **可回滚**：每阶段都有 feature flag，随时切回旧模式

---

## Phase 1：结构化策略卡片 + Diff 修补

**目标**：把不可拆的文本笔记变成可插拔的策略卡片，实现精准归因和局部回滚。

### 1.1 数据模型改造

**修改文件**：`backend/app/models/log.py`

```python
class StrategyCard(BaseModel):
    card_id: str           # 如 "night_kill_priority"
    category: str          # "night" | "day" | "meta"
    weight: float = 1.0    # 0~1，Prompt 中可标注优先级
    text: str              # 策略文本
    created_at: datetime = Field(default_factory=datetime.utcnow)

class AgentProfile(BaseModel):
    role_description: str
    strategy_notes: str = ""   # 兼容旧数据，新逻辑优先读 cards
    strategy_cards: list[StrategyCard] = Field(default_factory=list)
    persona: str = "冷静理性的玩家"
    version: int = 1
    agent_profile_id: str = ""
    model_name: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

**新增文件**：`backend/app/evolution/strategy_cards.py`

- 预置各角色的默认卡片模板（狼人 8 张、预言家 6 张...）
- `render_cards_to_text(cards) -> str`：把卡片列表渲染成旧版 `strategy_notes` 格式（兼容层）

### 1.2 Prompt 渲染改造

**修改文件**：`backend/app/agents/base.py`

`_system_prompt()` 改为优先渲染 `strategy_cards`：

```python
def _system_prompt(self) -> str:
    cards_text = ""
    if self.profile.strategy_cards:
        cards_text = "\n".join(
            f"- [{c.card_id}] (权重{c.weight}): {c.text}"
            for c in self.profile.strategy_cards
        )
    else:
        cards_text = self.profile.strategy_notes or "暂无"

    return (
        f"你是一名狼人杀玩家，座位号 {self.agent_id}...\n"
        f"【策略卡片】\n{cards_text}\n..."
    )
```

**修改文件**：`backend/app/agents/roles/*.py`

- 把 `get_role_strategy_context()` 返回的字符串拆成 **默认卡片**，在 `AgentProfile` 初始化时注入

### 1.3 Optimizer 支持 Diff 模式

**修改文件**：`backend/app/evolution/optimizer.py`

新增 `_build_diff_prompt()`：

```python
prompt = (
    f"【当前策略卡片】\n"
    f"{json.dumps([c.model_dump() for c in current_profile.strategy_cards], ensure_ascii=False, indent=2)}\n\n"
    f"【表现最差卡片诊断】\n"
    f"{worst_card_id}: 该卡片在最近 5 局中违反次数最多 / 对应决策评分最低\n\n"
    f"请输出 JSON diff：\n"
    f'{{"patches": ['
    f'  {{"card_id": "xxx", "op": "replace"|"add"|"delete", "text": "..."}},'
    f'  {{"card_id": "xxx", "op": "adjust_weight", "weight": 0.5}}'
    f']}}'
)
```

`optimize()` 方法增加 `mode: str = "diff"` 参数，默认 `"diff"`，保留 `"full"` 做 fallback。

### 1.4 数据库 Schema 升级

**修改文件**：`backend/app/evaluation/leaderboard.py`

```sql
-- 新增表
CREATE TABLE strategy_cards (
    profile_id TEXT,
    card_id TEXT,
    category TEXT,
    weight REAL,
    text TEXT,
    version INTEGER,
    PRIMARY KEY (profile_id, card_id, version)
);

-- 修改 agent_profiles 表，增加 strategy_cards_version 字段（兼容）
```

`save_profile()` / `load_latest_profiles()` 同步支持 cards 读写。

### 1.5 Guard 精准回滚

**修改文件**：`backend/app/evolution/guard.py`

`check_metrics()` 返回结果中增加 `affected_card_ids` 字段。若拒绝新版本，可只回滚被修改的卡片，保留其他卡片不变。

### 验收标准

- [ ] 运行一局游戏，Prompt 中 `strategy_notes` 被替换为结构化卡片列表
- [ ] Optimizer 生成 diff（非全文重写），且只修改 1~2 张卡片
- [ ] 旧版 `leaderboard.db` 可无缝迁移（`strategy_notes` 自动解析为单张默认卡片）
- [ ] 单元测试：`StrategyCard` 渲染、`diff_apply()` 正确性

**预估工时**：3~4 天

---

## Phase 2：统计显著性 + 评估体系加固

**目标**：消除小样本噪声，避免"假阳性进化"。

### 2.1 引入统计检验

**新增依赖**：`scipy`（`backend/pyproject.toml`）

**修改文件**：`backend/app/evolution/guard.py`

新增 `StatisticalGuard` 类：

```python
from scipy import stats
import numpy as np

class StatisticalGuard:
    def __init__(self, significance_level: float = 0.05):
        self.alpha = significance_level

    def compare(self, old_scores: list[float], new_scores: list[float]) -> GuardResult:
        if len(old_scores) < 3 or len(new_scores) < 3:
            return GuardResult(approved=False, reason="样本量不足")

        # Mann-Whitney U：不要求正态分布
        statistic, pvalue = stats.mannwhitneyu(
            new_scores, old_scores, alternative='greater'
        )

        mean_old = np.mean(old_scores)
        mean_new = np.mean(new_scores)

        if mean_new > mean_old and pvalue < self.alpha:
            return GuardResult(
                approved=True,
                reason=f"新策略显著更优 (p={pvalue:.3f}, {mean_old:.1f} -> {mean_new:.1f})"
            )
        return GuardResult(
            approved=False,
            reason=f"未达到显著性 (p={pvalue:.3f})"
        )
```

### 2.2 Loop 收集原始分数

**修改文件**：`backend/app/evolution/loop.py`

`_run_generation()` 中把每局每个 Agent 的 `overall_score` 按 `agent_id` 收集到列表，而非只存平均值：

```python
self._score_buffer[agent_id].append(overall_score)
```

`_get_agent_metrics()` 返回增加 `score_list` 字段，供 Guard 使用。

### 2.3 评估指标分层

**修改文件**：`backend/app/evaluation/metrics.py`

新增 `compute_overall_score()` 的权重配置：

```python
class ScoreWeights(BaseModel):
    win_rate: float = 0.30
    survival_rounds: float = 0.15
    speech_quality: float = 0.20
    vote_consistency: float = 0.15
    info_utilization: float = 0.20
```

支持按角色配置不同权重（如预言家 `info_utilization` 权重更高）。

### 2.4 增加每代对局数配置

**修改文件**：`backend/app/evolution/loop.py`

`EvolutionConfig` 增加：

```python
min_games_for_significance: int = 15   # 默认从 5 提升到 15
significance_level: float = 0.05
```

`_run_generation()` 中若 `generation > 0`（非基线），可并行运行多局加速（利用 `asyncio.gather`）。

### 验收标准

- [ ] 新策略胜率 60% vs 旧策略 50%，但 p=0.12 → 被 Guard 拒绝
- [ ] 新策略胜率 60% vs 旧策略 45%，p=0.03 → 被 Guard 接受
- [ ] 每代对局数可配置为 15~30，运行时间可接受（Mock LLM 下 < 5 分钟/代）
- [ ] 预言家和狼人使用不同的评分权重

**预估工时**：2~3 天

---

## Phase 3：策略种群进化

**目标**：从"单线程爬山"升级为"种群遗传"，避免局部最优。

### 3.1 种群管理器

**新增文件**：`backend/app/evolution/population.py`

```python
@dataclass
class StrategyVariant:
    variant_id: str
    profile: AgentProfile
    elo: float = 1500.0
    games_played: int = 0
    win_count: int = 0

class StrategyPopulation:
    def __init__(self, role: str, size: int = 5):
        self.role = role
        self.variants: list[StrategyVariant] = []
        self.size = size

    def initialize(self, base_profile: AgentProfile):
        # 基线 + 4 个 LLM 扰动变体
        self.variants.append(StrategyVariant("v0", base_profile))
        for i in range(1, self.size):
            mutated = await self._llm_mutate(base_profile, strength=0.3)
            self.variants.append(StrategyVariant(f"v{i}", mutated))

    def select_for_game(self) -> StrategyVariant:
        # 按 Elo 加权采样（兼顾探索和利用）
        weights = [math.exp(v.elo / 200) for v in self.variants]
        return random.choices(self.variants, weights=weights, k=1)[0]

    def evolve_generation(self):
        # 淘汰 Bottom 20%，用 Top 40% 交叉变异填充
        self.variants.sort(key=lambda v: v.elo, reverse=True)
        survivors = self.variants[:int(self.size * 0.8)]
        # ... 交叉 + 变异逻辑
```

### 3.2 Loop 改造

**修改文件**：`backend/app/evolution/loop.py`

- `role_profiles: dict[str, AgentProfile]` 改为 `role_populations: dict[str, StrategyPopulation]`
- `_run_generation()` 每局从种群中采样 profile 注入 GameMaster
- 每代结束后，根据对局结果更新各变体的 Elo（可用 [trueskill](https://trueskill.org/) 库）

### 3.3 交叉算子

**新增文件**：`backend/app/evolution/crossover.py`

```python
def crossover_cards(parent_a: list[StrategyCard], parent_b: list[StrategyCard]) -> list[StrategyCard]:
    """按 category 交叉：night 策略取 A，day 策略取 B"""
    child = []
    for card_a in parent_a:
        card_b = next((c for c in parent_b if c.card_id == card_a.card_id), None)
        if card_b and random.random() < 0.5:
            child.append(card_b)
        else:
            child.append(card_a)
    return child
```

### 3.4 DB 支持种群

**修改文件**：`backend/app/evaluation/leaderboard.py`

```sql
CREATE TABLE strategy_variants (
    variant_id TEXT PRIMARY KEY,
    role TEXT,
    population_gen INTEGER,
    profile_json TEXT,
    elo REAL,
    games_played INTEGER
);
```

### 验收标准

- [ ] 狼人种群有 5 个变体，每代对局中不同变体被采样
- [ ] 运行 3 代后，Elo 最低变体被淘汰，由 Top2 交叉产生新变体
- [ ] 可观察到"夜间激进刀法"和"白天保守发言"的解耦进化
- [ ] 种群数据可持久化，重启后从 DB 恢复

**预估工时**：1.5~2 周

---

## Phase 4：红蓝协同进化（Coevolution）

**目标**：狼人和好人同步进化，找到博弈均衡而非"过拟合固定对手"。

### 4.1 双种群架构

**修改文件**：`backend/app/evolution/loop.py`

```python
class EvolutionLoop:
    def __init__(...):
        # 同时维护两个种群
        self.wolf_pop = StrategyPopulation("werewolf", size=5)
        self.good_pop = StrategyPopulation("good", size=5)  # 好人通用策略池
```

> 注意：好人内部可细分为 seer_pop / witch_pop / villager_pop（Phase 4.5 可选）。

### 4.2 非对称采样对局

**修改文件**：`backend/app/evolution/loop.py` `_run_generation()`

```python
for i in range(self.evo_config.games_per_generation):
    wolf_variant = self.wolf_pop.select_for_game()
    good_variant = self.good_pop.select_for_game()

    gm = GameMaster(config=self.game_config, llm_client=self.llm)
    await gm.setup()

    # 狼人注入 wolf_variant.profile，好人注入 good_variant.profile
    for pid, agent in gm.agents.items():
        if agent.role == Role.WEREWOLF:
            agent.profile = copy.deepcopy(wolf_variant.profile)
        else:
            agent.profile = copy.deepcopy(good_variant.profile)

    await gm.run()

    # 根据胜负更新双方 Elo
    self._update_elo(wolf_variant, good_variant, gm.game_state.winner)
```

### 4.3 均衡检测

**新增文件**：`backend/app/evolution/equilibrium.py`

```python
def check_nash_approximation(pop_a: StrategyPopulation, pop_b: StrategyPopulation, history: list) -> bool:
    """检查最近 20 局是否出现循环克制（石头剪刀布），若是则增加种群多样性"""
    # 简单启发式：若胜率在 45%~55% 之间波动且不再单调变化，视为接近均衡
```

### 4.4 GameMaster 批量 Profile 注入优化

**修改文件**：`backend/app/engine/game_master.py`

新增 `inject_profiles(self, role_profile_map: dict[Role, AgentProfile])` 方法，替代当前 Loop 中的手动循环注入。

### 验收标准

- [ ] 运行 5 代后，狼人胜率从 70%（过拟合）回落到 50%~55%（均衡）
- [ ] 好人种群演化出"反悍跳"策略，狼人种群演化出"深水狼"策略
- [ ] 可可视化双方 Elo 变化曲线（前端 / 命令行输出）
- [ ] 移除一方种群后，另一方胜率不再维持 50%（证明是博弈结果而非随机）

**预估工时**：2~3 周

---

## Phase 5：过程归因 + 元策略库

**目标**：从"结果驱动"进化为"因果驱动"，让 LLM 知道"为什么这局输了"。

### 5.1 决策日志增强

**修改文件**：`backend/app/agents/base.py`

`act()` 方法中把完整的 `(observation, messages, result, action)` 记录到 `GameLog.agent_decisions`：

```python
self.game_master.log.agent_decisions.append(
    AgentDecisionLog(
        agent_id=self.agent_id,
        round_num=observation.round_num,
        phase=Phase(observation.phase),
        observation=observation.model_dump(),
        llm_prompt=json.dumps(messages, ensure_ascii=False),
        llm_response=json.dumps(result, ensure_ascii=False),
        action=action,
    )
)
```

> 需要 GameMaster 反向注入 log 引用，或让 Agent 持有 `game_log: GameLog` 引用。

### 5.2 归因 Judge

**新增文件**：`backend/app/evolution/attribution.py`

```python
class StrategyAttributionJudge:
    async def judge_decision(self, decision_log: AgentDecisionLog, profile: AgentProfile) -> dict:
        prompt = (
            f"【Agent 策略卡片】\n{profile.strategy_cards}\n\n"
            f"【决策场景】第{decision_log.round_num}轮 {decision_log.phase}\n"
            f"【当时局面】{decision_log.observation}\n"
            f"【Agent 选择】{decision_log.action}\n"
            f"【后续结果】该 Agent 本轮后存活/死亡，阵营最终胜利/失败\n\n"
            f"请输出 JSON："
            f'{{"score": 1-10, "violated_cards": ["card_id"], "reason": "...", "suggestion": "..."}}'
        )
        return await self.llm.chat_json(...)
```

### 5.3 失败案例库

**新增文件**：`backend/app/evolution/case_library.py`

```python
class FailureCaseLibrary:
    """按 (role, phase, scenario_hash) 索引失败决策"""
    def add(self, decision_log: AgentDecisionLog, judgement: dict):
        key = self._hash_scenario(decision_log.observation)
        self.cases[key].append({"log": decision_log, "judgement": judgement})

    def retrieve(self, role: str, observation: dict, k: int = 3) -> list[dict]:
        """RAG：检索相似历史失败案例"""
```

### 5.4 Optimizer 基于案例推理（CBR）

**修改文件**：`backend/app/evolution/optimizer.py`

`optimize()` 在构造 Prompt 前，先从 `FailureCaseLibrary` 检索该角色最近 3 个高相似度失败案例：

```python
cases = case_library.retrieve(role, recent_observation, k=3)
prompt += (
    f"【历史失败案例】\n"
    f"{cases}\n"
    f"请确保新策略能避免上述错误。"
)
```

### 5.5 前端追踪页升级

**修改文件**：`frontend/src/pages/EvolutionPage.tsx`

- 显示某 Agent 的"最常被违反的策略卡片"
- 显示"失败案例时间线"

### 验收标准

- [ ] 某局狼人第一晚刀到猎人被反杀，归因 Judge 正确指出 `night_kill_priority` 卡片执行错误
- [ ] Optimizer 生成新策略时，明确引用了"避免刀猎人"的历史案例
- [ ] 运行 10 代后，归因准确率（Judge 评分 vs 实际结果相关性）> 0.6
- [ ] 失败案例库支持向量检索（可用 sqlite-vec 或简单 TF-IDF）

**预估工时**：2~3 周

---

## 依赖关系与执行顺序

```
Phase 1 (结构化卡片)
       ↓
Phase 2 (统计显著性) ──→ 可独立并行
       ↓
Phase 3 (种群进化) ────→ 依赖 Phase 1
       ↓
Phase 4 (协同进化) ────→ 依赖 Phase 3
       ↓
Phase 5 (归因+CBR) ────→ 依赖 Phase 1 + 可选并行 Phase 4
```

## 资源建议

| 阶段    | 人力   | 算力/LLM 消耗                            | 风险               |
| ------- | ------ | ---------------------------------------- | ------------------ |
| Phase 1 | 1 人   | 低                                       | 低（纯重构）       |
| Phase 2 | 1 人   | 中（对局数增加）                         | 低                 |
| Phase 3 | 1~2 人 | 高（5x 策略变体 = 5x LLM Prompt 多样性） | 中（需调交叉参数） |
| Phase 4 | 2 人   | 极高（双种群对局量翻倍）                 | 高（可能不收敛）   |
| Phase 5 | 1~2 人 | 高（每决策点调一次 Judge LLM）           | 中（Judge 幻觉）   |
