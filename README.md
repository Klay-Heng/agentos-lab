# AgentOS

AgentOS 是围绕现有 Agent 工作流框架补充任务管理、恢复和工具治理等能力的轻量级运行时项目。正式项目定位与阶段安排见 [项目计划书](docs/00-project-plan.md)。

**当前 API 仍为基础服务骨架，阶段 1 正在推进。** 已实现应用工厂、配置、日志和健康检查，附带测试与 CI。尚未实现 Runtime/Task 生命周期、业务工作流与 Checkpointer 接入、interrupt/resume、Governance/审批、Scheduler、Memory/去重、审计存储、论文简报工作流、真实 LLM、邮件和 Dashboard。

阶段 1 的 P1-01 已补充共享 Task 模型、请求/响应校验与 Repository/Adapter/Runtime 接口，并安装 LangGraph、SQLite Checkpointer，完成依赖兼容性测试。实际业务存储、图适配器、Runtime 和任务 API 尚待后续任务实现；分工和交接约定见 [阶段 1 任务书](docs/01-phase1-tasks.md)。

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

配置从当前工作目录的 `.env` 读取，进程环境变量优先。`.env` 不提交，示例文件不包含密钥。基础日志输出到标准错误；普通日志不代表业务审计能力。

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

需要自动格式化时运行 `uv run --locked ruff format .`。测试验证健康检查状态码、JSON 响应结构，以及环境变量和 `.env` 配置优先级。GitHub Actions 在 push 和 pull_request 时运行相同的安装、lint、格式和测试命令。

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
tests/test_health.py
tests/test_task_models.py
tests/test_langgraph_dependencies.py
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
