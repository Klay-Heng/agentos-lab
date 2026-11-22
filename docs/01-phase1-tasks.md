# AgentOS 阶段 1 任务与分工

本阶段完成 Runtime 最小执行闭环：通过 API 创建 Task，由 Runtime 调用真实的最小 LangGraph 工作流，保存任务状态、执行结果和 Checkpoint，再通过 API 查询。依赖安装完成后，整个演示不需要外网、模型密钥或邮件账号。

本任务书用于四人小组内部发布和协作，依据 [项目计划书](00-project-plan.md) 第 5、8、9 节。A–D 沿用计划书的成员代号，发布时替换为实际姓名。下述接口与执行方式是本阶段的默认实施约定；若联调发现需要调整，由 A 更新本文件并同步受影响成员。

## 1 阶段目标与边界

### 当前起点

仓库已有 Python 3.12、uv 依赖管理、FastAPI 应用工厂、配置与日志、`GET /api/v1/health`、健康检查测试、Ruff 和基础 CI。本阶段在这些代码上增量开发，不重建工程，不删除已有测试。

### 必须交付

1. Task 数据模型与 SQLite Repository，分别持久化 `task_id` 和 `thread_id`。
2. Runtime 管理任务创建、执行、状态更新、结果和错误保存。
3. LangGraph Adapter 与一个确定性的最小 StateGraph，接入 SQLite Checkpointer。
4. `POST /api/v1/tasks` 和 `GET /api/v1/tasks/{task_id}`。
5. 成功、失败、非法输入、任务不存在、持久化等测试，以及 README 中的可执行演示步骤。

### 留到后续阶段

不实现 interrupt/resume、Approval、工具治理策略、取消接口、任务重试、Scheduler、业务去重、论文简报工作流、真实 LLM、邮件或 Dashboard；也不建立这些模块的空包。审计事件存储与查询留到后续阶段，本阶段只补充关联任务 ID 的普通日志。

**Checkpoint 落盘不等于服务重启后自动恢复执行。** 本阶段只要求任务记录与已保存的图状态可重新读取，不承诺崩溃续跑，不发布 `/resume` 接口。

## 2 四人分工

| 成员 | 本阶段主责 | 任务编号 | 主要交接对象 |
| --- | --- | --- | --- |
| A 项目负责人 | 接口收敛、Runtime、资源装配、依赖集成与最终合并 | P1-01、P1-04、P1-06 | 向 B/C/D 提供统一模型与调用约定 |
| B 存储负责人 | Task SQLite Repository、初始化、事务与持久化测试 | P1-02 | 向 A/D 提供任务读写能力，与 C 对齐存储路径 |
| C 执行适配负责人 | 最小 LangGraph 工作流、Adapter、SQLite Checkpointer | P1-03 | 向 A 提供执行接口，与 D 对齐失败测试方式 |
| D API 与测试负责人 | 任务 API、接口测试、端到端验证、README 演示说明 | P1-05、P1-06 | 使用 A 的 Runtime，验证 B/C 的真实实现 |

B、C 在本阶段承担支撑最小闭环的实现工作；长期的 Scheduler/Memory、Governance 主责不变。每人负责自己实现的单元测试，D 负责跨模块集成测试，不包办所有测试。

## 3 共同实施约定

### 执行方式与状态

默认采用**请求内同步完成执行**：创建接口等待最小图结束后返回任务详情。这里指请求等待结果，不强制所有 Python 方法都写成同步函数；数据库、Checkpointer 与 Adapter 的调用方式须保持兼容，阻塞调用不能直接阻塞异步事件循环。

本阶段仅实现以下转换，并集中在 Runtime 校验：

```text
CREATED -> RUNNING -> SUCCEEDED
                  -> FAILED
```

本阶段没有后台队列，因此不实现 `QUEUED`；计划书中的排队、审批等待和取消状态随对应执行机制后续加入。终态不能重新转为 RUNNING。暂不增加 Worker、后台线程池队列或消息中间件，也不把进程内后台任务描述为可靠调度。

步骤顺序为：校验输入 → 保存 CREATED → 保存 RUNNING → 调用 Adapter → 保存 SUCCEEDED 或 FAILED。各次状态保存应提交事务；不要持有 Task 数据库写事务等待图执行结束。查询接口只读记录，不触发执行。

### 模型与持久化

