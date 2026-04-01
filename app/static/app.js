const EXAMPLES = {
  peptide: {
    query: "请根据蛋白质序列 MKTAYIAKQRQISFVKSHFSRQDILDLWIYHTQGYFP 生成一个配对多肽",
    proteinSequence: "",
  },
  aptamer: {
    query: "请为这个蛋白质设计一个 RNA 核酸适配体",
    proteinSequence: "MKTAYIAKQRQISFVKSHFSRQDILDLWIYHTQGYFP",
  },
  protein: {
    query: "请帮我预测这个蛋白质的结合潜力",
    proteinSequence: "MKTAYIAKQRQISFVKSHFSRQDILDLWIYHTQGYFP",
  },
};

const {
  escapeHtml,
  fetchJson,
  formatTaskLabel,
  setActiveNav,
} = window.ProteinUI;

const elements = {
  serviceStatus: document.getElementById("service-status"),
  modelCount: document.getElementById("model-count"),
  ragStatus: document.getElementById("rag-status"),
  form: document.getElementById("run-form"),
  query: document.getElementById("query"),
  proteinSequence: document.getElementById("protein-sequence"),
  includeMetrics: document.getElementById("include-metrics"),
  checkHealth: document.getElementById("check-health"),
  requestStatus: document.getElementById("request-status"),
  requestBadge: document.getElementById("request-badge"),
  thread: document.getElementById("thread"),
  threadEmpty: document.getElementById("thread-empty"),
  exampleButtons: Array.from(document.querySelectorAll("[data-example]")),
};

const taskRenderState = new Map();

function setExample(name) {
  const example = EXAMPLES[name];
  if (!example) {
    return;
  }
  elements.query.value = example.query;
  elements.proteinSequence.value = example.proteinSequence;
}

function setStatus(message, state = "idle") {
  elements.requestStatus.textContent = message;
  elements.requestBadge.className = "status-pill";

  if (state === "loading") {
    elements.requestBadge.classList.add("is-running");
    elements.requestBadge.textContent = "RUNNING";
    return;
  }
  if (state === "success") {
    elements.requestBadge.classList.add("is-success");
    elements.requestBadge.textContent = "SUCCESS";
    return;
  }
  if (state === "error") {
    elements.requestBadge.classList.add("is-error");
    elements.requestBadge.textContent = "FAILED";
    return;
  }
  elements.requestBadge.textContent = "IDLE";
}

function toggleEmptyState(visible) {
  elements.threadEmpty.classList.toggle("is-hidden", !visible);
}

function appendMessage(html) {
  toggleEmptyState(false);
  const wrapper = document.createElement("div");
  wrapper.innerHTML = html.trim();
  elements.thread.appendChild(wrapper.firstElementChild);
  elements.thread.scrollTop = elements.thread.scrollHeight;
}

function getTaskState(taskId) {
  if (!taskRenderState.has(taskId)) {
    taskRenderState.set(taskId, {
      visibleCount: 0,
      revealTimer: null,
      latestTask: null,
      terminalNotified: false,
    });
  }
  return taskRenderState.get(taskId);
}

function addUserMessage(payload) {
  appendMessage(`
    <article class="message message-user">
      <div class="message-meta">Request</div>
      <div class="message-card">
        <p class="message-text">${escapeHtml(payload.query)}</p>
        ${
          payload.protein_sequence
            ? `<pre class="inline-sequence">${escapeHtml(payload.protein_sequence)}</pre>`
            : ""
        }
      </div>
    </article>
  `);
}

function findOrCreateAgentMessage(taskId) {
  const current = elements.thread.querySelector(`[data-task-id="${taskId}"]`);
  if (current) {
    return current;
  }

  appendMessage(`
    <article class="message message-agent" data-task-id="${escapeHtml(taskId)}">
      <div class="message-meta">Protein Agent</div>
      <div class="message-card">
        <div class="message-heading">
          <strong class="message-title">任务已受理</strong>
          <a class="detail-link is-hidden" href="#">查看完整结果</a>
        </div>
        <p class="message-summary">请求已提交至后台执行链路，系统正在准备任务环境。</p>
        <section class="thinking-block">
          <div class="thinking-head">
            <span class="thinking-tag">Execution Trace</span>
            <span class="thinking-state">处理中</span>
          </div>
          <div class="thinking-stream">
            <article class="thinking-line thinking-line-placeholder">系统正在整理当前任务的执行轨迹。</article>
          </div>
        </section>
      </div>
    </article>
  `);

  return elements.thread.querySelector(`[data-task-id="${taskId}"]`);
}

