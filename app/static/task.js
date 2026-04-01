const {
  escapeHtml,
  fetchJson,
  formatDateTime,
  getDisplayTaskLabel,
  isLegacyStaleRecord,
  setActiveNav,
} = window.ProteinUI;

const detailElements = {
  title: document.getElementById("detail-title"),
  subtitle: document.getElementById("detail-subtitle"),
  status: document.getElementById("detail-status"),
  taskId: document.getElementById("detail-task-id"),
  taskType: document.getElementById("detail-task-type"),
  keywords: document.getElementById("detail-keywords"),
  model: document.getElementById("detail-model"),
  createdAt: document.getElementById("detail-created-at"),
  completedAt: document.getElementById("detail-completed-at"),
  sequence: document.getElementById("detail-sequence"),
  metrics: document.getElementById("detail-metrics"),
  query: document.getElementById("detail-query"),
  output: document.getElementById("detail-output"),
  routerOutput: document.getElementById("detail-router-output"),
  rag: document.getElementById("detail-rag"),
  trace: document.getElementById("detail-trace"),
};

function getTaskIdFromLocation() {
  const pathParts = window.location.pathname.split("/").filter(Boolean);
  const taskIndex = pathParts.indexOf("tasks");
  if (taskIndex >= 0 && pathParts[taskIndex + 1]) {
    return pathParts[taskIndex + 1];
  }
  return new URLSearchParams(window.location.search).get("task_id") || "";
}

function renderMetrics(metrics) {
  const entries = Object.entries(metrics || {});
  if (!entries.length) {
    detailElements.metrics.innerHTML = '<p class="empty-copy">当前任务未返回评价指标。</p>';
    return;
  }
  detailElements.metrics.innerHTML = entries
    .map(
      ([key, value]) => `
        <article class="metric-card">
          <p class="metric-label">${escapeHtml(key)}</p>
          <strong>${escapeHtml(typeof value === "number" ? value.toFixed(3) : value)}</strong>
        </article>
      `
    )
    .join("");
}

function renderTrace(events) {
  if (!events || !events.length) {
    detailElements.trace.innerHTML = `
      <li class="trace-row">
        <span class="trace-bullet"></span>
        <div>
          <p class="trace-title">暂无轨迹</p>
          <p class="trace-detail">当前记录未写入执行轨迹。</p>
        </div>
      </li>
    `;
    return;
  }

  detailElements.trace.innerHTML = events
    .map(
      (event) => `
        <li class="trace-row">
          <span class="trace-bullet trace-bullet-${escapeHtml(event.status || "completed")}"></span>
          <div>
            <p class="trace-title">${escapeHtml(event.title || event.step || "步骤")}</p>
            <p class="trace-detail">${escapeHtml(event.detail || "")}</p>
          </div>
        </li>
      `
    )
    .join("");
}

function renderRagContext(chunks) {
  if (!chunks || !chunks.length) {
    detailElements.rag.innerHTML = '<p class="empty-copy">当前任务未命中可展示的检索上下文。</p>';
    return;
  }
  detailElements.rag.innerHTML = chunks
    .map(
      (chunk, index) => `
        <article class="knowledge-card">
          <p class="eyebrow">Chunk ${index + 1} · score ${escapeHtml(Number(chunk.score || 0).toFixed(4))}</p>
          <h3>${escapeHtml(chunk.source || "unknown")}</h3>
          <p>${escapeHtml(chunk.text || "")}</p>
        </article>
      `
    )
    .join("");
}

function buildSubtitle(task) {
  if (isLegacyStaleRecord(task)) {
    return "该记录来自旧版页面改造前的遗留任务，不包含完整执行轨迹，因此详情页不再继续轮询。";
  }
  if (task.status === "FAILED") {
    return task.error_message || "任务执行失败，请结合下方错误信息进行排查。";
  }
  if (task.status === "SUCCESS" && task.route_reason) {
    return task.route_reason;
  }
  return "后台任务仍在执行中，详情页会持续刷新并同步最新状态。";
}

function renderTask(task) {
  document.title = `Protein Agent - ${task.task_id}`;
  detailElements.title.textContent = getDisplayTaskLabel(task);
  detailElements.subtitle.textContent = buildSubtitle(task);
  detailElements.status.className = "status-pill";
  if (task.status === "SUCCESS") {
    detailElements.status.classList.add("is-success");
  } else if (task.status === "FAILED") {
    detailElements.status.classList.add("is-error");
  } else {
    detailElements.status.classList.add("is-running");
  }
  detailElements.status.textContent = task.status || "UNKNOWN";
  detailElements.taskId.textContent = `task_id: ${task.task_id}`;
  detailElements.taskType.textContent = getDisplayTaskLabel(task);
  detailElements.keywords.textContent = (task.matched_keywords || []).join("、") || "--";
  detailElements.model.textContent = task.model_name
    ? `${task.model_name} (${task.model_provider})`
    : "--";
  detailElements.createdAt.textContent = formatDateTime(task.created_at);
  detailElements.completedAt.textContent = formatDateTime(task.completed_at);
  detailElements.sequence.textContent = task.generated_sequence || "暂无候选序列";
  detailElements.query.textContent = task.request_query || "--";
  detailElements.output.textContent = task.output_text || task.error_message || "--";
  detailElements.routerOutput.textContent = task.router_output_text || "当前任务未返回路由模型输出";

  if (isLegacyStaleRecord(task)) {
    detailElements.sequence.textContent = "该记录为历史遗留任务，未生成完整候选结果。";
    detailElements.routerOutput.textContent = "历史遗留任务未保留路由模型输出。";
  }

  renderMetrics(task.metrics);
  renderTrace(task.trace_events);
  renderRagContext(task.rag_context);
}

async function loadTask() {
  const taskId = getTaskIdFromLocation();
  if (!taskId) {
    detailElements.title.textContent = "缺少 task_id";
    detailElements.subtitle.textContent = "当前页面无法识别要查看的任务记录。";
    return;
  }

  try {
    const task = await fetchJson(`/tasks/${encodeURIComponent(taskId)}`);
    renderTask(task);
    if (!isLegacyStaleRecord(task) && task.status !== "SUCCESS" && task.status !== "FAILED") {
      window.setTimeout(loadTask, 1200);
    }
  } catch (error) {
    detailElements.title.textContent = "读取任务失败";
    detailElements.subtitle.textContent = error.message;
    detailElements.status.className = "status-pill is-error";
    detailElements.status.textContent = "ERROR";
  }
}

setActiveNav("");
loadTask();
