# AgentOS 项目计划书

- 版本：v1.1
- 文档性质：项目组内部阶段 0 计划说明
- 项目类型：课程期末项目
- 团队规模：4 人
- 当前阶段：阶段 0——项目理解与基础工程搭建

---

## 1. 项目概述

### 1.1 项目名称

**AgentOS：面向可恢复、可治理 Agent 工作流的轻量级运行时平台**

### 1.2 一句话介绍

AgentOS 是一层构建在现有 Agent 工作流框架之上的运行时基础设施。它不负责重新发明大模型或 Agent 推理算法，而是负责把 Agent 工作流作为“可管理的任务”运行起来，并补足任务生命周期、持久化恢复、工具权限控制、定时触发、业务去重和执行审计等工程能力。

这里的“OS”是对 Agent 应用运行支撑层的比喻，不是操作系统内核，也不涉及进程调度、内存管理等传统操作系统功能。

### 1.3 项目背景与要解决的问题

直接使用 Agent 框架通常可以较快实现一个能够执行任务的 Demo，但当它需要长期运行或接入真实工具时，会遇到一系列工程问题：

1. **任务不可管理**：调用一次工作流不等于具备任务管理能力。系统需要知道任务何时创建、何时开始、是否完成、是否失败，以及当前是否正在等待人工处理。
2. **中断后难以可靠恢复**：工作流可能因人工审批、服务重启或运行异常而暂停，需要从保存的执行状态继续，而不是简单地从头再跑。
3. **工具权限缺乏统一治理**：读数据、发邮件、写入外部系统等工具的风险不同，不能所有工具都不经判断直接执行。
4. **重复执行可能造成副作用**：任务重试或恢复时，可能重复发送邮件、重复写入数据或重复提交外部请求。
5. **缺少外部触发与业务去重**：系统需要能够定时创建任务，并记住哪些业务对象已经处理过。
6. **运行过程难以追踪**：开发者需要知道任务经历了哪些步骤、为什么等待审批、哪个工具被允许或拒绝、失败发生在哪里。

AgentOS 的目标是把这些通用运行能力集中在基础设施层，让上层 Agent 工作流更容易被管理、恢复、约束和观察。

---

## 2. 项目目标与范围

### 2.1 核心目标

最终项目应形成一个可运行的轻量级 Agent 运行时平台，至少体现以下能力：

- **统一任务管理**：通过 API 创建任务，查询任务状态和结果。
- **工作流执行接入**：接入 LangGraph 等现有执行框架，由 AgentOS 负责外围任务管理。
- **持久化与恢复**：保存任务业务状态和工作流 Checkpoint；对可恢复任务使用原执行线程继续运行。
- **工具治理**：提供 `ALLOW`、`CONFIRM`、`DENY` 三类决策；支持人工审批闭环。
- **幂等保护**：为受控工具操作建立稳定操作标识和执行记录，降低重复副作用风险。
- **外部调度**：允许定时器等外部触发源创建任务，调度器本身不直接执行工作流。
- **业务记忆/去重**：保存已处理业务对象，避免相同内容反复进入处理流程。
- **运行审计**：记录任务状态变化、治理决策、审批结果和工具执行情况。
- **可演示性**：提供一个完整的示例 Agent 工作流，展示上述能力如何协同工作。

### 2.2 本项目不打算做什么

为控制课程项目规模，MVP 不追求：

- 自研大语言模型、模型训练或推理引擎；
- 自研通用 Agent 图执行框架，替代 LangGraph；
- 复杂的多 Agent 自主协商或分布式 Agent 集群；
- 多机高可用、跨区域容灾、企业级多租户；
- 操作系统级沙箱、容器编排或强制进程隔离；
- 对任意第三方系统副作用提供绝对的 Exactly-once 保证；
- 一开始就建设复杂的前端控制台。

项目的重点是**把一个范围明确的 Agent 工作流可靠地运行起来**，并用工程机制解释清楚它如何被管理、恢复和治理。

