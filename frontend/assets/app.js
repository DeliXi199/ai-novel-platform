import {
  API,
  isReaderMode,
  state,
  refs,
  normalizeChapterPayload,
  getCurrentChapterIndex,
  apiFetch,
  showFlash,
  pushActivity,
  renderActivity,
  hasLiveBusyTask,
  mergeNovelIntoShelf,
  escapeHtml,
  fmtDate,
} from "/app/assets/app/core.js?v=20260316c";
import {
  showConfirm,
  closeConfirm,
  collectStylePreferences,
  formatQualityFeedback,
} from "/app/assets/app/ui_helpers.js?v=20260316c";
import {
  setTopbar,
  renderBookshelf,
  renderMetrics,
  renderPlanning,
  renderInterventions,
  renderCatalog,
  renderPreview,
  renderReaderMode,
  renderReaderAudio,
  renderTaskCenter,
  syncReaderUrl,
} from "/app/assets/app/renderers.js?v=20260316c";

function applyLiveRuntimePayload(payload) {
  if (!payload?.novel || !state.selectedNovelId || payload.novel.id !== state.selectedNovelId) return;
  state.selectedNovel = { ...(state.selectedNovel || {}), ...payload.novel };
  mergeNovelIntoShelf(state.selectedNovel);

  if (!state.planningData || typeof state.planningData !== "object") state.planningData = {};
  if (!state.planningData.planning_state || typeof state.planningData.planning_state !== "object") state.planningData.planning_state = {};
  state.planningData.planning_state.live_runtime = payload.live_runtime || {};
  state.planningData.planning_state.current_pipeline = payload.current_pipeline || {};
  state.planningData.planning_status = { ...(state.planningData.planning_status || {}), ...(payload.planning_status || {}) };
  if (!Array.isArray(state.planningData.chapter_card_queue) || !state.planningData.chapter_card_queue.length) {
    state.planningData.chapter_card_queue = payload.queue_preview || [];
  }

  if (!state.consoleData || typeof state.consoleData !== "object") state.consoleData = {};
  if (!state.consoleData.control_console || typeof state.consoleData.control_console !== "object") state.consoleData.control_console = {};
  state.consoleData.control_console.planning_status = { ...(state.consoleData.control_console.planning_status || {}), ...(payload.planning_status || {}) };

  const live = payload.live_runtime || {};
  const snapshotKey = [live.stage || "", live.note || "", live.updated_at || "", live.target_chapter_no || "", state.selectedNovel.current_chapter_no || 0].join("|");
  if (snapshotKey && snapshotKey !== state.lastLiveSnapshotKey && (live.stage || live.note)) {
    state.lastLiveSnapshotKey = snapshotKey;
    if (live.stage !== state.lastLiveStage) state.lastLiveStage = live.stage || null;
    pushActivity("流程推进", live.note || live.stage || "生成进度已更新", "info");
  }

  renderBookshelf({ onSelectNovel: selectNovel });
  syncRenameControls();
  setTopbar();
  renderMetrics();
  renderPlanning();
}

async function silentRefreshSelectedNovel({ chapterNo = null } = {}) {
  if (!state.selectedNovelId || state.liveRefreshInFlight) return;
  state.liveRefreshInFlight = true;
  try {
    const now = Date.now();
    const needFullBundle = !state.selectedNovel || !state.planningData || !state.consoleData || now - (state.lastBundleRefreshAt || 0) > 15000;
    if (needFullBundle) {
      await loadNovelBundle(state.selectedNovelId, { desiredChapterNo: chapterNo || state.selectedChapterNo, updateReaderUrl: isReaderMode });
      return;
    }
    const payload = await apiFetch(`/novels/${state.selectedNovelId}/live-runtime`, { timeoutMs: 4000 });
    applyLiveRuntimePayload(payload);
    const latestChapterNo = payload?.latest_chapter?.chapter_no || 0;
    const localLastChapterNo = state.chapters.length ? state.chapters[state.chapters.length - 1].chapter_no : 0;
    if (latestChapterNo > localLastChapterNo) {
      await loadNovelBundle(state.selectedNovelId, { desiredChapterNo: chapterNo || latestChapterNo || state.selectedChapterNo, updateReaderUrl: isReaderMode });
    }
  } catch (error) {
    console.warn("silent refresh failed", error);
  } finally {
    state.liveRefreshInFlight = false;
  }
}

function syncStudioUrl({ replace = true } = {}) {
  if (isReaderMode) return;
  const url = new URL(window.location.href);
  const basePath = state.viewMode === "create" ? "/app/create" : "/app";
  url.pathname = basePath;
  if (state.viewMode === "workspace" && state.selectedNovelId) {
    url.searchParams.set("novelId", String(state.selectedNovelId));
    if (state.selectedChapterNo) url.searchParams.set("chapterNo", String(state.selectedChapterNo));
    else url.searchParams.delete("chapterNo");
  } else {
    url.searchParams.delete("novelId");
    url.searchParams.delete("chapterNo");
  }
  if (replace) window.history.replaceState({}, "", url.toString());
  else window.history.pushState({}, "", url.toString());
}

function createTaskStageLabel(task) {
  const progress = task?.progress_payload || {};
  if (task?.status === "succeeded") return "初始化完成";
  if (task?.status === "failed") return "初始化失败";
  if (task?.status === "cancelled") return "已取消";
  return progress.stage_label || progress.stage || "排队中";
}

function createTaskStepText(task) {
  const progress = task?.progress_payload || {};
  const stepIndex = Number(progress.step_index || 0);
  const stepTotal = Number(progress.step_total || 0);
  if (!stepTotal) return "等待阶段信息";
  return `阶段 ${stepIndex} / ${stepTotal}`;
}

function createTaskPercent(task) {
  const progress = task?.progress_payload || {};
  const percent = Number(progress.percent || 0);
  if (Number.isFinite(percent) && percent >= 0) return Math.max(0, Math.min(percent, 100));
  return task?.status === "succeeded" ? 100 : 0;
}

async function syncTaskEvents(task, { limit = 8, force = false } = {}) {
  if (!task?.id || !task?.novel_id) return [];
  const cached = Array.isArray(state.taskEventCache?.[task.id]) ? state.taskEventCache[task.id] : null;
  if (cached && !force) return cached;
  const payload = await apiFetch(`/novels/${task.novel_id}/tasks/${task.id}/events?limit=${limit}`, { timeoutMs: 8000 });
  state.taskEventCache = { ...(state.taskEventCache || {}), [task.id]: payload.items || [] };
  return payload.items || [];
}

