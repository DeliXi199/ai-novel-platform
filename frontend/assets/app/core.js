export const API = "/api/v1";
export const isReaderMode = window.location.pathname.startsWith("/app/reader");

export const state = {
  novels: [],
  selectedNovelId: null,
  selectedNovel: null,
  chapters: [],
  selectedChapterNo: null,
  selectedChapter: null,
  consoleData: null,
  planningData: null,
  interventions: [],
  managementMode: false,
  activityItems: [],
  confirmResolver: null,
  liveRefreshTimer: null,
  liveRefreshInFlight: false,
  lastLiveStage: null,
  lastLiveSnapshotKey: null,
  lastBundleRefreshAt: 0,
  busy: {
    creating: false,
    generating: false,
    batch: false,
    preparing: false,
    deleting: false,
  },
};

export const refs = {
  studioShell: document.getElementById("studioShell"),
  readerShell: document.getElementById("readerShell"),
  flashContainer: document.getElementById("flashContainer"),
  topbarTitle: document.getElementById("topbarTitle"),
  topbarSubtitle: document.getElementById("topbarSubtitle"),
  shelfSearchInput: document.getElementById("shelfSearchInput"),
  bookshelfList: document.getElementById("bookshelfList"),
  shelfStats: document.getElementById("shelfStats"),
  refreshShelfBtn: document.getElementById("refreshShelfBtn"),
  apiStatusText: document.getElementById("apiStatusText"),
  llmStatusText: document.getElementById("llmStatusText"),
  pingApiBtn: document.getElementById("pingApiBtn"),
  pingLlmBtn: document.getElementById("pingLlmBtn"),
  openCreatePanelBtn: document.getElementById("openCreatePanelBtn"),
  closeCreatePanelBtn: document.getElementById("closeCreatePanelBtn"),
  createPanel: document.getElementById("createPanel"),
  createNovelForm: document.getElementById("createNovelForm"),
  metricNovelTitle: document.getElementById("metricNovelTitle"),
  metricNovelMeta: document.getElementById("metricNovelMeta"),
  metricChapterNo: document.getElementById("metricChapterNo"),
  metricStatus: document.getElementById("metricStatus"),
  metricPlanningWindow: document.getElementById("metricPlanningWindow"),
  metricPlanningState: document.getElementById("metricPlanningState"),
  metricUpdatedAt: document.getElementById("metricUpdatedAt"),
  metricCreatedAt: document.getElementById("metricCreatedAt"),
  prepareWindowBtn: document.getElementById("prepareWindowBtn"),
  generateNextBtn: document.getElementById("generateNextBtn"),
  batchCountInput: document.getElementById("batchCountInput"),
  generateBatchBtn: document.getElementById("generateBatchBtn"),
  deleteLastChapterBtn: document.getElementById("deleteLastChapterBtn"),
  deleteNovelBtn: document.getElementById("deleteNovelBtn"),
  toggleManageModeBtn: document.getElementById("toggleManageModeBtn"),
  chapterManageHint: document.getElementById("chapterManageHint"),
  chapterSearchInput: document.getElementById("chapterSearchInput"),
  chapterList: document.getElementById("chapterList"),
  chapterCountText: document.getElementById("chapterCountText"),
  refreshChapterBtn: document.getElementById("refreshChapterBtn"),
  openReaderBtn: document.getElementById("openReaderBtn"),
  readerChapterTitle: document.getElementById("readerChapterTitle"),
  readerMeta: document.getElementById("readerMeta"),
  readerContent: document.getElementById("readerContent"),
  planningSummary: document.getElementById("planningSummary"),
  consoleHighlights: document.getElementById("consoleHighlights"),
  interventionForm: document.getElementById("interventionForm"),
  interventionList: document.getElementById("interventionList"),
  activityLog: document.getElementById("activityLog"),
  confirmModal: document.getElementById("confirmModal"),
  confirmEyebrow: document.getElementById("confirmEyebrow"),
  confirmTitle: document.getElementById("confirmTitle"),
  confirmMessage: document.getElementById("confirmMessage"),
  confirmCancelBtn: document.getElementById("confirmCancelBtn"),
  confirmOkBtn: document.getElementById("confirmOkBtn"),
  bookshelfItemTemplate: document.getElementById("bookshelfItemTemplate"),
  chapterCardTemplate: document.getElementById("chapterCardTemplate"),
  readerNovelTitle: document.getElementById("readerNovelTitle"),
  readerShellMeta: document.getElementById("readerShellMeta"),
  readerPageEyebrow: document.getElementById("readerPageEyebrow"),
  readerPageTitle: document.getElementById("readerPageTitle"),
  readerPageMeta: document.getElementById("readerPageMeta"),
  readerPageContent: document.getElementById("readerPageContent"),
  readerPrevBtn: document.getElementById("readerPrevBtn"),
  readerNextBtn: document.getElementById("readerNextBtn"),
  readerBackBtn: document.getElementById("readerBackBtn"),
  readerTocToggleBtn: document.getElementById("readerTocToggleBtn"),
  readerToc: document.getElementById("readerToc"),
  readerTocList: document.getElementById("readerTocList"),
};

export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export function fmtDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")} ${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

export function formatParagraphs(content) {
  const blocks = String(content || "").split(/\n{2,}/).map((item) => item.trim()).filter(Boolean);
  if (!blocks.length) return "<p>（空）</p>";
  return blocks.map((item) => `<p>${escapeHtml(item).replaceAll("\n", "<br>")}</p>`).join("");
}