### 2.3 最终项目成果的判断标准

最终应以一个实际可运行的系统为中心。演示时应能够让观看者看到：

1. 创建一项 Agent 任务，并查询其状态；
2. 工作流执行并产生结果；
3. 当工作流请求执行受限工具时，系统能够暂停并等待人工审批；
4. 审批通过后，工作流能够从原有执行上下文恢复；审批拒绝时，受限工具不会执行；
5. 重复触发或重复提交时，系统能够识别并处理重复任务/业务对象；
6. 能够查询任务执行过程和关键审计事件。

真实模型、真实论文接口和真实邮件服务可以作为增强项。核心机制必须能够在 Mock/离线模式下演示，避免外部 API、密钥、网络或邮件账号成为项目能否运行的前提。

---

## 3. 验证应用：每日网络安全论文简报 Agent

AgentOS 本身是运行时平台。为了证明它不是一组互不相关的 API，需要一个具体工作流作为验证载体。

选择 **每日网络安全论文简报 Agent**：定时收集近期网络安全论文，识别已处理内容，筛选与整理论文信息，生成简报，并在发送前请求人工审批。

### 3.1 预期工作流

```text
定时触发 / 手动触发
        |
        v
创建 AgentOS Task
        |
        v
获取论文列表（先使用 Mock 数据）
        |
        v
论文规范化与业务去重
        |
        v
筛选论文、提取关键信息
        |
        v
生成简报（Mock 摘要优先，模型接入为可选增强）
        |
        v
请求发送简报工具
        |
        v
Governance 策略判断
   |          |          |
 ALLOW     CONFIRM      DENY
   |          |          |
执行工具   暂停并审批   阻止工具调用
              |
              v
       人工批准 / 拒绝
              |
              v
       恢复工作流并继续
              |
              v
       保存处理结果与审计事件
```

### 3.2 示例应用的实现边界

- 第一版采用固定 Mock 论文数据，保证无需外网即可演示。
- 论文去重优先使用 DOI，其次规范化 URL，再使用内容哈希作为兜底标识。
- 摘要节点先支持确定性的 Mock 输出；后续可增加真实 LLM 适配器。
- 邮件工具先实现 Mock 版本：不真正发送邮件，只记录“将要发送”的内容与结果。
- 核心能力稳定后，再考虑接入 arXiv 等真实数据源、PDF 解析和真实 SMTP。

这个示例应用不应反过来绑死 AgentOS 的核心设计。Runtime、治理、调度、去重和审计接口应尽量保持通用。

---

## 4. 总体技术架构

### 4.1 架构图

```text
                  示例应用层
       Daily Security Paper Briefing Agent
                         |
                  FastAPI 接入层
                         |
                 AgentOS 运行时层
       +-----------------+------------------+
       | Runtime         | Scheduler        |
       | Task 生命周期    | 定时/外部触发     |
       +-----------------+------------------+
       | Governance      | Memory           |
       | 工具策略/审批    | 业务记录/去重     |
       +-----------------+------------------+
       | Observability / Audit               |
       | 事件记录、执行追踪、状态查询          |
       +------------------------------------+
                         |
                  工作流适配层
                  LangGraph Adapter
              StateGraph / Checkpointer
                         |
                 持久化与基础组件
         SQLite 业务数据 / Checkpoint Store
         配置 / 日志 / 测试 / 运行环境
```

### 4.2 各部分职责

