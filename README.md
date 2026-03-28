# Protein Agent

这是我在 `Agent / AI 应用工程` 方向上的第二个专门项目。  
它不再是通用聊天 agent，而是一个面向 `蛋白质序列 → 任务路由 → 模型调用` 的轻量工程骨架。

项目目录与第一个项目分开，独立放在：

- `/Users/alakazan/Documents/Playground/求职/protein-agent`

当前目标很明确：

- 根据 query 中的关键词选择合适的蛋白质语言模型
- 支持三类任务：
  - `蛋白质预测`
  - `多肽生成`
  - `核酸适配体生成`
- 默认支持 `local-stub` 离线联调
- 预留真实模型 API 对接入口
- 通过离线友好的 RAG 在模型调用前注入蛋白质领域背景知识

## 1. 当前能力

- `GET /health`
- `GET /models`
- `GET /knowledge`
- `GET /`（前端页面）
- `POST /route`
- `POST /run`
- 关键词路由：
  - 命中 `多肽` → 多肽生成模型
  - 命中 `适配体 / 核酸 / 核算` → 核酸适配体生成模型
  - 命中 `蛋白质 / 预测` → 蛋白质预测模型
- 蛋白质序列抽取：
  - 优先识别显式标签：`蛋白质序列`、`蛋白序列`、`protein sequence`、`sequence`、`seq`
  - 安全 fallback：只接受独立的大写氨基酸 token
  - 不再把普通英文句子误识别成蛋白质序列
- 对每个任务返回结构化结果
- 生成任务附带本地启发式评价指标
- RAG 知识增强：
  - 默认后端是 `local-hash`
  - 离线可跑，不依赖联网下载模型
  - 同一份知识库会缓存复用，不会在每个请求里重复初始化
- 自带前端页面，可直接在浏览器里发请求、看路由结果、评价指标和 RAG 检索上下文
  - 新版页面采用“实验工作台”布局
  - 包含状态侧栏、示例切换、指标卡片和结果总览
- 模型 provider 抽象：
  - `local-stub`
  - `generic-json`

## 2. 项目目录

```text
protein-agent/
├── .env.example
├── .gitignore
├── README.md
├── requirements.txt
├── requirements-rag.txt
├── app/
│   ├── agent.py
│   ├── config.py
│   ├── knowledge_base.py
│   ├── main.py
│   ├── metrics.py
│   ├── model_clients.py
│   ├── router.py
│   ├── schemas.py
│   ├── sequence_utils.py
│   ├── data/
│   │   └── protein_knowledge.jsonl
│   └── static/
│       ├── app.js
│       ├── index.html
│       └── styles.css
└── tests/
    ├── test_agent.py
    ├── test_knowledge_base.py
    ├── test_router.py
    └── test_sequence_utils.py
```

## 3. 每个文件负责什么

### [app/main.py](/Users/alakazan/Documents/Playground/求职/protein-agent/app/main.py)

服务入口层。

负责：

- 定义 `FastAPI` 接口
- 接收 query / protein_sequence
- 组装共享的 `ProteinAgent`
- 返回结构化响应

当前接口：

- `GET /`
- `GET /health`
- `GET /models`
- `GET /knowledge`
- `POST /route`
- `POST /run`

另外：

- `GET /static/{asset_path}` 提供前端静态资源

### [app/config.py](/Users/alakazan/Documents/Playground/求职/protein-agent/app/config.py)

配置层。

负责：

- 读取 `.env`
- 解析三类模型配置
- 解析 RAG 配置
- 统一输出 `AppConfig`

核心配置项：

- `PROTEIN_MODEL_PROVIDER`
- `PROTEIN_MODEL_NAME`
- `PROTEIN_MODEL_BASE_URL`
- `PEPTIDE_MODEL_PROVIDER`
- `PEPTIDE_MODEL_NAME`
- `PEPTIDE_MODEL_BASE_URL`
- `APTAMER_MODEL_PROVIDER`
- `APTAMER_MODEL_NAME`
- `APTAMER_MODEL_BASE_URL`
- `RAG_ENABLED`
- `RAG_BACKEND`
- `RAG_TOP_K`
- `RAG_DATA_PATH`
- `RAG_EMBEDDING_MODEL`

### [app/router.py](/Users/alakazan/Documents/Playground/求职/protein-agent/app/router.py)

关键词路由层。

负责：

- 识别 query 中的目标任务
- 决定走哪一个模型槽位
- 拒绝同时命中 `多肽` 和 `适配体` 的歧义 query

路由优先级：

1. `适配体 / 核酸 / 核算`
2. `多肽`
3. `蛋白质 / 预测`

### [app/sequence_utils.py](/Users/alakazan/Documents/Playground/求职/protein-agent/app/sequence_utils.py)

序列处理层。

负责：

- 从 query 中提取蛋白质序列
- 规范化蛋白质序列
- 检查长度和非法字符

当前策略：