| 字段 | 本阶段约定 |
| --- | --- |
| `task_id` | 服务端生成的 UUID 字符串，Task 主键 |
| `thread_id` | 独立生成的 UUID 字符串，关联 LangGraph 执行上下文；不可直接复用 task_id |
| `task_type` | 本阶段只支持 `demo_echo` |
| `status` | CREATED、RUNNING、SUCCEEDED、FAILED |
| `input` | JSON 对象，至少包含 `text` |
| `result` | 成功时为 JSON 对象，其他情况为 null |
| `error` | 失败时为包含 `code`、`message` 的对象，其他情况为 null |
| `created_at`、`updated_at` | 带时区的 UTC 时间，API 使用 ISO 8601 字符串 |

业务 Task 与 LangGraph Checkpoint 使用两个独立 SQLite 文件，默认可放在 `data/tasks.sqlite3`、`data/checkpoints.sqlite3`；通过统一 Settings 配置路径。父目录按需创建，数据库文件不入库。测试使用临时目录，不能访问开发数据库。

Task 存储默认使用标准库 `sqlite3`，无需提前引入 ORM、迁移框架或通用存储抽象。Checkpoint 交给 LangGraph 的 SQLite Checkpointer 管理，不自行创建或解析其内部表。两库不承诺跨库原子事务。

### 模块调用与交接

以下名称用于统一交接，可在 P1-01 中细化类型，但不应由各成员分别发明另一套契约。

| 提供方 | 提供的能力 | 调用方 |
| --- | --- | --- |
| B Repository | `TaskRepository.create(task) -> Task`、`get(task_id) -> Task \| None`、`update_state(...) -> Task` | A Runtime |
| C Adapter | `WorkflowAdapter.execute(task_type, input_data, thread_id) -> TaskResult` | A Runtime |
| A Runtime | `TaskRuntime.create_and_run(request) -> TaskResponse`、`get_task(task_id) -> TaskResponse` | D API |

Task 模型和请求/响应模型由 P1-01 先落地，放在同一个明确的模型模块中，不重复定义。LangGraph 的导入和框架配置集中在 Adapter/工作流模块，API 不接触图对象或 Checkpointer。模型、存储和 Adapter 均不直接操作 FastAPI 请求。

### P1-01 已落地的交接接口

共享模型位于 `agentos/models.py`，类型接口与异常位于 `agentos/contracts.py`。B/C/D 应直接导入使用，不另建同名模型。Protocol 用于结构化类型约束和测试替身，不是业务实现，也不要求具体类继承它。

- `CreateTaskRequest` 包含必填的 `task_type`、`input: TaskInput`，两层均禁止额外字段，拒绝客户端传入 task_id、status 或故障开关。文本必须是字符串，去除首尾空白后校验 1–2000 字符。
- `Task` 是不可变的完整快照，`TaskResponse` 为其别名；ID 在 Python 内使用 UUID，JSON 中输出字符串。时间必须带时区，统一转换为 UTC；更新时间不能早于创建时间，两个 ID 不能相同。
- `TaskResult` 为 `{text: str}`，`TaskError` 包含固定的 `WORKFLOW_EXECUTION_FAILED` 错误码与安全摘要。SUCCEEDED 必须有结果且无错误，FAILED 必须有错误且无结果，CREATED/RUNNING 两者均为空。
- 状态变化由后续 Runtime 校验，并重新构造完整、经过校验的 Task；不要用 `model_copy(update=...)` 绕过校验。P1-01 仅校验快照一致性，没有提前实现状态机。

**调用方式：所有 Protocol 方法均为同步 `def`。** D 后续使用 FastAPI 同步路由，并通过依赖函数获取 `TaskRuntime`；如改用异步路由，应将一次完整 Runtime 调用卸载到线程中，不能在事件循环内直接执行阻塞数据库/图调用。

B 的 `update_state` 签名为 `update_state(task_id, *, expected_status, status, updated_at, result=None, error=None) -> Task`。必须以 expected_status 做原子条件更新，更新成功后提交并返回新快照，保留 ID、input、task_type、created_at。记录不存在抛 `TaskNotFoundError`，预期状态不匹配抛 `TaskStateConflictError`，其他数据库失败抛 `TaskStorageError`。Repository 只检查条件写入和快照合法性，合法状态转换规则仍由 Runtime 决定。

Repository 的 `get` 无记录返回 None；Runtime 的 `get_task` 将其转换为 `TaskNotFoundError`。API 将该异常映射为 404，将 `TaskStorageError`（含其子类 TaskStateConflictError）映射为 503。创建接口的字段错误由请求模型校验为 422。Runtime 捕获普通节点异常，持久化 FAILED 后返回任务；捕获 `TaskStorageError` 时继续向外抛出，不伪装为普通工作流失败。

