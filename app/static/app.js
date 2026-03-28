const EXAMPLES = {
  peptide: {
    query: "请根据蛋白质序列 MKTAYIAKQRQISFVKSHFSRQDILDLWIYHTQGYFP 生成一个配对多肽",
    proteinSequence: "",
  },
  aptamer: {
    query: "请为这个蛋白质设计一个核酸适配体",
    proteinSequence: "MKTAYIAKQRQISFVKSHFSRQDILDLWIYHTQGYFP",
  },
  protein: {
    query: "请帮我预测这个蛋白质的结合潜力",
    proteinSequence: "MKTAYIAKQRQISFVKSHFSRQDILDLWIYHTQGYFP",
  },
};

const elements = {
  serviceStatus: document.getElementById("service-status"),
  modelCount: document.getElementById("model-count"),
  ragStatus: document.getElementById("rag-status"),
  taskType: document.getElementById("task-type"),
  matchedKeywords: document.getElementById("matched-keywords"),
  selectedModel: document.getElementById("selected-model"),
  generatedSequence: document.getElementById("generated-sequence"),
  ragHitCount: document.getElementById("rag-hit-count"),
  metricCount: document.getElementById("metric-count"),
  metricSummary: document.getElementById("metric-summary"),
  metricsGrid: document.getElementById("metrics-grid"),
  routeReason: document.getElementById("route-reason"),
  outputText: document.getElementById("output-text"),
  ragContext: document.getElementById("rag-context"),
  requestStatus: document.getElementById("request-status"),
  requestBadge: document.getElementById("request-badge"),
  form: document.getElementById("run-form"),
  query: document.getElementById("query"),
  proteinSequence: document.getElementById("protein-sequence"),
  includeMetrics: document.getElementById("include-metrics"),
  checkHealth: document.getElementById("check-health"),
  exampleButtons: Array.from(document.querySelectorAll("[data-example]")),
};

function setExample(exampleName) {
  const example = EXAMPLES[exampleName];
  if (!example) {
    return;
  }

  elements.query.value = example.query;
  elements.proteinSequence.value = example.proteinSequence;
  elements.exampleButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.example === exampleName);
  });
}

function setStatus(message, state = "idle") {
  elements.requestStatus.textContent = message;
  elements.requestStatus.classList.remove("status-error", "status-loading");
  elements.requestBadge.classList.remove("is-loading", "is-error", "is-success");

  if (state === "loading") {
    elements.requestStatus.classList.add("status-loading");
    elements.requestBadge.classList.add("is-loading");
    elements.requestBadge.textContent = "请求中";
    return;
  }

  if (state === "error") {
    elements.requestStatus.classList.add("status-error");
    elements.requestBadge.classList.add("is-error");
    elements.requestBadge.textContent = "请求失败";
    return;
  }

  if (state === "success") {
    elements.requestBadge.classList.add("is-success");
    elements.requestBadge.textContent = "请求成功";
    return;
  }

  elements.requestBadge.textContent = "等待请求";
}

function formatValue(value) {
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(3);
  }
  return String(value);
}

function renderMetrics(metrics) {
  const entries = Object.entries(metrics || {});
  elements.metricCount.textContent = String(entries.length);
  elements.metricSummary.textContent = entries.length > 0 ? `${entries.length} 项指标` : "无指标";

  if (entries.length === 0) {
    elements.metricsGrid.innerHTML = '<article class="metric-empty">当前没有可展示的评价指标。</article>';
    return;
  }

  elements.metricsGrid.innerHTML = entries
    .map(
      ([key, value]) => `
        <article class="metric-card">
          <p class="card-label">${key}</p>
          <strong>${formatValue(value)}</strong>
        </article>
      `
    )
    .join("");
}

function renderRagContext(ragContext) {
  if (!ragContext || ragContext.length === 0) {
    return "无相关背景知识。";
  }

  return ragContext
    .map(
      (chunk, index) =>
        `[${index + 1}] score=${Number(chunk.score).toFixed(4)}\n${chunk.text}\n来源: ${chunk.source}`
    )
    .join("\n\n");
}

function renderResult(data) {
  elements.taskType.textContent = data.task_type || "-";
  elements.matchedKeywords.textContent = (data.matched_keywords || []).join(", ") || "-";
  elements.selectedModel.textContent = `${data.selected_model.model_name} (${data.selected_model.provider})`;
  elements.generatedSequence.textContent = data.generated_sequence || "-";
  elements.ragHitCount.textContent = String((data.rag_context || []).length);
  elements.routeReason.textContent = data.route_reason || "-";
  elements.outputText.textContent = data.output_text || "-";
  elements.ragContext.textContent = renderRagContext(data.rag_context || []);
  renderMetrics(data.metrics || {});
}

async function refreshHealth() {
  setStatus("正在检查服务状态...", "loading");
  try {
    const [healthResponse, modelsResponse] = await Promise.all([
      fetch("/health"),
      fetch("/models"),
    ]);

    if (!healthResponse.ok || !modelsResponse.ok) {
      throw new Error("服务状态接口返回失败");
    }

    const health = await healthResponse.json();
    const models = await modelsResponse.json();
    const configuredModels = models.filter((item) => item.configured);

    elements.serviceStatus.textContent = health.status === "ok" ? "服务正常" : "服务异常";
    elements.modelCount.textContent = `${configuredModels.length} / ${models.length}`;

    if (health.rag) {
      const ragInfo = health.rag;
      elements.ragStatus.textContent = ragInfo.enabled
        ? `已启用 (${ragInfo.backend}, ${ragInfo.entries} 条)`
        : "未启用";
    } else {
      elements.ragStatus.textContent = "未检测到";
    }

    setStatus("状态已刷新，可以发起请求。");
  } catch (error) {
    elements.serviceStatus.textContent = "检测失败";
    elements.modelCount.textContent = "0";
    elements.ragStatus.textContent = "检测失败";
    setStatus(`状态检测失败: ${error.message}`, "error");
  }
}

async function runAgent(event) {
  event.preventDefault();
  const payload = {
    query: elements.query.value.trim(),
    protein_sequence: elements.proteinSequence.value.trim() || null,
    include_metrics: elements.includeMetrics.checked,
  };

  setStatus("正在调用 /run ...", "loading");

  try {
    const response = await fetch("/run", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "请求失败");
    }

    renderResult(data);
    setStatus("请求成功，结果已更新。", "success");
  } catch (error) {
    elements.outputText.textContent = String(error.message || error);
    elements.routeReason.textContent = "-";
    elements.ragContext.textContent = "无相关背景知识。";
    elements.generatedSequence.textContent = "-";
    elements.taskType.textContent = "-";
    elements.selectedModel.textContent = "-";
    elements.matchedKeywords.textContent = "-";
    elements.ragHitCount.textContent = "0";
    renderMetrics({});
    setStatus(`请求失败: ${error.message}`, "error");
  }
}

elements.form.addEventListener("submit", runAgent);
elements.checkHealth.addEventListener("click", refreshHealth);
elements.exampleButtons.forEach((button) => {
  button.addEventListener("click", () => setExample(button.dataset.example));
});

setExample("peptide");
renderMetrics({});
refreshHealth();
