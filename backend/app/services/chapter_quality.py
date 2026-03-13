from __future__ import annotations

import re
from collections import Counter
from typing import Any, Iterable

from app.services.generation_exceptions import ErrorCodes, GenerationError


FORBIDDEN_REGEX_RULES: list[tuple[str, str]] = [
    (r"上一章《", "正文混入了上一章回顾模板"),
    (r"他今晚冒险来到这里，只为一件事", "正文出现了明显的固定任务模板句"),
    (r"可就在他以为.*新的异样还是冒了出来", "正文出现了明显的固定结尾模板句"),
    (r"在凡人流修仙这样的处境里", "正文混入了题材说明式模板句"),
    (r"请只输出 JSON|schema|提示词|读者可以看到|本章任务", "正文混入了元叙事或提示词残留"),
]

SENTENCE_SPLIT_RE = re.compile(r"[。！？!?；;\n]+")
WHITESPACE_RE = re.compile(r"\s+")
VISIBLE_CHAR_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]")
TERMINAL_PUNCTUATION = "。！？!?…』」》）)】"
TRUNCATION_TRAILING_WORDS = (
    "像一",
    "像是",
    "仿佛",
    "似乎",
    "岩石下方",
    "门外有",
    "他正要",
    "却忽然",
    "就在这",
    "随后便",
)
ACTION_MARKERS = ("抬", "按", "抓", "推", "看", "听", "摸", "藏", "退", "走", "停", "问", "答", "递", "翻", "敲")
DISCOVERY_MARKERS = ("发现", "看见", "听见", "察觉", "摸到", "意识到", "露出", "显出", "有异样", "不对")
HOOK_MARKERS = ("忽然", "却", "但", "未必", "还没", "还在", "将要", "像是", "不对", "异样")
DECISION_MARKERS = ("决定", "盘算", "索性", "干脆", "打定主意", "心里有了数", "改了主意", "临时改口")
PROACTIVE_CHAIN_PATTERNS = (
    r"先[^。！？!?]{0,24}(?:再|然后|接着)",
    r"(?:借着|故意|索性|干脆|顺手|径直|立刻|当即)[^。！？!?]{0,24}(?:问|试|探|换|压|摆|藏|扣|敲|拦|退|逼|翻|封|拿)",
    r"(?:没有立刻|并未立刻)[^。！？!?]{0,16}(?:而是|反而)[^。！？!?]{0,24}(?:问|试|探|换|压|摆|藏|扣|敲|拦|退|逼|翻|封|拿)",
)
PASSIVE_DRIFT_PATTERNS = (
    r"站在[^。！？!?]{0,18}(?:没有动|没动)",
    r"(?:没有立刻|并未立刻)[^。！？!?]{0,18}(?:做什么|开口|行动)",
    r"(?:只是|只是在)[^。！？!?]{0,24}(?:看着|听着|想着|等着|站着)",
    r"压下(?:这个|那点)?念头",
)
TRANSITION_ENDING_STYLES = {"平稳过渡", "余味收束", "normal_transition", "transition", "quiet_close"}
STYLE_OVERUSE_RULES: list[tuple[str, int]] = [
    (r"不是错觉", 2),
    (r"心跳(?:快了几分|快了一拍|漏了一拍|微微一紧)", 2),
    (r"看了片刻", 2),
    (r"若有若无", 2),
    (r"微弱的暖意", 2),
    (r"温凉(?:的触感)?", 3),
    (r"微弱", 4),
    (r"几息", 3),
    (r"没有再说什么", 2),
    (r"盯着[^。！？!?]{0,12}看了片刻", 2),
    (r"他心中一凛", 2),
    (r"事情没有那么简单", 2),
]
WEAK_ENDING_PATTERNS = [
    r"回去休息了[。！？!?]?$",
    r"暂时压下念头[。！？!?]?$",
    r"打算明日再看[。！？!?]?$",
    r"夜色沉沉.*暂告一段落[。！？!?]?$",
]
PROACTIVE_MARKERS = (
    "主动",
    "故意",
    "索性",
    "先去",
    "先把",
    "试探",
    "设局",
    "引开",
    "误导",
    "换取",
    "买下",
    "借着",
    "顺势",
    "绕开",
    "抢先",
    "布置",
    "伪装",
    "压价",
)

