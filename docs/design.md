# 狼人杀多 Agent 协作系统 — 实施计划

## 总体路线：1 + 2 → 3

以 **方向②（评测+复盘）为底座**，叠加上 **方向①（通用Agent自演化）的能力**，最终自然形成 **方向③（自进化闭环）**。

```
Phase 1: 通用 Agent 基座 + 角色特化 + 自我反思/修改能力（方向①） ✅ 完成
Phase 2: 对局引擎 + 结构化日志 + 多维评测 + Leaderboard（方向②） ✅ 完成
Phase 3: 对局 → 分析 → 优化 → 再对局的自进化循环（方向③）      ✅ 完成
Phase 4: 前端观战 UI + 人机混战（加分项）                          ✅ 完成
```

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 / Agent 引擎 | Python 3.11+, FastAPI, asyncio, Pydantic v2 |
| 多 Agent 框架 | **自研轻量框架**（BaseAgent → RoleAgent → GameMaster），参考 ReAct/CoT |
| LLM 接入 | `openai` SDK + 自研 Mock 客户端 |
| 记忆/上下文 | 内存级 `ConversationBuffer` |
| 前端观战 UI | React 18 + TypeScript + Tailwind CSS |
| 实时通信 | WebSocket（FastAPI原生 + 前端原生 WebSocket API）|
| 结构化日志 | JSON Lines（Pydantic 模型序列化）|
| 数据/复盘 | Pandas + NumPy |
| 评测（LLM-as-a-Judge）| 规则-based 过程指标 + 可选 GPT-4 发言质量评分 |
| 容器化 | Docker + Docker Compose |
| 部署 | Nginx（前端静态资源 + 反向代理）|

---

## Phase 1：通用 Agent 基座与自演化能力（方向①） ✅ 已完成

**目标**：搭建可运行的狼人杀对局，Agent 不是 if-else 规则机，而是具备"读懂自己→修改自己→运行自己"能力的 LLM-driven Agent。

### 1.1 项目骨架搭建 ✅
- 创建 `backend/` 目录结构（见 AGENTS.md）
- 初始化 `pyproject.toml`，锁定核心依赖

### 1.2 BaseAgent — 通用 Agent 设计 ✅
- 定义抽象基类 `BaseAgent`：
  - `agent_id: int`, `role: Role`, `alive: bool`
  - `memory: ConversationBuffer` — 私有推理 + 公共消息
  - `profile: AgentProfile` — **可修改的自我描述**（核心自演化载体）
  - `act(observation: Observation) -> Action` — 核心决策接口
- `AgentProfile` 结构：
  ```python
  class AgentProfile(BaseModel):
      role_description: str      # 角色身份与目标
      strategy_notes: str        # 当前策略描述（可被Agent自己修改）
      persona: str               # 性格/说话风格
      version: int               # 策略版本号
  ```
- LLM 调用层封装：支持 temperature 配置，JSON mode / prompt-level schema 约束

### 1.3 角色特化 Agent ✅
- 每个角色继承 `BaseAgent`，重写：
  - `action_space: list[ActionType]`（狼人有 `kill/speak/vote`；女巫有 `save/poison` 等）
  - `get_role_strategy_context(observation)` — **角色特化策略提示注入**
- 角色 Prompt 模板设计：
  - 系统 Prompt 注入 `AgentProfile`（让Agent知道自己的策略和风格）
  - **角色策略提示**动态注入 User Prompt（如预言家的验人优先级、狼人的刀法策略）

### 1.4 GameMaster — 对局引擎 ✅
- 基于 `transitions` 状态机管理游戏阶段：
  ```
  Setup → Night_Werewolf → Night_Seer → Night_Witch → Day_Announce → Day_Discuss → Day_Vote → Day_Execution → (CheckWin) → Night...
  ```
- 核心职责：
  - 按阶段收集各 Agent 的 Action
  - **严格信息隔离**：只向每个 Agent 发送它应该知道的信息
  - **狼人夜间协商**：多狼时两轮协商（收集提议 → 投票决策）
  - 规则裁决：验人、刀人、救人、毒人、猎人开枪、投票计票
  - 胜负判定：屠边局（神/民边死完则狼胜，狼死完则好人胜）
- 每轮输出 `RoundLog`（Pydantic 模型），包含完整的动作序列与结果