| 部分 | 主要职责 | 不应该承担的职责 |
|---|---|---|
| FastAPI 接入层 | 接收请求、参数校验、返回任务和审批信息 | 直接编写复杂工作流逻辑 |
| Runtime | 创建任务、排队、执行调度、维护状态、查询结果、恢复工作流 | 实现大模型推理或具体论文业务 |
| LangGraph Adapter | 将 AgentOS 的执行请求转换为 LangGraph 调用；封装 invoke/resume 和 Checkpointer 接入 | 管理业务 Task 的全部生命周期 |
| Scheduler | 维护定时配置、产生触发事件、请求 Runtime 创建任务 | 自己直接调用图节点或操作工具 |
| Governance | 判断工具权限、创建审批、传递审批结果、阻止未授权调用 | 取代工具自身的参数校验 |
| Memory | 保存已处理业务对象并提供去重查询 | 把 Checkpoint 当成业务记忆 |
| Observability/Audit | 记录状态变化、工具决策、审批及执行结果 | 只依靠普通文本日志充当审计数据库 |
| 示例工作流 | 展示平台能力并完成论文简报业务 | 把平台能力重复实现一遍 |

### 4.3 第三方组件与自研边界

| 能力 | 复用的组件/机制 | 本项目需要实现的部分 |
|---|---|---|
| Web 服务 | FastAPI、Uvicorn | AgentOS 的 API 和业务服务 |
| Agent 图执行 | LangGraph | Runtime 与图执行之间的适配和生命周期管理 |
| 中断/恢复 | LangGraph interrupt、Command resume | 审批业务、恢复入口、权限复核和状态同步 |
| 执行状态保存 | LangGraph Checkpointer | task_id 与 thread_id 的关联、恢复编排 |
| 定时触发 | APScheduler 3.x 系列 | Trigger 事件、触发去重、调用 Runtime |
| 业务数据保存 | SQLite | Task、Approval、AuditEvent、ProcessedItem、ToolOperation 等业务记录 |
| 数据校验 | Pydantic | 请求、响应和配置模型 |
| 自动化测试 | pytest | 项目自己的单元、集成和端到端测试 |
| 代码规范 | Ruff | 项目代码质量配置 |

不要把“使用 LangGraph”说成自研 Agent 执行引擎，也不要把“使用 SQLite”说成自研数据库。项目要体现的工作是围绕这些组件设计并实现运行时管理机制。

---

## 5. 核心模块设计

### 5.1 Runtime：任务运行时

Runtime 是 AgentOS 的中心，负责把一次工作流运行包装成一个可跟踪的 Task。

主要职责：

- 创建 Task，分配 `task_id` 和 `thread_id`；
- 将任务交给执行器/Worker；
- 维护 Task 状态和合法状态转换；
- 调用 LangGraph Adapter 执行或恢复工作流；
- 保存输入、输出摘要、错误信息和关键时间；
- 对外提供任务查询、取消请求和恢复入口。

**Task 状态建议：**

```text
CREATED -> QUEUED -> RUNNING -> SUCCEEDED
                         |----> FAILED
                         |----> WAITING_APPROVAL -> RUNNING
                         |----> CANCEL_REQUESTED -> CANCELLED
```

说明：

- `CREATED`：任务记录已经创建；
- `QUEUED`：等待执行；
- `RUNNING`：工作流正在运行；
- `WAITING_APPROVAL`：工作流因审批中断；
- `CANCEL_REQUESTED`：收到取消请求，等待执行流程在安全位置响应；
- `SUCCEEDED`：工作流正常结束；
- `FAILED`：工作流执行失败；
- `CANCELLED`：任务已取消。

审批拒绝不应简单等同于 Task 被取消。审批结果应作为工作流输入恢复执行，由工作流决定是跳过当前操作、走拒绝分支还是结束任务；Task 是否成功取决于该工作流的业务定义。

状态转换应集中在 Runtime 的状态管理逻辑中，避免不同 API 路由随意更新状态。

### 5.2 `task_id` 与 `thread_id` 必须分离

- `task_id` 是 AgentOS 的任务 ID，用于 API、任务查询、审计、调度和业务管理。
- `thread_id` 是 LangGraph Checkpointer 用来定位工作流执行上下文的标识。
- MVP 可以让一个 Task 对应一个 thread，但必须分别保存两个字段。
- 恢复工作流必须使用原 `thread_id`，不能通过创建一个新 thread 假装恢复。

