import {
  state,
  refs,
  fmtDate,
  cloneTemplateFirstElement,
} from "/app/assets/app/core.js?v=20260316c";

export function buildChapterCardNode(chapter, lastChapterNo, { onSelectChapter, onOpenReader, onDeleteTailFrom }) {
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
  node.querySelector(".chapter-preview-btn").addEventListener("click", () => onSelectChapter(chapter.chapter_no));
  node.querySelector(".chapter-open-btn").addEventListener("click", () => onOpenReader(chapter.chapter_no));

  const deleteBtn = node.querySelector(".chapter-delete-tail-btn");
  const deleteCount = lastChapterNo - chapter.chapter_no + 1;
  deleteBtn.textContent = `从这里删到末尾（${deleteCount} 章）`;
  deleteBtn.classList.toggle("hidden", !state.managementMode);
  deleteBtn.addEventListener("click", () => onDeleteTailFrom(chapter.chapter_no));
  return node;
}

export function updateCreatePanel(open) {
  refs.createPanel?.classList.toggle("hidden", !open);
}

export function showConfirm({ eyebrow = "请确认", title, message, confirmText = "确认", danger = false }) {
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

export function closeConfirm(result) {
  refs.confirmModal.classList.add("hidden");
  const resolver = state.confirmResolver;
  state.confirmResolver = null;
  if (resolver) resolver(result);
}

export function collectStylePreferences(form) {
  const formData = new FormData(form);
  const read = (...names) => {
    for (const name of names) {
      const value = formData.get(name);
      if (value == null) continue;
      const text = value.toString().trim();
      if (text) return text;
    }
    return "";
  };

  const style = {
    tone: read("tone"),
    pacing: read("pace", "pacing"),
    pov: read("pov"),
    combat_style: read("combat_style"),
    extra: read("style_notes", "extraStyle"),
    golden_finger: read("goldenFinger"),
    atmosphere: read("atmosphere"),
    target_length: read("targetLength"),
  };

  const advancedJson = read("style_json");
  if (!advancedJson) return Object.fromEntries(Object.entries(style).filter(([, value]) => value));

  try {
    const parsed = JSON.parse(advancedJson);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return { ...Object.fromEntries(Object.entries(style).filter(([, value]) => value)), ...parsed };
    }
    throw new Error('高级风格 JSON 必须是对象，例如 {"target_audience": "男频"}');
  } catch (error) {
    throw new Error(error?.message || "高级风格 JSON 格式错误");
  }
}

export function formatQualityFeedback(payload) {
  const feedback = payload?.quality_feedback || payload?.details?.quality_feedback;
  if (!feedback || typeof feedback !== "object") return "";
  const parts = [];
  if (feedback.reasons?.length) parts.push(`原因：${feedback.reasons.join("；")}`);
  if (feedback.suggestions?.length) parts.push(`建议：${feedback.suggestions.join("；")}`);
  return parts.join("\n");
}

export function parseSseBlock(block) {
  const lines = String(block || "").split("\n");
  let event = "message";
  const dataLines = [];
  lines.forEach((line) => {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  });
  const dataText = dataLines.join("\n");
  return { event, data: dataText ? JSON.parse(dataText) : null };
}
