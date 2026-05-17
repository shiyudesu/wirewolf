# 🐺 WireWolf — 狼人杀多 Agent 自进化平台

> 让 LLM Agent 在狼人杀中自我博弈、自我反思、自我进化。

**WireWolf** 是一个多 Agent 协作系统，核心目标是让 LLM-driven Agent 具备"**读懂自己 → 修改自己 → 运行自己**"的自演化能力。系统在完整的狼人杀对局中运行多个 LLM Agent，通过批量对局、评测归因、策略优化形成闭环进化。

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=white)](https://react.dev/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## ✨ 核心特性

- 🎮 **12人标准局完整对局循环** — 支持 9/12 人经典板子
- 🧠 **角色特化推理逻辑** — 狼人/预言家/女巫/猎人/平民，各角色拥有独立的策略提示与行为模式
- 🤝 **狼人夜间协商机制** — 多狼时执行两轮协商（收集提议 → 分歧时投票决策）
- 🧪 **Mock LLM 快速测试** — 无需 API Key 即可运行完整对局，方便开发调试
- 🤖 **真实 LLM 接入** — 支持 GPT-4o / Claude-3 等 OpenAI 兼容接口
- 📊 **结构化日志 + 复盘报告** — JSON Lines 格式，含完整 reasoning 与协商记录
- 🏆 **多维度评测体系** — 结果指标 + 规则-based 过程指标（发言质量、投票一致性、信息利用度）+ 可选 LLM-as-a-Judge
- 📈 **Leaderboard 排行榜** — PostgreSQL 持久化，支持按角色/胜率/评测分/模型排名
- 🔄 **自进化闭环** — 批量对局 → 按角色表现排序优化 → 退化防护 → 再对局
- 👁️ **WebSocket 实时观战** — 前端实时同步对局状态，含心跳保活
- 🧑‍🤝‍🧑 **人机混战** — 支持人类玩家通过前端参与对局
- 💭 **局后反思** — 每局结束后 Agent 自动生成对局总结，反哺策略迭代

## 🏗️ 技术栈

| 层级 | 技术 |
|------|------|
| 后端 / Agent 引擎 | Python 3.11+, FastAPI, Pydantic v2, asyncio |
| 多 Agent 框架 | 自研轻量框架（BaseAgent → RoleAgent → GameMaster） |
| LLM 接入 | OpenAI SDK + Mock 客户端 |
| 记忆 | 内存级 ConversationBuffer |
| 数据库 | PostgreSQL + SQLAlchemy 2.0 async ORM + Alembic 迁移 |
| 前端 | React 18 + TypeScript + Tailwind CSS + Vite + Recharts |
| 实时通信 | WebSocket（FastAPI 原生，含 ping/pong 心跳） |
| 部署 | Docker + Docker Compose + Nginx |

## 🚀 快速开始

### 方式一：Docker 一键启动（推荐）

```bash
# 1. 克隆仓库
git clone <repo-url>
cd wirewolf

# 2. 配置环境变量
cp backend/.env.example backend/.env
# 编辑 backend/.env 填入 LLM_API_KEY（可选，使用 Mock 模式可不填）

# 3. 启动全部服务
docker-compose up --build

# 4. 访问 http://localhost/
```

### 方式二：本地开发

**后端一键启动**（自动检测 PostgreSQL、执行迁移、启动服务）：

```bash
cd wirewolf

# 首次启动前：安装依赖并初始化
# cd backend && pip install -e ".[dev]" && cd ..

./start_backend_pg.sh
```

脚本会自动：启动 PostgreSQL（若未运行）→ 执行 `alembic upgrade head` → 启动 FastAPI 服务。

**前端编译**（另一个终端）：

```bash
cd wirewolf/frontend
npm install
npm run build
# 访问 http://localhost:8000/
```

> FastAPI 启动后会自动挂载 `frontend/dist/`，前后端一体化访问。

**手动配置（如需自定义）**：

```bash
cd wirewolf/backend

# 虚拟环境 + 依赖
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 环境变量
cp .env.example .env
# 编辑 .env 填入 LLM_API_KEY、DATABASE_URL 等

# 数据库迁移
alembic upgrade head

# 启动
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

> 后端启动时会自动检测 `frontend/dist/` 目录并挂载到根路径 `/`，实现前后端一体化访问。

### 运行一局命令行对局（Mock LLM，无需 API Key）

```bash
cd backend
python3 run_cli.py --players 9 --wolves 3
```

### 运行测试

```bash
cd backend
python3 -m pytest tests/ -v
```

## 📁 项目结构

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
│   │   │   ├── base.py          # BaseAgent（通用 Agent 基类）
│   │   │   ├── memory.py        # 记忆管理
│   │   │   └── roles/           # 角色特化（5 个角色）
│   │   ├── llm/                 # LLM 统一接入
│   │   ├── models/              # Pydantic 数据模型
│   │   ├── evaluation/          # 评测体系
│   │   ├── evolution/           # 自进化模块
│   │   ├── batch/               # 批量对局
│   │   ├── websocket/           # WebSocket 观战
│   │   └── utils/               # 工具函数
│   ├── alembic/                 # 数据库迁移
│   ├── tests/                   # 测试
│   ├── run_cli.py               # 命令行运行一局
│   ├── run_batch.py             # 批量对局入口
│   ├── evaluate.py              # 评测流水线入口
│   ├── run_evolution.py         # 自进化循环入口
│   ├── pyproject.toml           # 依赖与工具配置
│   ├── Dockerfile               # 后端 Docker
│   └── .env.example             # 环境变量模板
├── frontend/                    # React 18 + TypeScript + Tailwind
│   ├── src/
│   │   ├── pages/               # 页面组件（大厅/对局列表/复盘/排行榜/进化追踪/实时观战）
│   │   ├── components/          # 布局组件
│   │   └── assets/              # 静态资源
│   └── dist/                    # 构建产物（FastAPI 自动挂载）
├── configs/                     # 游戏配置 JSON
├── logs/games/                  # 对局日志（JSON Lines）
├── docs/                        # 设计文档
├── docker-compose.yml           # 一键启动
├── Dockerfile.backend           # 后端镜像
├── Dockerfile.frontend          # 前端镜像
├── nginx.conf                   # Nginx 配置
└── LICENSE                      # MIT License
```

## 🌐 API 概览

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/health` | GET | 健康检查 |
| `/api/config` | GET | 获取服务端公开配置（llm_model、llm_base_url） |
| `/api/leaderboard` | GET | 排行榜（支持 `?role=`、`?model_name=`、`?limit=` 过滤） |
| `/api/games` | GET | 对局列表（`?limit=`，默认 50） |
| `/api/games/{id}` | GET | 单局详情 |
| `/api/games/{id}/report` | GET | 复盘报告 |
| `/api/games/{id}/metrics` | GET | 评测指标 |
| `/api/batch/run` | POST | 启动批量对局（支持 `seer_count`、`witch_count`、`hunter_count`、`model` 等） |
| `/api/batch/status` | GET | 批量对局状态 |
| `/api/game/start` | POST | 创建对局（支持 `human_seats`、`model` 等字段） |
| `/api/game/{id}/action` | POST | 人类玩家提交操作 |
| `/api/evolution/{agent_id}` | GET | Agent 进化历史 |
| `/ws/watch/{game_id}` | WS | 观战 WebSocket（支持 `ping`/`pong` 心跳） |

## 🧠 核心设计亮点

### 信息隔离

GameMaster 严格隔离信息，模拟真实狼人杀的信息不对称：
- 狼人知道队友身份
- 预言家只知道自己的查验结果
- 女巫只知道夜间刀口
- 平民只知道公共发言和投票

### 狼人夜间协商

多狼时不再"取第一个狼人的选择"，而是执行两轮协商：
1. **收集提议**：每个存活狼人独立提出击杀目标 + 理由
2. **投票决策**：若意见不一致，广播队友提议后重新投票，多数胜出（平票随机）

### 角色特化推理

| 角色 | 夜间策略 | 白天策略 |
|------|----------|----------|
| 狼人 | 优先刀神职（预言家>女巫>猎人），避免刀猎人 | 模仿好人逻辑，适当攻击队友做身份 |
| 预言家 | 优先验可疑玩家，避免连续验同一人 | 有狼人悍跳时必须对跳，报查验给出清晰逻辑链 |
| 女巫 | 预言家/自身/确认好人优先救；毒药宁晚开不盲毒 | 隐藏身份，通过"银水"信息侧面帮助好人 |
| 猎人 | 无夜间行动 | 隐藏身份，被放逐时优先带走确定狼人 |
| 平民 | 整理信息，分析可疑玩家 | 观察发言矛盾，不盲目跟票 |

### 自进化闭环

```
批量对局  ──▶  评测归因  ──▶  策略优化
    ▲                          │
    └──────────────────────────┘
         (用新策略再对局)
```

- **按角色表现排序优化**：每代从数据库查询各角色平均表现，优先优化评分低的角色
- **退化防护**：指标对比 + LLM 自审 + 回退到上一版本
- **版本追踪**：`AgentProfile.strategy_notes` 每次修改 `version += 1`，旧版本保留用于对比

### 静态文件一体化

FastAPI 启动时自动检测 `frontend/dist/` 目录，若存在则挂载到根路径 `/`，无需 Nginx 即可实现前后端一体化部署。生产环境仍推荐使用 Nginx 做反向代理和静态文件缓存。

## 🗺️ 开发计划

参见 [docs/design.md](docs/design.md)

- [ ] 更复杂的角色板子（守卫、白痴、丘比特等）
- [ ] 默认启用 LLM-as-a-Judge 发言质量评分
- [ ] 前端实时观战支持人类玩家操作
- [ ] 补充单元测试覆盖（Agent 层、评测指标、进化循环、API 路由）
- [ ] 生产环境 Redis 替代内存级 `active_games`

## 📄 License

[MIT](LICENSE)
