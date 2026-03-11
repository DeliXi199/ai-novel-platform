const API = "/api/v1";
const isReaderMode = window.location.pathname.startsWith("/app/reader");

const state = {
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
  busy: {
    creating: false,
    generating: false,
    batch: false,
    preparing: false,
    deleting: false,
  },
};

const refs = {
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

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function fmtDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")} ${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

function formatParagraphs(content) {
  const blocks = String(content || "").split(/\n{2,}/).map((item) => item.trim()).filter(Boolean);
  if (!blocks.length) return "<p>（空）</p>";
  return blocks.map((item) => `<p>${escapeHtml(item).replaceAll("\n", "<br>")}</p>`).join("");
}

function chapterPreviewText(content) {
  const compact = String(content || "").trim();
  if (!compact) return "（空）";
  if (compact.length <= 900) return compact;
  return `${compact.slice(0, 900).trim()}…`;
}

function normalizeChapterPayload(chapter) {
  if (!chapter || typeof chapter !== "object") return null;
  return {
    ...chapter,
    title: chapter.title || "未命名章节",
    content: typeof chapter.content === "string" ? chapter.content : "",
    generation_meta: chapter.generation_meta && typeof chapter.generation_meta === "object" ? chapter.generation_meta : {},
  };
}

function cloneTemplateFirstElement(templateRef) {
  const element = templateRef?.content?.firstElementChild;
  return element ? element.cloneNode(true) : null;
}

function buildBookshelfItemNode(item) {
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

function buildChapterCardNode(chapter, lastChapterNo) {
  const node = cloneTemplateFirstElement(refs.chapterCardTemplate) || document.createElement("article");
  if (!node.classList.contains("chapter-card")) {
    node.className = "chapter-card";
    node.innerHTML = `
      <div class="chapter-card-top">
        <div class="chapter-card-no"></div>
        <div class="chapter-card-headings">
          <strong class="chapter-card-title"></strong>
          <div class="chapter-card-meta"></div>
        </div>
      </div>
      <div class="chapter-card-preview"></div>
      <div class="chapter-card-actions">
        <button class="ghost-btn chapter-preview-btn" type="button">预览</button>
        <button class="ghost-btn chapter-open-btn" type="button">沉浸阅读</button>
        <button class="ghost-btn danger-btn chapter-delete-tail-btn hidden" type="button"></button>
      </div>
    `;
  }
  node.classList.toggle("active", chapter.chapter_no === state.selectedChapterNo);
  node.querySelector(".chapter-card-no").textContent = `第 ${chapter.chapter_no} 章`;
  node.querySelector(".chapter-card-title").textContent = chapter.title || "未命名章节";
  node.querySelector(".chapter-card-meta").textContent = `${fmtDate(chapter.created_at)} · 约 ${chapter.char_count || 0} 字`;
  node.querySelector(".chapter-card-preview").textContent = chapter.content_preview || "（无预览）";
  node.querySelector(".chapter-preview-btn").addEventListener("click", () => selectChapter(chapter.chapter_no));
  node.querySelector(".chapter-open-btn").addEventListener("click", () => openReader(chapter.chapter_no));

  const deleteBtn = node.querySelector(".chapter-delete-tail-btn");
  const deleteCount = lastChapterNo - chapter.chapter_no + 1;
  deleteBtn.textContent = `从这里删到末尾（${deleteCount} 章）`;
  deleteBtn.classList.toggle("hidden", !state.managementMode);
  deleteBtn.addEventListener("click", () => handleDeleteTailFrom(chapter.chapter_no));
  return node;
}

function getCurrentChapterIndex() {
  return state.chapters.findIndex((item) => item.chapter_no === state.selectedChapterNo);
}

async function apiFetch(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
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
}

function showFlash(message, type = "info") {
  if (!refs.flashContainer) return;
  const div = document.createElement("div");
  div.className = `flash ${type}`;
  div.textContent = message;
  refs.flashContainer.prepend(div);
  window.setTimeout(() => div.remove(), 3800);
}

function pushActivity(title, body = "", type = "info") {
  state.activityItems.unshift({ title, body, type, at: new Date().toISOString() });
  state.activityItems = state.activityItems.slice(0, 80);
  renderActivity();
}

function renderActivity() {
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

function hasLiveBusyTask() {
  return state.busy.generating || state.busy.batch || state.busy.preparing;
}

async function silentRefreshSelectedNovel({ chapterNo = null } = {}) {
  if (!state.selectedNovelId || state.liveRefreshInFlight) return;
  state.liveRefreshInFlight = true;
  try {
    await loadNovelBundle(state.selectedNovelId, { desiredChapterNo: chapterNo || state.selectedChapterNo, updateReaderUrl: isReaderMode });
  } catch (error) {
    console.warn("silent refresh failed", error);
  } finally {
    state.liveRefreshInFlight = false;
  }
}

function updateLiveRefreshLoop() {
  const shouldRun = hasLiveBusyTask() && !!state.selectedNovelId;
  if (!shouldRun) {
    if (state.liveRefreshTimer) {
      window.clearInterval(state.liveRefreshTimer);
      state.liveRefreshTimer = null;
    }
    return;
  }
  if (state.liveRefreshTimer) return;
  state.liveRefreshTimer = window.setInterval(() => {
    silentRefreshSelectedNovel().catch(() => {});
  }, 1500);
}

function setBusy(key, value) {
  state.busy[key] = value;
  if (refs.createNovelForm) refs.createNovelForm.querySelector("button[type='submit']").disabled = state.busy.creating;
  if (refs.prepareWindowBtn) {
    refs.prepareWindowBtn.disabled = state.busy.preparing || state.busy.generating || state.busy.batch;
    refs.prepareWindowBtn.textContent = state.busy.preparing ? "规划中..." : "强制补规划";
  }
  if (refs.generateNextBtn) {
    refs.generateNextBtn.disabled = state.busy.generating || state.busy.batch || state.busy.deleting || state.busy.preparing;
    refs.generateNextBtn.textContent = state.busy.generating ? "生成中..." : "生成下一章";
  }
  if (refs.generateBatchBtn) {
    refs.generateBatchBtn.disabled = state.busy.generating || state.busy.batch || state.busy.deleting || state.busy.preparing;
    refs.generateBatchBtn.textContent = state.busy.batch ? "批量生成中..." : "实时生成并显示进度";
  }
  if (refs.deleteLastChapterBtn) refs.deleteLastChapterBtn.disabled = state.busy.deleting || state.busy.generating || state.busy.batch;
  if (refs.deleteNovelBtn) refs.deleteNovelBtn.disabled = state.busy.deleting || state.busy.generating || state.busy.batch;
  updateLiveRefreshLoop();
}

function updateCreatePanel(open) {
  refs.createPanel?.classList.toggle("hidden", !open);
}

function showConfirm({ eyebrow = "请确认", title, message, confirmText = "确认", danger = false }) {
  return new Promise((resolve) => {
    refs.confirmEyebrow.textContent = eyebrow;
    refs.confirmTitle.textContent = title;
    refs.confirmMessage.innerHTML = message;
    refs.confirmOkBtn.textContent = confirmText;
    refs.confirmOkBtn.classList.toggle("danger-btn", danger);
    refs.confirmModal.classList.remove("hidden");
    state.confirmResolver = resolve;
  });
}

function closeConfirm(result) {
  refs.confirmModal.classList.add("hidden");
  const resolver = state.confirmResolver;
  state.confirmResolver = null;
  if (resolver) resolver(result);
}

function setTopbar() {
  if (!refs.topbarTitle) return;
  if (!state.selectedNovel) {
    refs.topbarTitle.textContent = "请选择一本书，或先新建项目";
    refs.topbarSubtitle.textContent = "你可以在这里管理书架、补规划、按章生成、从末尾回删章节，并以沉浸式阅读器查看正文。";
    return;
  }
  refs.topbarTitle.textContent = `《${state.selectedNovel.title}》`;
  refs.topbarSubtitle.textContent = `${state.selectedNovel.genre} · 主角 ${state.selectedNovel.protagonist_name} · 当前已写到第 ${state.selectedNovel.current_chapter_no} 章`;
}

function renderBookshelf() {
  if (!refs.bookshelfList) return;
  const keyword = refs.shelfSearchInput?.value?.trim().toLowerCase() || "";
  const items = state.novels.filter((item) => {
    if (!keyword) return true;
    return [item.title, item.genre, item.protagonist_name].some((field) => String(field || "").toLowerCase().includes(keyword));
  });

  refs.shelfStats.textContent = `共 ${state.novels.length} 本，当前显示 ${items.length} 本`;
  refs.bookshelfList.innerHTML = "";
  if (!items.length) {
    refs.bookshelfList.innerHTML = '<div class="panel-muted subtle-text">书架为空。先创建一本书，或者换一个关键词试试。</div>';
    return;
  }

  items.forEach((item) => {
    const node = buildBookshelfItemNode(item);
    node.addEventListener("click", () => {
      if (isReaderMode) {
        const latestChapter = item.current_chapter_no || 1;
        window.location.href = `/app/reader?novelId=${item.id}&chapterNo=${latestChapter}`;
      } else {
        selectNovel(item.id);
      }
    });
    refs.bookshelfList.appendChild(node);
  });
}

function renderMetrics() {
  if (!refs.metricNovelTitle) return;
  if (!state.selectedNovel) {
    refs.metricNovelTitle.textContent = "未选择";
    refs.metricNovelMeta.textContent = "—";
    refs.metricChapterNo.textContent = "第 0 章";
    refs.metricStatus.textContent = "状态：—";
    refs.metricPlanningWindow.textContent = "—";
    refs.metricPlanningState.textContent = "等待载入";
    refs.metricUpdatedAt.textContent = "—";
    refs.metricCreatedAt.textContent = "—";
    return;
  }

  const queue = state.planningData?.chapter_card_queue || [];
  const planningStatus = state.planningData?.planning_status || {};
  const liveRuntime = state.planningData?.planning_state?.live_runtime || {};
  const plannedRange = planningStatus?.planned_until || state.planningData?.planning_state?.planned_until || liveRuntime?.planned_until || "—";
  refs.metricNovelTitle.textContent = state.selectedNovel.title;
  refs.metricNovelMeta.textContent = `${state.selectedNovel.genre} · 主角 ${state.selectedNovel.protagonist_name}`;
  refs.metricChapterNo.textContent = `第 ${state.selectedNovel.current_chapter_no} 章`;
  refs.metricStatus.textContent = `状态：${state.selectedNovel.status}${liveRuntime.stage ? ` · ${liveRuntime.stage}` : ""}`;
  refs.metricPlanningWindow.textContent = plannedRange === "—" ? "—" : `已规划至 ${plannedRange}`;
  refs.metricPlanningState.textContent = liveRuntime.note || (queue.length ? `待写 chapter card：${queue.length}` : "目录与规划已同步");
  refs.metricUpdatedAt.textContent = fmtDate(state.selectedNovel.updated_at);
  refs.metricCreatedAt.textContent = `创建于 ${fmtDate(state.selectedNovel.created_at)}`;
}

function renderPlanning() {
  if (!refs.planningSummary) return;
  refs.planningSummary.innerHTML = "";
  refs.consoleHighlights.innerHTML = "";

  if (!state.selectedNovel) {
    refs.planningSummary.innerHTML = '<div class="panel-muted subtle-text">选择小说后，这里会显示当前规划窗口、活跃 arc、自动规划状态与执行卡。</div>';
    return;
  }

  const planning = state.planningData || {};
  const consoleData = state.consoleData || {};
  const planningState = planning.planning_state || {};
  const planningStatus = planning.planning_status || {};
  const liveRuntime = planningState.live_runtime || {};
  const currentPipeline = planningState.current_pipeline || {};
  const executionPacket = consoleData.control_console?.current_execution_packet || {};
  const executionCard = executionPacket.chapter_execution_card || {};
  const dailyWorkbench = executionPacket.daily_workbench || consoleData.control_console?.daily_workbench || {};
  const activeArcFromConsole = consoleData.control_console?.active_arc || {};
  const activeArcFromPlanning = planningStatus.active_arc || {};
  const activeArc = { ...activeArcFromPlanning, ...activeArcFromConsole };
  const pendingArc = planningStatus.pending_arc || {};
  const queue = planning.chapter_card_queue || [];

  const summaryCards = [
    {
      title: "自动规划",
      body: liveRuntime.note || "生成章节时会自动补齐后续规划，无需手动点击。手动按钮仅用于强制重算。",
    },
    {
      title: "规划窗口",
      body: `已规划至 ${planningStatus.planned_until ?? planningState.planned_until ?? liveRuntime.planned_until ?? "—"}\n就绪章节：${(liveRuntime.ready_cards || planningStatus.ready_chapter_cards || []).join("、") || "—"}`,
    },
    {
      title: "下一段 Arc",
      body: `active arc_no：${activeArc.arc_no ?? "—"}\npending arc_no：${pendingArc.arc_no ?? liveRuntime.pending_arc_no ?? "—"}`,
    },
    {
      title: "待写队列",
      body: queue.length ? queue.map((item) => `第 ${item.chapter_no} 章：${item.title || item.goal || "未命名"}`).join("\n") : "当前没有待写 card。",
    },
  ];

  summaryCards.forEach((card) => {
    const div = document.createElement("div");
    div.className = "info-card";
    div.innerHTML = `<strong>${escapeHtml(card.title)}</strong><div>${escapeHtml(card.body).replaceAll("\n", "<br>")}</div>`;
    refs.planningSummary.appendChild(div);
  });

  const runtimeList = [
    `当前流程：${currentPipeline.last_live_stage || currentPipeline.last_completed_stage || liveRuntime.stage || "等待中"}`,
    `目标章节：${liveRuntime.target_chapter_no || currentPipeline.target_chapter_no || "—"}`,
    `更新时间：${fmtDate(liveRuntime.updated_at)}`,
  ];
  if (liveRuntime.chapter_title) runtimeList.push(`执行标题：${liveRuntime.chapter_title}`);
  if (liveRuntime.chapter_goal) runtimeList.push(`本章目标：${liveRuntime.chapter_goal}`);

  const blocks = [
    {
      title: "活跃 Arc",
      list: [
        activeArc.focus || "—",
        activeArc.bridge_note || consoleData.planning_layers?.active_arc?.bridge_note || "—",
      ],
    },
    {
      title: "当前执行卡",
      list: [
        dailyWorkbench.today_function || executionCard.chapter_function || "等待执行卡写入",
        executionCard.opening || dailyWorkbench.three_line_outline?.opening || "—",
        executionCard.middle || dailyWorkbench.three_line_outline?.middle || "—",
        executionCard.ending || dailyWorkbench.three_line_outline?.ending || "—",
      ],
    },
    {
      title: "实时运行状态",
      list: runtimeList,
    },
  ];

  blocks.forEach((block) => {
    const div = document.createElement("div");
    div.className = "info-card";
    div.innerHTML = `<strong>${escapeHtml(block.title)}</strong><ul>${block.list.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
    refs.consoleHighlights.appendChild(div);
  });
}

function renderInterventions() {
  if (!refs.interventionList) return;
  refs.interventionList.innerHTML = "";
  if (!state.selectedNovel) {
    refs.interventionList.innerHTML = '<div class="panel-muted subtle-text">选择小说后，可向生成流程注入阶段性要求。</div>';
    return;
  }
  if (!state.interventions.length) {
    refs.interventionList.innerHTML = '<div class="panel-muted subtle-text">暂时还没有人工干预指令。</div>';
    return;
  }
  state.interventions.forEach((item) => {
    const div = document.createElement("div");
    div.className = "timeline-item";
    div.innerHTML = `
      <strong>第 ${escapeHtml(item.chapter_no)} 章起 · 持续 ${escapeHtml(item.effective_chapter_span)} 章</strong>
      <div>${escapeHtml(item.raw_instruction)}</div>
      <div class="subtle-text">创建于 ${escapeHtml(fmtDate(item.created_at))}</div>
    `;
    refs.interventionList.appendChild(div);
  });
}

function getFilteredChapters() {
  const keyword = refs.chapterSearchInput?.value?.trim().toLowerCase() || "";
  return state.chapters.filter((chapter) => {
    if (!keyword) return true;
    return String(chapter.chapter_no).includes(keyword) || String(chapter.title || "").toLowerCase().includes(keyword);
  });
}

function renderCatalog() {
  if (!refs.chapterList) return;
  refs.chapterList.innerHTML = "";

  if (!state.selectedNovel) {
    refs.chapterCountText.textContent = "0 章";
    refs.chapterManageHint.textContent = "先从书架选择一本小说。";
    refs.chapterList.innerHTML = '<div class="panel-muted subtle-text">选择小说后，这里会显示更规范的章节目录卡片。</div>';
    return;
  }

  const items = getFilteredChapters();
  refs.chapterCountText.textContent = `${state.chapters.length} 章`;
  refs.chapterManageHint.textContent = state.managementMode
    ? "管理删除模式已开启：只能从某一章开始，连续删到最后一章。"
    : "普通模式：点“预览”在工作台查看，点“沉浸阅读”在新界面打开。";

  if (!items.length) {
    refs.chapterList.innerHTML = '<div class="panel-muted subtle-text">还没有符合条件的章节。</div>';
    return;
  }

  const lastChapterNo = state.chapters[state.chapters.length - 1]?.chapter_no || 0;
  items.forEach((chapter) => {
    const node = buildChapterCardNode(chapter, lastChapterNo);
    refs.chapterList.appendChild(node);
  });
}

function renderPreview() {
  if (!refs.readerChapterTitle) return;
  if (!state.selectedChapter) {
    refs.readerChapterTitle.textContent = state.selectedNovel ? "请选择章节" : "请先选择小说";
    refs.readerMeta.textContent = state.selectedNovel ? "章节元信息会显示在这里。" : "";
    refs.readerContent.textContent = "这里会显示章节摘要预览，点“沉浸阅读”会在新界面里像电子书一样展开正文。";
    refs.openReaderBtn.disabled = true;
    return;
  }
  refs.openReaderBtn.disabled = false;
  const chapter = normalizeChapterPayload(state.selectedChapter);
  if (!chapter) {
    refs.readerChapterTitle.textContent = "章节载入失败";
    refs.readerMeta.textContent = "返回目录后可重新选择章节。";
    refs.readerContent.textContent = "当前章节数据为空，已启用前端容错。";
    return;
  }
  const provider = chapter.generation_meta?.provider || chapter.generation_meta?.llm_provider || "—";
  const trace = chapter.generation_meta?.trace_id || chapter.generation_meta?.llm_call_trace?.[0]?.trace_id || "—";
  refs.readerChapterTitle.textContent = `第 ${chapter.chapter_no} 章 · ${chapter.title}`;
  refs.readerMeta.textContent = `创建于 ${fmtDate(chapter.created_at)} · provider: ${provider} · trace: ${trace}`;
  refs.readerContent.textContent = chapterPreviewText(chapter.content);
}

function renderReaderMode() {
  if (!refs.readerShell || !isReaderMode) return;
  refs.readerNovelTitle.textContent = state.selectedNovel ? `《${state.selectedNovel.title}》` : "未选择小说";
  refs.readerShellMeta.textContent = state.selectedNovel
    ? `${state.selectedNovel.genre} · 主角 ${state.selectedNovel.protagonist_name}`
    : "从工作台打开沉浸阅读，或直接在地址栏带上 novelId 与 chapterNo。";

  refs.readerTocList.innerHTML = "";
  state.chapters.forEach((chapter) => {
    const button = document.createElement("button");
    button.className = "reader-toc-item";
    button.classList.toggle("active", chapter.chapter_no === state.selectedChapterNo);
    button.innerHTML = `<strong>第 ${escapeHtml(chapter.chapter_no)} 章</strong><div>${escapeHtml(chapter.title)}</div>`;
    button.addEventListener("click", () => selectChapter(chapter.chapter_no, { updateUrl: true }));
    refs.readerTocList.appendChild(button);
  });

  if (!state.selectedChapter) {
    refs.readerPageEyebrow.textContent = "正文";
    refs.readerPageTitle.textContent = "请选择章节";
    refs.readerPageMeta.textContent = "";
    refs.readerPageContent.textContent = "这里会显示章节正文。";
    refs.readerPrevBtn.disabled = true;
    refs.readerNextBtn.disabled = true;
    return;
  }

  const index = getCurrentChapterIndex();
  const chapter = normalizeChapterPayload(state.selectedChapter);
  if (!chapter) {
    refs.readerPageEyebrow.textContent = "正文";
    refs.readerPageTitle.textContent = "章节载入失败";
    refs.readerPageMeta.textContent = "返回目录后可重新选择章节。";
    refs.readerPageContent.innerHTML = "<p>当前章节数据为空，已启用阅读页容错。</p>";
    refs.readerPrevBtn.disabled = true;
    refs.readerNextBtn.disabled = true;
    return;
  }
  refs.readerPageEyebrow.textContent = `第 ${chapter.chapter_no} 章`;
  refs.readerPageTitle.textContent = chapter.title;
  refs.readerPageMeta.textContent = `创建于 ${fmtDate(chapter.created_at)}`;
  refs.readerPageContent.innerHTML = formatParagraphs(chapter.content);
  refs.readerPrevBtn.disabled = index <= 0;
  refs.readerNextBtn.disabled = index < 0 || index >= state.chapters.length - 1;
}

function syncReaderUrl() {
  if (!isReaderMode || !state.selectedNovelId || !state.selectedChapterNo) return;
  const url = new URL(window.location.href);
  url.searchParams.set("novelId", String(state.selectedNovelId));
  url.searchParams.set("chapterNo", String(state.selectedChapterNo));
  window.history.replaceState({}, "", url.toString());
}

async function loadShelf() {
  const data = await apiFetch("/novels?limit=100");
  state.novels = data.items || [];
  renderBookshelf();
  if (!state.selectedNovelId && !isReaderMode && state.novels.length) {
    await selectNovel(state.novels[0].id);
  }
}

async function loadNovelBundle(novelId, { desiredChapterNo = null, updateReaderUrl = false } = {}) {
  const [novel, chapters, consoleData, planningData, interventions] = await Promise.all([
    apiFetch(`/novels/${novelId}`),
    apiFetch(`/novels/${novelId}/chapters`),
    apiFetch(`/novels/${novelId}/control-console`),
    apiFetch(`/novels/${novelId}/planning-state`),
    apiFetch(`/novels/${novelId}/interventions`),
  ]);

  state.selectedNovelId = novelId;
  state.selectedNovel = novel;
  state.chapters = chapters.items || [];
  state.consoleData = consoleData;
  state.planningData = planningData;
  state.interventions = interventions.items || [];

  const fallbackChapterNo = state.chapters.length ? state.chapters[state.chapters.length - 1].chapter_no : null;
  const targetChapterNo = desiredChapterNo && state.chapters.some((item) => item.chapter_no === desiredChapterNo) ? desiredChapterNo : fallbackChapterNo;
  state.selectedChapterNo = targetChapterNo;
  state.selectedChapter = targetChapterNo ? normalizeChapterPayload(await apiFetch(`/novels/${novelId}/chapters/${targetChapterNo}`)) : null;

  renderBookshelf();
  setTopbar();
  renderMetrics();
  renderPlanning();
  renderInterventions();
  renderCatalog();
  renderPreview();
  renderReaderMode();

  const chapterNoField = refs.interventionForm?.elements?.namedItem("chapter_no");
  if (chapterNoField) chapterNoField.value = Math.max((state.selectedNovel?.current_chapter_no || 0) + 1, 1);
  if (updateReaderUrl) syncReaderUrl();
}

async function selectNovel(novelId, options = {}) {
  pushActivity("切换小说", `载入小说 #${novelId}`);
  try {
    await loadNovelBundle(novelId, options);
  } catch (error) {
    showFlash(`载入小说失败：${error.message}`, "error");
    pushActivity("载入失败", error.message, "error");
  }
}

async function selectChapter(chapterNo, { updateUrl = false } = {}) {
  if (!state.selectedNovelId) return;
  state.selectedChapterNo = chapterNo;
  state.selectedChapter = null;
  renderCatalog();
  renderPreview();
  renderReaderMode();
  try {
    state.selectedChapter = normalizeChapterPayload(await apiFetch(`/novels/${state.selectedNovelId}/chapters/${chapterNo}`));
    renderPreview();
    renderReaderMode();
    if (updateUrl) syncReaderUrl();
  } catch (error) {
    state.selectedChapter = null;
    renderPreview();
    renderReaderMode();
    showFlash(`读取章节失败：${error.message}`, "error");
  }
}

function openReader(chapterNo = null) {
  if (!state.selectedNovelId) return;
  const targetChapterNo = chapterNo || state.selectedChapterNo || state.chapters[state.chapters.length - 1]?.chapter_no;
  if (!targetChapterNo) {
    showFlash("当前还没有章节可供阅读。", "info");
    return;
  }
  const url = `/app/reader?novelId=${state.selectedNovelId}&chapterNo=${targetChapterNo}`;
  window.open(url, "_blank", "noopener,noreferrer");
}

function collectStylePreferences(form) {
  const formData = new FormData(form);
  const style = {};
  ["tone", "pace", "pov", "combat_style"].forEach((key) => {
    const value = formData.get(key)?.toString().trim();
    if (value) style[key] = value;
  });
  const notes = formData.get("style_notes")?.toString().trim();
  if (notes) style.style_notes = notes;
  const styleJson = formData.get("style_json")?.toString().trim();
  if (styleJson) {
    const parsed = JSON.parse(styleJson);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error("高级风格 JSON 不是合法对象，请检查格式");
    }
    Object.assign(style, parsed);
  }
  return style;
}

async function handleCreateNovel(event) {
  event.preventDefault();
  const form = event.currentTarget;
  try {
    setBusy("creating", true);
    const formData = new FormData(form);
    const payload = {
      genre: formData.get("genre")?.toString().trim(),
      protagonist_name: formData.get("protagonist_name")?.toString().trim(),
      premise: formData.get("premise")?.toString().trim(),
      style_preferences: collectStylePreferences(form),
    };
    const created = await apiFetch("/novels", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    showFlash(`《${created.title}》创建成功`, "success");
    pushActivity("创建成功", `《${created.title}》已生成初始规划`, "success");
    form.reset();
    updateCreatePanel(false);
    await loadShelf();
    await selectNovel(created.id);
  } catch (error) {
    showFlash(`创建失败：${error.message}`, "error");
    pushActivity("创建失败", error.message, "error");
  } finally {
    setBusy("creating", false);
  }
}

async function refreshSelectedNovel({ chapterNo = null } = {}) {
  if (!state.selectedNovelId) return;
  await loadNovelBundle(state.selectedNovelId, { desiredChapterNo: chapterNo || state.selectedChapterNo, updateReaderUrl: isReaderMode });
}

async function handlePrepareWindow() {
  if (!state.selectedNovelId) return;
  try {
    setBusy("preparing", true);
    const result = await apiFetch(`/novels/${state.selectedNovelId}/prepare-next-window`, { method: "POST" });
    showFlash("规划窗口已刷新完成", "success");
    pushActivity("规划更新", "已手动强制刷新后续规划窗口", "success");
    await refreshSelectedNovel();
  } catch (error) {
    showFlash(`准备规划失败：${error.message}`, "error");
    pushActivity("规划失败", error.message, "error");
  } finally {
    setBusy("preparing", false);
  }
}

async function handleGenerateNext() {
  if (!state.selectedNovelId) return;
  try {
    setBusy("generating", true);
    pushActivity("开始生成", `小说 #${state.selectedNovelId} 的下一章，主控台会自动刷新`, "info");
    const chapter = await apiFetch(`/novels/${state.selectedNovelId}/next-chapter`, { method: "POST" });
    showFlash(`第 ${chapter.chapter_no} 章生成成功`, "success");
    pushActivity("章节完成", `第 ${chapter.chapter_no} 章《${chapter.title}》`, "success");
    await refreshSelectedNovel({ chapterNo: chapter.chapter_no });
  } catch (error) {
    const payload = error.payload;
    const extra = payload?.code ? ` [${payload.code}]` : "";
    showFlash(`生成失败${extra}：${error.message}`, "error");
    pushActivity("生成失败", `${error.message}${extra}`, "error");
  } finally {
    setBusy("generating", false);
  }
}

function parseSseBlock(block) {
  const lines = block.split("\n");
  let event = "message";
  const dataLines = [];
  for (const line of lines) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  const joined = dataLines.join("\n");
  return { event, data: joined ? JSON.parse(joined) : null };
}

async function handleGenerateBatch() {
  if (!state.selectedNovelId) return;
  const count = Math.max(1, Math.min(20, Number(refs.batchCountInput.value || 1)));
  try {
    setBusy("batch", true);
    pushActivity("批量生成", `请求连续生成 ${count} 章`, "info");
    const response = await fetch(`${API}/novels/${state.selectedNovelId}/next-chapters/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ count }),
    });
    if (!response.ok || !response.body) {
      const text = await response.text();
      throw new Error(text || "SSE 请求失败");
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    let hadError = false;
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() || "";
      for (const part of parts) {
        if (!part.trim()) continue;
        const parsed = parseSseBlock(part);
        if (!parsed.data) continue;
        if (parsed.event === "error") {
          hadError = true;
          pushActivity("批量生成失败", parsed.data.message || "未知错误", "error");
          showFlash(`批量生成失败：${parsed.data.message || "未知错误"}`, "error");
          continue;
        }
        if (parsed.event === "chapter_succeeded") {
          pushActivity(`第 ${parsed.data.chapter_no} 章完成`, parsed.data.title || "", "success");
          silentRefreshSelectedNovel({ chapterNo: parsed.data.chapter_no }).catch(() => {});
        } else {
          pushActivity(parsed.event, JSON.stringify(parsed.data), "info");
        }
      }
    }
    showFlash(hadError ? "批量生成已结束，但过程中出现错误。" : "批量生成流程已结束，目录与主控台已自动同步。", hadError ? "info" : "success");
    await refreshSelectedNovel();
  } catch (error) {
    showFlash(`批量生成失败：${error.message}`, "error");
    pushActivity("批量生成失败", error.message, "error");
  } finally {
    setBusy("batch", false);
  }
}

async function handleAddIntervention(event) {
  event.preventDefault();
  if (!state.selectedNovelId) return;
  const form = event.currentTarget;
  try {
    const formData = new FormData(form);
    const payload = {
      chapter_no: Number(formData.get("chapter_no")),
      effective_chapter_span: Number(formData.get("effective_chapter_span")),
      raw_instruction: formData.get("raw_instruction")?.toString().trim(),
    };
    await apiFetch(`/novels/${state.selectedNovelId}/interventions`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    showFlash("人工干预已保存", "success");
    pushActivity("新增干预", payload.raw_instruction, "success");
    form.reset();
    form.elements.namedItem("chapter_no").value = Math.max((state.selectedNovel?.current_chapter_no || 0) + 1, 1);
    form.elements.namedItem("effective_chapter_span").value = 5;
    await refreshSelectedNovel();
  } catch (error) {
    showFlash(`保存干预失败：${error.message}`, "error");
    pushActivity("干预失败", error.message, "error");
  }
}

async function handleExport(format) {
  if (!state.selectedNovelId) return;
  try {
    const response = await fetch(`${API}/novels/${state.selectedNovelId}/export?format=${format}`);
    if (!response.ok) throw new Error(await response.text());
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    const disposition = response.headers.get("content-disposition") || "";
    const filenameMatch = disposition.match(/filename\*=UTF-8''([^;]+)/i) || disposition.match(/filename="?([^";]+)"?/i);
    link.href = url;
    link.download = filenameMatch ? decodeURIComponent(filenameMatch[1]) : `novel.${format}`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    pushActivity("导出完成", `格式：${format.toUpperCase()}`, "success");
  } catch (error) {
    showFlash(`导出失败：${error.message}`, "error");
  }
}

async function handlePingApi() {
  try {
    const data = await apiFetch("/health");
    refs.apiStatusText.textContent = data.status === "ok" ? "正常" : "异常";
    showFlash("后端接口正常", "success");
  } catch (error) {
    refs.apiStatusText.textContent = "异常";
    showFlash(`后端检测失败：${error.message}`, "error");
  }
}

async function handlePingLlm() {
  try {
    const data = await apiFetch("/health/llm?ping=true");
    refs.llmStatusText.textContent = data.status === "ok" ? `${data.llm.provider || "ok"}` : "异常";
    showFlash("模型接口连通性正常", "success");
  } catch (error) {
    refs.llmStatusText.textContent = "异常";
    showFlash(`模型检测失败：${error.message}`, "error");
    pushActivity("模型检测失败", error.message, "error");
  }
}

async function handleDeleteNovel() {
  if (!state.selectedNovelId || !state.selectedNovel) return;
  const confirmed = await showConfirm({
    eyebrow: "危险操作",
    title: `删除《${state.selectedNovel.title}》？`,
    message: `这会删除整本小说以及已生成的全部章节。\n\n当前章节数：${state.chapters.length} 章。\n该操作不可撤销。`,
    confirmText: "确认删除整本书",
    danger: true,
  });
  if (!confirmed) return;

  try {
    setBusy("deleting", true);
    const result = await apiFetch(`/novels/${state.selectedNovelId}`, { method: "DELETE" });
    showFlash(`已删除《${result.deleted_title}》`, "success");
    pushActivity("删除整本书", `《${result.deleted_title}》与其 ${result.deleted_chapter_count} 章内容已移除`, "success");
    state.selectedNovelId = null;
    state.selectedNovel = null;
    state.selectedChapterNo = null;
    state.selectedChapter = null;
    state.chapters = [];
    state.consoleData = null;
    state.planningData = null;
    state.interventions = [];
    await loadShelf();
    if (!isReaderMode) {
      if (state.novels.length) {
        await selectNovel(state.novels[0].id);
      } else {
        setTopbar();
        renderMetrics();
        renderPlanning();
        renderInterventions();
        renderCatalog();
        renderPreview();
      }
    } else if (state.novels.length) {
      const latest = state.novels[0];
      window.location.href = `/app/reader?novelId=${latest.id}&chapterNo=${latest.current_chapter_no || 1}`;
    } else {
      refs.readerPageTitle.textContent = "当前没有可读内容";
      refs.readerPageContent.textContent = "这本书已经删除。返回工作台创建新小说即可。";
    }
  } catch (error) {
    showFlash(`删除失败：${error.message}`, "error");
    pushActivity("删除失败", error.message, "error");
  } finally {
    setBusy("deleting", false);
  }
}

async function handleDeleteTailFrom(fromChapterNo) {
  if (!state.selectedNovelId || !state.selectedNovel) return;
  const startIndex = state.chapters.findIndex((item) => item.chapter_no === fromChapterNo);
  if (startIndex < 0) return;
  const deleting = state.chapters.slice(startIndex);
  const confirmed = await showConfirm({
    eyebrow: "尾部回滚",
    title: `删除第 ${fromChapterNo} 章到末尾？`,
    message: `将要删除 ${deleting.length} 章：\n${deleting.map((item) => `第 ${item.chapter_no} 章《${item.title}》`).join("\n")}\n\n规则：只能从最后一章向前连续删除。`,
    confirmText: `确认删除 ${deleting.length} 章`,
    danger: true,
  });
  if (!confirmed) return;

  try {
    setBusy("deleting", true);
    const result = await apiFetch(`/novels/${state.selectedNovelId}/chapters/delete-tail`, {
      method: "POST",
      body: JSON.stringify({ from_chapter_no: fromChapterNo }),
    });
    showFlash(`已删除 ${result.deleted_count} 章，当前回退到第 ${result.current_chapter_no} 章`, "success");
    pushActivity("尾部删章", `删除章节：${result.deleted_chapter_nos.join(", ") || "无"}`, "success");

    const survivingChapterNo = result.current_chapter_no || null;
    await refreshSelectedNovel({ chapterNo: survivingChapterNo });
  } catch (error) {
    showFlash(`删章失败：${error.message}`, "error");
    pushActivity("删章失败", error.message, "error");
  } finally {
    setBusy("deleting", false);
  }
}

async function handleDeleteLastChapter() {
  if (!state.chapters.length) {
    showFlash("当前没有可删除的章节。", "info");
    return;
  }
  await handleDeleteTailFrom(state.chapters[state.chapters.length - 1].chapter_no);
}

function attachStudioEvents() {
  refs.shelfSearchInput?.addEventListener("input", renderBookshelf);
  refs.chapterSearchInput?.addEventListener("input", renderCatalog);
  refs.refreshShelfBtn?.addEventListener("click", loadShelf);
  refs.refreshChapterBtn?.addEventListener("click", () => state.selectedChapterNo && selectChapter(state.selectedChapterNo));
  refs.openReaderBtn?.addEventListener("click", () => openReader());
  refs.openCreatePanelBtn?.addEventListener("click", () => updateCreatePanel(true));
  refs.closeCreatePanelBtn?.addEventListener("click", () => updateCreatePanel(false));
  refs.createNovelForm?.addEventListener("submit", handleCreateNovel);
  refs.prepareWindowBtn?.addEventListener("click", handlePrepareWindow);
  refs.generateNextBtn?.addEventListener("click", handleGenerateNext);
  refs.generateBatchBtn?.addEventListener("click", handleGenerateBatch);
  refs.interventionForm?.addEventListener("submit", handleAddIntervention);
  refs.pingApiBtn?.addEventListener("click", handlePingApi);
  refs.pingLlmBtn?.addEventListener("click", handlePingLlm);
  refs.deleteNovelBtn?.addEventListener("click", handleDeleteNovel);
  refs.deleteLastChapterBtn?.addEventListener("click", handleDeleteLastChapter);
  refs.toggleManageModeBtn?.addEventListener("click", () => {
    state.managementMode = !state.managementMode;
    refs.toggleManageModeBtn.textContent = state.managementMode ? "退出删除管理" : "管理删除";
    renderCatalog();
  });
  document.querySelectorAll(".export-btn").forEach((button) => {
    button.addEventListener("click", () => handleExport(button.dataset.format));
  });
}

function attachReaderEvents() {
  refs.readerBackBtn?.addEventListener("click", () => {
    const chapterNo = state.selectedChapterNo || state.chapters[state.chapters.length - 1]?.chapter_no || 1;
    window.location.href = `/app?novelId=${state.selectedNovelId || ""}&chapterNo=${chapterNo}`;
  });
  refs.readerPrevBtn?.addEventListener("click", () => {
    const index = getCurrentChapterIndex();
    if (index > 0) selectChapter(state.chapters[index - 1].chapter_no, { updateUrl: true });
  });
  refs.readerNextBtn?.addEventListener("click", () => {
    const index = getCurrentChapterIndex();
    if (index >= 0 && index < state.chapters.length - 1) selectChapter(state.chapters[index + 1].chapter_no, { updateUrl: true });
  });
  refs.readerTocToggleBtn?.addEventListener("click", () => {
    refs.readerToc.classList.toggle("hidden");
  });
}

function attachCommonEvents() {
  refs.confirmCancelBtn?.addEventListener("click", () => closeConfirm(false));
  refs.confirmOkBtn?.addEventListener("click", () => closeConfirm(true));
  refs.confirmModal?.addEventListener("click", (event) => {
    if (event.target === refs.confirmModal || event.target.classList.contains("modal-backdrop")) closeConfirm(false);
  });
}

async function bootStudio() {
  refs.readerShell?.classList.add("hidden");
  refs.studioShell?.classList.remove("hidden");
  attachStudioEvents();
  attachCommonEvents();
  await handlePingApi();
  await loadShelf();
  const url = new URL(window.location.href);
  const novelId = Number(url.searchParams.get("novelId") || 0);
  const chapterNo = Number(url.searchParams.get("chapterNo") || 0);
  if (novelId) {
    await selectNovel(novelId, { desiredChapterNo: chapterNo || null });
  }
}

async function bootReader() {
  refs.studioShell?.classList.add("hidden");
  refs.readerShell?.classList.remove("hidden");
  attachReaderEvents();
  attachCommonEvents();
  const url = new URL(window.location.href);
  const novelId = Number(url.searchParams.get("novelId") || 0);
  const chapterNo = Number(url.searchParams.get("chapterNo") || 0);
  if (!novelId) {
    refs.readerPageTitle.textContent = "缺少 novelId";
    refs.readerPageContent.textContent = "请从工作台点“沉浸阅读”进入，或在地址中带上 ?novelId=数字&chapterNo=数字。";
    return;
  }
  await loadShelf();
  await selectNovel(novelId, { desiredChapterNo: chapterNo || null, updateReaderUrl: true });
}

async function boot() {
  setBusy("creating", false);
  setBusy("generating", false);
  setBusy("batch", false);
  setBusy("preparing", false);
  setBusy("deleting", false);
  renderActivity();
  if (isReaderMode) {
    await bootReader();
  } else {
    await bootStudio();
  }
}

boot().catch((error) => {
  showFlash(`初始化失败：${error.message}`, "error");
  pushActivity("初始化失败", error.message, "error");
});
