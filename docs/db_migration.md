# WireWolf 数据库迁移指南：SQLite → PostgreSQL

## 变更概览

已将底层数据库从原生 `sqlite3` 迁移至 **SQLAlchemy 2.0 + 异步驱动**，支持：
- **PostgreSQL**（生产推荐）：`postgresql+asyncpg://...`
- **SQLite**（开发/本地）：`sqlite+aiosqlite:///...`

切换方式：仅修改环境变量 `DATABASE_URL`，**零代码改动**。

## 文件变更清单

### 新增
```
backend/app/db/
├── __init__.py
├── base.py          # Engine + AsyncSession + Base
├── models.py        # SQLAlchemy ORM 模型（Game / PlayerStat / AgentProfileModel）
└── database.py      # AsyncLeaderboardDB（异步数据库访问层）

backend/alembic/
├── env.py           # Alembic 异步迁移环境
├── script.py.mako   # 迁移脚本模板
├── versions/
│   └── 001_init_tables.py   # 初始建表迁移
└── alembic.ini      # Alembic 配置（位于 backend/alembic.ini）

backend/.env.example         # 增加 DATABASE_URL 示例
docs/db_migration.md         # 本文档
```

### 重写
```
backend/app/evaluation/leaderboard.py   # 改为 AsyncLeaderboardDB 的兼容包装
```

### 修改（调用方加 await）
```
backend/app/api/routes.py               # 移除直接 sqlite3 查询，全部 await
backend/app/batch/runner.py             # db.xxx() → await db.xxx()
backend/app/evolution/loop.py           # 移除直接 sqlite3，全部 await
backend/app/evolution/optimizer.py      # 移除直接 sqlite3，全部 await
backend/pyproject.toml                  # +sqlalchemy, +asyncpg, +aiosqlite, +alembic
backend/docker-compose.yml              # +postgres 服务
```

## 快速开始

### 1. 安装新依赖

```bash
cd backend

# 若使用 venv
python -m pip install -e ".[dev]"

# 或仅安装新增依赖
pip install sqlalchemy[asyncio] asyncpg aiosqlite alembic
```

### 2. 本地开发（SQLite，零配置）

```bash
# 默认即 SQLite，无需修改任何配置
cd backend
python -m uvicorn app.main:app --reload
```

### 3. 使用 PostgreSQL（Docker 一键启动）

```bash
# 1. 确保 .env 中 DATABASE_URL 指向 PostgreSQL
#    （docker-compose 已自动注入，无需手动改）

# 2. 启动
docker-compose up --build

# 3. 运行迁移（首次启动后，进入 backend 容器执行）
docker-compose exec backend alembic upgrade head
```

### 4. 手动连接 PostgreSQL

```bash
# 创建本地数据库
createdb wirewolf

# 设置环境变量并启动
export DATABASE_URL="postgresql+asyncpg://user:password@localhost:5432/wirewolf"
cd backend
alembic upgrade head        # 建表
python -m uvicorn app.main:app --reload
```

## 双后端切换说明

| 场景 | DATABASE_URL 示例 |
|------|-------------------|
| 本地开发（SQLite） | `sqlite+aiosqlite:///./leaderboard.db` |
| Docker Compose（PG） | `postgresql+asyncpg://wirewolf:wirewolf@db:5432/wirewolf` |
| 生产环境（PG） | `postgresql+asyncpg://user:pass@host:5432/dbname` |

> **注意**：`LEADERBOARD_DB` 环境变量已废弃，但向后兼容——未设置 `DATABASE_URL` 时，旧版 `LEADERBOARD_DB` 仍会被映射为 `sqlite+aiosqlite://` URL。

## Alembic 迁移命令

```bash
cd backend

# 首次建表
alembic upgrade head

# 生成新迁移（修改 models.py 后）
alembic revision --autogenerate -m "add strategy_cards table"

# 升级
alembic upgrade +1

# 回滚
alembic downgrade -1
```

## 数据迁移（旧 SQLite → 新 PostgreSQL）

若已有 `leaderboard.db` 数据需要导入 PostgreSQL：

```bash
# 方法 1：pgloader（推荐）
pgloader sqlite:///path/to/leaderboard.db postgresql://user:pass@localhost/wirewolf

# 方法 2：Python 脚本导出 JSON 后导入
python scripts/migrate_sqlite_to_pg.py
```

> 若继续使用 SQLite 后端，则**无需任何数据迁移**，原 `leaderboard.db` 文件直接可用。

## 常见问题和回滚

### Q: 新代码报错 `ModuleNotFoundError: No module named 'sqlalchemy'`
A: 安装依赖：`pip install sqlalchemy[asyncio] asyncpg aiosqlite`

### Q: 想暂时回滚到旧版 sqlite3 代码？
A: 本项目保留 `LeaderboardDB` 类名和主要方法签名，但内部已改为 async。若必须回滚，从 Git 回退以下文件即可：
- `backend/app/evaluation/leaderboard.py`（旧版）
- `backend/app/api/routes.py`、`batch/runner.py`、`evolution/loop.py`、`evolution/optimizer.py`（去掉 await）

### Q: SQLite 下是否需要启动 PostgreSQL？
A: **不需要**。`docker-compose.yml` 中添加了 `depends_on: db`，若你想纯 SQLite 运行，临时注释掉 backend 的 `depends_on` 和 `db` 服务即可。

## 下一步（可选优化）

- [ ] 在 `app/main.py` 中添加 FastAPI lifespan，在启动时 `await db.init_db()` 和 `alembic upgrade head`
- [ ] 为 `PlayerStat` 等表增加更多索引（如 `(game_id, agent_id)` 联合索引）
- [ ] 使用 `pgvector` 扩展支持 Phase 5 的向量检索