function toThinkingText(event) {
  const step = event.step || "";
  const detail = event.detail || "";
  if (step === "queued") return "任务已进入队列，等待后台执行资源接管。";
  if (step === "running") return "后台 worker 已接手任务，开始解析请求内容。";
  if (step === "route") return `系统已完成任务识别与路由判断：${detail}`;
  if (step === "sequence") return `系统已完成输入序列校验与规范化：${detail}`;
  if (step === "rag") return `系统已完成知识库检索：${detail}`;
  if (step === "model") return `系统已选择执行模型：${detail}`;
  if (step === "model-output") return detail || "模型已返回原始输出，正在整理结果。";
  if (step === "generation") return `系统已拿到候选生成结果：${detail}`;
  if (step === "prediction") return `系统已完成预测结果整理：${detail}`;
  if (step === "metrics") return `系统已计算结构化评价指标：${detail}`;
  if (step === "complete") return "任务结果已整理完成，可进入详情页查看完整信息。";
  if (step === "failed") return `任务执行失败，系统返回原因：${detail}`;
  return detail || event.title || "系统正在处理当前任务。";
}

function renderThinking(events) {
  if (!events || events.length === 0) {
    return '<article class="thinking-line thinking-line-placeholder">系统正在整理当前任务的执行轨迹。</article>';
  }

  return events
    .map((event) => {
      const status = escapeHtml(event.status || "completed");
      const isLast = event === events[events.length - 1];
      return `<article class="thinking-line thinking-line-${status} ${isLast ? "is-fresh" : ""}">${escapeHtml(toThinkingText(event))}</article>`;
    })
    .join("");
}

function buildSummary(task, settled) {
  if (!settled) {
    return "系统正在按步骤展开当前任务的执行轨迹。";
  }
  if (task.status === "FAILED") {
    return task.error_message || "任务执行失败，请查看详情页中的错误信息。";
  }
  if (task.task_type === "protein_prediction" && task.metrics?.prediction_label) {
    return `蛋白质评分任务已完成，预测标签为 ${task.metrics.prediction_label}。`;
  }
  if (task.generated_sequence) {
    return "任务已完成，候选结果与评价指标已整理完毕。";
  }
  return "任务已完成，完整执行结果已可查看。";
}

function getDisplayPhase(task, settled) {
  if (!settled) {
    return "PROCESSING";
  }
  return task.status || "PENDING";
}

function isTerminal(task) {
  return task.status === "SUCCESS" || task.status === "FAILED";
}

function finalizeTaskStatus(task, state) {
  if (!isTerminal(task) || state.terminalNotified) {
    return;
  }

  if (task.status === "SUCCESS") {
    setStatus("任务执行完成，完整结果已可查看。", "success");
  } else {
    setStatus(`任务执行失败：${task.error_message || "未知错误"}`, "error");
  }
  state.terminalNotified = true;
}

function scheduleTraceReveal(taskId) {
  const state = getTaskState(taskId);
  const task = state.latestTask;
  const total = task?.trace_events?.length ?? 0;

  if (!task) {
    return;
  }

  if (state.visibleCount >= total) {
    finalizeTaskStatus(task, state);
    return;
  }

  if (state.revealTimer) {
    return;
  }

  const delay = state.visibleCount === 0 ? 180 : 420;
  state.revealTimer = window.setTimeout(() => {
    state.revealTimer = null;

    const currentTask = state.latestTask;
    const currentTotal = currentTask?.trace_events?.length ?? 0;
    if (state.visibleCount < currentTotal) {
      state.visibleCount += 1;
      updateAgentMessage(currentTask);
    }

    scheduleTraceReveal(taskId);
  }, delay);
}

