# Protein Agent

这是我在 `Agent / AI 应用工程` 方向上的第二个专门项目。  
它和第一个通用聊天 agent 不同，定位是一个面向 `蛋白质序列 -> 任务路由 -> 模型调用 -> 异步结果回收` 的专门 Agent 工程。

当前版本已经不是最早的同步版本，而是一个带有 `FastAPI + Celery + Redis + SQLite + 多页面任务控制台 + 任务详情页` 的异步任务骨架，适合拿来做作品集展示、真实模型 API 对接和后续工程化扩展。

## 1. 当前项目阶段

当前阶段可以概括为：

- 已完成蛋白任务的专用路由与核心业务骨架
- 已升级为异步任务执行模式
- 已补上 `Chat / Archive / System / Task Detail` 多页面前端结构、历史记录和持久化
- 已接入 `Router LLM`，用于自然语言任务识别，并保留关键词 fallback
- 已支持 `local-stub`、`generic-json`、`openai-compatible` 三种模型接入方式
- 已支持可展示的 `trace_events` 执行轨迹，并在聊天主页面中按步骤逐步展开
- 已具备作品集展示价值，但还没有把真实模型接入和更完整的集成测试完全收尾

## 2. 当前功能

### 2.1 支持的任务类型

- `多肽生成`
- `核酸适配体生成`
- `蛋白质预测`

### 2.2 当前能力

- 优先由 `Router LLM` 对自然语言 query 做任务识别，失败时 fallback 到关键词路由
- 从 query 或 `protein_sequence` 字段提取蛋白质序列
- 对序列做规范化和合法性校验
- 在模型调用前检索蛋白质领域知识作为 RAG 上下文
- 异步下发任务，立即返回 `task_id`
- 通过 `/tasks/{task_id}` 轮询查看任务状态
- 在任务执行过程中写入 `trace_events`，用于前端展示“思考轨迹 / 执行轨迹”
- 保存 `route_source` 与 `router_output_text`，用于区分路由来源并展示 Router LLM 原始输出
- 将历史任务写入 SQLite，并通过 `/history` 返回
- 前端页面支持：
  - `Chat` 页面提交任务并逐步展示执行轨迹
  - `Archive` 页面单独查看历史任务档案
  - `System` 页面查看服务状态、模型配置和知识库准备情况
  - `Task Detail` 页面查看完整结果、指标、RAG 上下文、原始输出和 Router LLM 输出

### 2.3 当前模型接入方式

- `Router LLM`
  - 当前用于自然语言任务识别
  - 已支持 `openai-compatible` 风格接口
  - 当前本地配置接入的是豆包 `doubao-seed-2-0-pro-260215`
- `local-stub`
  - 离线可跑
  - 适合本地调试、接口联调和作品集演示
- `generic-json`
  - 适合接任意遵循统一 JSON 输入输出协议的内部模型服务
- `openai-compatible`
  - 适合接豆包、DeepSeek、OpenAI-compatible 网关等 `/chat/completions` 风格接口

## 3. 当前架构

### 3.1 技术栈

- Web/API: `FastAPI`
- 异步任务队列: `Celery`
- Broker/Backend: `Redis`
- 持久化: `SQLAlchemy 2.0 + aiosqlite`
- 本地数据库: `SQLite`
- 前端: 原生 `HTML + CSS + JavaScript`
- RAG: 默认 `local-hash`，可选 `sentence-transformer`

### 3.2 技术栈对应功能

这一部分不只是“用了什么”，而是说明每个技术栈在项目里承担什么职责。

#### `Python`

这是整个项目的主语言。

对应功能：

- 承载后端 API、异步任务、模型适配、RAG 和本地指标计算
- 统一业务逻辑，避免前后端和模型调用层割裂
- 让 `FastAPI / Celery / SQLAlchemy` 这些组件能在同一语言里协作

在这个项目里，Python 负责把“蛋白任务路由、模型调用、结果存储、前端服务”串成一个完整闭环。

#### `FastAPI`

这是项目的 Web 网关与接口层，对外暴露 HTTP 服务。

对应功能：

- 提供 `/run`、`/tasks/{task_id}`、`/history`、`/health` 等接口
- 接收前端或外部调用方的请求
- 使用 `Pydantic` 做请求体校验
- 负责把任务写入数据库并派发给 Celery
- 直接托管单页前端和静态资源

