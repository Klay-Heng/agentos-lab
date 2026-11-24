# AgentOS

AgentOS 是围绕现有 Agent 工作流框架补充任务管理、恢复和工具治理等能力的轻量级运行时项目。正式项目定位与阶段安排见 [项目计划书](docs/00-project-plan.md)。

**当前已完成阶段 1 的 P1-01 至 P1-04，任务 HTTP API 尚待 P1-05。** 已实现共享模型、SQLite Task 存储、最小 LangGraph 工作流与 Checkpointer、同步 Runtime 和应用资源装配；现有 HTTP 接口仍只有健康检查。尚未实现 interrupt/resume、Governance/审批、Scheduler、Memory/去重、审计存储、论文简报工作流、真实 LLM、邮件和 Dashboard。

Runtime 采用同步调用，通过 `create_and_run` 执行 `CREATED → RUNNING → SUCCEEDED/FAILED`，通过 `get_task` 只读查询。工作流失败保存安全错误摘要；存储失败直接抛出 `TaskStorageError`，保留最后已提交状态。业务数据库与 Checkpoint 分开保存，两者没有跨库原子事务。重启后可查询旧任务，不自动重跑 CREATED/RUNNING 任务，也不承诺崩溃续跑。分工和交接约定见 [阶段 1 任务书](docs/01-phase1-tasks.md)。

## 环境与安装

使用 Python **3.12** 和 [uv](https://docs.astral.sh/uv/getting-started/installation/)；本项目通过 `.python-version` 与 `requires-python` 统一使用 3.12 系列。以下命令均在项目根目录执行，无需手动激活虚拟环境。

```powershell
uv python install 3.12
uv sync --locked --dev
```

`uv.lock` 锁定依赖，提交仓库；`.venv` 是本地环境，不提交。开发依赖包含 pytest、httpx 和 Ruff。运行依赖包含 FastAPI、Uvicorn、Pydantic、Pydantic Settings，以及阶段 1 使用的 LangGraph 和 SQLite Checkpointer；仅安装依赖不代表已接入业务能力。

本机验证使用 Python 3.12.15、uv 0.13.1。此 Windows 环境中，`uv python install 3.12` 下载了解释器，但创建 minor-version 快捷链接时提示 `Missing expected target directory`；随后 `uv sync --locked --dev` 能找到实际解释器并成功安装，测试与服务启动均通过。如遇相同提示，先执行同步命令确认实际解释器是否可用；若同步仍失败，可自行安装 Python 3.12 后重试。该提示属于本机安装环境限制。

可选：复制默认配置（PowerShell）：

```powershell
Copy-Item .env.example .env
```

macOS/Linux 使用 `cp .env.example .env`。不创建 `.env` 也可直接启动。

| 环境变量 | 默认值 | 用途 |
| --- | --- | --- |
| `AGENTOS_APP_NAME` | `AgentOS` | 应用名称 |
| `AGENTOS_ENVIRONMENT` | `development` | 运行环境标识 |
| `AGENTOS_LOG_LEVEL` | `INFO` | DEBUG/INFO/WARNING/ERROR/CRITICAL |
| `AGENTOS_TASK_DATABASE_PATH` | `data/tasks.sqlite3` | Task 业务数据库 |
| `AGENTOS_CHECKPOINT_DATABASE_PATH` | `data/checkpoints.sqlite3` | LangGraph Checkpoint 数据库 |

配置从当前工作目录的 `.env` 读取，进程环境变量优先。`.env` 不提交，示例文件不包含密钥。基础日志输出到标准错误；普通日志不代表业务审计能力。

数据库路径在读取 Settings 时解析为绝对路径，两个文件必须不同。应用启动时自动建目录、初始化两库并将 Runtime 放在 `app.state.runtime`；关闭或启动失败时释放 Checkpointer，关闭后移除 Runtime 引用。Task Repository 每次操作独立打开、关闭连接，Runtime 不持有跨图执行的数据库事务。

## 启动 API

```powershell
uv run --locked uvicorn agentos.main:create_app --factory --reload --host 127.0.0.1 --port 8000
```

访问健康检查：<http://127.0.0.1:8000/api/v1/health>。默认配置返回：

```json
{"status":"ok","app_name":"AgentOS","environment":"development"}
```

该接口仅表示 API 进程存活，不表示尚未实现的 AgentOS 模块已就绪。交互式 API 文档位于 <http://127.0.0.1:8000/docs>。`--reload` 用于本地开发。

## 测试与代码规范

```powershell
uv run --locked pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
```

需要自动格式化时运行 `uv run --locked ruff format .`。测试覆盖模型、存储、图与 Adapter、Runtime 状态和故障分类、lifespan 资源关闭、重启读取、测试数据隔离及健康检查。测试只使用临时库，并实际进入 lifespan；不访问开发数据库。GitHub Actions 在 push 和 pull_request 时运行相同的安装、lint、格式和测试命令。

## 代码结构

```text
agentos/
  __init__.py
  main.py                 # create_app 应用工厂
  models.py               # 阶段 1 共享模型与请求响应
  contracts.py            # 同步接口与异常契约
  api/
    __init__.py
    health.py             # 健康检查路由与响应模型
  core/
    __init__.py
    config.py             # 统一配置
    logging.py            # 日志初始化
  storage/tasks.py        # 按操作管理连接的 Task Repository
  workflows/demo.py       # 确定性 echo 图
  adapters/langgraph.py   # 同步图执行适配器
  runtime/service.py      # Task 状态、执行与查询
tests/                    # 单元、资源生命周期与真实组件集成测试
docs/00-project-plan.md   # 项目计划书
.github/workflows/ci.yml
.env.example
.gitignore
.python-version
pyproject.toml
uv.lock
README.md
```

当前工程独立构建，没有预建后续业务空包。后续依照正式计划书逐阶段添加能力和依赖。
