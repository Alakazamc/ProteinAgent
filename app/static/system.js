const {
  escapeHtml,
  fetchJson,
  formatTaskLabel,
  setActiveNav,
} = window.ProteinUI;

const systemElements = {
  refresh: document.getElementById("refresh-system"),
  note: document.getElementById("system-note"),
  summary: document.getElementById("system-summary"),
  models: document.getElementById("system-models"),
  knowledge: document.getElementById("system-knowledge"),
};

function renderSummary(health) {
  systemElements.summary.innerHTML = `
    <article class="summary-card">
      <p>服务</p>
      <strong>${escapeHtml(health.status || "--")}</strong>
    </article>
    <article class="summary-card">
      <p>数据库</p>
      <strong>${escapeHtml(health.database || "--")}</strong>
    </article>
    <article class="summary-card">
      <p>RAG</p>
      <strong>${escapeHtml(health.rag?.backend || "disabled")}</strong>
    </article>
  `;
}

function renderModels(models) {
  if (!models.length) {
    systemElements.models.innerHTML = '<p class="empty-copy">没有模型配置。</p>';
    return;
  }
  systemElements.models.innerHTML = models
    .map(
      (model) => `
        <article class="model-card">
          <p class="eyebrow">${escapeHtml(formatTaskLabel(model.task_type))}</p>
          <h3>${escapeHtml(model.model_name || "--")}</h3>
          <p>${escapeHtml(model.provider || "--")}</p>
          <span class="model-state ${model.configured ? "is-ready" : "is-missing"}">
            ${model.configured ? "已配置" : "未配置"}
          </span>
        </article>
      `
    )
    .join("");
}

function renderKnowledge(payload) {
  if (!payload.ready || !payload.entries?.length) {
    systemElements.knowledge.innerHTML = '<p class="empty-copy">知识库尚未就绪。</p>';
    return;
  }
  systemElements.knowledge.innerHTML = payload.entries
    .slice(0, 12)
    .map(
      (entry) => `
        <article class="knowledge-card">
          <p class="eyebrow">${escapeHtml(entry.category || "general")}</p>
          <h3>${escapeHtml(entry.source || "unknown")}</h3>
          <p>${escapeHtml(entry.text || "")}</p>
        </article>
      `
    )
    .join("");
}

async function loadSystem() {
  systemElements.note.textContent = "正在同步";
  try {
    const [health, models, knowledge] = await Promise.all([
      fetchJson("/health"),
      fetchJson("/models"),
      fetchJson("/knowledge"),
    ]);
    renderSummary(health);
    renderModels(models);
    renderKnowledge(knowledge);
    systemElements.note.textContent = "已同步";
  } catch (error) {
    systemElements.note.textContent = "同步失败";
    systemElements.models.innerHTML = `<p class="empty-copy">${escapeHtml(error.message)}</p>`;
    systemElements.knowledge.innerHTML = `<p class="empty-copy">${escapeHtml(error.message)}</p>`;
  }
}

systemElements.refresh.addEventListener("click", loadSystem);

setActiveNav("system");
loadSystem();