为什么适合这里：

- 这个项目需要一套轻量但规范的 API 服务，而不是只写脚本
- `FastAPI` 在异步、类型标注、接口定义和演示体验上都很适合求职作品集

#### `Pydantic`

`Pydantic` 是接口层的数据校验和结构约束工具。

对应功能：

- 校验 `query`、`protein_sequence`、`include_metrics` 这些请求字段
- 约束返回模型的数据结构
- 让接口输入输出更稳定，减少前端和后端对不齐的情况

为什么适合这里：

- 这个项目面向的是结构化任务，不是自由聊天接口
- 用 `Pydantic` 可以把“输入必须合法”这件事明确落在代码里

#### `Celery`

`Celery` 是异步任务执行层。

对应功能：

- 接收 `/run` 派发出来的任务
- 在 worker 进程里执行 `ProteinAgent.run(...)`
- 避免模型调用阻塞 HTTP 请求
- 让前端可以通过 `task_id` 轮询任务状态，而不是一直等接口返回

为什么适合这里：

- 模型调用、RAG 和结果组装天然就更像后台任务
- 用 Celery 能把“接收请求”和“处理任务”拆开，结构上更像真实业务系统

#### `Redis`

`Redis` 在这里不是缓存主角，而是 Celery 的 broker / result backend。

对应功能：

- 暂存待执行任务
- 支撑 worker 拉取任务并执行
- 让 Web 进程和 worker 进程之间通过消息队列解耦

为什么适合这里：

- 这个项目的异步执行链路需要一个轻量、稳定、配置简单的消息中间件
- Redis 对作品集项目来说足够直接，也容易本地跑通

#### `SQLAlchemy 2.0`

`SQLAlchemy` 是数据库访问和 ORM 层。

对应功能：

- 定义 `AgentExecutionRecord` 数据模型
- 管理任务记录的读写
- 支撑 `/tasks/{task_id}` 和 `/history` 这类接口
- 把请求、模型、结果、指标、RAG 上下文这些信息落成结构化数据

为什么适合这里：

- 这个项目已经不是一次性脚本，历史结果和状态流转需要持久化
- ORM 让数据表结构更清晰，也方便后续切 PostgreSQL

#### `aiosqlite`

`aiosqlite` 是当前的异步 SQLite 驱动。

对应功能：

- 支撑当前项目在本地环境下用异步方式访问 SQLite
- 配合 SQLAlchemy 的 async engine 运行

为什么适合这里：

- 当前阶段主要是作品集和本地开发，SQLite 部署成本最低
- 用 `aiosqlite` 可以在不引入更重数据库的前提下保留异步接口形态

#### `SQLite`

`SQLite` 是当前默认的本地持久化存储。

对应功能：

- 保存历史任务记录
- 保存任务状态、错误、指标和 RAG 上下文
- 让前端历史看板有真实数据来源

为什么适合这里：

- 本地启动快，依赖少
- 对“单人开发 + 作品集展示 + 本地调试”场景很合适

当前边界：

- 适合现在的项目阶段
- 如果后续要强调更强并发或更真实的生产部署，建议切 PostgreSQL

#### `HTML + CSS + JavaScript`

这是当前前端工作台的实现方式，没有额外引入 React/Vue。

对应功能：

- 展示对话输入区、思考轨迹、任务档案和详情页
- 调用 `/health`、`/run`、`/tasks/{task_id}`、`/history`
- 轮询异步任务状态
- 将主对话和完整结果拆开，提升展示层次

为什么适合这里：

- 这个项目的重点是 Agent 工作流，不是大型前端工程
- 原生前端足够支撑展示，同时不会把注意力转移到框架搭建上
- 前端可以快速表达“聊天主界面 + 详情页”的产品形态

#### `local-hash RAG`

这是当前默认的知识检索后端。

对应功能：

- 从 `protein_knowledge.jsonl` 里加载蛋白领域知识
- 在模型调用前检索最相关的背景知识
- 把上下文一起带进结果输出和历史记录

为什么适合这里：

- 离线可跑，不依赖联网拉模型
- 更适合当前“稳定演示优先”的目标