### 1.5 自我反思与修改能力（方向①核心） ✅
- **局内反思**：每轮行动后，Agent 在 `private_memory` 中写入本轮推理
- **局后反思**：一局结束后，系统向每个 Agent 提供对局记录、胜负结果、关键决策点回顾
- **自我修改**：Agent 的 `AgentProfile.strategy_notes` 在局后被 LLM 重写
- **版本管理**：每次修改 `strategy_notes` 时 `version += 1`，旧版本保留在日志中用于对比

### 1.6 可运行对局（Phase 1 验收标准） ✅
- 命令行可以运行一局 9/12 人标准局
- Agent 能根据角色做出合理决策，不再完全依赖裸 LLM Prompt
- 输出结构化 JSON Lines 日志

---

## Phase 2：评测体系与复盘归因（方向②） ✅ 已完成

**目标**：构建多维可量化评测体系，产出 Leaderboard，使 Agent 的"好坏"可比较、可解释。

### 2.1 结构化日志升级 ✅
- 定义完整的日志 Schema（Pydantic）：
  - `GameLog`：整局元数据（玩家列表、胜负结果、轮数、耗时）
  - `RoundLog`：每轮的所有动作与状态
  - `AgentDecisionLog`：单个Agent在单个决策点的完整上下文
- 输出 JSON Lines，便于后续分析
- 日志落盘：`logs/games/{game_id}.jsonl`

### 2.2 结果评测（Outcome Metrics） ✅
- 按角色统计：
  - 胜率（Win Rate）
  - 存活轮数（Survival Rounds）
  - 狼人首刀命中率（First Night Kill Accuracy）
  - 预言家验人准确率（Seer Check Accuracy）
  - 女巫救人生还率（Witch Save Success Rate）
  - 抗推率（被投票出局率）

### 2.3 过程评测（Process Metrics） ✅
- **发言质量**（1-10分）：
  - 规则-based：逻辑连接词密度、玩家 ID 引用、角色提及、长度合理性
  - 可选 LLM-as-a-Judge：逻辑性、说服力、信息密度、伪装度（对狼人）
- **投票一致性**（0-1）：Agent 的投票是否与其公开表态一致（检测"言行不一"）
- **信息利用度**（0-1）：Agent 是否充分利用了已知信息（如预言家是否及时报查验）
- **压力应对**（1-10）：被抗推时的辩护质量

### 2.4 复盘归因系统 ✅
- 对每一局失败案例，自动生成 `PostGameReport`：
  - "败因归因"：用规则分析+LLM总结，指出最关键的决策失误
  - "时间线"：关键决策点的因果链
  - "对比"：与同角色历史平均表现的对比

### 2.5 Leaderboard ✅
- 设计评分模型：综合结果指标（60%）+ 过程指标（40%）
- 支持多维度排名：
  - 按角色（最佳狼人Agent、最佳预言家Agent）
  - 按版本（同一Agent不同 strategy_notes 版本的演进对比）
- 前端页面：React + Recharts 展示排行榜、胜率趋势

### 2.6 评测流水线自动化 ✅
- 批量对局脚本：`run_batch.py --games 100 --config configs/standard_9p.json`
- 对局结束后自动触发评测：`evaluate.py --game-log logs/games/xxx.jsonl`
- 评测结果入库：SQLite（`leaderboard.db`）

---

## Phase 3：自进化闭环（方向③） ✅ 已完成

**目标**：将 Phase 1 的"自我修改能力"与 Phase 2 的"评测反馈"串联，形成自动化进化循环。

### 3.1 进化循环架构 ✅
```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   批量对局    │────▶│   评测归因    │────▶│   策略优化    │
│  (n局自对弈)  │     │ (方向②产出)   │     │ (修改Profile) │
└──────────────┘     └──────────────┘     └──────┬───────┘
       ▲                                          │
       └──────────────────────────────────────────┘
                        (用新策略再对局)
```

### 3.2 策略优化器（Optimizer） ✅
- 输入：某 Agent 最近 N 局的对局日志 + 评测报告
- 输出：新的 `AgentProfile.strategy_notes`
- 实现方式：**Prompt 级优化** — 直接用 LLM 写新的策略描述

### 3.3 进化策略选择 ✅
- **动态选择优化目标**：
  - 从数据库查询最近对局中各角色的平均表现
  - 选择评分最低的角色进行优化（取代早期硬编码 agent_id 的做法）
- **按角色注入策略**：
  - 进化循环维护 `role_profiles: dict[str, AgentProfile]`
  - 每局 `setup()` 后，按角色匹配注入对应 profile（解决 agent_id 随机分配问题）