- 显式标签优先：`蛋白质序列`、`蛋白序列`、`protein sequence`、`sequence`、`seq`
- 安全 fallback：只接受独立的大写氨基酸 token
- 普通英文自由文本不会再被静默当成蛋白质序列

### [app/knowledge_base.py](/Users/alakazan/Documents/Playground/求职/protein-agent/app/knowledge_base.py)

RAG 检索增强层。

负责：

- 加载 JSONL 格式的蛋白质领域知识条目
- 默认使用 `local-hash` 做轻量检索
- 可选切换到 `sentence-transformer` 后端
- 暴露 `search(query, top_k)` 接口返回最相关的知识片段
- 通过缓存复用知识库实例，避免每个请求重复初始化

核心类/函数：

- `ProteinKnowledgeBase` — 知识库管理与检索
- `RetrievedChunk` — 单条检索结果（text, source, score）
- `get_cached_knowledge_base(...)` — 共享知识库构造函数

### [app/data/protein_knowledge.jsonl](/Users/alakazan/Documents/Playground/求职/protein-agent/app/data/protein_knowledge.jsonl)

内置种子知识库。

包含蛋白质领域背景知识条目，覆盖：

- 蛋白质家族
- 结构生物学
- 多肽药物设计
- 适配体技术
- 计算预测方法

每条格式：`{"text": "...", "source": "...", "category": "..."}`。

### [app/model_clients.py](/Users/alakazan/Documents/Playground/求职/protein-agent/app/model_clients.py)

模型调用适配层。

负责：

- 屏蔽不同模型 provider 的调用差异
- 提供统一的 `run(model_request, model_config)` 能力
- 解析真实模型 API 的 JSON 返回

当前支持：

- `LocalStubSequenceModelClient`
- `GenericJsonSequenceModelClient`

### [app/metrics.py](/Users/alakazan/Documents/Playground/求职/protein-agent/app/metrics.py)

评价指标层。

负责：

- 蛋白质预测的本地启发式指标
- 多肽候选的本地启发式指标
- 适配体候选的本地启发式指标

当前指标不是实验验证指标，只是工程联调用的快速反馈。

### [app/agent.py](/Users/alakazan/Documents/Playground/求职/protein-agent/app/agent.py)

agent 核心编排层。

负责：

- 路由 query
- 提取蛋白质序列
- 检索相关背景知识
- 选择模型配置
- 调用模型 client
- 合并返回文本与评价指标

主流程：

```text
用户 query
→ router.py 判断任务类型
→ sequence_utils.py 提取蛋白质序列
→ knowledge_base.py 检索蛋白质领域背景知识（RAG）
→ agent.py 选择模型配置
→ model_clients.py 调用对应 provider
→ metrics.py 计算评价指标
→ 返回结构化响应（含 RAG 上下文）
```

### [app/static/index.html](/Users/alakazan/Documents/Playground/求职/protein-agent/app/static/index.html)

前端页面入口。

负责：

- 提供浏览器侧交互界面
- 组织“英雄区 + 输入台 + 结果总览”的单页结构
- 填充多肽 / 适配体 / 蛋白预测示例
- 展示任务类型、命中关键词、模型、候选序列、指标和 RAG 检索上下文

### [app/static/app.js](/Users/alakazan/Documents/Playground/求职/protein-agent/app/static/app.js)

前端交互逻辑。

负责：

- 调用 `/health`、`/models`、`/run`
- 将响应回填到页面
- 管理前端示例按钮和状态提示
- 将指标渲染为卡片而不是原始 JSON 文本
- 渲染 RAG 检索上下文

### [app/static/styles.css](/Users/alakazan/Documents/Playground/求职/protein-agent/app/static/styles.css)

前端样式层。

负责：

- 页面视觉风格
- 响应式布局
- 结果卡片、状态区和交互反馈样式
- “实验工作台”式的视觉层次和动画过渡

### [tests/test_router.py](/Users/alakazan/Documents/Playground/求职/protein-agent/tests/test_router.py)

验证关键词路由逻辑。

### [tests/test_agent.py](/Users/alakazan/Documents/Playground/求职/protein-agent/tests/test_agent.py)

验证 agent 主流程、stub 模型分支和异常分支。

### [tests/test_knowledge_base.py](/Users/alakazan/Documents/Playground/求职/protein-agent/tests/test_knowledge_base.py)

验证知识库数据完整性、离线检索与容错行为。

### [tests/test_sequence_utils.py](/Users/alakazan/Documents/Playground/求职/protein-agent/tests/test_sequence_utils.py)

验证序列抽取规则，避免英文自然语言误判。

## 4. Generic JSON 模型 API 约定

如果后面要接真实模型 API，当前工程默认约定模型接口接受这样的 JSON：

```json
{
  "model": "paired-peptide-generator",
  "task_type": "peptide_generation",
  "query": "请根据蛋白质序列生成配对多肽",
  "protein_sequence": "MKTAYIAKQRQISFVKSHFSRQDILDLWIYHTQGYFP"
}
```

推荐返回：