AGENCY_MODE_MARKERS: dict[str, tuple[str, ...]] = {
    "aggressive_probe": ("试探", "逼", "抢先", "追问", "压前", "拦住", "探口风"),
    "strategic_setup": ("故意", "装作", "借着", "顺势", "留半句", "误导", "设局", "不动声色"),
    "transactional_push": ("条件", "交换", "代价", "筹码", "压价", "还价", "让步", "表态"),
    "curiosity_driven": ("验证", "比对", "试了试", "拆开", "确认", "印证", "复盘", "换个法子"),
    "emotional_initiative": ("先开口", "表态", "摊开", "道歉", "拒绝", "答应", "划清", "不再"),
    "reverse_pressure_choice": ("明知", "仍", "索性", "干脆", "押上", "退路", "硬着头皮", "扛下"),
}

AGENCY_MODE_PASSIVE_LIMIT: dict[str, int] = {
    "strategic_setup": 3,
    "curiosity_driven": 3,
}
PROGRESS_RESULT_MARKERS: dict[str, tuple[str, ...]] = {
    "信息推进": ("知道", "确认", "发现", "线索", "真相", "情报", "看清", "摸清", "认出", "对上", "意识到", "摸到", "听出"),
    "关系推进": ("合作", "同意", "试探", "拉近", "翻脸", "结交", "师兄", "盟", "松口", "表态", "答应"),
    "资源推进": ("灵石", "丹", "药", "材料", "功法", "法器", "资源", "拿到", "换到", "押给", "赎回"),
    "实力推进": ("突破", "修为", "境界", "掌握", "术法", "成功运转", "摸到门槛", "稳住气息"),
    "风险升级": ("盯上", "暴露", "追查", "危机", "杀机", "围堵", "记住了", "起疑", "退路", "价码", "代价"),
    "地点推进": ("进城", "进山", "离开", "转到", "到了", "换到", "走入", "折回", "改道"),
}
GENERIC_PROGRESS_RESULT_MARKERS: tuple[str, ...] = (
    "于是", "结果", "最终", "这才", "果然", "终于", "立刻", "当场", "只得", "不得不", "只能",
    "知道", "确认", "拿到", "换到", "看清", "摸清", "认出", "记下", "露出", "松口", "答应",
    "退路", "代价", "价码", "限制", "麻烦", "后患", "风险", "条件", "筹码",
)
PROGRESS_RESULT_PATTERNS: tuple[str, ...] = (
    r"(?:于是|结果|最终|这才|果然|终于)[^。！？!?]{0,28}(?:知道|确认|看清|摸清|认出|拿到|换到|露出|松口|答应|起疑|盯上|被迫|不得不)",
    r"(?:让|令|使得|逼得)[^。！？!?]{0,24}(?:对方|那人|他|她|众人|掌柜|帮众|守卫|同门)?[^。！？!?]{0,12}(?:露出|改口|松口|退后|起疑|记住|答应|翻脸|暴露)",
    r"(?:再也不能|不得不|只得|只能)[^。！？!?]{0,28}",
    r"(?:退路|价码|代价|风险|麻烦|后患)[^。！？!?]{0,16}(?:更|只剩|没了|断了|抬高|压紧|逼近|变重)",
    r"(?:原本|本来)[^。！？!?]{0,18}(?:如今|现在|却|反而)[^。！？!?]{0,24}",
)
PROGRESS_KIND_PATTERNS: dict[str, tuple[str, ...]] = {
    "信息推进": (
        r"(?:知道|确认|看清|摸清|认出|意识到|听出|问出|试出|摸到)[^。！？!?]{0,28}",
        r"(?:线索|情报|口风|破绽|来路|去向)[^。！？!?]{0,18}(?:露出|坐实|对上|拼上|接上)",
    ),
    "关系推进": (
        r"(?:松口|答应|表态|默认|翻脸|缓和|站到)[^。！？!?]{0,24}",
        r"(?:关系|立场|态度|称呼)[^。！？!?]{0,18}(?:变了|软了|更近|更远|坐实)",
    ),
    "资源推进": (
        r"(?:拿到|换到|押给|赎回|借到|凑出|保住)[^。！？!?]{0,24}",
        r"(?:灵石|丹药|材料|功法|法器|路引|令牌)[^。！？!?]{0,18}(?:到手|归手|换来|落袋)",
    ),
    "实力推进": (
        r"(?:突破|掌握|稳住|运转成|摸到门槛|练成|催动出)[^。！？!?]{0,24}",
        r"(?:修为|气息|法门|术法|窍穴)[^。！？!?]{0,18}(?:稳住|松开|贯通|更进一步)",
    ),
    "风险升级": (
        r"(?:被|让|令)[^。！？!?]{0,18}(?:盯上|记住|记下|起疑|追查)",
        r"(?:退路|后路|价码|代价|麻烦|后患)[^。！？!?]{0,18}(?:只剩|没了|断了|更高|更重|更紧)",
        r"(?:暴露|露底|露出破绽|顺藤摸瓜|查到|摸到)[^。！？!?]{0,24}",
    ),
    "地点推进": (
        r"(?:进城|进山|离开|改道|折回|转到|潜入|混入)[^。！？!?]{0,24}",
        r"(?:到了|踏入|转进|摸到)[^。！？!?]{0,18}(?:新地方|内院|后巷|山道|坊市|门内)",
    ),
}
PROGRESS_KIND_RESULT_GUIDANCE: dict[str, str] = {
    "信息推进": "至少落下一条能复述的新信息：谁说漏嘴了、哪条线索被坐实、哪个判断被主角亲手验证。",
    "关系推进": "至少落下一项关系变化：有人松口、表态、翻脸、默认站队，或双方的条件被改写。",
    "资源推进": "至少落下一项资源结果：拿到、换到、保住、赎回了什么，或为此付出了什么新代价。",
    "实力推进": "至少落下一项能力结果：突破、掌握、试出上限、稳住伤势，不能只写感觉更强。",
    "风险升级": "至少落下一项可复述的新压力：谁开始盯上主角、哪条退路被堵住、什么代价被抬高，或主角被迫接受什么新限制。",
    "地点推进": "至少落下明确位移或场域变化：进入了哪里、离开了哪里、换到了什么更危险或更关键的位置。",
}