### 5.3 LangGraph Adapter：执行适配层

Adapter 把 Runtime 和 LangGraph 隔离开：

- 根据工作流类型找到对应的图；
- 为执行传入 `thread_id` 和必要配置；
- 统一封装首次执行和恢复执行；
- 将图的完成、中断和异常结果转换成 Runtime 能处理的结果；
- 接入 Checkpointer。

这样做是为了避免 LangGraph 的具体 API 散落到 API 路由、Scheduler 或业务代码中，降低后续框架版本变动的影响。

### 5.4 Governance：工具治理与人工审批

工具调用前必须经过统一策略判断，至少支持三种决策：

| 决策 | 含义 | 行为 |
|---|---|---|
| `ALLOW` | 当前工具调用允许直接执行 | 记录决策后执行工具 |
| `CONFIRM` | 需要人工确认 | 创建审批记录，中断工作流，等待审批 |
| `DENY` | 当前工具调用不允许执行 | 记录拒绝，不调用工具 |

审批流程：

1. 工作流请求执行工具；
2. Governance 根据工具类型、参数和策略作出决策；
3. `ALLOW` 直接执行；`DENY` 阻止调用；`CONFIRM` 创建 Approval 并中断；
4. 用户通过 API 提交批准或拒绝；
5. Runtime 使用原 `thread_id` 恢复工作流，并传入审批结果；
6. 恢复后的工作流再次校验审批记录和工具参数，只有批准且校验通过才能执行工具。

**重要实现约束：** LangGraph 的 interrupt/resume 可能导致包含 interrupt 的节点从节点开头重新执行。因此，在中断点之前不要执行不可重复的外部副作用；审批记录需要稳定 ID；恢复后不能仅凭客户端传来的“已批准”字段就直接执行工具。

### 5.5 幂等与外部副作用

Checkpoint 只保存工作流状态，不自动保证邮件发送、HTTP 写请求等外部副作用只发生一次。

对受控工具调用设计稳定的 `operation_id` 或 idempotency key，并保存执行记录。可采用如下逻辑状态：

```text
PENDING -> EXECUTING -> SUCCEEDED
                    -> FAILED
```

同一逻辑操作再次请求时，先检查操作记录：

- 已 `SUCCEEDED`：返回已保存结果，不重复执行；
- 正在 `EXECUTING`：根据工具能力和恢复策略处理，不盲目重放；
- `FAILED`：根据错误类型和重试策略决定是否重试。

这是一种有边界的幂等保护，不应宣传成对任意外部系统的绝对 Exactly-once。对于不支持幂等键的第三方工具，仍需说明不确定窗口和限制。

### 5.6 Scheduler：外部定时触发

Scheduler 负责“什么时候创建任务”，不负责“如何执行任务”。

- 管理定时任务配置；
- 到达触发时间后生成统一 Trigger Event；
- 将 Trigger Event 交给 Runtime 创建 Task；
- 通过触发 ID/时间窗口等机制避免重复创建；
- 记录触发成功、失败和跳过原因。

MVP 先采用单机、单实例调度，不承诺多实例分布式调度。计划采用 APScheduler 3.x API，避免把 3.x 与 4.x 的配置方式混用。

### 5.7 Memory：业务记忆与去重

本项目第一版的 Memory 是**业务记录与去重存储**，不是长期对话记忆或完整认知记忆系统。

对于论文数据，使用 DOI、规范化 URL、内容哈希等建立稳定业务标识；数据库唯一约束负责最终防重，不能只依靠“先查询、再插入”的应用层逻辑。

### 5.8 Observability / Audit：审计与可观测

围绕一次 Task 记录关键事件，例如：

- task_created、task_started、task_succeeded、task_failed；
- workflow_interrupted、workflow_resumed；
- tool_policy_allowed、tool_policy_denied；
- approval_requested、approval_approved、approval_rejected；
- tool_operation_started、tool_operation_succeeded、tool_operation_failed；
- duplicate_item_skipped。