#### `sentence-transformer`（可选）

这是可选的增强型 RAG 后端。

对应功能：

- 在本地已有模型缓存的前提下，提供比 `local-hash` 更强的语义检索

为什么现在是可选而不是默认：

- 当前更强调项目稳定、依赖轻、离线可演示
- 不希望默认路径被外部模型下载和环境差异拖慢

#### `Docker / docker-compose`

这是项目的运行编排层。

对应功能：

- 用容器统一 Web、Worker、Redis 的启动方式
- 降低本地环境差异
- 方便后续给别人演示或部署到云主机

为什么适合这里：

- 这个项目已经有多进程协作，不再是一个命令就能完整表达的单体脚本
- 用 `docker-compose` 能更清楚地体现工程化能力
### 3.3 技术栈与功能映射总结

如果从“项目问题”反推“为什么要选这些技术”，可以这样理解：

- 需要对外提供稳定接口，所以用了 `FastAPI + Pydantic`
- 需要异步执行长任务，所以用了 `Celery + Redis`
- 需要保留历史和状态，所以用了 `SQLAlchemy + SQLite`
- 需要本地能稳定演示，所以用了 `local-stub + local-hash`
- 需要前端直接展示，所以用了原生 `HTML + CSS + JavaScript`
- 需要多服务更容易启动，所以补了 `Docker + docker-compose`

这套栈的核心价值不是“堆技术名词”，而是让 `Protein Agent` 从一个同步调用 demo，变成一个更像真实业务中间件的专门 Agent 工程。

### 3.4 执行流程

```text
用户在前端或接口发起 POST /run
-> FastAPI 创建 task_id，并在 SQLite 中写入一条 PENDING 记录
-> FastAPI 把任务派发给 Celery
-> Worker 读取任务，先把状态改为 RUNNING，并持续追加 trace_events
-> Worker 调用 ProteinAgent.prepare_execution(...)
   - Router LLM 自然语言任务识别（失败时回退到关键词路由）
   - 蛋白质序列解析
   - RAG 检索
   - 选择模型
-> Worker 调用对应模型并生成候选结果或预测摘要
-> Worker 合并模型输出和本地指标，整理最终 AgentExecutionResult
-> Worker 把 SUCCESS / FAILED 结果写回 SQLite
-> 前端主页面轮询 /tasks/{task_id}
   - 对话区按步骤逐步展示执行轨迹
-> 用户点击“查看完整结果”后，跳转到 /tasks/{task_id}/view
   - 查看候选序列
   - 查看评价指标
   - 查看 RAG 上下文
   - 查看完整文本输出
-> 用户也可以通过 /archive 查看历史档案，通过 /system 查看运行状态和模型配置
```

### 3.5 当前状态说明

- `/run` 现在已经是异步任务入口，不再直接返回最终结果
- 如果没有启动 Redis 和 Celery worker，任务会停留在 `PENDING`
- 当前数据库里会保留请求、模型、指标、RAG 上下文和错误信息

## 4. 项目目录

```text
protein-agent/
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── README.md
├── requirements.txt
├── requirements-rag.txt
├── app/
│   ├── agent.py
│   ├── config.py
│   ├── database.py
│   ├── knowledge_base.py
│   ├── main.py
│   ├── metrics.py
│   ├── model_clients.py
│   ├── models.py
│   ├── router.py
│   ├── schemas.py
│   ├── sequence_utils.py
│   ├── worker.py
│   ├── data/
│   │   └── protein_knowledge.jsonl
│   └── static/
│       ├── archive.html
│       ├── archive.js
│       ├── app.js
│       ├── favicon.svg
│       ├── index.html
│       ├── protein-field.svg
│       ├── shared.js
│       ├── system.html
│       ├── system.js
│       ├── task.html
│       ├── task.js
│       └── styles.css
└── tests/
    ├── test_agent.py
    ├── test_knowledge_base.py
    ├── test_router.py
    └── test_sequence_utils.py
```

## 5. 核心文件职责

### [app/main.py](/Users/alakazan/Documents/Playground/求职/protein-agent/app/main.py)

负责 FastAPI 服务入口和接口定义。

当前接口：

