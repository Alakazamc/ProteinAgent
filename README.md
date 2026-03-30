# Protein Agent

这是我在 `Agent / AI 应用工程` 方向上的第二个专门项目。  
它不再是一个纯粹的同步玩具脚本，目前已被升级重构为一个**基于高并发异步架构（Celery + Redis + FastAPI + SQLite持久化）**的企业级工程骨干。

项目定位：**面向 `蛋白质序列 → 任务路由 → 模型调用` 的轻量级高并发任务下发工作台**。

## 1. 核心架构与技术栈

本项目的架构严格遵循了现代 AI SaaS 中间件的标准三层结构：

- **Web 网关与 API 层：`FastAPI`**
  - 使用异步 I/O (ASGI)，天然支持高爆发并发访问。
  - 所有请求经过 `Pydantic` 严格校验序列合法性。
  - 提供 RESTful 接口进行模型管理查探、代理路由决策。
- **任务消息队列层：`Celery` + `Redis`**
  - 对于耗时长的大模型推理调用，FastAPI 收到请求后会在第一时间生成唯一 `task_id`，交由 Redis Broker 派发给后端的 Celery Worker，防止 HTTP 连接长时间阻塞导致前端 504 Gateway Timeout。
- **持久化记录层：`SQLAlchemy 2.0` + `aiosqlite` (SQLite)**
  - 利用异步游标引擎全链路记录每一次 AI Worker 的执行状态（`PENDING` -> `RUNNING` -> `SUCCESS`），并详尽保留用户的 Query、生成的预测数据、各类模型跑分指标（Metrics）与历史 RAG 上下文溯源追查。
- **业务集成：大模型标准化接入**
  - 不仅保留了离线测试的 `local-stub` 桩代码，更内置了 `openai-compatible` ModelClient！现在已直接支持对接豆包大模型（Volcengine）和各类基于 GPT/DeepSeek API 格式的大模型。
- **容器编排**
  - 提供了完整的 `Dockerfile` 与 `docker-compose.yml`。

## 2. 界面展示机制

自带原生 JavaScript 前端工作台页面，无需单独配 React/Vue 环境。支持：
- 轮询机制（Polling）：下发任务后即时显示 `后台异步执行中...`，轮询 `/tasks/{task_id}` 获取最终生成状态。
- **历史跑题回放**：通过异步对接 SQLite 查询接口，页面拥有了“历史运行记录”看板，点击即可随时回看过去命中的候选分子片段以及得分。

## 3. 项目目录设计

```text
protein-agent/
├── .env.example
├── .gitignore
├── docker-compose.yml   <-- 生产/演示用：一键编排 (Web+Worker+Redis)
├── Dockerfile          <-- 镜像构建规范
├── README.md
├── requirements.txt    <-- 运行时：涵盖了 fastapi, celery, sqlalchemy, etc.
├── app/
│   ├── main.py         <-- FastAPI 路由和任务调度（网关）
│   ├── worker.py       <-- Celery 异步爬虫 / 大模型推理端点
│   ├── database.py     <-- SQLAlchemy 异步引擎装配器
│   ├── models.py       <-- ORM: AgentExecutionRecord 数据表
│   ├── agent.py        <-- Agent 核心业务逻辑实现
│   ├── model_clients.py<-- 模型适配层 (local-stub / generic-json / openai-compatible)
│   ├── knowledge_base.py<- RAG 向量检索
│   ├── router.py       <-- 关键词决策
│   ├── schemas.py      <-- Pydantic DTO
│   ├── sequence_utils.py<- 序列合规与抽取
│   ├── config.py       <-- 环境加载设定
│   ├── data/
│   │   ├── protein_knowledge.jsonl
│   │   └── protein_agent.db  <-- SQLite 本地化存储库自动生成于此
│   └── static/
│       ├── app.js
│       ├── index.html
│       └── styles.css
└── tests/              <-- pytest 单元回归测试
```

## 4. 全链路执行流程（Worker Flow）

```text
 用户发出多肽请求 (HTTP POST /run)
 ├──> [FastAPI] main.py 解析验证、写入数据库生成状态 PENDING，返回 task_id
 ├──> 前端收到 task_id，开启 2.5s 定时请求 /tasks/{task_id}
 └──> [Celery - worker.py] 从 Redis 队列抢到任务，连接 DB 将状态置为 RUNNING
      ├──> router.py 鉴权并决定任务路线 (PEPTIDE_GENERATION)
      ├──> sequence_utils.py 检测蛋白质串是否合规
      ├──> knowledge_base.py 进行本地 FAISS RAG 背景增强
      ├──> agent.py 判断为 openai-compatible，发起对 豆包 API 的组装与网络通信
      ├──> 提取并解析模型返回结果 (xml 的 <sequence> 等设定标签)
      └──> metrics.py 计算该项输出的先验启发式生物学分数
      └──> 更新 SQLite status 为 SUCCESS 并将组装内容填回记录。
前端第 N 次轮询发现变为了 SUCCESS，停止轮询，页面瞬间填充！
```

## 5. 本地运行体验

本项目支持两种环境的迅速拉起：

### 方案 A：极致省心的 Docker-Compose (推荐)
如果你电脑上有强大的 Docker 守护进程，这是最规范的操作模式：
```bash
docker-compose up --build
```
然后直接打开浏览器：`http://127.0.0.1:8000`

### 方案 B：Mac/Linux 本地双终端开发调试
> 必须保障你提前通过 `brew install redis` 安装了 Redis。

**步骤 1: 准备环境**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```
（在 `.env` 中填上你想连接的真实 OpenAI 格式的 API 秘钥与 Base URL，如未配置会 fallback 给本地的 mock桩）

**步骤 2: 启动 API 和网关 (终端 1)**
```bash
uvicorn app.main:app --reload --port 8001
```
浏览器进入工作台：`http://127.0.0.1:8001`

**步骤 3: 启动执行工人 (终端 2)**
```bash
source .venv/bin/activate
celery -A app.worker.celery_app worker -l info
```

## 6. RAG (基于知识库的生成增强)
项目支持不依赖外部图数据库的轻量 FAISS 缓存型语义搜索算法。
默认采取 `local-hash`，在 `local-stub` 状态下快速体验。
你只需向 `app/data/protein_knowledge.jsonl` 中追写 JSON 行数据：
```json
{"text": "你的专业科普文本", "source": "论文摘要", "category": "多肽"}
```
它们将立刻在下一个推理节点中经由相似度算法自动注入到与 LLM 的系统交互之中。

## 7. 接口开放能力概览 (REST API)
- `POST /run` (异步入队并获取排队凭证)
- `GET /tasks/{task_id}` (获取任意计算流水情况、结果和报错信息)
- `GET /history` (调阅过往历史执行单)
- `POST /route` (前置验证模型选择器)
- `GET /health` (监控存活率、DB 健康与模型配额检查)
- `GET /knowledge` (检视挂载的参考知识库缓存体积)