def visible_length(text: str) -> int:
    return len(VISIBLE_CHAR_RE.findall(text or ""))


def _normalize_line(text: str) -> str:
    text = WHITESPACE_RE.sub("", text)
    return re.sub(r"[，。、“”‘’：:；;！？!?（）()《》<>\-—…·,.]", "", text)


def _non_empty_paragraphs(text: str) -> list[str]:
    return [item.strip() for item in text.split("\n") if item.strip()]


def _duplicate_paragraphs(text: str) -> list[str]:
    paragraphs = _non_empty_paragraphs(text)
    normalized = [_normalize_line(item) for item in paragraphs if _normalize_line(item)]
    counts = Counter(normalized)
    return [item for item, count in counts.items() if count >= 2 and len(item) >= 18]


def _sentence_repeat_ratio(text: str) -> float:
    sentences = [_normalize_line(x) for x in SENTENCE_SPLIT_RE.split(text) if _normalize_line(x)]
    if not sentences:
        return 0.0
    counts = Counter(sentences)
    repeated = sum(count for sentence, count in counts.items() if count >= 2 and len(sentence) >= 12)
    return repeated / max(len(sentences), 1)


def _ending_issue(text: str) -> str | None:
    stripped = (text or "").rstrip()
    if not stripped:
        return "empty"
    if stripped[-1] not in TERMINAL_PUNCTUATION:
        return "missing_terminal_punctuation"
    tail = stripped[-40:]
    if any(tail.endswith(token) for token in TRUNCATION_TRAILING_WORDS):
        return "truncated_phrase"
    if tail.count("“") > tail.count("”") or tail.count("『") > tail.count("』") or tail.count("《") > tail.count("》"):
        return "unclosed_quote"
    if re.search(r"(像一|像是|仿佛|似乎|随后|然后|就在|门外|崖边).{0,6}$", tail):
        return "hanging_clause"
    return None


