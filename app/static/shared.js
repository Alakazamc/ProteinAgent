window.ProteinUI = (() => {
  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function formatDateTime(value) {
    if (!value) {
      return "--";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return value;
    }
    return date.toLocaleString("zh-CN");
  }

  function formatTaskLabel(taskType) {
    if (taskType === "peptide_generation") {
      return "多肽生成";
    }
    if (taskType === "aptamer_generation") {
      return "适配体生成";
    }
    if (taskType === "protein_prediction") {
      return "蛋白质跑分";
    }
    return taskType || "未识别任务";
  }

  function inferTaskLabel(query = "", status = "") {
    const lowered = String(query).toLowerCase();
    if (lowered.includes("适配体") || lowered.includes("核酸") || lowered.includes("aptamer")) {
      return "适配体生成";
    }
    if (lowered.includes("多肽") || lowered.includes("peptide")) {
      return "多肽生成";
    }
    if (
      lowered.includes("蛋白") ||
      lowered.includes("protein") ||
      lowered.includes("预测") ||
      lowered.includes("打分")
    ) {
      return "蛋白质跑分";
    }
    if (status === "FAILED") {
      return "路由失败";
    }
    return "未识别任务";
  }

  function getDisplayTaskLabel(record) {
    return record.task_type
      ? formatTaskLabel(record.task_type)
      : inferTaskLabel(record.request_query, record.status);
  }

  function isLegacyStaleRecord(record) {
    return (
      record.status === "PENDING" &&
      (!record.trace_events || record.trace_events.length === 0) &&
      !record.task_type
    );
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || data.message || "请求失败");
    }
    return data;
  }

  function setActiveNav(pageKey) {
    document.querySelectorAll("[data-nav]").forEach((node) => {
      node.classList.toggle("is-active", node.dataset.nav === pageKey);
    });
  }

  return {
    escapeHtml,
    formatDateTime,
    formatTaskLabel,
    inferTaskLabel,
    getDisplayTaskLabel,
    isLegacyStaleRecord,
    fetchJson,
    setActiveNav,
  };
})();