事件至少应能关联 `task_id`，在适用时同时关联 `thread_id`、approval_id 和 operation_id。普通运行日志与结构化审计事件可以共存，但不能互相替代。

---

## 6. 数据与接口的总体方向

这一节用于统一项目组对数据和 API 的理解，具体字段可在实现时随代码调整，不要求阶段 0 另行产出数据字典或接口报告。

### 6.1 核心业务实体

| 实体 | 用途 | 典型字段 |
|---|---|---|
| Task | 记录一次 AgentOS 任务 | task_id、thread_id、task_type、status、input、result、error、时间字段 |
| Approval | 记录一次人工审批 | approval_id、task_id、tool_name、参数摘要、status、decision_by、reason、时间字段 |
| AuditEvent | 记录可追踪事件 | event_id、task_id、event_type、actor、resource、decision、result、metadata、created_at |
| ProcessedItem | 记录已处理业务对象 | item_id、source、external_id、canonical_url、content_hash、processed_at、task_id |
| ToolOperation | 记录受控工具操作 | operation_id、task_id、tool_name、idempotency_key、status、request_digest、result、时间字段 |

LangGraph Checkpoint 由其 Checkpointer 管理。AgentOS 不应复制或自行解析 Checkpoint 内部结构；业务 Task 状态和 Checkpoint 应保持逻辑分离。

### 6.2 API 方向

API 前缀建议使用 `/api/v1`。预计主要接口如下：

| 方法 | 路径 | 用途 |
|---|---|---|
| `POST` | `/api/v1/tasks` | 创建任务 |
| `GET` | `/api/v1/tasks/{task_id}` | 查询任务状态和结果 |
| `GET` | `/api/v1/tasks/{task_id}/events` | 查询任务事件 |
| `POST` | `/api/v1/tasks/{task_id}/resume` | 在满足条件时恢复任务 |
| `POST` | `/api/v1/tasks/{task_id}/cancel` | 请求取消任务 |
| `GET` | `/api/v1/approvals` | 查询审批列表 |
| `POST` | `/api/v1/approvals/{approval_id}/decision` | 提交审批决定 |
| `GET` | `/api/v1/health` | 检查 API 服务状态 |

阶段 0 只需要实现健康检查，不需要把上述业务 API 全部提前写出来。后续按实际功能逐项实现。

### 6.3 存储策略

课程 MVP 默认采用 SQLite，原因是单机部署简单、便于演示和测试。需要明确：

- 业务表由 AgentOS 自己设计和管理；
- LangGraph Checkpoint 由 Checkpointer 管理；
- 两类数据在逻辑上分离，必要时可使用独立数据库文件；
- SQLite 适合本项目的单机低并发场景，不将其描述成高并发分布式存储方案。

---

## 7. 技术选型方向

| 类别 | 计划采用 | 说明 |
|---|---|---|
| 语言 | Python 3.12 | 统一运行环境 |
| API | FastAPI + Uvicorn | 提供 HTTP 接入 |
| 数据模型 | Pydantic | 请求、响应与配置校验 |
| Agent 工作流 | LangGraph | 图执行、中断和恢复机制 |
| Checkpoint | LangGraph SQLite Checkpointer | 保存图执行状态 |
| 业务数据 | SQLite | 保存 Task、Approval、审计和去重记录 |
| Scheduler | APScheduler 3.x | 单机定时触发 |
| 测试 | pytest + httpx | 单元和 API 测试 |
| 代码质量 | Ruff | lint 与 format |
| 包管理 | 优先使用 uv | 管理依赖与 lock 文件 |
| UI | 可选 Streamlit 或简单 Web 页面 | 核心 API 稳定后再决定 |

