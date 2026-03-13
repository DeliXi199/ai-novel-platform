import {
  isReaderMode,
  state,
  refs,
  escapeHtml,
  fmtDate,
  formatParagraphs,
  chapterPreviewText,
  normalizeChapterPayload,
  buildBookshelfItemNode,
  getCurrentChapterIndex,
} from "/app/assets/app/core.js?v=20260313b";
import { buildChapterCardNode } from "/app/assets/app/ui_helpers.js?v=20260313b";

export function setTopbar() {
  if (!refs.topbarTitle) return;
  if (!state.selectedNovel) {
    refs.topbarTitle.textContent = "请选择一本书，或先新建项目";
    refs.topbarSubtitle.textContent = "你可以在这里管理书架、补规划、按章生成、从末尾回删章节，并以沉浸式阅读器查看正文。";
    return;
  }
  refs.topbarTitle.textContent = `《${state.selectedNovel.title}》`;
  refs.topbarSubtitle.textContent = `${state.selectedNovel.genre} · 主角 ${state.selectedNovel.protagonist_name} · 当前已写到第 ${state.selectedNovel.current_chapter_no} 章`;
}

export function renderBookshelf({ onSelectNovel }) {
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
        onSelectNovel(item.id);
      }
    });
    refs.bookshelfList.appendChild(node);
  });
}

export function renderMetrics() {
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

export function renderPlanning() {
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

export function renderInterventions() {
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

export function renderCatalog({ onSelectChapter, onOpenReader, onDeleteTailFrom }) {
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
    const node = buildChapterCardNode(chapter, lastChapterNo, {
      onSelectChapter: (chapterNo) => onSelectChapter(chapterNo),
      onOpenReader: (chapterNo) => onOpenReader(chapterNo),
      onDeleteTailFrom: (chapterNo) => onDeleteTailFrom(chapterNo),
    });
    refs.chapterList.appendChild(node);
  });
}

export function renderPreview() {
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

export function renderReaderMode({ onSelectChapter }) {
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
    button.addEventListener("click", () => onSelectChapter(chapter.chapter_no, { updateUrl: true }));
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

export function syncReaderUrl() {
  if (!isReaderMode || !state.selectedNovelId || !state.selectedChapterNo) return;
  const url = new URL(window.location.href);
  url.searchParams.set("novelId", String(state.selectedNovelId));
  url.searchParams.set("chapterNo", String(state.selectedChapterNo));
  window.history.replaceState({}, "", url.toString());
}
