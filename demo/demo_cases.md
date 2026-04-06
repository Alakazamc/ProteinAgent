# ProteinAgent Demo Cases

这 3 组输入用于本地录屏、README 展示和面试时讲解项目主链路。默认使用 `local-stub` 任务模型，可稳定复现。

## Demo 1: 多肽生成

- 页面: `Chat`
- 输入:

```json
{
  "query": "请根据蛋白质序列 MKTAYIAKQRQISFVKSHFSRQDILDLWIYHTQGYFP 设计一个配对多肽",
  "include_metrics": true
}
```

- 预期路由: `peptide_generation`
- 预期 route_source: `keyword`
- 预期 trace_events 重点:
  - `queued`
  - `running`
  - `route`
  - `sequence`
  - `rag`
  - `model`
  - `model-output`
  - `metrics`
  - `complete`
- 预期结果页重点:
  - 看到候选多肽序列
  - 看到 `binding_proxy_score`
  - 看到 RAG 参考知识

## Demo 2: 适配体生成（展示 Router fallback）

- 页面: `Chat`
- 输入:

```json
{
  "query": "我想为这个蛋白靶点生成 RNA aptamer",
  "protein_sequence": "MSDIFEAQKIEWHEGAFDTYKGKTVEVQAKGKKVNVAKNVEAAGVDVVAT",
  "include_metrics": true
}
```

- 预期路由: `aptamer_generation`
- 推荐演示方式:
  - 如果已配置真实 `Router LLM`，展示 `router_output_text`
  - 如果走离线模式，可在 README 中讲解 fallback 逻辑
- 预期结果页重点:
  - 看到候选适配体序列
  - 看到 `gc_content`
  - 看到 `route_source` 与 `router_output_text`

## Demo 3: 蛋白预测

- 页面: `Chat` 或 `Task Detail`
- 输入:

```json
{
  "query": "请预测这个蛋白质序列 MNNIRRVAILAGAGGTRAAATLAQEQGADVVVVDDGTTDLDIATQAMKAGADVVVVNQK 的结合潜力",
  "include_metrics": true
}
```

- 预期路由: `protein_prediction`
- 预期 route_source: `keyword`
- 预期 trace_events 重点:
  - `prediction`
  - `metrics`
  - `complete`
- 预期结果页重点:
  - 看到文本分析摘要
  - 看到结构化评价指标
  - 不生成新的候选序列

## 演示建议

- 录屏时先打开 `/system` 页面，展示模型、队列和知识库状态
- 再切到 `/chat` 页面跑 Demo 1 和 Demo 2
- 最后在 `/tasks/{task_id}/view` 或 `Archive` 页面展示历史记录和完整详情
