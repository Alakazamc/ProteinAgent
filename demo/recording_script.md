# ProteinAgent 录屏脚本

目标时长：`60 - 90 秒`

## 0 - 10 秒：开场

- 打开 `System` 页面
- 讲：
  - “这个项目不是简单的 RAG 问答 demo，而是一个面向垂直任务的异步 AI Agent 编排系统。”
  - “它把自然语言路由、模型网关、RAG、异步调度、执行轨迹和历史持久化串成了一条完整链路。”

## 10 - 25 秒：展示系统状态

- 指向 `database / queue / models / rag`
- 讲：
  - “后端是 `FastAPI + Celery + Redis + SQLite`。”
  - “我在 `/health` 里把队列、模型和知识库状态单独暴露出来，方便排查部署问题和演示系统 readiness。”

## 25 - 45 秒：跑一个生成任务

- 切到 `Chat`
- 输入 Demo 1 的多肽生成请求并发送
- 讲：
  - “这里先返回 `task_id`，不会阻塞请求。”
  - “后台 worker 接管任务后，会依次记录路由、序列抽取、RAG、模型执行和指标整理的 `trace_events`。”

## 45 - 60 秒：展示任务详情

- 打开任务详情页
- 指向：
  - `route_source`
  - `router_output_text`
  - `trace_events`
  - `metrics`
  - `rag_context`
- 讲：
  - “我把结果、执行轨迹和路由来源都持久化了，所以这不是一次性聊天，而是可追溯的任务系统。”

## 60 - 90 秒：收尾

- 切到 `Archive` 或再展示一个预测任务
- 讲：
  - “为了让它适合作为作品集，我又补了 API 级测试和离线评测集。”
  - “当前离线评测覆盖 `30` 条 query，包含三类任务、Router fallback 和错误路径，路由正确率和成功率都能稳定复现。”

## 录屏注意事项

- 默认使用 `local-stub` 模型，保证 demo 稳定
- 如果接真实 Router LLM，可以额外展示 `router_output_text`
- 不要一口气演示所有页面，优先讲主链路：`System -> Chat -> Task Detail -> Archive`