- `GET /`
- `GET /chat`
- `GET /archive`
- `GET /system`
- `GET /health`
- `GET /models`
- `GET /knowledge`
- `POST /route`
- `POST /run`
- `GET /tasks/{task_id}`
- `GET /tasks/{task_id}/view`
- `GET /history`
- `GET /static/{asset_path}`

### [app/worker.py](/Users/alakazan/Documents/Playground/求职/protein-agent/app/worker.py)

负责 Celery worker 侧的任务消费与结果落库。

当前行为：

- 接收 `task_id + query + protein_sequence + include_metrics`
- 分阶段执行 `prepare_execution(...)`、`run_model(...)`、`finalize_execution(...)`
- 在 `RUNNING -> SUCCESS / FAILED` 过程中持续追加 `trace_events`
- 将结果写回 `agent_executions` 表
- 失败时把异常写入 `error_message`

### [app/agent.py](/Users/alakazan/Documents/Playground/求职/protein-agent/app/agent.py)

负责业务主编排。

主流程：

- 路由任务类型
- 提取或校验蛋白质序列
- 检索 RAG 上下文
- 选择模型配置
- 调用 provider
- 合并本地指标
- 组装结构化输出

### [app/router.py](/Users/alakazan/Documents/Playground/求职/protein-agent/app/router.py)

负责任务路由。

当前规则：

- 优先使用 `Router LLM` 做自然语言分类
- 当 Router LLM 不可用或解析失败时，回退到关键词路由
- 命中 `适配体 / 核酸 / 核算 / aptamer / dna / rna` -> `aptamer_generation`
- 命中 `多肽 / peptide` -> `peptide_generation`
- 命中 `蛋白质 / 蛋白 / protein / 预测 / 打分 / 分类` -> `protein_prediction`
- 同时命中多肽和适配体时直接报错，避免歧义

### [app/sequence_utils.py](/Users/alakazan/Documents/Playground/求职/protein-agent/app/sequence_utils.py)

负责蛋白质序列抽取与规范化。

当前策略：

- 优先识别显式标签：`蛋白质序列`、`蛋白序列`、`protein sequence`、`sequence`、`seq`
- 安全 fallback：只接受独立的大写氨基酸 token
- 避免把普通英文句子误识别成蛋白质序列

### [app/knowledge_base.py](/Users/alakazan/Documents/Playground/求职/protein-agent/app/knowledge_base.py)

负责蛋白质领域 RAG 检索。

当前实现：

- 默认后端：`local-hash`
- 可选后端：`sentence-transformer`
- 使用共享缓存，避免每个请求重复初始化知识库
- 从 `app/data/protein_knowledge.jsonl` 读取知识条目

### [app/model_clients.py](/Users/alakazan/Documents/Playground/求职/protein-agent/app/model_clients.py)

负责模型 provider 适配。

当前支持：

- `LocalStubSequenceModelClient`
- `GenericJsonSequenceModelClient`
- `OpenAICompatibleSequenceModelClient`

### [app/metrics.py](/Users/alakazan/Documents/Playground/求职/protein-agent/app/metrics.py)

负责本地启发式指标计算。

当前输出包括：

- 蛋白预测：`binding_potential_score`、`prediction_label`
- 多肽生成：`binding_proxy_score`、`shared_trimer_ratio`
- 适配体生成：`affinity_proxy_score`、`gc_content`

### [app/database.py](/Users/alakazan/Documents/Playground/求职/protein-agent/app/database.py)

负责异步数据库引擎和 `AsyncSession` 装配。

### [app/models.py](/Users/alakazan/Documents/Playground/求职/protein-agent/app/models.py)

负责 ORM 数据结构定义。

当前核心表：

- `agent_executions`

当前状态字段：

- `PENDING`
- `RUNNING`
- `SUCCESS`
- `FAILED`

当前还会记录这些与路由相关的字段：

- `route_reason`
- `route_source`
- `router_output_text`

### [app/static/index.html](/Users/alakazan/Documents/Playground/求职/protein-agent/app/static/index.html)

负责 `Chat` 页面结构。

### [app/static/app.js](/Users/alakazan/Documents/Playground/求职/protein-agent/app/static/app.js)

负责前端交互逻辑。

当前行为：

