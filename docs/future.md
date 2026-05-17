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
- **`validate_card_id(cards)`**：确保 card_id 全局唯一，避免交叉算子取错卡片

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

> **优化建议**：`weight` 字段不要只当注释，要根据权重调整强调程度。
> 例如 weight >= 0.8 时加前缀 `【核心策略】`，weight <= 0.3 时加 `【参考策略】`，
> 让 LLM 真正感知到优先级差异。

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

> **优化建议**：LLM 输出精确 JSON diff 的失败率较高，务必增加以下容错：
> 1. **Prompt 中增加 Few-shot 示例**：给出 2~3 个正确的 diff 样例。
> 2. **增加 `fallback_to_full` 开关**：如果 diff 解析失败（如 card_id 不存在、op 非法），
>    自动降级为 `"full"` 模式重写，并打印 warning。
> 3. **Diff 应用前做预检**：`diff_apply()` 应该先返回预览（preview），
>    确认卡片总数、总文本长度无异常后再真正写入。

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

> **优化建议**：`strategy_cards` 的 PRIMARY KEY 包含 `version`，
> 这意味着同一 profile 的不同版本卡片历史都会被保留，长期可能数据膨胀。
> 建议增加一个 `card_history` 表存历史版本，而 `strategy_cards` 只存当前版本，
> 或者增加定期归档机制（保留最近 10 个 version）。

### 1.5 Guard 精准回滚

**修改文件**：`backend/app/evolution/guard.py`

`check_metrics()` 返回结果中增加 `affected_card_ids` 字段。若拒绝新版本，可只回滚被修改的卡片，保留其他卡片不变。

> **优化建议**：在种群进化（Phase 3+）阶段，"精准回滚"的概念会变模糊——
> 如果新变体由交叉变异产生，"回滚"应该恢复为哪个父本？
> 建议此时改为**变体级别淘汰**（直接删除整个变体），而非卡片级别回滚。
> Phase 1 阶段可先保留卡片级回滚，Phase 3 后文档应说明回滚策略的切换。

### 验收标准

- [ ] 运行一局游戏，Prompt 中 `strategy_notes` 被替换为结构化卡片列表
- [ ] Optimizer 生成 diff（非全文重写），且只修改 1~2 张卡片
- [ ] 旧版 `leaderboard.db` 可无缝迁移（`strategy_notes` 自动解析为单张默认卡片）
- [ ] 单元测试：`StrategyCard` 渲染、`diff_apply()` 正确性
- [ ] **新增**：diff 解析失败时自动降级为 full 模式，不中断进化流程

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

> **优化建议**：
> 1. **避免单边检验的盲区**：当前 `alternative='greater'` 只检测"新策略是否显著更好"，
>    但如果新策略**显著更差**（比如引入了一个致命 bug），p 值也会很大，导致"不显著"而被拒绝。
>    这本身没问题，但建议增加**双向安全检测**：
>    如果 `mean_new < mean_old` 且差值超过一个阈值（如 2 个标准差），直接标记为"退化风险"，
>    即使统计上不显著也提前终止，避免浪费算力。
> 2. **增加效应量（Effect Size）**：统计显著 ≠ 实际显著。
>    建议计算 Cliff's delta 或 Cohen's d，只有效应量也达到"中等"以上（|d| > 0.3）才接受。
>    否则可能出现"p=0.01 但只提升了 0.5%"的情况。

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

> **优化建议**：
> 1. **权重本身也应进化**：固定权重可能导致某些角色被系统性低估。
>    可以增加一层元优化（meta-optimization），用少量对局数据验证当前权重组合
>    是否能预测最终胜率。但这属于长期优化，Phase 2 可先固定，在 Phase 5 后考虑。
> 2. **增加"对局难度校准"**：Agent 的 score 应该考虑对手强度。
>    例如击败高 Elo 对手应获得更高分。这在 Phase 3（Elo 体系）引入后自然解决，
>    但 Phase 2 的 `overall_score` 可以作为 Phase 3 的输入之一。

### 2.4 增加每代对局数配置

**修改文件**：`backend/app/evolution/loop.py`

`EvolutionConfig` 增加：

```python
min_games_for_significance: int = 15   # 默认从 5 提升到 15
significance_level: float = 0.05
```

`_run_generation()` 中若 `generation > 0`（非基线），可并行运行多局加速（利用 `asyncio.gather`）。