def repair_incomplete_ending(text: str, ending_issue: str | None = None) -> str | None:
    stripped = (text or "").rstrip()
    if not stripped:
        return None

    issue = ending_issue or _ending_issue(stripped)
    if not issue:
        return stripped

    def _last_terminal_index(value: str) -> int:
        return max((value.rfind(ch) for ch in TERMINAL_PUNCTUATION), default=-1)

    def _trim_to_last_complete_sentence(value: str, *, max_fragment_chars: int = 80) -> str | None:
        last_terminal = _last_terminal_index(value)
        if last_terminal < 0:
            return None
        trailing = value[last_terminal + 1 :].strip()
        if not trailing:
            return value[: last_terminal + 1].rstrip()
        if len(trailing) <= max_fragment_chars:
            return value[: last_terminal + 1].rstrip()
        return None

    if issue == "unclosed_quote":
        repaired = stripped
        quote_pairs = (("“", "”"), ("『", "』"), ("《", "》"), ("（", "）"), ("(", ")"), ("【", "】"), ("[", "]"))
        for left, right in quote_pairs:
            diff = repaired.count(left) - repaired.count(right)
            if diff > 0:
                repaired += right * diff
        if repaired and repaired[-1] not in TERMINAL_PUNCTUATION:
            repaired += "。"
        return repaired if repaired != stripped else None

    trimmed = _trim_to_last_complete_sentence(stripped, max_fragment_chars=96 if issue == "missing_terminal_punctuation" else 140)
    if trimmed and trimmed != stripped:
        return trimmed

    if stripped[-1] in "，,、：:；;—-":
        return stripped[:-1].rstrip() + "。"

    if issue == "missing_terminal_punctuation":
        return stripped + "。"

    if issue in {"truncated_phrase", "hanging_clause"}:
        trimmed = _trim_to_last_complete_sentence(stripped, max_fragment_chars=240)
        if trimmed:
            return trimmed
        return stripped + "。"

    return None


def _style_overuse(text: str) -> dict[str, int]:
    hits: dict[str, int] = {}
    for pattern, threshold in STYLE_OVERUSE_RULES:
        count = len(re.findall(pattern, text))
        if count >= threshold:
            hits[pattern] = count
    return hits


def _progress_signals(text: str) -> dict[str, int]:
    paragraphs = _non_empty_paragraphs(text)
    dialogue_count = text.count("“") + text.count('"')
    action_hits = sum(text.count(marker) for marker in ACTION_MARKERS)
    discovery_hits = sum(text.count(marker) for marker in DISCOVERY_MARKERS)
    hook_hits = sum(text.count(marker) for marker in HOOK_MARKERS)
    return {
        "paragraphs": len(paragraphs),
        "dialogue_count": dialogue_count,
        "action_hits": action_hits,
        "discovery_hits": discovery_hits,
        "hook_hits": hook_hits,
    }


def _proactive_signal_count(text: str) -> int:
    marker_hits = sum(text.count(marker) for marker in PROACTIVE_MARKERS)
    decision_hits = sum(text.count(marker) for marker in DECISION_MARKERS)
    chain_hits = sum(len(re.findall(pattern, text)) for pattern in PROACTIVE_CHAIN_PATTERNS)
    return marker_hits + decision_hits + chain_hits


def _passive_drift_count(text: str) -> int:
    return sum(len(re.findall(pattern, text)) for pattern in PASSIVE_DRIFT_PATTERNS)


def _agency_mode_fit_hits(text: str, agency_mode: str | None) -> int:
    if not agency_mode:
        return 0
    markers = AGENCY_MODE_MARKERS.get(str(agency_mode).strip(), ())
    return sum(text.count(marker) for marker in markers)


def _agency_passive_limit(agency_mode: str | None) -> int:
    if not agency_mode:
        return 2
    return int(AGENCY_MODE_PASSIVE_LIMIT.get(str(agency_mode).strip(), 2))