- 调用 `/health`、`/models`、`/run`、`/tasks/{task_id}`
- 发起任务后轮询状态
- 将 `trace_events` 以分步 reveal 的方式逐条展示在主对话中
- 任务完成后提供详情页跳转入口

### [app/static/archive.html](/Users/alakazan/Documents/Playground/求职/protein-agent/app/static/archive.html)

负责 `Archive` 页面结构。

### [app/static/archive.js](/Users/alakazan/Documents/Playground/求职/protein-agent/app/static/archive.js)

负责读取 `/history` 并按状态筛选任务档案。

### [app/static/system.html](/Users/alakazan/Documents/Playground/求职/protein-agent/app/static/system.html)

负责 `System` 页面结构。

### [app/static/system.js](/Users/alakazan/Documents/Playground/求职/protein-agent/app/static/system.js)

负责读取 `/health`、`/models`、`/knowledge` 并展示系统状态。

### [app/static/task.html](/Users/alakazan/Documents/Playground/求职/protein-agent/app/static/task.html)

负责任务详情页结构。

### [app/static/task.js](/Users/alakazan/Documents/Playground/求职/protein-agent/app/static/task.js)

负责详情页数据读取、轮询和结构化渲染。

当前也会单独展示：

- Router LLM 的原始路由输出
- 路由来源（Router LLM 或关键词 fallback）

### [app/static/shared.js](/Users/alakazan/Documents/Playground/求职/protein-agent/app/static/shared.js)

负责多页面共享的前端格式化和导航逻辑。

### [tests/test_agent.py](/Users/alakazan/Documents/Playground/求职/protein-agent/tests/test_agent.py)

验证同步业务主链路。

### [tests/test_knowledge_base.py](/Users/alakazan/Documents/Playground/求职/protein-agent/tests/test_knowledge_base.py)

验证知识库数据完整性和离线检索逻辑。

## 6. 配置模型

主要配置来自 [.env.example](/Users/alakazan/Documents/Playground/求职/protein-agent/.env.example)。

### 6.1 模型配置

- `ROUTER_LLM_PROVIDER`
- `ROUTER_LLM_MODEL_NAME`
- `ROUTER_LLM_BASE_URL`
- `ROUTER_LLM_API_KEY`
- `ROUTER_LLM_TIMEOUT_SECONDS`
- `ROUTER_LLM_FALLBACK_TO_KEYWORDS`
- `LLM_PROVIDER`
- `MODEL_NAME`
- `MODEL_BASE_URL`
- `MODEL_API_KEY`
- `MODEL_TIMEOUT_SECONDS`
- `PROTEIN_MODEL_PROVIDER`
- `PROTEIN_MODEL_NAME`
- `PROTEIN_MODEL_BASE_URL`
- `PROTEIN_MODEL_API_KEY`
- `PEPTIDE_MODEL_PROVIDER`
- `PEPTIDE_MODEL_NAME`
- `PEPTIDE_MODEL_BASE_URL`
- `PEPTIDE_MODEL_API_KEY`
- `APTAMER_MODEL_PROVIDER`
- `APTAMER_MODEL_NAME`
- `APTAMER_MODEL_BASE_URL`
- `APTAMER_MODEL_API_KEY`

### 6.2 RAG 配置

- `RAG_ENABLED`
- `RAG_BACKEND`
- `RAG_TOP_K`
- `RAG_DATA_PATH`
- `RAG_EMBEDDING_MODEL`

### 6.3 异步任务与数据库配置

- `DATABASE_URL`
- `CELERY_BROKER_URL`

## 7. Provider 行为

### 7.1 `local-stub`

- 不依赖网络
- 多肽和适配体通过简单启发式规则生成候选序列
- 蛋白预测返回本地摘要文本

### 7.2 `generic-json`

请求体默认是：

```json
{
  "model": "paired-peptide-generator",
  "task_type": "peptide_generation",
  "query": "请根据蛋白质序列生成配对多肽",
  "protein_sequence": "MKTAYIAKQRQISFVKSHFSRQDILDLWIYHTQGYFP"
}
```

当前优先解析这些字段：

- `generated_sequence`
- `sequence`
- `candidate_sequence`
- `candidate`
- `summary`
- `prediction`
- `message`
- `result`
- `text`
- `metrics`