function renderCreateTaskPanel(task = state.pendingCreateTask) {
  if (!refs.createTaskPanel || !refs.createTaskStatusText || !refs.createTaskMeta) return;
  const current = task || null;
  if (!current) {
    refs.createTaskPanel.classList.add("hidden");
    refs.createTaskStatusText.textContent = "等待提交创建任务。";
    if (refs.createTaskStageChip) {
      refs.createTaskStageChip.textContent = "等待提交";
      refs.createTaskStageChip.className = "task-status-chip queued";
    }
    if (refs.createTaskStepText) refs.createTaskStepText.textContent = "阶段 0 / 0";
    if (refs.createTaskProgressBar) refs.createTaskProgressBar.style.width = "0%";
    refs.createTaskMeta.textContent = "创建成功后会自动进入小说管理页；失败时会保留失败现场和任务记录。";
    if (refs.createTaskEventList) refs.createTaskEventList.innerHTML = '<div class="panel-muted">这里会显示初始化阶段日志，告诉你它到底在忙哪一步。</div>';
    return;
  }
  refs.createTaskPanel.classList.remove("hidden");
  refs.createTaskStatusText.textContent = current.progress_message || "创建任务正在处理中。";
  if (refs.createTaskStageChip) {
    refs.createTaskStageChip.textContent = createTaskStageLabel(current);
    refs.createTaskStageChip.className = `task-status-chip ${escapeHtml(current.status || "queued")}`;
  }
  if (refs.createTaskStepText) refs.createTaskStepText.textContent = createTaskStepText(current);
  if (refs.createTaskProgressBar) refs.createTaskProgressBar.style.width = `${createTaskPercent(current)}%`;
  const progress = current.progress_payload || {};
  const bits = [
    progress.stage_description || null,
    current.novel_id ? `小说 ID：${current.novel_id}` : null,
    current.updated_at ? `更新时间：${fmtDate(current.updated_at)}` : null,
  ].filter(Boolean);
  refs.createTaskMeta.textContent = bits.join(" · ") || "创建任务已启动。";
  if (refs.createTaskEventList) {
    const events = Array.isArray(state.taskEventCache?.[current.id]) ? state.taskEventCache[current.id].slice(0, 6) : [];
    if (!events.length) {
      refs.createTaskEventList.innerHTML = '<div class="create-task-event-item">阶段日志稍后会出现在这里。</div>';
    } else {
      refs.createTaskEventList.innerHTML = events
        .map((event) => `<div class="create-task-event-item"><strong>${escapeHtml(fmtDate(event.created_at))}</strong> · ${escapeHtml(event.message || "")}<div class="subtle-text">${escapeHtml((event.payload || {}).stage_label || (event.payload || {}).stage || "")}</div></div>`)
        .join("");
    }
  }
}

function syncRenameControls() {
  if (refs.renameNovelInput) refs.renameNovelInput.value = state.selectedNovel?.title || "";
  const disabled = !state.selectedNovelId || state.busy.renaming || state.busy.creating;
  if (refs.renameNovelInput) refs.renameNovelInput.disabled = disabled;
  if (refs.renameNovelBtn) refs.renameNovelBtn.disabled = disabled;
}

function switchStudioView(mode, { replaceUrl = false } = {}) {
  state.viewMode = mode === "create" ? "create" : "workspace";
  refs.createView?.classList.toggle("hidden", state.viewMode !== "create");
  refs.workspaceView?.classList.toggle("hidden", state.viewMode !== "workspace");
  refs.backToWorkspaceBtn?.classList.toggle("hidden", state.viewMode !== "create");
  if (refs.openCreatePanelBtn) {
    refs.openCreatePanelBtn.textContent = state.viewMode === "create" ? "正在创建页" : "进入创建页";
    refs.openCreatePanelBtn.disabled = state.viewMode === "create";
  }
  renderCreateTaskPanel();
  syncRenameControls();
  setTopbar();
  syncStudioUrl({ replace: replaceUrl });
}


function setTtsStatus(text, tone = "info") {
  state.tts.statusText = text;
  state.tts.statusTone = tone;
  renderReaderAudio();
}

function setTtsBusy(value, text = "") {
  state.tts.busy = value;
  if (text) setTtsStatus(text, value ? "generating" : state.tts.statusTone || "info");
  else renderReaderAudio();
}

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

const taskWatchers = new Map();

async function pollTaskUntilTerminal(novelId, taskId, { intervalMs = 1200, timeoutMs = 20 * 60 * 1000, onProgress = null } = {}) {
  const startedAt = Date.now();
  let lastProgressKey = null;
  while (Date.now() - startedAt < timeoutMs) {
    const task = await apiFetch(`/novels/${novelId}/tasks/${taskId}`, { timeoutMs: Math.min(intervalMs, 5000) + 5000 });
    const progressKey = [task.status || "", task.progress_message || "", task.updated_at || ""].join("|");
    if (onProgress && progressKey !== lastProgressKey) {
      lastProgressKey = progressKey;
      onProgress(task);
    }
    if (task.status === "succeeded" || task.status === "failed" || task.status === "cancelled") return task;
    await sleep(intervalMs);
  }
  const error = new Error("任务轮询超时，请稍后手动刷新状态。");
  error.payload = { code: "TASK_POLL_TIMEOUT", task_id: taskId, novel_id: novelId };
  throw error;
}

function bindActiveTask(task) {
  if (!task?.id) return;
  if (task.task_type === "generate_next_chapter") state.activeTasks.chapterGeneration = task.id;
  if (task.task_type === "generate_next_chapters_batch") state.activeTasks.batchGeneration = task.id;
  if (task.task_type === "generate_chapter_tts") state.activeTasks.chapterTts = task.id;
  if (task.task_type === "bootstrap_novel") state.activeTasks.novelBootstrap = task.id;
  updateLiveRefreshLoop();
}

