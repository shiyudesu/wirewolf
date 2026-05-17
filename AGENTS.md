# WireWolf — Agent 开发指南

## 项目概述

狼人杀多 Agent 协作系统，核心目标是让 LLM-driven Agent 具备"读懂自己→修改自己→运行自己"的自演化能力。

## 当前状态

**Phase 1-4 全部完成**，系统可运行。支持：
- ✅ 12人标准局完整对局循环
- ✅ 5 个角色（狼人/预言家/女巫/猎人/平民）
- ✅ **角色特化推理逻辑** — 每个角色拥有独立的策略提示（刀法优先级、验人策略、跳身份时机等）
- ✅ **狼人夜间协商机制** — 多狼时两轮协商：收集提议 → 分歧时投票决策
- ✅ Mock LLM 快速测试 + 真实 LLM 接入
- ✅ 结构化日志（JSON Lines，含完整 reasoning 与协商记录）
- ✅ 评测体系（结果指标 + **规则-based 过程指标** + 可选 LLM-as-a-Judge + 复盘报告）
- ✅ Leaderboard（**PostgreSQL** + 多维度排名）
- ✅ 自进化闭环（批量对局 → 评测 → **按角色表现排序优化** → 再对局）
- ✅ 退化防护（指标对比 + LLM 自审 + **回退到上一版本**）
- ✅ 前端 React + Tailwind（排行榜/对局列表/复盘/进化追踪/**实时观战**）
- ✅ WebSocket 实时观战（含心跳 ping/pong）
- ✅ 人机混战基础（人类玩家通过前端操作）
- ✅ 局后反思（Post-game Reflection）
- ✅ FastAPI 自动挂载前端构建产物（`frontend/dist` → `/`）

## 目录结构

```
wirewolf/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口（静态文件挂载、WebSocket、局后反思触发）
│   │   ├── api/routes.py        # REST API 路由
│   │   ├── db/                  # 数据库层（PostgreSQL + SQLAlchemy async ORM）
│   │   │   ├── base.py          # Engine / Session / DeclarativeBase
│   │   │   ├── models.py        # SQLAlchemy ORM 模型
│   │   │   └── database.py      # AsyncLeaderboardDB 数据访问层
│   │   ├── engine/              # 对局引擎
│   │   │   ├── game_master.py   # 游戏主控（人机混战 + 狼人协商 + 局后反思）
│   │   │   ├── state_machine.py # 阶段状态机
│   │   │   └── rules.py         # 规则与胜负裁决
│   │   ├── agents/              # Agent 层
│   │   │   ├── base.py          # BaseAgent（通用 Agent 基类，含角色策略 hook）
│   │   │   ├── memory.py        # 记忆管理
│   │   │   └── roles/           # 角色特化（5 个角色，各含独立策略提示）
│   │   ├── llm/                 # LLM 统一接入
│   │   │   ├── client.py        # OpenAI 格式客户端
│   │   │   └── mock_client.py   # Mock 客户端（测试用）
│   │   ├── models/              # Pydantic 数据模型
│   │   │   ├── action.py        # Action 动作模型
│   │   │   ├── enums.py         # 枚举定义
│   │   │   ├── game.py          # GameConfig 配置模型
│   │   │   └── log.py           # Log / AgentProfile 日志与策略模型
│   │   ├── evaluation/          # 评测体系
│   │   │   ├── metrics.py       # 结果指标 + 过程指标（规则-based + 异步 LLM）
│   │   │   ├── judge.py         # LLM-as-a-Judge
│   │   │   ├── report.py        # PostGameReport
│   │   │   └── leaderboard.py   # 排行榜数据访问
│   │   ├── evolution/           # 自进化模块
│   │   │   ├── optimizer.py     # 策略优化器
│   │   │   ├── guard.py         # 退化防护
│   │   │   └── loop.py          # 进化主循环（按角色表现排序选择优化目标）
│   │   ├── batch/               # 批量对局
│   │   │   └── runner.py        # 批量运行器
│   │   ├── websocket/           # WebSocket 观战
│   │   │   └── manager.py       # 连接管理器
│   │   └── utils/               # 工具函数
│   │       └── logger.py        # 日志配置
│   ├── alembic/                 # 数据库迁移
│   │   ├── env.py
│   │   └── versions/001_init_tables.py
│   ├── tests/                   # 测试（当前覆盖：规则引擎、整局对局）
│   ├── run_cli.py               # 命令行运行一局
│   ├── run_batch.py             # 批量对局入口
│   ├── evaluate.py              # 评测流水线入口
│   ├── run_evolution.py         # 自进化循环入口
│   ├── pyproject.toml           # 依赖与工具配置（black/ruff/mypy/pytest）
│   ├── Dockerfile               # 后端 Docker（backend/ 内）
│   ├── .env.example             # 环境变量模板
│   └── alembic.ini              # Alembic 配置
├── frontend/                    # React 18 + TypeScript + Tailwind CSS + Vite
│   ├── src/
│   │   ├── pages/               # 页面组件
│   │   │   ├── Home.tsx         # 大厅（创建对局/批量/观战）
│   │   │   ├── GamesPage.tsx    # 对局列表
│   │   │   ├── GameReplayPage.tsx # 复盘回放
│   │   │   ├── LeaderboardPage.tsx # 排行榜
│   │   │   ├── EvolutionPage.tsx   # 进化追踪
│   │   │   └── WatchPage.tsx    # 实时观战
│   │   ├── components/
│   │   │   └── Layout.tsx       # 布局组件
│   │   ├── assets/              # 静态资源（hero.png、svg 图标）
│   │   ├── App.tsx              # 路由入口
│   │   └── main.tsx             # 应用挂载点
│   └── dist/                    # 构建产物（FastAPI 自动挂载）
├── configs/                     # 游戏配置 JSON
├── logs/games/                  # 对局日志（JSON Lines，运行时生成）
├── docs/                        # 设计文档
│   ├── design.md                # 架构设计
│   ├── db_migration.md          # 数据库迁移说明
│   └── future.md                # 未来规划
├── Dockerfile.backend           # 后端 Docker（项目根）
├── Dockerfile.frontend          # 前端 Docker
├── docker-compose.yml           # 一键启动
├── nginx.conf                   # Nginx 配置
├── start_backend_pg.sh          # 本地启动后端脚本（PostgreSQL 依赖）
├── LICENSE                      # MIT License
└── README.md                    # 项目介绍
```

## 快速开始

### 本地开发

```bash
cd wirewolf

# 后端
cd backend

# 安装依赖（推荐用虚拟环境）
pip install -e ".[dev]"

# 或手动安装核心依赖
# pip install fastapi uvicorn pydantic openai httpx structlog transitions \
#     python-dotenv sqlalchemy[asyncio] asyncpg alembic pandas numpy plotly

# 配置环境变量
cp .env.example .env
# 编辑 .env：填入 LLM_API_KEY、DATABASE_URL 等

# 启动 PostgreSQL（如使用 Docker Compose）
# docker-compose up -d postgres

# 数据库迁移
alembic upgrade head

# 启动 FastAPI
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 前端（另一个终端）
cd frontend
npm install
npm run build
# 访问 http://localhost:8000/
```

### Docker 一键启动

```bash
cd wirewolf
cp backend/.env.example backend/.env
# 编辑 backend/.env 填入 LLM_API_KEY（可选，Mock 模式可不填）
docker-compose up --build
# 访问 http://localhost/
```

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/health` | GET | 健康检查 |
| `/api/config` | GET | 获取服务端公开配置（llm_model、llm_base_url） |
| `/api/leaderboard` | GET | 排行榜（支持 `?role=`、`?model_name=`、`?limit=` 过滤） |
| `/api/games` | GET | 对局列表（`?limit=`，默认 50） |
| `/api/games/{id}` | GET | 单局详情 |
| `/api/games/{id}/report` | GET | 复盘报告 |
| `/api/games/{id}/metrics` | GET | 评测指标 |
| `/api/batch/run` | POST | 启动批量对局（支持 `seer_count`、`witch_count`、`hunter_count`、`model` 等字段） |
| `/api/batch/status` | GET | 批量对局状态 |
| `/api/game/start` | POST | 创建对局（支持 `human_seats`、`model` 等字段） |
| `/api/game/{id}/action` | POST | 人类玩家提交操作 |
| `/api/evolution/{agent_id}` | GET | Agent 进化历史 |
| `/ws/watch/{game_id}` | WS | 观战 WebSocket（支持 `ping`/`pong` 心跳） |

## 核心设计

### 信息隔离

GameMaster 严格隔离信息：
- 狼人知道队友身份
- 预言家只知道自己的查验结果
- 女巫只知道夜间刀口
- 平民只知道公共发言和投票

### 狼人夜间协商

多狼时不再"取第一个狼人的选择"，而是执行两轮协商：
1. **收集提议**：每个存活狼人独立提出击杀目标 + 理由
2. **投票决策**：若意见不一致，广播队友提议后重新投票，多数胜出（平票随机）

协商过程完整记录到 `RoundLog.actions` 中，可全程观测。

### 角色特化推理

`BaseAgent` 提供 `get_role_strategy_context(observation) -> str` hook，各角色覆盖此方法注入策略提示：

| 角色 | 夜间策略 | 白天策略 |
|------|----------|----------|
| 狼人 | 优先刀神职（预言家>女巫>猎人），避免刀猎人 | 模仿好人逻辑，适当攻击队友做身份，投票分散或集中 |
| 预言家 | 优先验可疑玩家，避免连续验同一人 | 有狼人悍跳时必须对跳，报查验给出清晰逻辑链 |
| 女巫 | 预言家/自身/确认好人优先救；毒药宁晚开不盲毒 | 隐藏身份，通过"银水"信息侧面帮助好人 |
| 猎人 | 无夜间行动 | 隐藏身份，被放逐时优先带走确定狼人 |
| 平民 | 整理信息，分析可疑玩家 | 观察发言矛盾，不盲目跟票，金水可适当带队 |

### 过程评测

`MetricsCalculator.compute_process_metrics()` 实现了完整的规则-based 评分：

- **发言质量**（1-10）：逻辑连接词密度、玩家 ID 引用、角色提及、长度合理性
- **投票一致性**（0-1）：发言中提及的玩家 vs 实际投票目标
- **信息利用度**（0-1）：私有信息（查验结果/刀口）是否在发言中被引用
- **辩护质量**（1-10）：被放逐轮次的发言评分

同时提供 `compute_process_metrics_async(llm_judge)`，可接入 LLM-as-a-Judge 进行更精细的评分。

### 自演化载体

`AgentProfile.strategy_notes` 是核心演化载体：
- 局后可被 LLM 重写
- 每次修改 `version += 1`
- 旧版本保留在日志中用于对比

### 退化防护

- **指标对比**：新版本必须至少在一个关键指标上不比旧版本差
- **LLM 自审**：检查新策略是否有逻辑矛盾
- **回滚机制**：连续退化时回退到**上一版本**（`old_profile`），而非历史最佳版本

### 自进化循环

`EvolutionLoop` 每代进化流程：
1. 运行基线对局
2. **按角色表现排序选择优化目标**：从数据库查询各角色平均表现，按评分升序排列，返回所有角色对应的 Agent 进行优化（优先优化表现差的角色）
3. 对每个角色的 Agent 执行策略优化（LLM 生成新 strategy_notes）
4. LLM 自审新策略
5. 用新策略运行对局，按角色注入 profile（解决 agent_id 随机分配的匹配问题）
6. 指标防护检查 → 接受/拒绝/回退到上一版本

### 人机混战

通过 `human_seats` 参数指定人类玩家座位：
```json
POST /api/game/start
{
  "player_count": 9,
  "werewolf_count": 3,
  "use_mock": true,
  "human_seats": [1, 2]
}
```

轮到人类玩家时，WebSocket 广播 `human_turn` 事件，前端显示操作界面，提交后通过 `/api/game/{id}/action` 发送。

### 局后反思

每局结束后自动触发 `GameMaster.post_game_reflection()`：
- 各 Agent 基于完整对局日志生成反思总结
- 反思内容可影响后续策略调整
- 失败时仅打印日志，不中断主流程

### 静态文件服务

FastAPI 启动时自动检测 `frontend/dist/` 目录，若存在则挂载到根路径 `/`，实现前后端一体化部署：
```python
app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.11+, FastAPI, Pydantic v2, asyncio |
| Agent 框架 | 自研轻量框架（BaseAgent → RoleAgent → GameMaster） |
| LLM | OpenAI SDK + Mock 客户端 |
| 记忆 | 内存级 ConversationBuffer |
| 数据库 | PostgreSQL + SQLAlchemy 2.0 async ORM + Alembic 迁移 |
| 评测 | structlog JSON Lines + 规则-based 过程指标 + 可选 LLM Judge |
| 前端 | React 18 + TypeScript + Tailwind CSS + Vite + Recharts |
| 实时通信 | WebSocket（FastAPI 原生，含心跳） |
| 部署 | Docker + Docker Compose + Nginx |
| 代码质量 | black, ruff, mypy, pytest, pytest-asyncio, pytest-cov |

## 依赖清单

核心依赖（见 `backend/pyproject.toml`）：
- `fastapi`, `uvicorn[standard]`, `pydantic`
- `openai`, `httpx`
- `structlog`, `python-dotenv`
- `transitions`
- `sqlalchemy[asyncio]`, `asyncpg`, `alembic`
- `pandas`, `numpy`, `plotly`

开发依赖：
- `pytest`, `pytest-asyncio`, `pytest-cov`
- `black`, `ruff`, `mypy`

## 下一步

- [ ] 更复杂的角色板子（守卫、白痴、丘比特等）
- [ ] 更精细的过程评测（默认启用 LLM-as-a-Judge 发言质量评分）
- [ ] 前端实时观战支持人类玩家操作
- [ ] 补充单元测试覆盖（Agent 层、评测指标、进化循环、API 路由）
- [ ] 生产环境 Redis 替代内存级 `active_games`