def _weak_ending(text: str) -> str | None:
    last_para = (_non_empty_paragraphs(text) or [""])[-1]
    for pattern in WEAK_ENDING_PATTERNS:
        if re.search(pattern, last_para):
            return pattern
    return None


def _plan_progress_cues(chapter_plan: dict[str, Any] | None, progress_kind: str | None) -> tuple[str, ...]:
    if not isinstance(chapter_plan, dict):
        return ()
    source = " ".join(
        str(chapter_plan.get(key) or "")
        for key in ("payoff_or_pressure", "ending_hook", "goal", "conflict", "discovery", "closing_image")
    )
    source = source.strip()
    if not source:
        return ()
    cues: list[str] = []
    token_pool = list(GENERIC_PROGRESS_RESULT_MARKERS)
    if progress_kind and progress_kind in PROGRESS_RESULT_MARKERS:
        token_pool.extend(PROGRESS_RESULT_MARKERS[progress_kind])
    for token in token_pool:
        token = str(token or "").strip()
        if len(token) < 2:
            continue
        if token in source and token not in cues:
            cues.append(token)
    for token in re.findall(r"[一-鿿]{2,6}", source):
        if token in cues:
            continue
        if any(marker in token for marker in ("线索", "破绽", "盯", "疑", "退路", "代价", "条件", "限制", "松口", "答应", "拿到", "换到", "确认", "暴露", "改道", "进城", "进山", "突破")):
            cues.append(token)
    return tuple(cues[:8])


def _progress_result_metrics(text: str, progress_kind: str | None, chapter_plan: dict[str, Any] | None = None) -> dict[str, Any]:
    if progress_kind:
        kind_tokens = PROGRESS_RESULT_MARKERS.get(progress_kind or "", ())
        kind_patterns = PROGRESS_KIND_PATTERNS.get(progress_kind, ())
    else:
        token_pool: list[str] = []
        for tokens in PROGRESS_RESULT_MARKERS.values():
            for token in tokens:
                if token not in token_pool:
                    token_pool.append(token)
        kind_tokens = tuple(token_pool)
        pattern_pool: list[str] = []
        for patterns in PROGRESS_KIND_PATTERNS.values():
            for pattern in patterns:
                if pattern not in pattern_pool:
                    pattern_pool.append(pattern)
        kind_patterns = tuple(pattern_pool)
    plan_cues = _plan_progress_cues(chapter_plan, progress_kind)
    generic_hits = sum(text.count(token) for token in GENERIC_PROGRESS_RESULT_MARKERS)
    direct_hits = sum(text.count(token) for token in kind_tokens)
    pattern_hits = sum(len(re.findall(pattern, text)) for pattern in PROGRESS_RESULT_PATTERNS)
    pattern_hits += sum(len(re.findall(pattern, text)) for pattern in kind_patterns)
    cue_hits = sum(text.count(token) for token in plan_cues)

    sentences = [item.strip() for item in SENTENCE_SPLIT_RE.split(text or "") if item.strip()]
    result_sentence_hits = 0
    evidence: list[str] = []
    for sentence in sentences:
        score = 0
        if any(token and token in sentence for token in kind_tokens):
            score += 1
        if any(token and token in sentence for token in plan_cues):
            score += 1
        if any(token and token in sentence for token in GENERIC_PROGRESS_RESULT_MARKERS):
            score += 1
        if any(re.search(pattern, sentence) for pattern in PROGRESS_RESULT_PATTERNS):
            score += 1
        if any(re.search(pattern, sentence) for pattern in kind_patterns):
            score += 1
        if score >= 2:
            result_sentence_hits += 1
            if len(evidence) < 3:
                evidence.append(sentence[:70])

    last_para = (_non_empty_paragraphs(text) or [""])[-1]
    ending_hits = 0
    if last_para:
        if any(token and token in last_para for token in kind_tokens):
            ending_hits += 1
        if any(token and token in last_para for token in plan_cues):
            ending_hits += 1
        if any(re.search(pattern, last_para) for pattern in PROGRESS_RESULT_PATTERNS):
            ending_hits += 1
        if any(re.search(pattern, last_para) for pattern in kind_patterns):
            ending_hits += 1

    progress_score = direct_hits + pattern_hits + result_sentence_hits + min(cue_hits, 2) + min(ending_hits, 2)
    bucket_hits = sum(1 for value in (direct_hits, pattern_hits, result_sentence_hits, cue_hits, ending_hits) if int(value) > 0)
    return {
        "progress_hits": bucket_hits,
        "progress_score": progress_score,
        "progress_direct_hits": direct_hits,
        "progress_pattern_hits": pattern_hits,
        "progress_sentence_hits": result_sentence_hits,
        "progress_plan_cue_hits": cue_hits,
        "progress_ending_hits": ending_hits,
        "progress_generic_hits": generic_hits,
        "progress_plan_cues": list(plan_cues),
        "progress_evidence": evidence,
    }


