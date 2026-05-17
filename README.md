# 🐺 WireWolf — 狼人杀多 Agent 协作系统

> 让 LLM Agent 在狼人杀中自我博弈、自我反思、自我进化。

## 愿景

构建一个**多 Agent 自进化平台**：
- **方向①**：通用 Agent 基座，具备"读懂自己 → 修改自己 → 运行自己"的能力
- **方向②**：评测+复盘体系，量化 Agent 表现，产出可解释的 Leaderboard
- **方向③**：自进化闭环，批量对局 → 评测归因 → 策略优化 → 再对局

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 / Agent 引擎 | Python 3.11+, FastAPI, Pydantic v2, asyncio |
| 多 Agent 框架 | 自研轻量框架（BaseAgent → RoleAgent → GameMaster） |
| LLM 接入 | OpenAI SDK + 统一路由 |
| 记忆 | 内存级 ConversationBuffer |
| 前端 | React 18 + TypeScript + Vite |
| 日志 | structlog → JSON Lines |

## 快速开始

```bash
# 克隆仓库
git clone <repo>
cd wirewolf

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入 LLM_API_KEY

# 运行一局命令行对局（Mock LLM，无需 API Key）
cd backend
python3 run_cli.py --players 9 --wolves 3

# 运行测试
python3 tests/test_game.py
python3 tests/test_rules.py

# 启动 FastAPI
python3 -m app.main
```

## 架构

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   批量对局   │────▶│   评测归因   │────▶│   策略优化   │
│  (n局自对弈) │     │ (LLM-as-Judge)│    │ (修改Profile)│
└─────────────┘     └─────────────┘     └──────┬──────┘
       ▲                                       │
       └───────────────────────────────────────┘
                        (用新策略再对局)
```

## 角色

- **狼人** (Werewolf): 夜间杀人，白天伪装
- **预言家** (Seer): 夜间查验身份
- **女巫** (Witch): 一瓶解药 + 一瓶毒药
- **猎人** (Hunter): 被放逐可开枪
- **平民** (Villager): 无特殊技能

## 开发计划

参见 [docs/design.md](docs/design.md)

## License

MIT
