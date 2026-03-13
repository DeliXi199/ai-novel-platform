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
} from "/app/assets/app/core.js?v=20260313b";
import {
  updateCreatePanel,
  showConfirm,
  closeConfirm,
  collectStylePreferences,
  formatQualityFeedback,
  parseSseBlock,
} from "/app/assets/app/ui_helpers.js?v=20260313b";
import {
  setTopbar,
  renderBookshelf,
  renderMetrics,
  renderPlanning,
  renderInterventions,
  renderCatalog,
  renderPreview,
  renderReaderMode,
  syncReaderUrl,
} from "/app/assets/app/renderers.js?v=20260313b";

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
  const [novel, chapters, consoleData, planningData, interventions] = await Promise.all([
    apiFetch(`/novels/${novelId}`, { timeoutMs: 12000 }),
    apiFetch(`/novels/${novelId}/chapters`, { timeoutMs: 12000 }),
    apiFetch(`/novels/${novelId}/control-console`, { timeoutMs: 12000 }),
    apiFetch(`/novels/${novelId}/planning-state`, { timeoutMs: 12000 }),
    apiFetch(`/novels/${novelId}/interventions`, { timeoutMs: 12000 }),
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
  state.selectedChapter = targetChapterNo ? normalizeChapterPayload(await apiFetch(`/novels/${novelId}/chapters/${targetChapterNo}`, { timeoutMs: 12000 })) : null;
  state.lastBundleRefreshAt = Date.now();

  renderBookshelf({ onSelectNovel: selectNovel });
  setTopbar();
  renderMetrics();
  renderPlanning();
  renderInterventions();
  renderCatalog({ onSelectChapter: selectChapter, onOpenReader: openReader, onDeleteTailFrom: handleDeleteTailFrom });
  renderPreview();
  renderReaderMode({ onSelectChapter: selectChapter });

  const chapterNoField = refs.interventionForm?.elements?.namedItem("chapter_no");
  if (chapterNoField) chapterNoField.value = Math.max((state.selectedNovel?.current_chapter_no || 0) + 1, 1);
  if (updateReaderUrl) syncReaderUrl();
}

async function selectNovel(novelId, options = {}) {
  const { suppressNotFoundFlash = false, ...loadOptions } = options;
  pushActivity("切换小说", `载入小说 #${novelId}`);
  try {
    await loadNovelBundle(novelId, loadOptions);
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
      state.selectedChapterNo = null;
      state.selectedChapter = null;
      renderBookshelf({ onSelectNovel: selectNovel });
      renderMetrics();
      renderPlanning();
      renderInterventions();
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
  renderCatalog({ onSelectChapter: selectChapter, onOpenReader: openReader, onDeleteTailFrom: handleDeleteTailFrom });
  renderPreview();
  renderReaderMode({ onSelectChapter: selectChapter });
  try {
    state.selectedChapter = normalizeChapterPayload(await apiFetch(`/novels/${state.selectedNovelId}/chapters/${chapterNo}`));
    renderPreview();
    renderReaderMode({ onSelectChapter: selectChapter });
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
    const failedNovelId = error?.payload?.novel?.id || error?.payload?.novel_id;
    if (failedNovelId) {
      await loadShelf();
      await selectNovel(failedNovelId);
    }
    showFlash(`创建失败：${error.message}`, "error");
    pushActivity(
      "创建失败",
      failedNovelId ? `${error.message}（已保留失败现场，可直接重试初始化）` : error.message,
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
    const rejectionSummary = Array.isArray(chapter?.generation_meta?.quality_rejections) && chapter.generation_meta.quality_rejections.length
      ? `；本次共纠偏 ${chapter.generation_meta.quality_rejections.length} 次质检问题`
      : "";
    showFlash(`第 ${chapter.chapter_no} 章生成成功${rejectionSummary}`, "success");
    pushActivity("章节完成", `第 ${chapter.chapter_no} 章《${chapter.title}》${rejectionSummary}`, "success");
    if (Array.isArray(chapter?.generation_meta?.quality_rejections)) {
      chapter.generation_meta.quality_rejections.forEach((item, index) => {
        const checks = Array.isArray(item?.failed_checks) && item.failed_checks.length ? item.failed_checks.join("、") : item?.display_message || item?.message || "质检未通过";
        pushActivity(`质检回退 ${index + 1}`, checks, "info");
      });
    }
    await refreshSelectedNovel({ chapterNo: chapter.chapter_no });
  } catch (error) {
    const payload = error.payload;
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
    await loadShelf();
    if (!isReaderMode) {
      if (state.novels.length) {
        await selectNovel(state.novels[0].id);
      } else {
        setTopbar();
        renderMetrics();
        renderPlanning();
        renderInterventions();
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
  const url = new URL(window.location.href);
  const novelId = Number(url.searchParams.get("novelId") || 0);
  const chapterNo = Number(url.searchParams.get("chapterNo") || 0);
  await loadShelf({ preferredNovelId: novelId || null, autoSelectFirst: !novelId });
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