function clearActiveTask(task) {
  if (!task?.id) return;
  if (task.task_type === "generate_next_chapter" && state.activeTasks.chapterGeneration === task.id) state.activeTasks.chapterGeneration = null;
  if (task.task_type === "generate_next_chapters_batch" && state.activeTasks.batchGeneration === task.id) state.activeTasks.batchGeneration = null;
  if (task.task_type === "generate_chapter_tts" && state.activeTasks.chapterTts === task.id) state.activeTasks.chapterTts = null;
  if (task.task_type === "bootstrap_novel" && state.activeTasks.novelBootstrap === task.id) state.activeTasks.novelBootstrap = null;
  updateLiveRefreshLoop();
}

function buildTaskError(finalTask, fallbackMessage) {
  const taskError = finalTask?.error_payload || {};
  return Object.assign(new Error(taskError.message || fallbackMessage), { payload: taskError });
}

async function watchNextChapterTask(task, { silent = false } = {}) {
  bindActiveTask(task);
  const finalTask = await pollTaskUntilTerminal(task.novel_id, task.id, {
    intervalMs: 1500,
    onProgress: (snapshot) => {
      if (!snapshot.progress_message || silent) return;
      const tone = snapshot.status === "failed" ? "error" : snapshot.status === "cancelled" ? "info" : "info";
      pushActivity(snapshot.reused_existing ? "继续等待" : "生成进度", snapshot.progress_message, tone);
    },
  });
  clearActiveTask(finalTask);
  if (finalTask.status === "cancelled") {
    await refreshTaskHistory({ silent: true });
    if (!silent) {
      showFlash(finalTask.progress_message || "章节生成已取消。", "info");
      pushActivity("任务已取消", finalTask.progress_message || "章节生成已取消。", "info");
    }
    return finalTask;
  }
  if (finalTask.status !== "succeeded") throw buildTaskError(finalTask, "章节生成失败");
  const result = finalTask.result_payload || {};
  await refreshSelectedNovel({ chapterNo: result.chapter_no || state.selectedChapterNo });
  if (!silent) {
    showFlash(`第 ${result.chapter_no} 章生成成功`, "success");
    pushActivity("章节完成", `第 ${result.chapter_no} 章《${result.title || "未命名章节"}》已写入目录`, "success");
    const chapter = state.selectedChapter;
    const rejectionSummary = Array.isArray(chapter?.generation_meta?.quality_rejections) && chapter.generation_meta.quality_rejections.length
      ? `；本次共纠偏 ${chapter.generation_meta.quality_rejections.length} 次质检问题`
      : "";
    if (rejectionSummary) showFlash(`第 ${chapter.chapter_no} 章生成成功${rejectionSummary}`, "success");
    if (Array.isArray(chapter?.generation_meta?.quality_rejections)) {
      chapter.generation_meta.quality_rejections.forEach((item, index) => {
        const checks = Array.isArray(item?.failed_checks) && item.failed_checks.length ? item.failed_checks.join("、") : item?.display_message || item?.message || "质检未通过";
        pushActivity(`质检回退 ${index + 1}`, checks, "info");
      });
    }
  }
  return finalTask;
}

async function watchBatchGenerationTask(task, { silent = false } = {}) {
  bindActiveTask(task);
  let seenChapterNos = new Set();
  const seedChapters = Array.isArray(task.progress_payload?.generated_chapters) ? task.progress_payload.generated_chapters : [];
  seedChapters.forEach((item) => item?.chapter_no && seenChapterNos.add(item.chapter_no));
  const finalTask = await pollTaskUntilTerminal(task.novel_id, task.id, {
    intervalMs: 1500,
    onProgress: (snapshot) => {
      const generated = Array.isArray(snapshot.progress_payload?.generated_chapters) ? snapshot.progress_payload.generated_chapters : [];
      generated.forEach((item) => {
        if (!item?.chapter_no || seenChapterNos.has(item.chapter_no)) return;
        seenChapterNos.add(item.chapter_no);
        if (!silent) pushActivity(`第 ${item.chapter_no} 章完成`, item.title || "", "success");
        silentRefreshSelectedNovel({ chapterNo: item.chapter_no }).catch(() => {});
      });
      if (snapshot.progress_message && !silent) {
        const tone = snapshot.status === "failed" ? "error" : snapshot.status === "cancelled" ? "info" : "info";
        pushActivity("批量进度", snapshot.progress_message, tone);
      }
    },
  });
  clearActiveTask(finalTask);
  if (finalTask.status === "cancelled") {
    await refreshSelectedNovel();
    const partial = finalTask.result_payload || finalTask.error_payload?.partial_result || {};
    if (!silent) {
      showFlash(`批量任务已取消，已新增 ${partial.generated_count || 0} 章。`, "info");
      pushActivity("批量已取消", `取消前已新增 ${partial.generated_count || 0} 章`, "info");
    }
    return finalTask;
  }
  if (finalTask.status !== "succeeded") throw buildTaskError(finalTask, "批量生成失败");
  await refreshSelectedNovel();
  if (!silent) {
    const result = finalTask.result_payload || {};
    showFlash(`批量生成完成，共新增 ${result.generated_count || 0} 章。`, "success");
    pushActivity("批量完成", `本次共新增 ${result.generated_count || 0} 章`, "success");
  }
  return finalTask;
}

async function watchTtsTask(task, { autoplay = false, silent = false } = {}) {
  bindActiveTask(task);
  const targetVoice = task.request_payload?.voice || getSelectedVoice();
  if (task.reused_existing && task.progress_message && !silent) {
    setTtsStatus(task.progress_message, "generating");
  }
  const finalTask = await pollTaskUntilTerminal(task.novel_id, task.id, {
    intervalMs: 1200,
    onProgress: (snapshot) => {
      if (!snapshot.progress_message) return;
      const tone = snapshot.status === "failed" ? "error" : snapshot.status === "cancelled" ? "info" : "generating";
      setTtsStatus(snapshot.progress_message, tone);
    },
  });
  clearActiveTask(finalTask);
  if (finalTask.status === "cancelled") {
    await refreshTaskHistory({ silent: true });
    setTtsStatus(finalTask.progress_message || "朗读任务已取消。", "info");
    if (!silent) showFlash(finalTask.progress_message || "朗读任务已取消。", "info");
    return finalTask;
  }
  if (finalTask.status !== "succeeded") throw buildTaskError(finalTask, "朗读生成失败");
  const status = finalTask.result_payload || {};
  state.tts.status = status;
  state.tts.selectedVoice = status.voice || targetVoice;
  state.tts.playbackVoice = status.voice || targetVoice;
  setTtsStatus(`${getVoiceLabel(state.tts.playbackVoice)} 的 MP3 与字幕已生成。`, "ready");
  renderReaderAudio();
  if (!silent) {
    showFlash(`第 ${state.selectedChapterNo} 章 ${getVoiceLabel(state.tts.playbackVoice)} 版本已生成`, "success");
    pushActivity("朗读完成", `第 ${state.selectedChapterNo} 章 ${getVoiceLabel(state.tts.playbackVoice)} 版本已就绪`, "success");
  }
  if (autoplay && refs.readerAudioPlayer) {
    try {
      await refs.readerAudioPlayer.play();
    } catch (error) {
      if (!silent) showFlash("音频已生成，但浏览器拦截了自动播放，请手动点播放。", "info");
    }
  }
  return finalTask;
}

