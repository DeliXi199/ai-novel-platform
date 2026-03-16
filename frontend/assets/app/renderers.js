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
} from "/app/assets/app/core.js?v=20260316c";
import { buildChapterCardNode } from "/app/assets/app/ui_helpers.js?v=20260316c";

export function setTopbar() {
  if (!refs.topbarTitle) return;
  if (state.viewMode === "create") {
    refs.topbarTitle.textContent = "创建小说";
    refs.topbarSubtitle.textContent = "创建会以任务形式执行。先填写题材与前提，再等待初始化任务完成；完成后会自动进入小说管理页。";
    return;
  }
  if (!state.selectedNovel) {
    refs.topbarTitle.textContent = "请选择一本书，或进入创建页";
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

function summarizeCastingLayoutReview(summary, label = "当前 Arc") {
  if (!summary || typeof summary !== "object") return "";
  const lines = [];
  if (label) lines.push(`${label}：${summary.window_verdict || "—"}`);
  if (summary.review_note) lines.push(summary.review_note);
  const displayLines = Array.isArray(summary.display_lines) ? summary.display_lines.filter(Boolean).slice(0, 4) : [];
  if (displayLines.length) lines.push(...displayLines);
  return lines.filter(Boolean).join("\n");
}

function describeQueueItem(item) {
  const lines = [`第 ${item.chapter_no} 章：${item.title || item.goal || "未命名"}`];
  if (item.stage_casting_action || item.stage_casting_target) {
    const action = item.stage_casting_action || "人物投放";
    const target = item.stage_casting_target ? ` · ${item.stage_casting_target}` : "";
    lines.push(`动作：${action}${target}`);
  }
  if (item.stage_casting_note) lines.push(`说明：${item.stage_casting_note}`);
  return lines.join("\n");
}

function collectStageCastingRuntimeLines(liveRuntime, executionCard, dailyWorkbench) {
  const runtime = executionCard.stage_casting_runtime || dailyWorkbench.chapter_stage_casting_runtime || liveRuntime.stage_casting_runtime || {};
  const lines = [];
  const displayLines = Array.isArray(runtime.display_lines) ? runtime.display_lines.filter(Boolean).slice(0, 4) : [];
  if (displayLines.length) lines.push(...displayLines);
  const runtimeNote = dailyWorkbench.chapter_stage_casting_runtime_note || runtime.runtime_note || liveRuntime.stage_casting_runtime_note || "";
  if (runtimeNote && !lines.includes(runtimeNote)) lines.unshift(runtimeNote);
  return lines.filter(Boolean);
}

function planningRefreshReasonLabel(reason) {
  const mapping = {
    queue_low: "待写队列偏短",
    active_arc_nearly_exhausted: "当前 Arc 快用完",
    planning_window_already_ready: "现有规划已够用",
  };
  return mapping[String(reason || "").trim()] || String(reason || "—");
}

function summarizePlanningRefresh(liveRuntime) {
  const refresh = liveRuntime.planning_refresh || {};
  if (!refresh || typeof refresh !== "object" || !Object.keys(refresh).length) return null;
  const triggered = Boolean(refresh.triggered);
  const readyBefore = Array.isArray(refresh.ready_cards_before) ? refresh.ready_cards_before.filter(Boolean) : [];
  const readyAfter = Array.isArray(refresh.ready_cards_after) ? refresh.ready_cards_after.filter(Boolean) : [];
  const startChapter = Number(refresh.start_chapter || 0);
  const endChapter = Number(refresh.end_chapter || 0);
  const lastCovered = readyAfter.length ? readyAfter[readyAfter.length - 1] : (endChapter || liveRuntime.planned_until || 0);
  const statusLine = triggered
    ? `本次已刷新：新增第 ${startChapter || "—"}-${endChapter || "—"} 章，当前覆盖到第 ${lastCovered || "—"} 章。`
    : `本次未补规划：直接沿用现有近 5 章窗口，当前覆盖到第 ${lastCovered || "—"} 章。`;
  const lines = [
    statusLine,
    `触发原因：${planningRefreshReasonLabel(refresh.reason)}`,
  ];
  if (typeof refresh.queue_size_before === "number" || typeof refresh.queue_size_after === "number") {
    lines.push(`待写队列：${refresh.queue_size_before ?? "—"} → ${refresh.queue_size_after ?? "—"}`);
  }
  if (readyBefore.length || readyAfter.length) {
    lines.push(`就绪章节：${readyBefore.join("、") || "—"} → ${readyAfter.join("、") || "—"}`);
  }
  if (refresh.arc_no) lines.push(`对应 Arc：第 ${refresh.arc_no} 段`);
  return {
    title: triggered ? "近 5 章规划刷新" : "近 5 章规划就绪",
    body: lines.join("\n"),
    lines,
    triggered,
  };
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
      body: queue.length ? queue.map((item) => describeQueueItem(item)).join("\n\n") : "当前没有待写 card。",
    },
  ];

  const activeLayoutReview = activeArc.casting_layout_review_summary || planningStatus.active_arc_casting_layout_review || {};
  const pendingLayoutReview = pendingArc.casting_layout_review_summary || planningStatus.pending_arc_casting_layout_review || {};
  const activeLayoutText = summarizeCastingLayoutReview(activeLayoutReview, "当前 Arc 排法复核");
  const pendingLayoutText = summarizeCastingLayoutReview(pendingLayoutReview, "待命 Arc 排法复核");
  const planningRefreshSummary = summarizePlanningRefresh(liveRuntime);
  if (activeLayoutText) {
    summaryCards.push({ title: "人物投放排法复核", body: activeLayoutText });
  }
  if (pendingLayoutText) {
    summaryCards.push({ title: "下一段 Arc 排法复核", body: pendingLayoutText });
  }
  if (planningRefreshSummary) {
    summaryCards.push({ title: planningRefreshSummary.title, body: planningRefreshSummary.body });
  }

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
  if (liveRuntime.stage_casting_runtime_note) runtimeList.push(`人物投放：${liveRuntime.stage_casting_runtime_note}`);
  if (planningRefreshSummary?.lines?.[0]) runtimeList.push(`补规划：${planningRefreshSummary.lines[0]}`);

  const stageCastingRuntimeLines = collectStageCastingRuntimeLines(liveRuntime, executionCard, dailyWorkbench);

  const blocks = [
    {
      title: "活跃 Arc",
      list: [
        activeArc.focus || "—",
        activeArc.bridge_note || consoleData.planning_layers?.active_arc?.bridge_note || "—",
      ],
    },
    ...(activeLayoutText
      ? [{ title: "排法复核细节", list: activeLayoutText.split("\n").filter(Boolean) }]
      : []),
    {
      title: "当前执行卡",
      list: [
        dailyWorkbench.today_function || executionCard.chapter_function || "等待执行卡写入",
        executionCard.opening || dailyWorkbench.three_line_outline?.opening || "—",
        executionCard.middle || dailyWorkbench.three_line_outline?.middle || "—",
        executionCard.ending || dailyWorkbench.three_line_outline?.ending || "—",
        ...(stageCastingRuntimeLines.length ? stageCastingRuntimeLines.slice(0, 2) : []),
      ],
    },
    ...(stageCastingRuntimeLines.length
      ? [{ title: "人物投放执行提示", list: stageCastingRuntimeLines }]
      : []),
    ...(planningRefreshSummary?.lines?.length
      ? [{ title: planningRefreshSummary.title, list: planningRefreshSummary.lines }]
      : []),
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
    renderReaderAudio();
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
    renderReaderAudio();
    return;
  }
  refs.readerPageEyebrow.textContent = `第 ${chapter.chapter_no} 章`;
  refs.readerPageTitle.textContent = chapter.title;
  refs.readerPageMeta.textContent = `创建于 ${fmtDate(chapter.created_at)}`;
  refs.readerPageContent.innerHTML = formatParagraphs(chapter.content);
  refs.readerPrevBtn.disabled = index <= 0;
  refs.readerNextBtn.disabled = index < 0 || index >= state.chapters.length - 1;
  renderReaderAudio();
}