### 3.4 防止退化（Degeneration Guard） ✅
- 策略版本必须比上一个版本在至少一个关键指标上更优（如胜率不下降）
- 设置"回滚"机制：如果连续3个新版本表现更差，回退到历史最佳版本
- 策略修改需通过 LLM 自审："请检查你的新策略是否有逻辑矛盾"

### 3.5 前端进化看板 ✅
- 在现有 Leaderboard 上增加"进化追踪"页面：
  - 折线图：某 Agent 的 strategy_notes 从 v1 到 vN 的胜率/评分变化
  - 版本详情表：每个版本的具体数值

---

## Phase 4：前端观战 UI（加分项） ✅ 已完成

**目标**：直观呈现多 Agent 实时博弈，支持纯 AI 对战或人机混战。

### 4.1 核心页面 ✅
- **大厅页**：创建房间、选择配置（人数、角色板子）、选择 Agent 模型
- **观战页**：
  - 中央座位图（显示身份、存活状态）
  - 实时事件流（phase_change / public_chat / vote_update / death_announce / human_turn）
  - 玩家状态面板（存活/死亡、人类玩家标记）
- **复盘页**：对局结束后展示胜负归因、关键决策点、各 Agent 评分
- **Leaderboard 页**：排行榜与进化追踪

### 4.2 人机混战支持 ✅
- 在人类玩家的座位号上标记"👤玩家"
- 人类玩家通过前端操作面板提交动作（发言框、目标选择、技能按钮）
- GameMaster 对真人玩家和 AI Agent 一视同仁

### 4.3 实时通信设计 ✅
- WebSocket 事件类型：
  - `phase_change`：阶段切换通知
  - `public_chat`：公开发言
  - `vote_update`：投票结果
  - `death_announce`：死亡公告
  - `human_turn`：人类玩家操作回合
  - `game_over`：游戏结束

---

## 里程碑与验收标准

| 阶段 | 里程碑 | 验收标准 | 状态 |
|------|--------|---------|------|
| **Week 1** | Phase 1 骨架 + 可运行对局 | 命令行运行一局 9 人局，Agent 正常决策，输出结构化日志 | ✅ |
| **Week 2** | Phase 1 完善 + Phase 2 评测 | 完成所有角色Agent，实现局后反思与策略修改；结果指标可统计 | ✅ |
| **Week 3** | Phase 2 完整 + 前端基础 | 过程评测（规则-based + LLM-as-a-Judge 框架）跑通；前端观战页可连接后端 | ✅ |
| **Week 4** | Phase 3 自进化 + 前端完善 | 批量自对弈跑起来，Agent 策略在 N 局后胜率有可见提升；Leaderboard 上线 | ✅ |
| **优化迭代** | 狼人协商 + 角色特化 + 评测深化 | 多狼夜间协商、角色独立策略提示、过程指标从默认值改为真实计算 | ✅ |

---

## 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| LLM API 费用过高（批量对局消耗大） | 使用 MockLLM 做基线对比，真实 LLM 只做关键评测 |
| Agent 策略不稳定（LLM 输出随机性） | temperature 调低（0.2-0.5），使用 JSON mode 约束输出格式 |
| 信息隔离逻辑复杂易出错 | 用单元测试覆盖每个角色的可见信息范围 |
| 自进化效果不明显 | 先固定评测体系（Phase 2），确保"好坏"能量化；再小步迭代策略 |

---

## 已完成的关键优化

1. **狼人夜间协商机制**：从"取第一个狼人选择"升级为两轮协商（收集提议 → 投票决策）
2. **角色特化推理逻辑**：每个角色拥有独立的 `get_role_strategy_context()`，在 Prompt 中注入刀法/验人/跳身份等策略
3. **过程评测真实化**：从全默认值改为规则-based 真实计算（发言质量、投票一致性、信息利用度、辩护质量）
4. **进化循环健壮化**：动态选择表现最差角色优化，按角色注入 profile 解决时序问题

## 下一步行动

1. 接入真实 LLM（GPT-4o / Claude-3）测试 Agent 在协商和角色特化策略下的表现提升
2. 扩展角色板子（守卫、白痴、丘比特等）
3. 补充单元测试覆盖（Agent 层、评测指标、进化循环、API 路由）
4. 默认启用 LLM-as-a-Judge 进行发言质量评分（当前为可选）