function updateAgentMessage(task) {
  const renderState = getTaskState(task.task_id);
  renderState.latestTask = task;

  const totalEvents = task.trace_events?.length ?? 0;
  if (renderState.visibleCount > totalEvents) {
    renderState.visibleCount = totalEvents;
  }
  if (!isTerminal(task)) {
    renderState.terminalNotified = false;
  }

  const card = findOrCreateAgentMessage(task.task_id);
  const visibleEvents = (task.trace_events || []).slice(0, renderState.visibleCount);
  const settled = renderState.visibleCount >= totalEvents && isTerminal(task);
  const taskLabel = task.task_type ? formatTaskLabel(task.task_type) : "任务处理中";

  card.querySelector(".message-title").textContent = `${getDisplayPhase(task, settled)} · ${taskLabel}`;
  card.querySelector(".message-summary").textContent = buildSummary(task, settled);
  card.querySelector(".thinking-stream").innerHTML = renderThinking(visibleEvents);

  const thinkingState = card.querySelector(".thinking-state");
  if (settled && task.status === "SUCCESS") {
    thinkingState.textContent = "已完成";
  } else if (settled && task.status === "FAILED") {
    thinkingState.textContent = "失败";
  } else {
    thinkingState.textContent = "处理中";
  }

  const link = card.querySelector(".detail-link");
  if (settled) {
    link.href = `/tasks/${encodeURIComponent(task.task_id)}/view`;
    link.classList.remove("is-hidden");
  } else {
    link.classList.add("is-hidden");
  }

  elements.thread.scrollTop = elements.thread.scrollHeight;
  scheduleTraceReveal(task.task_id);
  if (settled) {
    finalizeTaskStatus(task, getTaskState(task.task_id));
  }
  return settled;
}

async function refreshHealth() {
  setStatus("正在同步系统运行状态...", "loading");
  try {
    const [health, models] = await Promise.all([
      fetchJson("/health"),
      fetchJson("/models"),
    ]);
    const configured = models.filter((item) => item.configured);
    elements.serviceStatus.textContent = health.status === "ok" ? `在线 / DB ${health.database}` : "异常";
    elements.modelCount.textContent = `${configured.length} / ${models.length}`;
    elements.ragStatus.textContent = health.rag?.enabled
      ? `${health.rag.backend} · ${health.rag.entries} 条`
      : "未启用";
    setStatus("系统状态已同步，可以提交新任务。");
  } catch (error) {
    elements.serviceStatus.textContent = "检测失败";
    elements.modelCount.textContent = "0 / 0";
    elements.ragStatus.textContent = "检测失败";
    setStatus(`系统状态读取失败：${error.message}`, "error");
  }
}

async function pollTask(taskId) {
  try {
    const task = await fetchJson(`/tasks/${encodeURIComponent(taskId)}`);
    const settled = updateAgentMessage(task);
    if (task.status === "SUCCESS") {
      if (!settled) {
        setStatus("模型已返回，系统正在逐步展开执行轨迹...", "loading");
      }
      return;
    }
    if (task.status === "FAILED") {
      if (!settled) {
        setStatus("任务已结束，系统正在逐步展开失败轨迹...", "loading");
      }
      return;
    }
    setStatus(`任务 ${task.task_id} 正在后台执行...`, "loading");
    window.setTimeout(() => pollTask(taskId), 1200);
  } catch (error) {
    setStatus(`任务状态读取失败：${error.message}`, "error");
  }
}

async function runAgent(event) {
  event.preventDefault();
  const payload = {
    query: elements.query.value.trim(),
    protein_sequence: elements.proteinSequence.value.trim() || null,
    include_metrics: elements.includeMetrics.checked,
  };

  if (!payload.query) {
    setStatus("请先填写任务请求。", "error");
    return;
  }

  addUserMessage(payload);
  elements.query.value = "";
  setStatus("正在提交任务请求...", "loading");

  try {
    const task = await fetchJson("/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const state = getTaskState(task.task_id);
    state.visibleCount = 0;
    state.terminalNotified = false;
    updateAgentMessage({
      task_id: task.task_id,
      status: task.status,
      task_type: "",
      trace_events: [
        {
          step: "queued",
          detail: "请求已提交，等待后台执行。",
          status: "queued",
        },
      ],
    });
    pollTask(task.task_id);
  } catch (error) {
    appendMessage(`
      <article class="message message-agent">
        <div class="message-meta">Protein Agent</div>
        <div class="message-card">
          <strong class="message-title">请求提交失败</strong>
          <p class="message-summary">${escapeHtml(error.message)}</p>
        </div>
      </article>
    `);
    setStatus(`任务提交失败：${error.message}`, "error");
  }
}

setActiveNav("chat");
setExample("protein");
toggleEmptyState(true);

elements.form.addEventListener("submit", runAgent);
elements.checkHealth.addEventListener("click", refreshHealth);
elements.exampleButtons.forEach((button) => {
  button.addEventListener("click", () => setExample(button.dataset.example));
});

refreshHealth();