### 7.3 `openai-compatible`

- 可用于任务模型，也可用于 `Router LLM`
- 当前项目已将其用于豆包路由模型接入

当前行为：

- 调用 `/chat/completions`
- 构造 `system + user` 消息
- 期望在输出中提取 `<sequence>...</sequence>` 里的候选序列
- 适合接豆包等 OpenAI-compatible 网关

## 8. 当前接口

### 8.1 `GET /health`

返回：

- 服务状态
- 数据库可用性
- 模型配置概览
- RAG 状态

### 8.2 `GET /models`

返回三个任务槽位当前的 provider、model_name、base_url、configured。

### 8.3 `POST /route`

只做任务类型路由，不执行模型。

### 8.4 `POST /run`

创建任务并返回：

```json
{
  "task_id": "uuid",
  "status": "PENDING",
  "message": "Job created and is running in the background."
}
```

### 8.5 `GET /tasks/{task_id}`

返回某次任务的完整状态记录，包括：

- 状态
- 输入 query
- 任务类型
- 模型信息
- 候选序列
- 文本输出
- 指标
- RAG 上下文
- 错误信息

### 8.6 `GET /history`

按时间倒序返回历史任务列表。

## 9. 本地运行

### 9.1 仅启动 Web

适合看前端、看 `/health`、看 `/route`、看页面结构。

```bash
cd /Users/alakazan/Documents/Playground/求职/protein-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

说明：

- 这种方式下 `/run` 仍然会创建任务
- 但如果没有 Redis 和 Celery worker，任务会一直停在 `PENDING`

### 9.2 本地完整异步链路

```bash
cd /Users/alakazan/Documents/Playground/求职/protein-agent
source .venv/bin/activate
redis-server
```

另开一个终端：

```bash
cd /Users/alakazan/Documents/Playground/求职/protein-agent
source .venv/bin/activate
celery -A app.worker.celery_app worker -l info
```

再开一个终端：

```bash
cd /Users/alakazan/Documents/Playground/求职/protein-agent
source .venv/bin/activate
uvicorn app.main:app --reload
```

### 9.3 Docker Compose

```bash
docker-compose up --build
```

## 10. 当前验证情况

已确认：

- `python -m unittest discover -s tests` 当前通过，`20` 个测试全绿
- `from app.main import app` 可导入
- `from app.worker import celery_app` 可导入
- 本地 `GET /health`、`POST /route`、`POST /run` 可正常返回

已观察到的事实：

- 未启动 worker 时，`/run` 创建的任务会持续停留在 `PENDING`
- 当前测试主要覆盖同步 agent 核心，还没有覆盖完整异步链路

## 11. 当前限制

- 当前对话入口虽然已接入 `Router LLM`，但系统本质上仍然只支持 `多肽生成 / 核酸适配体生成 / 蛋白质预测` 这 3 类任务；纯寒暄或无关自由对话不会被正常执行
- `Router LLM` 只负责任务识别，真正的任务模型当前仍是 `local-stub`，真实多肽/适配体/蛋白模型还没有正式接入
- 当前没有 broker / worker 可用性检查，`/health` 只检查了数据库，没有检查 Redis 和 worker
- `worker.py` 当前还没有在任务开始时把状态显式写成 `RUNNING`
- 前端会轮询异步任务，但没有超时终止、没有任务取消，也没有导出能力
- `openai-compatible` 当前主要依赖 `<sequence>` 标签提取，不支持更稳的结构化输出协议
- `generic-json` 只支持一套统一协议，真实模型若字段不同，需要继续补适配
- SQLite 适合本地演示和作品集，不适合更高强度并发
- 当前测试还没有覆盖 `/run -> /tasks -> /history` 的完整集成链路，也没有覆盖前端轮询和多页面跳转逻辑

## 12. 下一步建议

1. 先把异步链路补完整：`RUNNING` 状态写回、broker/worker 健康检查、任务超时/失败提示。
2. 补集成测试：至少覆盖 `/run`、`/tasks/{task_id}`、`/history`、worker 落库流程和前端轮询主链路。
3. 再接真实多肽模型 API 和真实适配体模型 API，并补结构化输出协议。
4. 最后补固定输入集、页面截图和录屏，用于简历和作品集展示。