def _progress_result_is_clear(text: str, progress_kind: str | None, chapter_plan: dict[str, Any] | None = None) -> tuple[bool, dict[str, Any]]:
    metrics = _progress_result_metrics(text, progress_kind, chapter_plan=chapter_plan)
    score = int(metrics.get("progress_score") or 0)
    buckets = int(metrics.get("progress_hits") or 0)
    generic_hits = int(metrics.get("progress_generic_hits") or 0)
    clear = score >= 2 or (buckets >= 1 and generic_hits >= 2)
    return clear, metrics


def _plan_event_repeated(chapter_plan: dict[str, Any] | None, recent_plan_meta: Iterable[dict[str, Any]] | None) -> str | None:
    current = str((chapter_plan or {}).get("event_type") or "").strip()
    if not current:
        return None
    recent = [str((item or {}).get("event_type") or "").strip() for item in (recent_plan_meta or [])]
    recent = [item for item in recent if item]
    if len(recent) >= 2 and recent[-1] == current and recent[-2] == current:
        return current
    return None


def build_quality_feedback(exc: GenerationError) -> dict[str, Any]:
    details = exc.details or {}
    feedback: dict[str, Any] = {
        "code": exc.code,
        "message": exc.message,
        "stage": exc.stage,
        "category": "quality",
        "failed_checks": [],
        "metrics": {},
        "suggestions": [],
    }

    def add_check(label: str) -> None:
        if label not in feedback["failed_checks"]:
            feedback["failed_checks"].append(label)

    def add_suggestion(text: str) -> None:
        if text and text not in feedback["suggestions"]:
            feedback["suggestions"].append(text)

    metrics_keys = (
        "visible_chars", "hard_min_visible_chars", "target_min_visible_chars", "target_visible_chars_max",
        "paragraphs", "action_hits", "discovery_hits", "hook_hits", "progress_hits", "progress_score",
        "progress_direct_hits", "progress_pattern_hits", "progress_sentence_hits", "progress_plan_cue_hits",
        "progress_ending_hits", "progress_generic_hits", "progress_plan_cues", "progress_evidence",
        "proactive_hits", "agency_fit_hits", "agency_strength", "passive_drift_hits", "passive_limit",
        "similarity", "ending_issue", "event_type", "progress_kind", "agency_mode", "agency_mode_label",
    )
    for key in metrics_keys:
        if key in details and details.get(key) is not None:
            feedback["metrics"][key] = details.get(key)

    if exc.code == ErrorCodes.CHAPTER_TOO_SHORT:
        add_check("篇幅不足")
        add_suggestion("补足完整场景，至少写清开场动作、中段受阻、一次发现和结尾收束。")
        add_suggestion("少做总结，多写动作、对话、试探和因果。")
    elif exc.code == ErrorCodes.CHAPTER_ENDING_INCOMPLETE:
        add_check("结尾不完整")
        add_suggestion("把最后一段补到自然收束，避免半句截断、引号未闭合或悬空短语。")
    elif exc.code == ErrorCodes.CHAPTER_DUPLICATED_PARAGRAPHS:
        add_check("段落重复")
        add_suggestion("重写重复段落，换动作链与句式，不要机械回环。")
    elif exc.code == ErrorCodes.CHAPTER_TOO_MESSY:
        if details.get("style_hits"):
            add_check("套话/固定句式过密")
            add_suggestion("减少安全词和高频口头禅，换成更具体的动作、触感和判断。")
        else:
            add_check("文本噪音过多")
            add_suggestion("清掉 JSON、元提示、重复句或结构化残留，只保留正文。")
    elif exc.code == ErrorCodes.CHAPTER_TOO_SIMILAR:
        add_check("与近章过于相似")
        add_suggestion("更换开场动作、核心矛盾或收尾方式，避免重复最近章节的桥段和句式。")
    elif exc.code == ErrorCodes.CHAPTER_PROGRESS_TOO_WEAK:
        if details.get("proactive_move") is not None or details.get("agency_mode") is not None:
            add_check("主角主动性不足")
            add_suggestion("前两段先让主角做可见动作、试探、验证、改条件或留后手，不要先站着看。")
            add_suggestion("中段受阻后再追一步，让主角改变局势、信息分布或关系条件。")
        if details.get("paragraphs") is not None or details.get("action_hits") is not None:
            add_check("事件推进不足")
            add_suggestion("补出一段明确动作链和一次具体发现，别让正文停在气氛铺垫。")
        if details.get("event_type"):
            add_check("主事件类型重复")
            add_suggestion("本章换挡，不要连续第三章都写同一种事件类型。")
        if details.get("ending_pattern"):
            add_check("结尾钩子偏弱")
            add_suggestion("结尾要落在结果变化、新压力或人物选择，不要平平收掉。")
    else:
        add_check("质检未通过")

    feedback["display_message"] = "；".join(feedback["failed_checks"]) if feedback["failed_checks"] else exc.message
    return feedback