async function watchBootstrapTask(task, { silent = false } = {}) {
  bindActiveTask(task);
  state.pendingCreateTask = task;
  await syncTaskEvents(task, { limit: 8 }).catch(() => {});
  renderCreateTaskPanel(task);
  const finalTask = await pollTaskUntilTerminal(task.novel_id, task.id, {
    intervalMs: 1400,
    onProgress: (snapshot) => {
      state.pendingCreateTask = snapshot;
      syncTaskEvents(snapshot, { limit: 8, force: true }).then(() => renderCreateTaskPanel(snapshot)).catch(() => renderCreateTaskPanel(snapshot));
      if (!snapshot.progress_message || silent) return;
      const tone = snapshot.status === "failed" ? "error" : snapshot.status === "cancelled" ? "info" : "info";
      pushActivity(snapshot.reused_existing ? "继续等待创建任务" : "创建进度", snapshot.progress_message, tone);
    },
  });
  clearActiveTask(finalTask);
  state.pendingCreateTask = finalTask;
  await syncTaskEvents(finalTask, { limit: 8, force: true }).catch(() => {});
  renderCreateTaskPanel(finalTask);
  await loadShelf({ preferredNovelId: finalTask.novel_id, autoSelectFirst: false });
  const targetNovelId = finalTask.result_payload?.novel_id || finalTask.novel_id;
  if (finalTask.status === "succeeded" && targetNovelId) {
    await selectNovel(targetNovelId, { suppressNotFoundFlash: true });
    switchStudioView("workspace");
  }
  if (finalTask.status === "cancelled") {
    if (!silent) showFlash(finalTask.progress_message || "创建任务已取消。", "info");
    return finalTask;
  }
  if (finalTask.status !== "succeeded") throw buildTaskError(finalTask, "小说初始化失败");
  if (!silent) {
    const title = finalTask.result_payload?.title || state.selectedNovel?.title || "未命名小说";
    showFlash(`《${title}》创建成功`, "success");
    pushActivity("创建完成", `《${title}》已完成初始化并进入小说管理页`, "success");
  }
  state.pendingCreateTask = null;
  renderCreateTaskPanel(null);
  return finalTask;
}

function ensureTaskWatcher(task, options = {}) {
  if (!task?.id || !task?.novel_id) return Promise.resolve(task);
  if (taskWatchers.has(task.id)) return taskWatchers.get(task.id);
  let watcher;
  if (task.task_type === "generate_next_chapter") watcher = watchNextChapterTask(task, options);
  else if (task.task_type === "generate_next_chapters_batch") watcher = watchBatchGenerationTask(task, options);
  else if (task.task_type === "generate_chapter_tts") watcher = watchTtsTask(task, options);
  else if (task.task_type === "bootstrap_novel") watcher = watchBootstrapTask(task, options);
  else watcher = Promise.resolve(task);
  const tracked = Promise.resolve(watcher).finally(() => {
    taskWatchers.delete(task.id);
    refreshTaskHistory({ silent: true }).catch(() => {});
    updateLiveRefreshLoop();
  });
  taskWatchers.set(task.id, tracked);
  return tracked;
}

function resumeWorkspaceTasks(activeTasks) {
  const items = Array.isArray(activeTasks) ? activeTasks : [];
  state.activeTasks.chapterGeneration = null;
  state.activeTasks.batchGeneration = null;
  state.activeTasks.chapterTts = null;
  state.activeTasks.novelBootstrap = null;
  if (!items.length) {
    updateLiveRefreshLoop();
    return;
  }
  items.forEach((task) => {
    bindActiveTask(task);
    if (task.task_type === "generate_next_chapter" || task.task_type === "generate_next_chapters_batch") {
      ensureTaskWatcher(task, { silent: true }).catch((error) => {
        pushActivity("后台任务失败", error.message, "error");
      });
      return;
    }
    if (task.task_type === "generate_chapter_tts" && task.chapter_no === state.selectedChapterNo) {
      setTtsStatus(task.progress_message || "朗读任务正在处理中。", "generating");
      ensureTaskWatcher(task, { silent: true }).catch(() => {
        setTtsStatus("朗读任务失败，请重试。", "error");
      });
      return;
    }
    if (task.task_type === "bootstrap_novel") {
      state.pendingCreateTask = task;
      syncTaskEvents(task, { limit: 8 }).then(() => renderCreateTaskPanel(task)).catch(() => renderCreateTaskPanel(task));
      ensureTaskWatcher(task, { silent: true }).catch((error) => {
        pushActivity("创建任务失败", error.message, "error");
      });
    }
  });
}

function getGeneratedVariants() {
  return Array.isArray(state.tts.status?.generated_variants) ? state.tts.status.generated_variants : [];
}

function getVoiceLabel(voice) {
  const options = Array.isArray(state.tts.status?.voice_options) ? state.tts.status.voice_options : [];
  const matched = options.find((item) => item.value === voice);
  return matched?.label || voice || "未知音色";
}

function getSelectedVoice() {
  return refs.readerVoiceSelect?.value || state.tts.selectedVoice || state.tts.status?.voice || "zh-CN-YunxiNeural";
}

function getActivePlaybackVariant() {
  const variants = getGeneratedVariants();
  return variants.find((item) => item.voice === state.tts.playbackVoice) || null;
}

function syncPlaybackVoice() {
  const variants = getGeneratedVariants();
  const preferred = [state.tts.playbackVoice, state.tts.selectedVoice, variants[0]?.voice].find((value) => variants.some((item) => item.voice === value));
  state.tts.playbackVoice = preferred || null;
}