export function chapterPreviewText(content) {
  const compact = String(content || "").trim();
  if (!compact) return "（空）";
  if (compact.length <= 900) return compact;
  return `${compact.slice(0, 900).trim()}…`;
}

export function normalizeChapterPayload(chapter) {
  if (!chapter || typeof chapter !== "object") return null;
  return {
    ...chapter,
    title: chapter.title || "未命名章节",
    content: typeof chapter.content === "string" ? chapter.content : "",
    generation_meta: chapter.generation_meta && typeof chapter.generation_meta === "object" ? chapter.generation_meta : {},
  };
}

export function cloneTemplateFirstElement(templateRef) {
  const element = templateRef?.content?.firstElementChild;
  return element ? element.cloneNode(true) : null;
}

export function buildBookshelfItemNode(item) {
  const node = cloneTemplateFirstElement(refs.bookshelfItemTemplate) || document.createElement("button");
  if (!node.classList.contains("bookshelf-item")) {
    node.className = "bookshelf-item";
    node.type = "button";
    node.innerHTML = `
      <div class="bookshelf-item-header">
        <strong class="bookshelf-item-title"></strong>
        <span class="bookshelf-item-badge"></span>
      </div>
      <div class="bookshelf-item-meta"></div>
      <div class="bookshelf-item-foot"></div>
    `;
  }
  node.classList.toggle("active", item.id === state.selectedNovelId);
  node.querySelector(".bookshelf-item-title").textContent = item.title;
  node.querySelector(".bookshelf-item-badge").textContent = item.status;
  node.querySelector(".bookshelf-item-meta").textContent = `${item.genre} · 主角 ${item.protagonist_name}`;
  node.querySelector(".bookshelf-item-foot").textContent = `当前第 ${item.current_chapter_no} 章 · 更新于 ${fmtDate(item.updated_at)}`;
  return node;
}

export function getCurrentChapterIndex() {
  return state.chapters.findIndex((item) => item.chapter_no === state.selectedChapterNo);
}

export async function apiFetch(path, options = {}) {
  const { timeoutMs = 0, signal: externalSignal, headers: optionHeaders, ...rest } = options || {};
  const controller = timeoutMs > 0 ? new AbortController() : null;
  const signal = controller ? controller.signal : externalSignal;
  let timeoutId = null;
  if (controller && externalSignal) {
    if (externalSignal.aborted) controller.abort(externalSignal.reason);
    else externalSignal.addEventListener("abort", () => controller.abort(externalSignal.reason), { once: true });
  }
  if (controller) {
    timeoutId = window.setTimeout(() => controller.abort(new DOMException("请求超时", "AbortError")), timeoutMs);
  }
  try {
    const response = await fetch(`${API}${path}`, {
      headers: { "Content-Type": "application/json", ...(optionHeaders || {}) },
      signal,
      ...rest,
    });

    const contentType = response.headers.get("content-type") || "";
    const isJson = contentType.includes("application/json");
    const payload = isJson ? await response.json() : await response.text();

    if (!response.ok) {
      const detail = isJson ? payload?.detail || payload : payload;
      const message = typeof detail === "string" ? detail : detail?.message || detail?.detail || JSON.stringify(detail);
      const error = new Error(message || `请求失败：${response.status}`);
      error.status = response.status;
      error.payload = detail;
      throw error;
    }

    return payload;
  } catch (error) {
    if (error?.name === "AbortError") {
      const wrapped = new Error(timeoutMs > 0 ? `请求超时（>${timeoutMs}ms）` : "请求已取消");
      wrapped.status = 0;
      wrapped.payload = { code: "REQUEST_TIMEOUT", path, timeout_ms: timeoutMs };
      throw wrapped;
    }
    throw error;
  } finally {
    if (timeoutId) window.clearTimeout(timeoutId);
  }
}

export function showFlash(message, type = "info") {
  if (!refs.flashContainer) return;
  const div = document.createElement("div");
  div.className = `flash ${type}`;
  div.textContent = message;
  refs.flashContainer.prepend(div);
  window.setTimeout(() => div.remove(), 3800);
}

export function pushActivity(title, body = "", type = "info") {
  state.activityItems.unshift({ title, body, type, at: new Date().toISOString() });
  state.activityItems = state.activityItems.slice(0, 80);
  renderActivity();
}

export function renderActivity() {
  if (!refs.activityLog) return;
  refs.activityLog.innerHTML = "";
  if (!state.activityItems.length) {
    refs.activityLog.innerHTML = '<div class="panel-muted subtle-text">这里会显示批量生成、删除、导出与错误日志。</div>';
    return;
  }
  state.activityItems.forEach((item) => {
    const div = document.createElement("div");
    div.className = `activity-item ${item.type}`;
    div.innerHTML = `<strong>${escapeHtml(item.title)}</strong><div>${escapeHtml(item.body)}</div><div class="subtle-text">${escapeHtml(fmtDate(item.at))}</div>`;
    refs.activityLog.appendChild(div);
  });
}

export function hasLiveBusyTask() {
  return state.busy.generating || state.busy.batch || state.busy.preparing;
}

export function mergeNovelIntoShelf(updatedNovel) {
  if (!updatedNovel?.id) return;
  const index = state.novels.findIndex((item) => item.id === updatedNovel.id);
  if (index >= 0) state.novels[index] = { ...state.novels[index], ...updatedNovel };
}