def validate_chapter_content(
    *,
    title: str,
    content: str,
    min_visible_chars: int,
    hard_min_visible_chars: int | None = None,
    recent_chapter_texts: Iterable[str] | None = None,
    similarity_checker=None,
    max_similarity: float = 0.76,
    target_visible_chars_max: int | None = None,
    hook_style: str | None = None,
    chapter_plan: dict[str, Any] | None = None,
    recent_plan_meta: Iterable[dict[str, Any]] | None = None,
) -> None:
    text = (content or "").strip()
    visible_chars = visible_length(text)
    hard_min = int(hard_min_visible_chars or min_visible_chars)
    if visible_chars < hard_min:
        raise GenerationError(
            code=ErrorCodes.CHAPTER_TOO_SHORT,
            message=f"模型返回的章节过短，未达到最低正文长度要求（至少 {hard_min} 个可见字符）。",
            stage="chapter_quality",
            retryable=True,
            http_status=422,
            details={
                "title": title,
                "visible_chars": visible_chars,
                "hard_min_visible_chars": hard_min,
                "target_min_visible_chars": min_visible_chars,
                "severity": "hard",
            },
        )
    if visible_chars < min_visible_chars:
        raise GenerationError(
            code=ErrorCodes.CHAPTER_TOO_SHORT,
            message=f"模型返回的章节偏短，尚未达到目标正文长度（至少 {min_visible_chars} 个可见字符）。",
            stage="chapter_quality",
            retryable=True,
            http_status=422,
            details={
                "title": title,
                "visible_chars": visible_chars,
                "hard_min_visible_chars": hard_min,
                "target_min_visible_chars": min_visible_chars,
                "target_visible_chars_max": target_visible_chars_max,
                "severity": "soft",
            },
        )

    if text.count("{") >= 2 and text.count("}") >= 2:
        raise GenerationError(
            code=ErrorCodes.CHAPTER_TOO_MESSY,
            message="模型返回内容仍像 JSON 或混有结构化残留，未形成可直接入库的正文。",
            stage="chapter_quality",
            retryable=True,
            http_status=422,
            details={"title": title},
        )

    ending_issue = _ending_issue(text)
    if ending_issue:
        raise GenerationError(
            code=ErrorCodes.CHAPTER_ENDING_INCOMPLETE,
            message="模型返回的正文疑似被截断，结尾没有自然收束，不适合直接入库。",
            stage="chapter_quality",
            retryable=True,
            http_status=422,
            details={"title": title, "tail": text[-60:], "ending_issue": ending_issue},
        )

    for pattern, msg in FORBIDDEN_REGEX_RULES:
        if re.search(pattern, text, flags=re.S):
            raise GenerationError(
                code=ErrorCodes.CHAPTER_META_TEXT,
                message=msg,
                stage="chapter_quality",
                retryable=True,
                http_status=422,
                details={"title": title, "pattern": pattern},
            )

    duplicated_paragraphs = _duplicate_paragraphs(text)
    if duplicated_paragraphs:
        raise GenerationError(
            code=ErrorCodes.CHAPTER_DUPLICATED_PARAGRAPHS,
            message="正文存在重复段落，说明本次生成质量不稳定。",
            stage="chapter_quality",
            retryable=True,
            http_status=422,
            details={"title": title, "duplicates": duplicated_paragraphs[:3]},
        )

    style_hits = _style_overuse(text)
    if style_hits:
        raise GenerationError(
            code=ErrorCodes.CHAPTER_TOO_MESSY,
            message="正文里高频口头禅或固定句式重复过多，AI 痕迹仍然偏重。",
            stage="chapter_quality",
            retryable=True,
            http_status=422,
            details={"title": title, "style_hits": style_hits},
        )

    if _sentence_repeat_ratio(text) > 0.22:
        raise GenerationError(
            code=ErrorCodes.CHAPTER_TOO_MESSY,
            message="正文内部重复句过多，整体读感接近模板拼接，不适合直接入库。",
            stage="chapter_quality",
            retryable=True,
            http_status=422,
            details={"title": title},
        )

    repeated_event_type = _plan_event_repeated(chapter_plan, recent_plan_meta)
    if repeated_event_type:
        raise GenerationError(
            code=ErrorCodes.CHAPTER_PROGRESS_TOO_WEAK,
            message="本章仍在重复最近两章的主事件类型，结构换挡不足。",
            stage="chapter_quality",
            retryable=True,
            http_status=422,
            details={"title": title, "event_type": repeated_event_type},
        )

    progress = _progress_signals(text)
    progress_kind = str((chapter_plan or {}).get("progress_kind") or "").strip() or None
    progress_metrics = {}
    transition_ending = str(hook_style or "").strip() in TRANSITION_ENDING_STYLES
    weak_progress = (
        progress["paragraphs"] < 4
        or progress["action_hits"] < 4
        or (progress["discovery_hits"] < 1 and progress["hook_hits"] < 1)
    )
    weak_ending = (not transition_ending) and progress["hook_hits"] < 1
    if weak_progress or weak_ending:
        raise GenerationError(
            code=ErrorCodes.CHAPTER_PROGRESS_TOO_WEAK,
            message="本章虽然成文，但事件推进不足，像片段或铺垫残段，不适合直接入库。",
            stage="chapter_quality",
            retryable=True,
            http_status=422,
            details={"title": title, **progress, "visible_chars": visible_chars, "progress_kind": progress_kind, **progress_metrics},
        )

    # 不再单独做“主角主动性”质检。
    # 主角本章要做什么，已经在 chapter_plan / prompt 中被规划和约束；
    # 这里的质量关只负责长度、收束、重复、事件推进和相似度，不再把“主动性”单独拦截。

    weak_ending_pattern = _weak_ending(text)
    if weak_ending_pattern:
        raise GenerationError(
            code=ErrorCodes.CHAPTER_PROGRESS_TOO_WEAK,
            message="本章结尾钩子偏弱，像平铺过渡收尾，追更拉力不足。",
            stage="chapter_quality",
            retryable=True,
            http_status=422,
            details={"title": title, "ending_pattern": weak_ending_pattern},
        )

    if similarity_checker and recent_chapter_texts:
        best_similarity = 0.0
        for previous in recent_chapter_texts:
            if not previous:
                continue
            best_similarity = max(best_similarity, float(similarity_checker(text, previous)))
        if best_similarity >= max_similarity:
            raise GenerationError(
                code=ErrorCodes.CHAPTER_TOO_SIMILAR,
                message="本章与最近章节过于相似，疑似重复套模板生成。",
                stage="chapter_quality",
                retryable=True,
                http_status=422,
                details={"title": title, "similarity": round(best_similarity, 4)},
            )