async function refreshChapterTtsState({ suppressErrors = false, voice = null } = {}) {
  if (!state.selectedNovelId || !state.selectedChapterNo) {
    state.tts.status = null;
    state.tts.selectedVoice = "zh-CN-YunxiNeural";
    state.tts.playbackVoice = null;
    setTtsStatus("选择章节后可生成朗读音频。", "info");
    return;
  }
  try {
    const targetVoice = voice || state.tts.selectedVoice || getSelectedVoice();
    const query = targetVoice ? `?voice=${encodeURIComponent(targetVoice)}` : "";
    const status = await apiFetch(`/novels/${state.selectedNovelId}/chapters/${state.selectedChapterNo}/tts${query}`, { timeoutMs: 12000 });
    state.tts.status = status;
    state.tts.selectedVoice = targetVoice || status.voice || "zh-CN-YunxiNeural";
    syncPlaybackVoice();
    if (status.ready) {
      setTtsStatus(`${getVoiceLabel(status.voice)} 的 MP3 已生成，可直接播放。`, "ready");
    } else if (status.enabled === false) {
      setTtsStatus(status.reason || "朗读功能当前不可用。", "error");
    } else {
      setTtsStatus(status.reason || "还没有生成本章音频。", "info");
    }
  } catch (error) {
    state.tts.status = null;
    if (!suppressErrors) showFlash(`读取朗读状态失败：${error.message}`, "error");
    setTtsStatus("朗读状态读取失败，请稍后重试。", "error");
  }
}

async function generateChapterTts({ forceRegenerate = false, autoplay = false } = {}) {
  if (!state.selectedNovelId || !state.selectedChapterNo) return;
  const targetVoice = getSelectedVoice();
  if (!forceRegenerate && state.tts.status?.ready && state.tts.status.voice === targetVoice) {
    state.tts.playbackVoice = targetVoice;
    setTtsStatus(`${getVoiceLabel(targetVoice)} 的 MP3 已生成，无需重复生成。`, "ready");
    renderReaderAudio();
    return;
  }
  try {
    setTtsBusy(true, `正在为第 ${state.selectedChapterNo} 章排队生成 ${getVoiceLabel(targetVoice)} 的 MP3 和字幕...`);
    pushActivity("朗读生成", `第 ${state.selectedChapterNo} 章开始准备 ${getVoiceLabel(targetVoice)} 的 MP3`, "info");
    const task = await apiFetch(`/novels/${state.selectedNovelId}/chapters/${state.selectedChapterNo}/tts/tasks`, {
      method: "POST",
      body: JSON.stringify({
        voice: targetVoice,
        force_regenerate: forceRegenerate,
      }),
    });
    await ensureTaskWatcher(task, { autoplay });
  } catch (error) {
    setTtsStatus(`朗读生成失败：${error.message}`, "error");
    showFlash(`朗读生成失败：${error.message}`, "error");
    pushActivity("朗读失败", error.message, "error");
  } finally {
    setTtsBusy(false);
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
  }, 2500);
}

function renderWorkspaceSidePanels() {
  renderInterventions();
  renderTaskCenter({ onRetryTask: handleRetryTask, onCancelTask: handleCancelTask, onInspectTask: handleToggleTaskEvents });
}

async function refreshTaskHistory({ silent = false } = {}) {
  if (!state.selectedNovelId) {
    state.recentTasks = [];
    renderTaskCenter({ onRetryTask: handleRetryTask, onCancelTask: handleCancelTask, onInspectTask: handleToggleTaskEvents });
    return;
  }
  try {
    const data = await apiFetch(`/novels/${state.selectedNovelId}/tasks?limit=12`, { timeoutMs: 8000 });
    state.recentTasks = Array.isArray(data.items) ? data.items : [];
    renderTaskCenter({ onRetryTask: handleRetryTask, onCancelTask: handleCancelTask, onInspectTask: handleToggleTaskEvents });
    if (!silent) showFlash("任务历史已刷新。", "success");
  } catch (error) {
    if (!silent) showFlash(`刷新任务历史失败：${error.message}`, "error");
  }
}


async function handleToggleTaskEvents(task) {
  if (!state.selectedNovelId || !task?.id) return;
  if (state.expandedTaskId === task.id) {
    state.expandedTaskId = null;
    renderTaskCenter({ onRetryTask: handleRetryTask, onCancelTask: handleCancelTask, onInspectTask: handleToggleTaskEvents });
    return;
  }
  try {
    if (!Array.isArray(state.taskEventCache?.[task.id])) {
      const payload = await apiFetch(`/novels/${state.selectedNovelId}/tasks/${task.id}/events?limit=40`, { timeoutMs: 8000 });
      state.taskEventCache = { ...(state.taskEventCache || {}), [task.id]: payload.items || [] };
    }
    state.expandedTaskId = task.id;
    renderTaskCenter({ onRetryTask: handleRetryTask, onCancelTask: handleCancelTask, onInspectTask: handleToggleTaskEvents });
  } catch (error) {
    showFlash(`读取任务日志失败：${error.message}`, "error");
  }
}

async function handleRetryTask(task) {
  if (!state.selectedNovelId || !task?.id) return;
  try {
    pushActivity("任务重试", `准备重试任务 #${task.id}`, "info");
    const retried = await apiFetch(`/novels/${state.selectedNovelId}/tasks/${task.id}/retry`, { method: "POST" });
    await refreshTaskHistory({ silent: true });
    await ensureTaskWatcher(retried, { silent: false });
  } catch (error) {
    showFlash(`重试失败：${error.message}`, "error");
    pushActivity("任务重试失败", error.message, "error");
  }
}

async function handleCancelTask(task) {
  if (!state.selectedNovelId || !task?.id) return;
  try {
    const cancelled = await apiFetch(`/novels/${state.selectedNovelId}/tasks/${task.id}/cancel`, { method: "POST" });
    const isImmediateTerminal = cancelled.status === "cancelled";
    if (isImmediateTerminal) clearActiveTask(cancelled);
    await refreshTaskHistory({ silent: true });
    setBusy("generating", state.busy.generating);
    showFlash(cancelled.progress_message || "已提交取消请求。", "info");
    pushActivity("请求取消", cancelled.progress_message || `任务 #${task.id} 已收到取消请求`, "info");
  } catch (error) {
    showFlash(`取消任务失败：${error.message}`, "error");
    pushActivity("取消任务失败", error.message, "error");
  }
}