> **优化建议**：15 局对于 Mock LLM 没问题，但真实 LLM 下成本很高。
> 建议增加**序贯检验（Sequential Testing）**机制：
> 先跑 5 局做快速筛选，如果新策略表现极差（比如 5 连败），直接淘汰；
> 如果表现很好（5 连胜），再跑 10 局确认；只有 middling 的结果才跑满 15 局。
> 这样可以在保证统计效力的同时大幅节省 LLM 调用成本。

### 验收标准

- [ ] 新策略胜率 60% vs 旧策略 50%，但 p=0.12 → 被 Guard 拒绝
- [ ] 新策略胜率 60% vs 旧策略 45%，p=0.03 → 被 Guard 接受
- [ ] 每代对局数可配置为 15~30，运行时间可接受（Mock LLM 下 < 5 分钟/代）
- [ ] 预言家和狼人使用不同的评分权重
- [ ] **新增**：新策略 5 连败时提前终止，不必跑满 15 局
- [ ] **新增**：接受的新策略效应量 |d| > 0.3

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

> **优化建议**：
> 1. **`initialize` 方法没有 async 标记却用了 await**：需要改为 `async def initialize(...)`。
> 2. **探索-利用平衡过于激进**：`math.exp(elo / 200)` 会让低 Elo 变体几乎永远不被采样。
>    建议改用 **Softmax with temperature**：
>    ```python
>    temperature = max(50, 200 - generation * 10)  # 随代数降低温度
>    weights = [math.exp(v.elo / temperature) for v in self.variants]
>    ```
>    早期温度高（探索），后期温度低（利用）。
> 3. **增加多样性保护（Diversity Preservation）**：
>    如果 Top 2 变体的策略卡片相似度 > 0.9（用文本相似度或 card_id 重叠度），
>    强制对其中一个注入随机扰动，避免种群过早收敛到同一个局部最优。
>    否则可能出现 5 个变体本质上是同一个策略的拷贝。

### 3.2 Loop 改造

**修改文件**：`backend/app/evolution/loop.py`