export function syncReaderUrl() {
  if (!isReaderMode || !state.selectedNovelId || !state.selectedChapterNo) return;
  const url = new URL(window.location.href);
  url.searchParams.set("novelId", String(state.selectedNovelId));
  url.searchParams.set("chapterNo", String(state.selectedChapterNo));
  window.history.replaceState({}, "", url.toString());
}


function taskTypeLabel(taskType) {
  if (taskType === "generate_next_chapter") return "单章生成";
  if (taskType === "generate_next_chapters_batch") return "批量生成";
  if (taskType === "generate_chapter_tts") return "章节朗读";
  if (taskType === "bootstrap_novel") return "创建小说";
  return taskType || "未知任务";
}

function taskStatusLabel(status) {
  if (status === "queued") return "排队中";
  if (status === "running") return "执行中";
  if (status === "succeeded") return "已完成";
  if (status === "failed") return "失败";
  if (status === "cancelled") return "已取消";
  return status || "未知";
}

function taskEventLevelLabel(level) {
  if (level === "error") return "错误";
  if (level === "warning") return "警告";
  return "记录";
}

function fmtTaskDuration(task) {
  const seconds = Number(task.duration_seconds || task.queue_wait_seconds || 0);
  if (!seconds) return "";
  if (seconds < 1) return "<1 秒";
  if (seconds < 60) return `${Math.round(seconds)} 秒`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} 分钟`;
  return `${Math.round(seconds / 3600)} 小时`;
}

export function renderTaskCenter({ onRetryTask, onCancelTask, onInspectTask } = {}) {
  if (!refs.taskHistoryList) return;
  refs.taskHistoryList.innerHTML = "";
  if (!state.selectedNovel) {
    refs.taskHistoryList.innerHTML = '<div class="panel-muted subtle-text">选择小说后，这里会显示最近任务、失败原因，以及可重试/可取消操作。</div>';
    return;
  }
  const items = Array.isArray(state.recentTasks) ? state.recentTasks : [];
  if (!items.length) {
    refs.taskHistoryList.innerHTML = '<div class="panel-muted subtle-text">最近还没有任务记录。生成章节或朗读后，这里会留下痕迹。</div>';
    return;
  }

  items.forEach((task) => {
    const div = document.createElement("div");
    const tone = task.status === "failed" ? "error" : task.status === "succeeded" ? "success" : "info";
    div.className = `activity-item ${tone} task-item`;
    const chapterText = task.chapter_no ? ` · 第 ${task.chapter_no} 章` : "";
    const retryText = task.retry_of_task_id ? ` · 重试自 #${task.retry_of_task_id}` : "";
    const details = task.progress_message || task.error_payload?.message || task.result_payload?.title || "暂无详细信息";
    const footerBits = [
      `创建于 ${fmtDate(task.created_at)}`,
      task.finished_at ? `结束于 ${fmtDate(task.finished_at)}` : null,
      task.duration_seconds ? `执行时长 ${fmtTaskDuration(task)}` : null,
      task.status === "queued" && task.queue_wait_seconds ? `已等待 ${fmtTaskDuration({ queue_wait_seconds: task.queue_wait_seconds })}` : null,
      retryText ? retryText.replace(/^ · /, "") : null,
    ].filter(Boolean);
    div.innerHTML = `
      <div class="task-item-top">
        <strong>${escapeHtml(taskTypeLabel(task.task_type))}${escapeHtml(chapterText)}</strong>
        <span class="task-status-chip ${escapeHtml(task.status || "")}">${escapeHtml(taskStatusLabel(task.status))}</span>
      </div>
      <div>${escapeHtml(details)}</div>
      <div class="subtle-text">${escapeHtml(footerBits.join(" · "))}</div>
      <div class="action-row wrap-row task-item-actions"></div>
    `;
    const actions = div.querySelector('.task-item-actions');
    if (task.can_retry && typeof onRetryTask === 'function') {
      const retryBtn = document.createElement('button');
      retryBtn.type = 'button';
      retryBtn.className = 'ghost-btn';
      retryBtn.textContent = '重试';
      retryBtn.addEventListener('click', () => onRetryTask(task));
      actions.appendChild(retryBtn);
    }
    if (task.can_cancel && typeof onCancelTask === 'function') {
      const cancelBtn = document.createElement('button');
      cancelBtn.type = 'button';
      cancelBtn.className = 'ghost-btn danger-btn';
      cancelBtn.textContent = task.cancel_requested_at ? '取消中...' : '取消';
      cancelBtn.disabled = !!task.cancel_requested_at;
      cancelBtn.addEventListener('click', () => onCancelTask(task));
      actions.appendChild(cancelBtn);
    }
    const inspectBtn = document.createElement('button');
    inspectBtn.type = 'button';
    inspectBtn.className = 'ghost-btn';
    inspectBtn.textContent = state.expandedTaskId === task.id ? '收起日志' : '查看日志';
    inspectBtn.addEventListener('click', () => onInspectTask?.(task));
    actions.appendChild(inspectBtn);
    if (!actions.children.length) actions.remove();

    if (state.expandedTaskId === task.id) {
      const eventWrap = document.createElement('div');
      eventWrap.className = 'task-event-list subtle-text';
      const events = Array.isArray(state.taskEventCache?.[task.id]) ? state.taskEventCache[task.id] : [];
      if (!events.length) {
        eventWrap.innerHTML = '<div class="panel-muted">这条任务还没有更多日志，或者日志还在路上。</div>';
      } else {
        eventWrap.innerHTML = events
          .map((event) => {
            const payloadText = event?.payload && Object.keys(event.payload).length ? ` · ${escapeHtml(JSON.stringify(event.payload))}` : '';
            return `<div class="task-event-item"><strong>${escapeHtml(taskEventLevelLabel(event.level))}</strong> · ${escapeHtml(fmtDate(event.created_at))} · ${escapeHtml(event.message || '')}${payloadText}</div>`;
          })
          .join('');
      }
      div.appendChild(eventWrap);
    }

    refs.taskHistoryList.appendChild(div);
  });
}