async function handleCleanupTaskHistory() {
  if (!state.selectedNovelId) return;
  try {
    const result = await apiFetch(`/novels/${state.selectedNovelId}/tasks/cleanup?keep_latest=12&older_than_days=14`, { method: "POST" });
    await refreshTaskHistory({ silent: true });
    showFlash(`已清理 ${result.deleted_count || 0} 条旧任务记录。`, "success");
    pushActivity("任务清理", `清理旧任务记录 ${result.deleted_count || 0} 条`, "success");
  } catch (error) {
    showFlash(`清理任务历史失败：${error.message}`, "error");
  }
}

function setBusy(key, value) {
  state.busy[key] = value;
  const generatingBusy = state.busy.generating || !!state.activeTasks.chapterGeneration;
  const batchBusy = state.busy.batch || !!state.activeTasks.batchGeneration;
  const deletingBusy = state.busy.deleting;
  const preparingBusy = state.busy.preparing;
  if (refs.createNovelForm) refs.createNovelForm.querySelector("button[type='submit']").disabled = state.busy.creating;
  if (refs.prepareWindowBtn) {
    refs.prepareWindowBtn.disabled = preparingBusy || generatingBusy || batchBusy;
    refs.prepareWindowBtn.textContent = preparingBusy ? "规划中..." : "强制补规划";
  }
  if (refs.generateNextBtn) {
    refs.generateNextBtn.disabled = generatingBusy || batchBusy || deletingBusy || preparingBusy;
    refs.generateNextBtn.textContent = generatingBusy ? "生成中..." : "生成下一章";
  }
  if (refs.generateBatchBtn) {
    refs.generateBatchBtn.disabled = generatingBusy || batchBusy || deletingBusy || preparingBusy;
    refs.generateBatchBtn.textContent = batchBusy ? "批量生成中..." : "批量任务生成";
  }
  if (refs.deleteLastChapterBtn) refs.deleteLastChapterBtn.disabled = deletingBusy || generatingBusy || batchBusy;
  if (refs.deleteNovelBtn) refs.deleteNovelBtn.disabled = deletingBusy || generatingBusy || batchBusy;
  if (refs.renameNovelBtn) refs.renameNovelBtn.textContent = state.busy.renaming ? "保存中..." : "保存新名称";
  syncRenameControls();
  updateLiveRefreshLoop();
}

async function loadShelf({ preferredNovelId = null, autoSelectFirst = true } = {}) {
  const data = await apiFetch("/novels?limit=100");
  state.novels = data.items || [];
  renderBookshelf({ onSelectNovel: selectNovel });
  if (state.selectedNovelId || isReaderMode || !autoSelectFirst || !state.novels.length) return;
  const preferred = preferredNovelId && state.novels.find((item) => item.id === preferredNovelId);
  if (preferred) {
    await selectNovel(preferred.id, { suppressNotFoundFlash: true });
    return;
  }
  await selectNovel(state.novels[0].id, { suppressNotFoundFlash: true });
}

async function loadNovelBundle(novelId, { desiredChapterNo = null, updateReaderUrl = false } = {}) {
  const query = desiredChapterNo ? `?desired_chapter_no=${encodeURIComponent(desiredChapterNo)}` : "";
  const workspace = await apiFetch(`/novels/${novelId}/workspace${query}`, { timeoutMs: 12000 });

  state.selectedNovelId = novelId;
  state.selectedNovel = workspace.novel || null;
  state.chapters = workspace.chapters?.items || [];
  state.consoleData = workspace.console_data || null;
  state.planningData = workspace.planning_data || null;
  state.interventions = workspace.interventions?.items || [];
  state.recentTasks = workspace.recent_tasks || [];
  state.taskEventCache = {};
  state.expandedTaskId = null;
  state.selectedChapterNo = workspace.selected_chapter_no || null;
  state.selectedChapter = normalizeChapterPayload(workspace.selected_chapter);
  state.tts.status = null;
  state.tts.selectedVoice = "zh-CN-YunxiNeural";
  state.tts.playbackVoice = null;
  state.lastBundleRefreshAt = Date.now();

  renderBookshelf({ onSelectNovel: selectNovel });
  setTopbar();
  renderMetrics();
  renderPlanning();
  renderWorkspaceSidePanels();
  renderCatalog({ onSelectChapter: selectChapter, onOpenReader: openReader, onDeleteTailFrom: handleDeleteTailFrom });
  renderPreview();
  renderReaderMode({ onSelectChapter: selectChapter });
  await refreshChapterTtsState({ suppressErrors: true });
  resumeWorkspaceTasks(workspace.active_tasks || []);
  setBusy("generating", state.busy.generating);

  const chapterNoField = refs.interventionForm?.elements?.namedItem("chapter_no");
  if (chapterNoField) chapterNoField.value = Math.max((state.selectedNovel?.current_chapter_no || 0) + 1, 1);
  if (updateReaderUrl) syncReaderUrl();
}

async function selectNovel(novelId, options = {}) {
  const { suppressNotFoundFlash = false, ...loadOptions } = options;
  pushActivity("切换小说", `载入小说 #${novelId}`);
  try {
    await loadNovelBundle(novelId, loadOptions);
    if (!isReaderMode) switchStudioView("workspace");
    return true;
  } catch (error) {
    const notFound = error?.status === 404 || /novel not found/i.test(error?.message || "");
    if (notFound) {
      state.selectedNovelId = null;
      state.selectedNovel = null;
      state.chapters = [];
      state.consoleData = null;
      state.planningData = null;
      state.interventions = [];
      state.recentTasks = [];
      state.selectedChapterNo = null;
      state.selectedChapter = null;
      state.activeTasks.chapterGeneration = null;
      state.activeTasks.batchGeneration = null;
      state.activeTasks.chapterTts = null;
      state.activeTasks.novelBootstrap = null;
      renderBookshelf({ onSelectNovel: selectNovel });
      syncRenameControls();
      renderMetrics();
      renderPlanning();
      renderWorkspaceSidePanels();
      renderCatalog({ onSelectChapter: selectChapter, onOpenReader: openReader, onDeleteTailFrom: handleDeleteTailFrom });
      renderPreview();
      renderReaderMode({ onSelectChapter: selectChapter });
      if (!suppressNotFoundFlash) {
        showFlash(`载入小说失败：${error.message}`, "error");
      }
      pushActivity("载入失败", `小说 #${novelId} 不存在或已被删除`, "error");
      return false;
    }
    showFlash(`载入小说失败：${error.message}`, "error");
    pushActivity("载入失败", error.message, "error");
    return false;
  }
}