- `role_profiles: dict[str, AgentProfile]` 改为 `role_populations: dict[str, StrategyPopulation]`
- `_run_generation()` 每局从种群中采样 profile 注入 GameMaster
- 每代结束后，根据对局结果更新各变体的 Elo（可用 [trueskill](https://trueskill.org/) 库）

> **优化建议**：**强烈推荐用 TrueSkill 替代 Elo**。狼人杀是团队博弈，
> Elo 本质是为 1v1 设计的，而 TrueSkill 天然支持队伍对局，
> 能更准确地更新狼人阵营和好人阵营中每个变体的评分。
> 如果坚持用 Elo，至少需要把阵营胜负映射为每个变体的"对局结果"，
> 但这样会丢失团队内部贡献差异。

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

> **优化建议**：
> 1. **交叉算子没有遗传 weight**：如果父本 A 的 `night_kill_priority` weight=0.9，
>    父本 B 的 weight=0.3，按当前逻辑子代要么全取 A 要么全取 B。
>    建议支持 weight 的**混合遗传**：`child.weight = (w_a + w_b) / 2 + 噪声`。
> 2. **按 category 交叉过于僵化**：可以在 Prompt 层面让 LLM 做"语义交叉"，
>    即把两张 parent 的卡片文本都丢给 LLM，让它生成一张融合两者优点的子代卡片。
>    这比按 card_id 随机交换更智能，但也更昂贵。可以作为可选算子。

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

> **优化建议**：`profile_json` 用 TEXT 存完整 JSON 在长期查询中效率低。
> 如果需要频繁检索某个角色的当前种群，建议把 `strategy_cards` 单独存一张表，
> `strategy_variants` 只存元数据，并通过 `profile_id` 外键关联。
> 或者直接用 PostgreSQL 的 `jsonb` 类型替代 TEXT，支持索引和查询。

### 验收标准

- [ ] 狼人种群有 5 个变体，每代对局中不同变体被采样
- [ ] 运行 3 代后，Elo 最低变体被淘汰，由 Top2 交叉产生新变体
- [ ] 可观察到"夜间激进刀法"和"白天保守发言"的解耦进化
- [ ] 种群数据可持久化，重启后从 DB 恢复
- [ ] **新增**：种群中不存在相似度 > 0.9 的两个变体（多样性保护）
- [ ] **新增**：使用 TrueSkill 替代 Elo 进行团队对局评分

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

> **优化建议**：**强烈建议 Phase 4 直接按角色分池，不要先做一个"好人通用池"。**
> 预言家和女巫的策略空间差异极大（一个需要主动暴露信息，一个需要隐藏信息），
> 混在一起会导致优化目标冲突。"好人通用池"只在 Phase 3 的种群框架尚未成熟时有过渡价值，
> 但既然 Phase 3 已经建立了 `StrategyPopulation(role=...)` 的架构，
> Phase 4 直接按角色实例化即可：
> ```python
> self.role_pops = {
>     "werewolf": StrategyPopulation("werewolf", size=5),
>     "seer": StrategyPopulation("seer", size=5),
>     "witch": StrategyPopulation("witch", size=5),
>     "hunter": StrategyPopulation("hunter", size=5),
>     "villager": StrategyPopulation("villager", size=5),
> }
> ```
> 这样每个角色都有独立的进化压力，不会出现"为了照顾预言家而损害了女巫"的情况。

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

> **优化建议**：
> 1. **同一局中所有狼人使用同一个 variant，损失了种群多样性**。
>    建议同一局内不同狼人座位可以采样不同 variant（只要 Elo 差距不太大，
>    比如限制在同一局内狼人 variant 的 Elo 差 < 200）。
>    这样能观察到"不同狼人分工"（如一个悍跳、一个深水）的进化效果。
> 2. **好人一方不同角色也应用不同 variant**：当前所有好人角色共享一个 `good_variant`，
>    这意味着预言家和女巫被迫使用同一套策略，极不合理。
>    如果采纳了上面的"按角色分池"建议，这里自然改为按角色注入各自的 variant。

### 4.3 均衡检测

**新增文件**：`backend/app/evolution/equilibrium.py`

```python
def check_nash_approximation(pop_a: StrategyPopulation, pop_b: StrategyPopulation, history: list) -> bool:
    """检查最近 20 局是否出现循环克制（石头剪刀布），若是则增加种群多样性"""
    # 简单启发式：若胜率在 45%~55% 之间波动且不再单调变化，视为接近均衡
```

> **优化建议**：
> 1. **"胜率 45%~55%"不一定是均衡**：标准 12 人狼人杀（4 狼 4 神 4 民）在随机策略下
>    胜率天然接近 50%。真正需要检测的是**策略多样性是否被维持**。
>    建议增加指标：种群内各 variant 的 Elo 标准差。如果标准差持续缩小到 < 50，
>    说明种群收敛了，此时即使胜率 50% 也需要注入新多样性。
> 2. **循环克制的检测**：可以用简单的"最近 N 代胜率序列的自相关性"来判断。
>    如果出现正负交替的显著模式，说明存在 Rock-Paper-Scissors 动态。

### 4.4 GameMaster 批量 Profile 注入优化

**修改文件**：`backend/app/engine/game_master.py`

新增 `inject_profiles(self, role_profile_map: dict[Role, AgentProfile])` 方法，替代当前 Loop 中的手动循环注入。

### 验收标准

- [ ] 运行 5 代后，狼人胜率从 70%（过拟合）回落到 50%~55%（均衡）
- [ ] 好人种群演化出"反悍跳"策略，狼人种群演化出"深水狼"策略
- [ ] 可可视化双方 Elo 变化曲线（前端 / 命令行输出）
- [ ] 移除一方种群后，另一方胜率不再维持 50%（证明是博弈结果而非随机）
- [ ] **新增**：按角色分池，预言家/女巫/猎人各自独立进化
- [ ] **新增**：同一局内不同狼人可采样不同 variant
- [ ] **新增**：种群 Elo 标准差 < 50 时自动注入多样性

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

> **优化建议**：`llm_prompt` 和 `llm_response` 可能非常长（单次调用可能就 4k~8k tokens），
> 全部存入内存或数据库会导致严重的存储膨胀。
> 建议：
> 1. **只存摘要**：用一个小型 Prompt 让 LLM 自己压缩决策理由（100 字以内），
>    只存摘要和关键 action，原始 prompt/response 以文件形式存到 `logs/decisions/`。
> 2. **只记录关键决策点**：不是每个 `act()` 都记录，只记录**夜间行动、白天投票、遗言、
>    关键发言**等。普通白天的"过"可以跳过。

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

> **优化建议**：
> 1. **信息隔离问题**：Judge 在评判时会看到完整 observation（包括隐藏信息如其他玩家身份），
>    这会导致"事后诸葛亮"偏差——Judge 知道谁是狼人，所以觉得"你当时应该投 3 号"，
>    但 Agent 当时并不知道。
>    **必须确保 Judge 只能看到 Agent 当时能看到的 observation**，
>    或者明确在 Prompt 中标注"以下信息是 Agent 当时已知的 / 未知的"。
> 2. **调用成本爆炸**：每决策点调一次 LLM，Phase 4 每代可能 20 局 × 12 人 × 10 轮 = 2400 个决策点。
>    建议：
>    - 只归因**失败对局**中的决策。
>    - 只归因**高影响决策**（如狼人首夜刀法、预言家首验、关键轮次投票）。
>    - 用规则-based 快速预筛选：如果某决策违反了明确的规则（如"刀猎人"），
>      直接用规则打分，不调用 LLM。
> 3. **Judge 自身的校准**：不同 LLM 的评判标准可能差异很大。
>    建议先用 50 个人工标注的决策样本校准 Judge，计算 Cohen's kappa，
>    只有 kappa > 0.6 才信任 Judge 的归因结果。

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

> **优化建议**：
> 1. **`_hash_scenario` 的设计是关键**：如果只用玩家存活状态做 hash，
>    会丢失大量上下文（如"3 号玩家昨天投了谁"、"预言家报了什么查验"）。
>    建议用**多粒度索引**：
>    - 粗粒度：`role + phase + 存活人数`
>    - 细粒度：用 LLM 生成的场景摘要（50 字）做 embedding，用向量检索。
> 2. **案例库的质量控制**：不是所有失败案例都值得入库。
>    只有 Judge 评分 <= 3 且归因明确的案例才入库，避免噪声案例污染检索结果。

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

> **优化建议**：CBR 的上下文长度需要控制。3 个案例如果每个都包含完整 observation，
> 可能远超 LLM 上下文窗口。建议每个案例只保留：
> - 场景摘要（2~3 句话）
> - Agent 当时的错误决策
> - Judge 的改进建议
> 总长度控制在 500 tokens 以内。

### 5.5 前端追踪页升级

**修改文件**：`frontend/src/pages/EvolutionPage.tsx`

- 显示某 Agent 的"最常被违反的策略卡片"
- 显示"失败案例时间线"

### 验收标准

- [ ] 某局狼人第一晚刀到猎人被反杀，归因 Judge 正确指出 `night_kill_priority` 卡片执行错误
- [ ] Optimizer 生成新策略时，明确引用了"避免刀猎人"的历史案例
- [ ] 运行 10 代后，归因准确率（Judge 评分 vs 实际结果相关性）> 0.6
- [ ] 失败案例库支持向量检索（可用 sqlite-vec 或简单 TF-IDF）
- [ ] **新增**：Judge 评分与人工标注的 Cohen's kappa > 0.6
- [ ] **新增**：每局 LLM Judge 调用次数 < 10（仅归因关键决策）
- [ ] **新增**：归因 Judge 只能访问 Agent 当时的已知信息

**预估工时**：2~3 周

---

## 全局优化建议（新增章节）

### 观测基础设施（贯穿所有 Phase）

Phase 3~5 的调试难度远高于前两个阶段，如果缺乏实时观测能力，
跑失败了你甚至不知道是种群不收敛、Judge 幻觉还是交叉算子 bug。
建议在每个 Phase 开始前，先完善以下基础设施：

1. **实验追踪**：引入 `wandb` 或 `mlflow`，记录每代的：
   - 各角色/变体的胜率、平均存活轮数、Elo 变化
   - 每局对局的完整配置（以便复现）
   - LLM 调用次数和 token 消耗（成本控制）
   
   如果嫌重，至少标准化一个 `ExperimentLog` JSON Lines 格式，
   每条记录包含 generation、game_id、variant_ids、winners、scores。

2. **实时看板**：在 `EvolutionPage.tsx` 增加一个"实验看板"，
   显示当前运行中的进化代数和关键指标（类似 TensorBoard 的折线图）。
   后端增加 `/api/evolution/status` 端点，Loop 运行时每完成一代就 push 一次数据。

3. **对局复现工具**：给定 `game_id`，能一键重跑该对局（固定随机种子和 variant 选择）。
   这对于 debug"为什么这局狼人崩了"至关重要。

### 成本预算控制

Phase 3~5 在真实 LLM 下的调用量：

| 阶段 | 每代估算调用 | 真实 LLM 成本（GPT-4o） |
|------|-------------|------------------------|
| Phase 1~2 | 15 局 × 12 人 × 8 轮 ≈ 1440 | ~$2~5 |
| Phase 3 | 5 变体 × 20 局 × 12 人 × 8 轮 ≈ 9600 | ~$15~30 |
| Phase 4 | 双种群 × 20 局 × 12 人 × 8 轮 ≈ 9600 | ~$15~30 |
| Phase 5 | + Judge 调用（若全量）≈ 额外 5000~10000 | +$10~20 |

> **建议**：在 `EvolutionConfig` 中增加 `budget_usd_per_generation` 字段，
> Loop 运行前根据历史 token 消耗估算成本，超预算时自动切换为 Mock LLM 或暂停。

### 回滚策略的澄清

当前文档提到"回退到上一版本"，但在种群进化中这一概念需要重新定义：

- **Phase 1~2（单策略）**：回滚 = 恢复上一 version 的 `AgentProfile`。
- **Phase 3~4（种群）**：回滚 = 恢复上一 generation 的完整 `StrategyPopulation` 快照。
  建议每代结束后将种群状态序列化到 DB（`population_snapshots` 表），
  包含 generation、timestamp、所有 variant 的 profile_json 和 Elo。
- **Phase 5（CBR）**：案例库本身不需要回滚，但如果 CBR 导致策略退化，
  回滚时应同时清空该周期内新增的失败案例（避免错误案例持续污染）。

---

## 依赖关系与执行顺序

```
Phase 1 (结构化卡片)
       ↓
Phase 2 (统计显著性) ──→ 依赖 Phase 1，不建议完全独立并行
       ↓
Phase 3 (种群进化) ────→ 依赖 Phase 1 + Phase 2（统计检验用于淘汰）
       ↓
Phase 4 (协同进化) ────→ 依赖 Phase 3
       ↓
Phase 5 (归因+CBR) ────→ 依赖 Phase 1 + Phase 3/4
```

> **优化建议**：原图中 Phase 2 标注为"可独立并行"，但实际上 Phase 2 的 `ScoreWeights`
> 和统计检验直接影响 Phase 3 的淘汰标准。如果 Phase 3 先上线而 Phase 2 的 Guard 还没做好，
> 种群淘汰可能基于噪声数据。建议 Phase 1 和 Phase 2 串行完成后，再进入 Phase 3。

---

## 资源建议（更新）

| 阶段    | 人力   | 算力/LLM 消耗                            | 风险               | 新增建议 |
| ------- | ------ | ---------------------------------------- | ------------------ | -------- |
| Phase 1 | 1 人   | 低                                       | 低（纯重构）       | diff 容错 + 数据归档 |
| Phase 2 | 1 人   | 中（对局数增加）                         | 低                 | 序贯检验 + 效应量 |
| Phase 3 | 1~2 人 | 高（5x 策略变体 = 5x LLM Prompt 多样性） | 中（需调交叉参数） | 多样性保护 + TrueSkill |
| Phase 4 | 2 人   | 极高（双种群对局量翻倍）                 | 高（可能不收敛）   | 按角色分池 + 均衡检测 |
| Phase 5 | 1~2 人 | 高（每决策点调一次 Judge LLM）           | 中（Judge 幻觉）   | 关键决策归因 + Judge 校准 |
| **观测基础设施** | 0.5 人 | 低 | 低 | **建议 Phase 3 之前完成** |

---

## 总结

原始路线图的核心架构（结构化卡片 → 统计检验 → 种群 → 协同进化 → 归因）是正确且成熟的。
上述优化建议主要集中在：

1. **实现层面的鲁棒性**：diff 容错、async 标记、数据归档、成本预算。
2. **统计方法的严谨性**：效应量、序贯检验、TrueSkill、多样性指标。
3. **架构设计的提前量**：Phase 4 直接按角色分池，避免后续返工。
4. **LLM 调用的成本控制**：关键决策归因、规则预筛选、上下文压缩。
5. **可观测性**：实验追踪、实时看板、种群快照，没有这些 Phase 3+ 会很难 debug。

建议优先级：**观测基础设施**（Phase 3 前）> **Phase 1 的 diff 容错** > **Phase 2 的序贯检验** > **Phase 4 按角色分池**。