阶段 0 的基础代码不必提前安装 LangGraph、APScheduler 或 UI 依赖。等相应阶段真正实现功能时，再加入并锁定依赖版本。

---

## 8. 开发路线与阶段安排

项目按功能闭环逐步推进。每一阶段结束时应有可运行的代码增量。

### 阶段 0：理解项目与基础工程搭建（当前阶段）

**目标：** 让项目有清晰的共同方向，并建立能够继续开发的基础代码工程。

由负责人完成：

- Python 项目初始化和依赖管理；
- 最小 FastAPI 应用与健康检查接口；
- 配置读取、基础日志；
- pytest 和 Ruff；
- 基础 Git 忽略配置和环境变量示例；
- README 中的安装、启动和测试命令；
- 最小 CI 检查（条件允许时）。

本阶段不实现 Runtime 的真实任务执行、LangGraph、审批、恢复、Scheduler、Memory、论文工作流或前端。

### 阶段 1：Runtime 最小执行闭环

**目标：** 从 API 创建任务，到 Runtime 调用一个最小 LangGraph 工作流，再到查询任务结果。

主要内容：
- Task 数据模型和 SQLite Repository；
- task_id/thread_id 关联；
- Task 状态管理；
- Runtime 与 LangGraph Adapter；
- 最小 StateGraph 和 Checkpointer；
- 创建任务、查询任务 API；
- 基本异常处理和集成测试。

阶段结果：能够创建任务、执行简单工作流、查询运行结果和状态。

### 阶段 2：任务中断、审批与恢复

**目标：** 把工具治理和人工审批做成真正的运行闭环。

主要内容：
- Allow / Confirm / Deny 策略；
- Approval 数据记录和审批 API；
- LangGraph interrupt/resume；
- 使用原 thread_id 恢复；
- 审批拒绝路径；
- ToolOperation 和 operation_id 幂等保护；
- 重复恢复、服务重启和工具失败测试。

阶段结果：需要审批的工具调用能够暂停；批准后恢复；拒绝时不会执行敏感工具；重复恢复不会无条件重复副作用。

### 阶段 3：Scheduler 与 Memory

**目标：** 让任务可以被外部定时触发，并避免重复处理同一个业务对象。

主要内容：
- APScheduler 定时任务；
- Trigger Event；
- Scheduler 调用 Runtime 创建 Task；
- 论文标识规范化；
- ProcessedItem 唯一约束和去重；
- 重复触发与重复论文测试。

阶段结果：定时触发能够创建任务，相同触发和相同论文能够按规则去重。

### 阶段 4：示例 Agent 工作流与审计

**目标：** 用每日网络安全论文简报 Agent 串联各项基础设施能力。

主要内容：
- Mock 论文数据源；
- 论文过滤、整理和摘要节点；
- Mock 邮件工具；
- 发送前人工审批；
- 任务和工具审计事件查询；
- 离线运行和演示路径；
- 视剩余时间增加真实 LLM/API 或轻量 UI。

阶段结果：可以现场演示从触发、去重、生成简报、等待审批、恢复执行到审计查询的完整流程。

### 阶段 5：系统稳定与课程展示

**目标：** 把项目整理为一个稳定、可复现、可解释的最终系统。

主要内容：
- 修复关键缺陷；
- 完成核心自动化测试；
- 优化错误提示和演示体验；
- 验证新环境安装与运行；
- 准备项目演示流程和答辩说明。

最终课程成果仍然是系统本身及其演示，不要求额外交付一套过程文档。

---

## 9. 四人团队的协作思路

采用“阶段式共同推进 + 模块主责 + 交叉 Review”。不建议四个人从一开始就各自封闭开发一个模块，最后才拼接。Runtime、治理、调度和存储之间存在较多接口依赖，需要先共同理解整体流程，再逐步明确每项任务的主责人。