async function selectChapter(chapterNo, { updateUrl = false } = {}) {
  if (!state.selectedNovelId) return;
  state.selectedChapterNo = chapterNo;
  state.selectedChapter = null;
  state.tts.status = null;
  state.tts.selectedVoice = "zh-CN-YunxiNeural";
  state.tts.playbackVoice = null;
  renderCatalog({ onSelectChapter: selectChapter, onOpenReader: openReader, onDeleteTailFrom: handleDeleteTailFrom });
  renderPreview();
  renderReaderMode({ onSelectChapter: selectChapter });
  try {
    state.selectedChapter = normalizeChapterPayload(await apiFetch(`/novels/${state.selectedNovelId}/chapters/${chapterNo}`));
    renderPreview();
    renderReaderMode({ onSelectChapter: selectChapter });
    await refreshChapterTtsState({ suppressErrors: true });
    if (updateUrl) syncReaderUrl();
  } catch (error) {
    state.selectedChapter = null;
    renderPreview();
    renderReaderMode({ onSelectChapter: selectChapter });
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
    const task = await apiFetch("/novels/tasks/bootstrap", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.pendingCreateTask = task;
    renderCreateTaskPanel(task);
    await loadShelf({ preferredNovelId: task.novel_id, autoSelectFirst: false });
    pushActivity("创建任务已提交", task.progress_message || `小说 #${task.novel_id} 已进入初始化队列`, "info");
    await ensureTaskWatcher(task);
    form.reset();
  } catch (error) {
    const failedNovelId = error?.payload?.novel?.id || error?.payload?.novel_id || state.pendingCreateTask?.novel_id;
    if (failedNovelId) {
      await loadShelf({ preferredNovelId: failedNovelId, autoSelectFirst: false });
      await selectNovel(failedNovelId, { suppressNotFoundFlash: true });
      switchStudioView("workspace");
    }
    showFlash(`创建失败：${error.message}`, "error");
    pushActivity(
      "创建失败",
      failedNovelId ? `${error.message}（已保留失败现场，可直接在任务中心重试）` : error.message,
      "error",
    );
  } finally {
    setBusy("creating", false);
  }
}

async function refreshSelectedNovel({ chapterNo = null } = {}) {
  if (!state.selectedNovelId) return;
  await loadNovelBundle(state.selectedNovelId, { desiredChapterNo: chapterNo || state.selectedChapterNo, updateReaderUrl: isReaderMode });
}

async function handleRenameNovel() {
  if (!state.selectedNovelId || !state.selectedNovel) return;
  const title = refs.renameNovelInput?.value?.trim() || "";
  if (!title) {
    showFlash("小说名称不能为空。", "info");
    return;
  }
  if (title === state.selectedNovel.title) {
    showFlash("书名没有变化。", "info");
    return;
  }
  try {
    setBusy("renaming", true);
    const updated = await apiFetch(`/novels/${state.selectedNovelId}/title`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    });
    state.selectedNovel = updated;
    mergeNovelIntoShelf(updated);
    syncRenameControls();
    renderBookshelf({ onSelectNovel: selectNovel });
    setTopbar();
    renderMetrics();
    showFlash(`书名已更新为《${updated.title}》`, "success");
    pushActivity("修改书名", `小说已更名为《${updated.title}》`, "success");
  } catch (error) {
    showFlash(`修改书名失败：${error.message}`, "error");
    pushActivity("修改书名失败", error.message, "error");
  } finally {
    setBusy("renaming", false);
  }
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
    pushActivity("开始生成", `小说 #${state.selectedNovelId} 的下一章已加入任务队列，主控台会自动刷新`, "info");
    const task = await apiFetch(`/novels/${state.selectedNovelId}/tasks/next-chapter`, { method: "POST" });
    await ensureTaskWatcher(task);
  } catch (error) {
    const payload = error.payload || {};
    const extra = payload?.code ? ` [${payload.code}]` : "";
    const qualityNote = formatQualityFeedback(payload);
    const suffix = qualityNote ? `｜${qualityNote}` : "";
    showFlash(`生成失败${extra}：${error.message}${suffix}`, "error");
    pushActivity("生成失败", `${error.message}${extra}${suffix}`, "error");
  } finally {
    setBusy("generating", false);
  }
}