**资源归属：** 后续 A 的具体 Runtime 构造函数接收 Repository、Adapter 两个依赖，API 通过可覆盖的依赖函数获取 Runtime。B 的 sqlite3 连接按操作创建并关闭，建表在应用启动时完成，避免跨线程共享默认连接。C 使用同步 `SqliteSaver.from_conn_string` 的上下文管理器；A 在 lifespan 中借助 ExitStack 持有它，交给 Adapter 使用，关闭时统一释放。Adapter 不自行关闭共享 Checkpointer，将 UUID 转为字符串后传入图配置。Checkpoint 存储失败转换为 `TaskStorageError`，普通节点异常保持原异常传播。

测试时向具体 Runtime 注入实现相同方法的 Repository/Adapter 替身；API 测试覆盖获取 Runtime 的依赖函数。资源持有者负责关闭资源，Runtime 与 API 不重复关闭；P1-04/P1-05 再落地装配与依赖函数，本任务不新增空实现。

依赖按 [LangGraph 包说明](https://pypi.org/project/langgraph/) 和 [SqliteSaver 官方接口](https://reference.langchain.com/python/langgraph.checkpoint.sqlite/SqliteSaver/from_conn_string) 核对。P1-01 新增依赖兼容性测试，仅在临时库中验证同步图调用、跨调用线程访问及关闭后读取 Checkpoint；它不替代 P1-03 的真实 Adapter 与工作流测试。具体安装版本以 `uv.lock` 为准。

### API 契约

**创建任务：** `POST /api/v1/tasks`

```json
{
  "task_type": "demo_echo",
  "input": {"text": "hello AgentOS"}
}
```

`text` 去除首尾空白后不能为空，长度上限 2000 字符。不支持的 `task_type`、缺失字段或非法输入返回 422，且不创建 Task。

任务及最终执行状态保存成功后返回 **201** 和任务详情。成功响应示意如下，ID 和时间使用运行时实际值：

```json
{
  "task_id": "0c7e30b7-245b-4ba1-8bc4-183589c6a16d",
  "thread_id": "8528cba9-eb90-46ad-aae4-bce335df92d8",
  "task_type": "demo_echo",
  "status": "SUCCEEDED",
  "input": {"text": "hello AgentOS"},
  "result": {"text": "hello AgentOS"},
  "error": null,
  "created_at": "2026-11-22T01:00:00Z",
  "updated_at": "2026-11-22T01:00:01Z"
}
```

图执行异常且 FAILED 已成功保存时，同样返回 201，`status` 为 FAILED、`result` 为 null、`error.code` 为 `WORKFLOW_EXECUTION_FAILED`。HTTP 创建成功与任务执行成功分别表达；`error.message` 只返回安全摘要，完整异常堆栈记录在服务端日志。

存储不可用、状态更新无法提交等基础设施故障返回 503，不伪装成成功创建或已保存 FAILED；不能保证此时未留下中间记录。本阶段不自动重放这些记录，重启后可查询已提交状态。

**查询任务：** `GET /api/v1/tasks/{task_id}` 返回 **200** 和相同结构的任务详情；合法 UUID 无对应记录返回 **404**，UUID 格式错误返回 **422**。读取数据库失败返回 **503**。

多次 POST 默认创建多个独立 Task，本阶段不提供业务去重或幂等保证。

## 4 开发任务

### P1-01 统一模型和接口

- **负责人：A；评审：B、C、D。依赖：无。**
- 落地 Task 状态、Task 数据模型、创建请求及响应模型，落实上一节的异常与调用约定。
- 明确 Repository 和 Adapter 方法的同步/异步形式、资源持有方式及可注入测试入口，避免联调时再更换调用方式。
- C 核对所需 LangGraph 与 SQLite Checkpointer 的官方接口和 Python 3.12 兼容性；A 统一修改 `pyproject.toml`、生成 `uv.lock`，安装验证。不得手写 lock 或假定未经验证的版本兼容。
- **验收：** 共享模型可导入，输入校验测试通过；B/C/D 可据此开始实现。接口约定直接维护在本任务书，不另开接口报告。

### P1-02 实现 Task 存储

- **负责人：B；评审：A。依赖：P1-01。**
- 建议代码范围：`agentos/storage/tasks.py` 与对应测试；按实际需要建包，不预建 Memory 等模块。
- 实现建表、创建、查询、状态/结果/错误更新和连接关闭；使用参数化 SQL，JSON 与时间字段往返读取一致。
- 约束 task_id 主键，检查更新是否命中记录；Repository 不自行决定工作流或 Task 状态转换规则。
- **验收：** 新建数据库可初始化；创建后读取一致；未知 ID 返回约定结果；关闭后重新打开同一文件仍能读到记录；独立任务互不覆盖；临时库测试通过。

### P1-03 接入最小图和 Checkpointer

- **负责人：C；评审：A，D 参与测试评审。依赖：P1-01。**
- 建议代码范围：`agentos/workflows/demo.py`、`agentos/adapters/langgraph.py` 与对应测试。
- 用真实 StateGraph 实现 `demo_echo`，一个确定性节点即可；输入文本返回相同文本，不调用网络和模型。
- Adapter 使用调用方传入的原 `thread_id` 执行图，不能在内部重新生成 ID；输出转换成约定的业务结果，不把框架对象直接返回 API。
- 接入文件型 SQLite Checkpointer，明确打开和关闭资源的方式；向 A 交接生命周期装配方式。
- **验收：** 真实图产生预期结果；通过 Checkpointer 公开接口读取到对应 thread 的图状态；关闭后重新打开仍可读取；不同 thread 状态隔离；节点异常能传给 Runtime。该验证不包含 resume。

### P1-04 实现 Runtime 并装配资源

- **负责人：A；评审：B、C。依赖：P1-01、P1-02、P1-03。**
- 建议代码范围：`agentos/runtime/service.py`、`agentos/main.py`、`agentos/core/config.py` 及相关测试。
- 实现 `create_and_run`、`get_task` 和集中状态转换；分别生成 task_id/thread_id，按约定提交状态，再调用 Adapter。
- 图失败时保存 FAILED 和安全错误摘要；存储失败按基础设施故障处理，不能只打印错误后返回成功。
- 在应用 lifespan 内初始化并关闭 Repository、Checkpointer 和 Runtime；延续 `create_app(settings)` 的可配置用法，保证不同测试应用不共享开发数据。
- 任务日志至少关联 task_id、thread_id、状态；不新增审计表。
- **验收：** 真实 Repository + Adapter 的成功链路可执行；替换为失败 Adapter 时持久化 FAILED；非法终态转换被拒绝；资源随应用关闭。进程异常退出留下的中间状态不被误标成功或自动重试。

### P1-05 实现任务 API

- **负责人：D；评审：A。依赖：P1-01，最终联调依赖 P1-04。**
- 建议代码范围：`agentos/api/tasks.py`、路由注册和 `tests/test_tasks.py`。
- 实现创建、查询及响应模型，调用 Runtime；异常映射遵守 API 契约，路由中不写 SQL、图执行或状态转换逻辑。
- Runtime 完成前，可使用与契约一致的测试替身编写 API 测试；最终必须用真实实现补足联调测试。
- **验收：** 201/200/404/422/503 及 FAILED 响应场景均有对应测试；健康检查保持原响应语义。

### P1-06 联调和交付

- **负责人：D 组织验证，A 集成合并；B/C 修复各自模块问题。依赖：P1-02 至 P1-05。**
- 用真实图与两个临时 SQLite 文件跑通 API 集成测试；覆盖下节矩阵，不以全量 Mock 替代真实执行验证。
- 测试必须真实进入应用 lifespan。使用仅发送 ASGI 请求的测试写法时，显式处理启动/关闭过程，避免跳过数据库初始化。
- 关闭并重建应用后，通过 API 查询之前完成的 Task，通过 Checkpointer 公共接口读取相同 thread 的状态；不通过重跑图伪装持久化验证。
- D 更新 README 中的当前能力、配置、创建/查询示例和限制；A 核对 CI 与本地命令一致，统一合并依赖变更。
- **验收：** 新环境按 README 安装后可演示；所有必测项与质量检查通过。交付物为代码、测试、lock 和 README，无需额外调研报告或签字表。

## 5 开发顺序与排期

以下为 **5 个工作日的建议安排**，以负责人宣布启动日为第 1 天，不代表已确定的课程截止日期。按交付依赖推进，遇到接口阻塞优先结对解决。

| 时间 | 主要工作 | 当日可检查结果 |
| --- | --- | --- |
| 第 1 天 | A 完成 P1-01；B/C/D 参与模型和交接约定，D 建立测试用例 | 模型及契约可用，依赖可安装，分支可开始开发 |
| 第 2 天 | B 实现存储，C 实现图与 Adapter，D 完成 API 校验/测试替身；A 编写 Runtime 状态逻辑 | 各模块有可运行单元测试，接口保持一致 |
| 第 3 天 | 合并 P1-02/P1-03，A 完成资源装配；D 接入真实 Runtime | 首条 POST → 图执行 → GET 链路通过 |
| 第 4 天 | 全员补异常、持久化、资源关闭与隔离测试 | 失败链路和重建应用后的读取通过 |
| 第 5 天 | D 更新 README 并组织演示，A 合并；全员修复验收问题 | 锁定依赖安装、pytest、Ruff 和完整演示通过 |

每个任务通过独立分支和 PR 交付，具体要求见下一节。依赖变更由 A 统一处理，B/C/D 提交所需包及使用位置，避免多人分别覆盖 lock。接口变化先更新本文件，再同步调用方。

## 6 分支与 PR 要求

### 每位成员的任务分支

所有成员（包括 A）必须从最新 `main` 新建任务分支，不在 `main` 上直接开发或推送业务改动。一个分支对应一个任务、一个主要作者；不要共用长期个人分支，也不要向其他成员的任务分支直接推送。

| 成员 | 任务 | 分支名称 | PR 评审人 |
| --- | --- | --- | --- |
| A | P1-01 模型与接口 | `feature/p1-01-a-contract` | B、C、D 参与接口确认，至少一人批准 |
| B | P1-02 Task 存储 | `feature/p1-02-b-task-storage` | A |
| C | P1-03 LangGraph 接入 | `feature/p1-03-c-langgraph` | A，D 参与测试评审 |
| A | P1-04 Runtime 与资源装配 | `feature/p1-04-a-runtime` | B、C 至少一人批准 |
| D | P1-05 任务 API | `feature/p1-05-d-task-api` | A |
| D | P1-06 集成测试与说明 | `test/p1-06-d-integration` | A，B/C 核对各自模块问题 |

P1-06 由 D 持有集成分支；B/C 的模块修复各自新建 `fix/p1-06-b-storage`、`fix/p1-06-c-langgraph` 等分支并提交独立 PR，合入 main 后由 D 同步。A 如需修改集成代码，也应使用独立分支和 PR。

成员拿到自己的任务后，先检查工作区；存在未提交改动时先妥善提交或保存，再切换分支。以下以 B 为例，其他成员替换为表中的分支名：

```powershell
git status
git switch main
git pull --ff-only origin main
git switch -c feature/p1-02-b-task-storage
git push -u origin feature/p1-02-b-task-storage
```

以上命令要求仓库已配置 `origin`，且远程已有 main。若尚未连接远程，A 先完成远程仓库准备；成员仍应在本地任务分支开发，远程就绪后补推并提交 PR，不能用口头确认代替最终 PR 记录。

P1-01 合入 main 后，B/C/D 再从最新 main 建立实现分支。提前开展的工作只限测试用例、任务梳理等不依赖共享模型的内容。P1-04/P1-05 不需要从别人的功能分支创建分支；先按已合并的契约使用测试替身，待依赖 PR 合并后同步 main，再完成真实联调。

### 同步与提交

每天开始开发前、依赖 PR 合并后，以及自己的 PR 请求正式评审前，都要在当前任务分支同步 main。先确认当前分支正确且工作区干净，再执行：

```powershell
git fetch origin
git merge origin/main
```

发生冲突时，由当前分支作者联系相关模块负责人处理，不直接覆盖对方修改。冲突解决后重跑受影响测试和质量检查，再推送；不要向 main 或共享任务分支强制推送。

每次提交只包含本任务相关改动。使用 `git add` 明确指定实际修改的文件路径，然后运行 `git diff --staged` 检查待提交内容，确认没有 `.env`、密钥、本地数据库、虚拟环境或无关文件。提交信息包含任务编号与具体改动，例如 `feat(P1-02): persist tasks in SQLite`。完成后推送自己的分支。

### 创建与更新 PR

每个任务至少提交一个 PR，**目标分支统一为 `main`**。开始实现并有可查看的代码后，可以先创建 Draft PR；依赖未合并或功能未完成时保留 Draft，并写明阻塞项。满足本任务验收要求后，再转为正式评审并指定上表评审人。

PR 标题包含任务编号与具体行为，例如 `P1-02 实现 Task SQLite 持久化`。描述至少写清：

- 对应任务编号、实现内容及涉及模块。
- 对外接口、数据结构或配置的变更；没有变化时简述即可。
- 依赖 PR 的编号或链接，以及是否已合并；不得在依赖未满足时申请合并。
- 实际执行的测试、Ruff 命令和结果；尚未运行的检查如实标明。
- 未解决问题、已知限制，以及需要评审者重点检查的内容。

请求正式评审前，作者在同步后的任务分支执行 `uv lock --check`、`uv run --locked pytest`、`uv run --locked ruff check .` 和 `uv run --locked ruff format --check .`，并确认 CI 通过。评审意见在同一分支修复并推送，PR 自动更新，不为每次修复重复新建 PR。

### 评审与合并

每个 PR 至少获得一名非作者成员批准；作者不能自行批准自己的 PR。A 负责组织并执行最终合并，A 自己的 PR 同样必须先由 B/C/D 按上表评审。评审重点是接口契约、状态与存储行为、测试有效性，以及是否超出本阶段范围。

只有依赖已合并、冲突已解决、评审意见已处理且 CI 全部通过，PR 才能合入 main。批准后如新增影响行为的修改，应请评审人复核最新改动。采用 Squash merge，合并后的提交标题保留任务编号，便于追踪。

合并顺序为 P1-01 → P1-02/P1-03 → P1-04 → P1-05 → P1-06；P1-02 与 P1-03 可以先后独立合并。模块修复应在最终集成验收前合并。合并后删除远程任务分支，成员更新本地 main；后续新任务重新建分支，不继续复用已合并分支。

## 7 验收用例

| 场景 | 必须观察到的结果 | 主要负责人 |
| --- | --- | --- |
| 创建并查询正常任务 | POST 201、SUCCEEDED、结果正确；GET 200 与保存数据一致 | D |
| 标识与任务隔离 | 每个 Task 的两个 ID 分别保存；不同任务、不同 thread 互不覆盖 | B/C/D |
| 输入和路径校验 | 缺失/空白/超长文本、未知 task_type、非法 UUID 返回 422；非法创建不落库 | D |
| 查询不存在任务 | 合法但不存在的 UUID 返回 404 | D |
| 工作流异常 | 可控失败 Adapter 的集成测试保存 FAILED；真实图节点异常测试验证异常传播 | A/C/D |
| 存储不可用 | 创建或查询返回 503，不返回虚假成功；不泄露堆栈 | B/D |
| 状态约束 | 完成态不能重新进入执行态；状态更新失败不宣称成功 | A |
| 业务与图状态持久化 | 关闭并重开后，Task 可查，同一 thread 的已存 Checkpoint 可读，无需再次执行 | B/C/D |
| 资源与测试隔离 | 正常启动/关闭，重复创建应用不复用已关闭连接；测试仅写临时库 | A/D |
| 基础功能回归 | 原健康检查测试及新增测试通过，lint 与格式检查通过 | 全员 |

失败测试通过依赖注入或测试节点故障构造，不向正式 API 添加 `force_fail`、故障开关等演示专用参数。

## 8 完成标准与演示

本阶段结束前，全员应能在项目根目录执行以下命令。它们是阶段验收要求，本文件不将尚未开发的功能标记为已通过。

```powershell
uv sync --locked --dev
uv lock --check
uv run --locked pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked uvicorn agentos.main:create_app --factory --host 127.0.0.1 --port 8000
```

服务启动后，在另一终端创建并查询任务：

```powershell
$requestBody = @{
    task_type = 'demo_echo'
    input = @{ text = 'hello AgentOS' }
} | ConvertTo-Json -Depth 3

$task = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/v1/tasks' -ContentType 'application/json' -Body $requestBody
$task | ConvertTo-Json -Depth 5
Invoke-RestMethod -Uri ('http://127.0.0.1:8000/api/v1/tasks/' + $task.task_id) | ConvertTo-Json -Depth 5
```

演示依次展示：创建后返回 SUCCEEDED 与结果 → 按 task_id 查询 → 停止并重启服务后查询同一 Task → 展示自动化失败测试和 Checkpoint 持久化测试。失败注入留在测试中，不需要人为破坏开发数据库。

合并条件为验收矩阵全部通过、README 与实际行为一致、数据库和密钥未入库、没有提前实现后续业务空壳。未通过项应说明实际问题并修复，不能以文档完成代替代码闭环。
