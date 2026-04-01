const {
  escapeHtml,
  fetchJson,
  formatDateTime,
  getDisplayTaskLabel,
  isLegacyStaleRecord,
  setActiveNav,
} = window.ProteinUI;

const archiveElements = {
  list: document.getElementById("archive-list"),
  refresh: document.getElementById("refresh-history"),
  count: document.getElementById("archive-count"),
  filters: Array.from(document.querySelectorAll("[data-filter]")),
};

let allRecords = [];
let currentFilter = "all";

function renderArchive() {
  const visible = allRecords
    .filter((record) => !isLegacyStaleRecord(record))
    .filter((record) => currentFilter === "all" || record.status === currentFilter);

  archiveElements.count.textContent = `${visible.length} 条档案记录`;

  if (visible.length === 0) {
    archiveElements.list.innerHTML = '<p class="empty-copy">当前筛选条件下没有可展示的任务记录。</p>';
    return;
  }

  archiveElements.list.innerHTML = visible
    .map(
      (record) => `
        <a class="archive-card" href="/tasks/${encodeURIComponent(record.task_id)}/view">
          <div class="archive-card-head">
            <span class="archive-status archive-status-${escapeHtml((record.status || "").toLowerCase())}">
              ${escapeHtml(record.status || "UNKNOWN")}
            </span>
            <span class="archive-time">${escapeHtml(formatDateTime(record.created_at))}</span>
          </div>
          <h3>${escapeHtml(record.request_query || "未命名任务")}</h3>
          <div class="archive-meta">
            <span>${escapeHtml(getDisplayTaskLabel(record))}</span>
            <span>${escapeHtml(record.model_name || "待定模型")}</span>
          </div>
        </a>
      `
    )
    .join("");
}

async function loadArchive() {
  archiveElements.count.textContent = "正在同步";
  try {
    allRecords = await fetchJson("/history");
    renderArchive();
  } catch (error) {
    archiveElements.list.innerHTML = `<p class="empty-copy">${escapeHtml(error.message)}</p>`;
    archiveElements.count.textContent = "同步失败";
  }
}

archiveElements.filters.forEach((button) => {
  button.addEventListener("click", () => {
    currentFilter = button.dataset.filter;
    archiveElements.filters.forEach((item) => {
      item.classList.toggle("is-active", item === button);
    });
    renderArchive();
  });
});

archiveElements.refresh.addEventListener("click", loadArchive);

setActiveNav("archive");
loadArchive();