async function handleGenerateBatch() {
  if (!state.selectedNovelId) return;
  const count = Math.max(1, Math.min(20, Number(refs.batchCountInput.value || 1)));
  try {
    setBusy("batch", true);
    pushActivity("批量生成", `请求连续生成 ${count} 章`, "info");
    const task = await apiFetch(`/novels/${state.selectedNovelId}/tasks/next-chapters`, {
      method: "POST",
      body: JSON.stringify({ count }),
    });
    await ensureTaskWatcher(task);
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
    const chapterNoField = form.elements?.namedItem("chapter_no");
    const spanField = form.elements?.namedItem("effective_chapter_span");
    if (chapterNoField) chapterNoField.value = Math.max((state.selectedNovel?.current_chapter_no || 0) + 1, 1);
    if (spanField) spanField.value = 5;
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
    state.recentTasks = [];
    await loadShelf();
    if (!isReaderMode) {
      if (state.novels.length) {
        await selectNovel(state.novels[0].id);
      } else {
        setTopbar();
        renderMetrics();
        renderPlanning();
        renderWorkspaceSidePanels();
        renderCatalog({ onSelectChapter: selectChapter, onOpenReader: openReader, onDeleteTailFrom: handleDeleteTailFrom });
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
  refs.shelfSearchInput?.addEventListener("input", () => renderBookshelf({ onSelectNovel: selectNovel }));
  refs.chapterSearchInput?.addEventListener("input", () => renderCatalog({ onSelectChapter: selectChapter, onOpenReader: openReader, onDeleteTailFrom: handleDeleteTailFrom }));
  refs.refreshShelfBtn?.addEventListener("click", () => loadShelf({ autoSelectFirst: !state.selectedNovelId && state.viewMode !== "create" }));
  refs.refreshChapterBtn?.addEventListener("click", () => state.selectedChapterNo && selectChapter(state.selectedChapterNo));
  refs.openReaderBtn?.addEventListener("click", () => openReader());
  refs.openCreatePanelBtn?.addEventListener("click", () => switchStudioView("create"));
  refs.closeCreatePanelBtn?.addEventListener("click", () => switchStudioView("workspace"));
  refs.backToWorkspaceBtn?.addEventListener("click", () => switchStudioView("workspace"));
  refs.createNovelForm?.addEventListener("submit", handleCreateNovel);
  refs.prepareWindowBtn?.addEventListener("click", handlePrepareWindow);
  refs.generateNextBtn?.addEventListener("click", handleGenerateNext);
  refs.generateBatchBtn?.addEventListener("click", handleGenerateBatch);
  refs.renameNovelBtn?.addEventListener("click", handleRenameNovel);
  refs.renameNovelInput?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      handleRenameNovel();
    }
  });
  refs.interventionForm?.addEventListener("submit", handleAddIntervention);
  refs.pingApiBtn?.addEventListener("click", handlePingApi);
  refs.pingLlmBtn?.addEventListener("click", handlePingLlm);
  refs.deleteNovelBtn?.addEventListener("click", handleDeleteNovel);
  refs.deleteLastChapterBtn?.addEventListener("click", handleDeleteLastChapter);
  refs.refreshTaskHistoryBtn?.addEventListener("click", () => refreshTaskHistory());
  refs.cleanupTaskHistoryBtn?.addEventListener("click", handleCleanupTaskHistory);
  refs.toggleManageModeBtn?.addEventListener("click", () => {
    state.managementMode = !state.managementMode;
    refs.toggleManageModeBtn.textContent = state.managementMode ? "退出删除管理" : "管理删除";
    renderCatalog({ onSelectChapter: selectChapter, onOpenReader: openReader, onDeleteTailFrom: handleDeleteTailFrom });
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
  refs.readerVoiceSelect?.addEventListener("change", async () => {
    state.tts.selectedVoice = refs.readerVoiceSelect.value;
    const existingVariant = getGeneratedVariants().find((item) => item.voice === state.tts.selectedVoice);
    if (existingVariant) state.tts.playbackVoice = existingVariant.voice;
    await refreshChapterTtsState({ suppressErrors: true, voice: state.tts.selectedVoice });
  });
  refs.readerPlaybackVoiceSelect?.addEventListener("change", () => {
    state.tts.playbackVoice = refs.readerPlaybackVoiceSelect.value || null;
    const active = getActivePlaybackVariant();
    if (active) setTtsStatus(`当前播放版本已切换为 ${active.voice_label}。`, "ready");
    else renderReaderAudio();
  });
  refs.readerGenerateTtsBtn?.addEventListener("click", () => generateChapterTts({ autoplay: true }));
  refs.readerRegenerateTtsBtn?.addEventListener("click", () => generateChapterTts({ forceRegenerate: true, autoplay: true }));
  refs.readerPlayTtsBtn?.addEventListener("click", async () => {
    if (!refs.readerAudioPlayer) return;
    try {
      await refs.readerAudioPlayer.play();
    } catch (error) {
      showFlash("浏览器没有允许直接播放，请点播放器上的播放按钮再试。", "info");
    }
  });
  refs.readerPauseTtsBtn?.addEventListener("click", () => refs.readerAudioPlayer?.pause());
  refs.readerDownloadTtsBtn?.addEventListener("click", () => {
    const active = getActivePlaybackVariant();
    if (!active?.audio_url) return;
    const link = document.createElement("a");
    link.href = active.audio_url;
    link.download = `chapter-${state.selectedChapterNo || "audio"}-${active.voice}.mp3`;
    document.body.appendChild(link);
    link.click();
    link.remove();
  });
  refs.readerDownloadSubtitleBtn?.addEventListener("click", () => {
    const active = getActivePlaybackVariant();
    if (!active?.subtitle_url) return;
    const link = document.createElement("a");
    link.href = active.subtitle_url;
    link.download = `chapter-${state.selectedChapterNo || "audio"}-${active.voice}.vtt`;
    document.body.appendChild(link);
    link.click();
    link.remove();
  });
  refs.readerAudioPlayer?.addEventListener("play", renderReaderAudio);
  refs.readerAudioPlayer?.addEventListener("pause", renderReaderAudio);
  refs.readerAudioPlayer?.addEventListener("ended", renderReaderAudio);
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
  switchStudioView(state.viewMode, { replaceUrl: true });
  await handlePingApi();
  const url = new URL(window.location.href);
  const novelId = Number(url.searchParams.get("novelId") || 0);
  const chapterNo = Number(url.searchParams.get("chapterNo") || 0);
  const shouldAutoSelectFirst = state.viewMode !== "create" && !novelId;
  await loadShelf({ preferredNovelId: novelId || null, autoSelectFirst: shouldAutoSelectFirst });
  if (novelId) {
    const loaded = await selectNovel(novelId, { desiredChapterNo: chapterNo || null, suppressNotFoundFlash: true });
    if (!loaded && state.novels.length) {
      url.searchParams.delete("novelId");
      url.searchParams.delete("chapterNo");
      window.history.replaceState({}, "", url.toString());
      await selectNovel(state.novels[0].id, { suppressNotFoundFlash: true });
      showFlash(`小说 #${novelId} 不存在，已为你切换到书架中的最新小说。`, "info");
    }
  }
  syncRenameControls();
  renderCreateTaskPanel();
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
  await loadShelf({ preferredNovelId: novelId, autoSelectFirst: false });
  const loaded = await selectNovel(novelId, { desiredChapterNo: chapterNo || null, updateReaderUrl: true, suppressNotFoundFlash: true });
  if (loaded) return;
  const fallback = state.novels[0];
  if (!fallback) {
    refs.readerPageTitle.textContent = "小说不存在";
    refs.readerPageContent.textContent = `编号为 ${novelId} 的小说不存在或已被删除。`;
    return;
  }
  await selectNovel(fallback.id, { suppressNotFoundFlash: true, updateReaderUrl: true });
  showFlash(`小说 #${novelId} 不存在，已切换到《${fallback.title}》。`, "info");
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