```json
{
  "generated_sequence": "QRQISFVKSHFSRQ",
  "summary": "模型返回一个候选多肽。",
  "metrics": {
    "remote_score": 0.81
  }
}
```

蛋白质预测分支可返回：

```json
{
  "prediction": "该蛋白具有中等结合潜力。",
  "metrics": {
    "confidence": 0.72
  }
}
```

当前解析器会优先读取这些字段：

- `generated_sequence`
- `sequence`
- `candidate_sequence`
- `summary`
- `prediction`
- `message`
- `result`
- `metrics`

## 5. 本地运行

```bash
cd /Users/alakazan/Documents/Playground/求职/protein-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

如果你直接复用我已经配好的本地环境，可以用：

```bash
cd /Users/alakazan/Documents/Playground/求职/protein-agent
source .venv/bin/activate
uvicorn app.main:app --reload
```

如果你想启用可选的 `sentence-transformer` 语义检索后端，再额外安装：

```bash
pip install -r requirements-rag.txt
```

默认的 `local-hash` RAG 不会联网下载任何模型。  
如果切换到 `sentence-transformer` 后端，推荐显式使用本地模型缓存或本地模型目录。

## 6. 接口示例

### 6.1 查看模型配置

```bash
curl http://127.0.0.1:8000/models
```

### 6.2 查看知识库状态

```bash
curl http://127.0.0.1:8000/knowledge
```

### 6.3 打开前端页面

启动服务后访问：

```text
http://127.0.0.1:8000/
```

页面结构包括：

- 顶部工作台概览
- 状态侧栏（服务状态 / 模型数量 / RAG 状态）
- 示例切换区
- 输入控制台
- 结果总览卡片
- 指标卡片区与上下文输出区

### 6.4 仅查看路由结果

```bash
curl -X POST http://127.0.0.1:8000/route \
  -H "Content-Type: application/json" \
  -d '{
    "query": "请根据蛋白质序列 MKTAYIAKQRQISFVKSHFSRQDILDLWIYHTQGYFP 生成一个配对多肽"
  }'
```

### 6.5 执行多肽生成

```bash
curl -X POST http://127.0.0.1:8000/run \
  -H "Content-Type: application/json" \
  -d '{
    "query": "请根据蛋白质序列 MKTAYIAKQRQISFVKSHFSRQDILDLWIYHTQGYFP 生成一个配对多肽"
  }'
```

### 6.6 执行核酸适配体生成

```bash
curl -X POST http://127.0.0.1:8000/run \
  -H "Content-Type: application/json" \
  -d '{
    "query": "请为这个蛋白质设计核酸适配体",
    "protein_sequence": "MKTAYIAKQRQISFVKSHFSRQDILDLWIYHTQGYFP"
  }'
```

## 7. RAG 检索增强

### 7.1 工作原理

在 `agent.py` 的 `run()` 流程中，当 RAG 启用时：

1. 用户 query 被发送给 `ProteinKnowledgeBase.search()`
2. 默认后端使用 `local-hash` 将 query 和知识条目映射到同一特征空间
3. 按相似度返回 top-k 条最相关的知识片段
4. 检索到的背景知识注入到输出文本的“参考知识”段落中
5. 同时通过 API 的 `rag_context` 字段返回给调用方

### 7.2 配置

通过 `.env` 控制：

```bash
RAG_ENABLED=true
RAG_BACKEND=local-hash              # local-hash | sentence-transformer
RAG_TOP_K=3
RAG_DATA_PATH=
RAG_EMBEDDING_MODEL=all-MiniLM-L6-v2
```

### 7.3 扩展知识库

在 `app/data/protein_knowledge.jsonl` 中追加条目即可，每条一行 JSON：

```json
{"text": "你的知识内容", "source": "来源标注", "category": "分类标签"}
```

重启服务后自动生效。

## 8. 当前限制

- 路由仍然是显式关键词匹配，不是语义分类
- `local-stub` 生成结果只用于联调，不代表真实生物学有效性
- 评价指标是启发式分数，不是实验或 benchmark 指标
- `generic-json` 默认只支持一种统一的 JSON 协议，真实模型若字段不同，需要在 `model_clients.py` 中补适配
- 默认 RAG 是轻量离线后端，检索质量优先保证稳定性，不追求最强语义效果
- 如果切换到 `sentence-transformer` 后端，需要本地已有模型缓存或显式指定本地模型目录
- 前端当前仍是单页控制台，没有历史记录、批量任务和结果导出
- 当前已经通过本地 `uvicorn` 启动和 `curl` 请求验证了首页与静态资源映射；尚未补真实浏览器截图或录屏级验收

## 9. 下一步

1. 对接真实多肽模型 API 和真实适配体模型 API
2. 为生成结果补充更可信的 rerank / 评价逻辑
3. 增加 Demo 请求集和简单前端或 notebook 展示
4. 如果后续确实需要更强 RAG，再为 `sentence-transformer` 后端补本地模型目录配置