| 成员 | 长期主要职责 | 协作要求 |
|---|---|---|
| A：项目负责人 | 总体方向、架构、Runtime、任务拆分、集成和进度 | 维护整体接口；组织阶段推进；Review 关键改动 |
| B | Scheduler、Memory | 与 Runtime 对齐触发和去重接口；参与联调 |
| C | Governance、审批与幂等 | 与 Runtime 对齐中断恢复；重点检查权限和副作用边界 |
| D | 测试、审计/可观测、工程质量，后期可负责展示层 | 与各模块共同定义测试场景；负责系统级验证 |

这只是长期责任划分，不意味着每人只写自己的模块。每个阶段开始时，负责人会发布具体任务，说明本次目标、接口、验收方式和相关代码范围；成员可以结对实现或互相 Review。遇到跨模块问题先一起确定接口，再分配实现，不让模块之间长期各自假设。

---

## 10. 工程协作约定

工程化是为了让四个人能够持续协作，不是为了制造额外文档工作。保持以下基本做法即可：

- 使用 Git 管理代码，主分支保持可运行；
- 新功能或修复使用独立分支，完成后合并；
- 提交信息写清楚改动目的；
- 重要改动通过 Pull Request 或等效代码 Review；
- 每个实际功能都应有对应测试，核心流程优先写集成测试；
- `.env`、API Key、数据库临时文件和虚拟环境不提交；
- README 保持足够清晰，让成员能安装、启动和运行测试；
- 不要求每个小改动都配套编写会议纪要、阶段报告、调研报告或形式化验收文档。

---

## 11. 主要风险与实现原则

| 风险 | 原则与应对 |
|---|---|
| LangGraph API 与版本变化 | 锁定依赖；将 LangGraph 调用集中在 Adapter；实现时验证 interrupt/resume 行为 |
| 把 Checkpoint 误认为完整任务数据库 | Task 等业务数据由 AgentOS 管理；Checkpoint 只管理图执行状态 |
| 审批恢复时节点重复执行 | interrupt 前不做不可重复副作用；恢复时复核审批和参数 |
| 工具副作用重复 | 使用 operation_id 和持久化操作记录；明确外部服务能力边界 |
| Scheduler 重复触发 | 为触发事件设计稳定 ID 和去重机制 |
| SQLite 并发能力有限 | 课程 MVP 限定单机低并发；通过 Repository 隔离存储实现 |
| 外部 LLM/API 不稳定 | Mock 优先；核心演示不依赖真实密钥和外部服务 |
| 四人接口不一致 | 阶段开始前共同梳理流程和接口；持续集成与交叉 Review |
| 一开始范围过大 | 先完成纵向闭环，再逐步添加能力；UI 和真实外部服务后置 |

### 11.1 必须坚持的实现原则

1. **先有最小闭环，再扩展模块。** 不为追求目录齐全而创建空壳。
2. **任务状态和工作流状态分离。** `task_id` 不等同于 `thread_id`。
3. **调度只负责触发。** Scheduler 不直接执行 Agent 图。
4. **工具执行必须经过治理入口。** 不能只在前端按钮上控制权限。
5. **拒绝和审批是业务结果。** 不应将审批拒绝简单伪装成任务取消。
6. **Checkpoint 不等于 Exactly-once。** 对外部副作用单独设计幂等机制。
7. **Mock 优先。** 基础能力先确保离线可测试、可演示。
8. **以真实代码能力为准。** 不宣称尚未实现或未测试的能力已经完成。

---

## 12. 当前阶段的结束状态

阶段 0 完成后，我们只需要得到一个可继续开发的基础工程：

- 项目目录和 Python 包结构合理；
- 能够安装依赖并启动 FastAPI；
- 健康检查接口能正常响应；
- 配置和日志有统一入口；
- 有最基本的 pytest、Ruff 和 CI 检查；
- README 能说明如何安装、运行和测试；
- 没有提前堆入尚未实现的业务模块空壳。

本文档是当前给成员理解项目的计划说明；后续真正的开发任务由负责人逐项发布。