export function renderReaderAudio() {
  if (!refs.readerAudioPanel || !isReaderMode) return;
  const status = state.tts.status;
  const audio = refs.readerAudioPlayer;
  const track = refs.readerAudioSubtitleTrack;
  const voiceSelect = refs.readerVoiceSelect;
  const playbackSelect = refs.readerPlaybackVoiceSelect;
  const voiceOptions = Array.isArray(status?.voice_options) && status.voice_options.length
    ? status.voice_options
    : [
        { value: "zh-CN-YunxiNeural", label: "云希（男声，沉稳）" },
        { value: "zh-CN-XiaoxiaoNeural", label: "晓晓（女声，通用）" },
      ];
  const generatedVariants = Array.isArray(status?.generated_variants) ? status.generated_variants : [];
  const selectedVoice = state.tts.selectedVoice || status?.voice || voiceOptions[0]?.value || "";

  if (voiceSelect) {
    voiceSelect.innerHTML = voiceOptions
      .map((item) => `<option value="${escapeHtml(item.value)}">${escapeHtml(item.label)}</option>`)
      .join("");
    voiceSelect.value = voiceOptions.some((item) => item.value === selectedVoice) ? selectedVoice : voiceOptions[0]?.value || "";
  }

  if (playbackSelect) {
    if (generatedVariants.length) {
      playbackSelect.innerHTML = generatedVariants
        .map((item) => `<option value="${escapeHtml(item.voice)}">${escapeHtml(item.voice_label)}</option>`)
        .join("");
      const desiredPlaybackVoice = [state.tts.playbackVoice, selectedVoice, generatedVariants[0]?.voice].find((value) => generatedVariants.some((item) => item.voice === value));
      state.tts.playbackVoice = desiredPlaybackVoice || generatedVariants[0]?.voice || null;
      playbackSelect.value = state.tts.playbackVoice || generatedVariants[0]?.voice || "";
      playbackSelect.disabled = false;
    } else {
      playbackSelect.innerHTML = '<option value="">暂无已生成音频</option>';
      playbackSelect.value = "";
      playbackSelect.disabled = true;
      state.tts.playbackVoice = null;
    }
  }

  const activeVariant = generatedVariants.find((item) => item.voice === state.tts.playbackVoice) || null;
  const selectedVoiceReady = !!(status?.ready && status?.voice === (voiceSelect?.value || selectedVoice));

  if (!state.selectedChapter) {
    refs.readerAudioStatus.textContent = "选择章节后可生成朗读音频。";
    refs.readerAudioStatus.className = "reader-audio-status subtle-text";
    refs.readerGenerateTtsBtn.disabled = true;
    refs.readerRegenerateTtsBtn.disabled = true;
    refs.readerPlayTtsBtn.disabled = true;
    refs.readerPauseTtsBtn.disabled = true;
    refs.readerDownloadTtsBtn.disabled = true;
    refs.readerDownloadSubtitleBtn.disabled = true;
    if (audio) {
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
    }
    if (track) track.removeAttribute("src");
    return;
  }

  const statusTone = state.tts.statusTone || (selectedVoiceReady ? "ready" : status?.enabled === false ? "error" : "info");
  refs.readerAudioStatus.textContent = state.tts.statusText || status?.reason || "选择音色后可生成朗读音频。";
  refs.readerAudioStatus.className = `reader-audio-status subtle-text ${statusTone}`;

  const audioUrl = activeVariant?.audio_url || "";
  if (audio) {
    if (audioUrl) {
      const absoluteUrl = new URL(audioUrl, window.location.origin).toString();
      if (audio.src !== absoluteUrl) {
        audio.pause();
        audio.src = audioUrl;
        if (track) {
          if (activeVariant?.subtitle_url) track.src = activeVariant.subtitle_url;
          else track.removeAttribute("src");
        }
        audio.load();
      }
    } else if (audio.getAttribute("src")) {
      audio.pause();
      audio.removeAttribute("src");
      if (track) track.removeAttribute("src");
      audio.load();
    }
  }

  const disabledByCapability = status?.enabled === false;
  refs.readerGenerateTtsBtn.disabled = state.tts.busy || disabledByCapability || !state.selectedChapter;
  refs.readerGenerateTtsBtn.textContent = state.tts.busy ? "生成中..." : (selectedVoiceReady ? "已生成" : "生成朗读音频");
  refs.readerRegenerateTtsBtn.disabled = state.tts.busy || disabledByCapability || !state.selectedChapter;
  refs.readerPlayTtsBtn.disabled = state.tts.busy || !activeVariant;
  refs.readerPauseTtsBtn.disabled = !activeVariant;
  refs.readerDownloadTtsBtn.disabled = !activeVariant;
  refs.readerDownloadSubtitleBtn.disabled = !activeVariant?.subtitle_url;
}

