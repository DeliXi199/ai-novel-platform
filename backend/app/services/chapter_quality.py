from __future__ import annotations

import re
from collections import Counter
from difflib import SequenceMatcher
from typing import Any, Iterable

from app.core.config import settings
from app.services.generation_exceptions import ErrorCodes, GenerationError
from app.services.llm_runtime import call_json_response, is_openai_enabled, provider_name
from app.services.prompt_support import compact_json
from app.services.prompt_templates import payoff_delivery_review_system_prompt, payoff_delivery_review_user_prompt


def _raise_ai_required_error(*, stage: str, message: str, detail_reason: str = "", retryable: bool = True) -> None:
    raise GenerationError(
        code=ErrorCodes.AI_REQUIRED_UNAVAILABLE,
        message=f"{message}{('：' + detail_reason) if detail_reason else ''}",
        stage=stage,
        retryable=retryable,
        http_status=503,
        provider=provider_name(),
        details={"reason": detail_reason} if detail_reason else None,
    )


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
SOFT_STYLE_CLUE_PATTERNS: tuple[str, ...] = (
    r"不是错觉",
    r"心跳(?:快了几分|快了一拍|漏了一拍|微微一紧)",
    r"看了片刻",
    r"若有若无",
    r"微弱的暖意",
    r"温凉(?:的触感)?",
    r"微弱",
    r"几息",
    r"没有再说什么",
    r"盯着[^。！？!?]{0,12}看了片刻",
    r"他心中一凛",
    r"事情没有那么简单",
)
MESSY_SENTENCE_REPEAT_RATIO = 0.24
MESSY_HARD_REPEAT_RATIO = 0.34
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

TIME_SKIP_STRONG_MARKERS: tuple[str, ...] = (
    "次日", "翌日", "第二天", "隔日", "天亮后", "清晨", "入夜后", "午后", "傍晚", "当夜", "一夜后",
    "半日后", "数日后", "三日后", "回到住处后", "回去后",
)
SCENE_TRANSITION_PATTERNS: tuple[str, ...] = (
    r"次日", r"翌日", r"第二天", r"隔日", r"天亮后", r"清晨", r"入夜后", r"午后", r"傍晚",
    r"片刻后", r"不多时", r"过了一阵", r"等到", r"随后", r"回到", r"回去", r"出了", r"离开",
    r"转到", r"赶到", r"折回", r"一路", r"来到", r"进了", r"出了门", r"走出", r"转身去了",
)
SCENE_HINT_STOPWORDS: set[str] = {
    "主角", "对方", "事情", "时候", "地方", "有人", "这个", "那个", "这里", "那里", "然后", "继续", "上一章",
    "本章", "场景", "动作", "结果", "问题", "局势", "后续", "东西", "东西还", "之后", "之前", "门外的人",
}

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
PAYOFF_DIRECT_MARKERS: tuple[str, ...] = (
    "拿到", "换到", "确认", "得手", "到手", "保住", "压回", "压住", "松口", "答应", "翻盘", "坐实", "落袋", "逼退", "稳住",
)
PAYOFF_REACTION_MARKERS: tuple[str, ...] = (
    "变脸", "改口", "迟疑", "愣", "沉默", "安静", "看了", "盯着", "不敢再", "起身", "后退", "收声", "松口", "皱眉", "眼神变了",
)
PAYOFF_PUBLIC_SUBJECTS: tuple[str, ...] = (
    "众人", "旁人", "掌柜", "对方", "围观", "伙计", "同门", "守卫", "人群", "那人", "顾青河", "师兄", "摊主",
)
PAYOFF_PRESSURE_MARKERS: tuple[str, ...] = (
    "盯上", "追查", "起疑", "记住", "后患", "代价", "退路", "麻烦", "风头", "暴露", "更紧", "更高", "留意", "盯梢",
)
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


def _style_clue_hits(text: str) -> dict[str, int]:
    hits: dict[str, int] = {}
    for pattern in SOFT_STYLE_CLUE_PATTERNS:
        count = len(re.findall(pattern, text))
        if count > 0:
            hits[pattern] = count
    return hits


def _sentence_units(text: str) -> list[str]:
    return [item.strip() for item in SENTENCE_SPLIT_RE.split(text or "") if item.strip()]


def _sentence_opening_metrics(text: str) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    for sentence in _sentence_units(text):
        normalized = _normalize_line(sentence)
        if len(normalized) < 12:
            continue
        opening = normalized[:8]
        if len(opening) < 6:
            continue
        counts[opening] += 1
    repeated = {key: value for key, value in counts.items() if value >= 3}
    return {
        "repeated_opening_groups": len(repeated),
        "repeated_opening_hits": sum(repeated.values()),
        "repeated_openings": dict(list(sorted(repeated.items(), key=lambda item: (-item[1], item[0]))[:4])),
    }


def _sentence_ending_metrics(text: str) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    for sentence in _sentence_units(text):
        normalized = _normalize_line(sentence)
        if len(normalized) < 12:
            continue
        ending = normalized[-8:]
        if len(ending) < 6:
            continue
        counts[ending] += 1
    repeated = {key: value for key, value in counts.items() if value >= 3}
    return {
        "repeated_ending_groups": len(repeated),
        "repeated_ending_hits": sum(repeated.values()),
        "repeated_endings": dict(list(sorted(repeated.items(), key=lambda item: (-item[1], item[0]))[:4])),
    }


def _messy_structure_metrics(text: str) -> dict[str, Any]:
    repeated_sentence_ratio = round(_sentence_repeat_ratio(text), 4)
    opening_metrics = _sentence_opening_metrics(text)
    ending_metrics = _sentence_ending_metrics(text)
    style_clues = _style_clue_hits(text)
    style_clue_total = sum(style_clues.values())
    style_clue_kinds = len(style_clues)
    messy_score = 0
    if repeated_sentence_ratio >= MESSY_SENTENCE_REPEAT_RATIO:
        messy_score += 2
    if int(opening_metrics.get("repeated_opening_groups") or 0) >= 1 and int(opening_metrics.get("repeated_opening_hits") or 0) >= 3:
        messy_score += 1
    if int(ending_metrics.get("repeated_ending_groups") or 0) >= 1 and int(ending_metrics.get("repeated_ending_hits") or 0) >= 3:
        messy_score += 1
    needs_ai_review = messy_score >= 2
    hard_fail = repeated_sentence_ratio >= MESSY_HARD_REPEAT_RATIO or (
        int(opening_metrics.get("repeated_opening_groups") or 0) >= 2
        and int(opening_metrics.get("repeated_opening_hits") or 0) >= 6
    )
    return {
        "repeated_sentence_ratio": repeated_sentence_ratio,
        **opening_metrics,
        **ending_metrics,
        "style_clue_hits": style_clues,
        "style_clue_total": style_clue_total,
        "style_clue_kinds": style_clue_kinds,
        "messy_score": messy_score,
        "needs_ai_review": needs_ai_review,
        "hard_fail": hard_fail,
    }


def _messy_review_excerpt(text: str, *, max_chars: int = 2200) -> str:
    stripped = (text or "").strip()
    if len(stripped) <= max_chars:
        return stripped
    head = stripped[: max_chars // 2]
    tail = stripped[-max_chars // 2 :]
    return f"{head}\n\n……（中间略）……\n\n{tail}"


def _messy_ai_review(title: str, text: str, metrics: dict[str, Any]) -> dict[str, Any] | None:
    from app.core.config import settings

    if not bool(getattr(settings, "chapter_messy_ai_review_enabled", True)):
        return None
    if not is_openai_enabled():
        _raise_ai_required_error(
            stage="chapter_style_review",
            message="章节结构复核需要可用的 AI，当前已停止生成",
            detail_reason="当前没有可用的 AI 配置或密钥。",
            retryable=False,
        )

    system_prompt = (
        "你是一名中文网文质检编辑，专门判断正文是否因为句式/结构重复而显得机械。"
        "注意：不要因为某个单词出现几次就误判；重点看写法和结构是否单调、重复、像模板回环。"
        "只输出 JSON。"
    )
    user_prompt = f"""
请判断下面这段正文是否真的存在“写法和结构层面的重复过密”。

判定标准：
1. 重点看句式、句子开合方式、段内动作链是否反复撞车。
2. 不能因为“微弱/温凉/若有若无”之类单个词重复就直接判失败。
3. 只有当读感明显机械、句型回环严重、同一种写法反复堆叠时，才给 verdict=messy。
4. 如果只是偶尔有安全词，但整体动作、信息和节奏仍自然，应给 verdict=ok。

请输出 JSON，格式：
{{
  "verdict": "messy" 或 "ok",
  "confidence": 0 到 1 的小数,
  "problem_types": ["句式重复", "开头写法单一", "结尾写法单一", "概括腔偏重", "安全表达过密"],
  "evidence": ["最多 3 条，简短说明问题出在哪里"],
  "repair_brief": "一句简洁可执行的修正建议",
  "must_change": ["最多 3 条必须改的点"],
  "avoid": ["最多 3 条这次别再来的写法"]
}}

【标题】
{title}

【本地结构信号】
{compact_json(metrics, max_depth=3, max_items=10, text_limit=100)}

【正文】
{_messy_review_excerpt(text)}
""".strip()
    try:
        data = call_json_response(
            stage="chapter_style_review",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_output_tokens=int(getattr(settings, "chapter_messy_ai_max_output_tokens", 700) or 700),
            timeout_seconds=int(getattr(settings, "chapter_messy_ai_timeout_seconds", 18) or 18),
        )
    except GenerationError:
        raise
    except Exception as exc:
        _raise_ai_required_error(
            stage="chapter_style_review",
            message="章节结构复核失败，已停止生成",
            detail_reason=str(exc),
            retryable=True,
        )
    if not isinstance(data, dict):
        return None
    verdict = str(data.get("verdict") or "").strip().lower()
    if verdict not in {"messy", "ok"}:
        return None
    data["verdict"] = verdict
    return data


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



def _dedupe_texts(values: Iterable[Any], *, limit: int = 8) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
    for value in values:
        text = str(value or "").strip()
        norm = re.sub(r"\s+", "", text)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        items.append(text)
        if len(items) >= limit:
            break
    return items


def _payoff_plan_token_hints(chapter_plan: dict[str, Any] | None) -> dict[str, list[str]]:
    if not isinstance(chapter_plan, dict):
        return {"reward": [], "reaction": [], "pressure": []}
    planning_packet = (chapter_plan.get("planning_packet") or {}) if isinstance(chapter_plan.get("planning_packet"), dict) else {}
    selected_card = (planning_packet.get("selected_payoff_card") or {}) if isinstance(planning_packet, dict) else {}
    reward_source = [
        chapter_plan.get("reader_payoff"),
        chapter_plan.get("payoff_or_pressure"),
        selected_card.get("reader_payoff"),
    ]
    reaction_source = [
        selected_card.get("external_reaction"),
        chapter_plan.get("payoff_external_reaction"),
        chapter_plan.get("payoff_or_pressure"),
    ]
    pressure_source = [
        chapter_plan.get("new_pressure"),
        selected_card.get("new_pressure"),
        selected_card.get("aftershock"),
        chapter_plan.get("payoff_or_pressure"),
    ]

    def collect(source_values: list[Any], marker_pool: tuple[str, ...], *, extra_hint_keys: tuple[str, ...] = ()) -> list[str]:
        source_text = " ".join(str(item or "") for item in source_values if str(item or "").strip())
        items: list[str] = [token for token in marker_pool if token in source_text]
        for token in re.findall(r"[一-鿿]{2,6}", source_text):
            if token in items:
                continue
            if any(key in token for key in extra_hint_keys):
                items.append(token)
        return _dedupe_texts(items, limit=8)

    return {
        "reward": collect(reward_source, PAYOFF_DIRECT_MARKERS, extra_hint_keys=("拿", "换", "得", "保", "确认", "坐实", "翻")),
        "reaction": collect(reaction_source, PAYOFF_REACTION_MARKERS + PAYOFF_PUBLIC_SUBJECTS, extra_hint_keys=("变脸", "改口", "迟疑", "安静", "眼神", "盯")),
        "pressure": collect(pressure_source, PAYOFF_PRESSURE_MARKERS, extra_hint_keys=("盯", "查", "疑", "记住", "后患", "代价", "暴露", "风头")),
    }


def assess_payoff_delivery(
    *,
    title: str,
    content: str,
    chapter_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    text = (content or "").strip()
    progress_kind = str((chapter_plan or {}).get("progress_kind") or "").strip() or None
    progress_clear, progress_metrics = _progress_result_is_clear(text, progress_kind, chapter_plan=chapter_plan)
    hints = _payoff_plan_token_hints(chapter_plan)
    reward_hits = sum(text.count(token) for token in hints["reward"] or PAYOFF_DIRECT_MARKERS)
    reaction_hits = sum(text.count(token) for token in hints["reaction"] or PAYOFF_REACTION_MARKERS)
    pressure_hits = sum(text.count(token) for token in hints["pressure"] or PAYOFF_PRESSURE_MARKERS)
    public_subject_hits = sum(text.count(token) for token in PAYOFF_PUBLIC_SUBJECTS)
    visibility = str((chapter_plan or {}).get("payoff_visibility") or "").strip()
    selected_level = str((chapter_plan or {}).get("payoff_level") or "").strip().lower() or "medium"
    visibility_fit = False
    if visibility == "public":
        visibility_fit = reaction_hits >= 1 and public_subject_hits >= 1
    elif visibility == "semi_public":
        visibility_fit = reaction_hits >= 1 or public_subject_hits >= 1
    elif visibility == "private":
        visibility_fit = reward_hits >= 1
    else:
        visibility_fit = reward_hits >= 1 and (reaction_hits >= 1 or pressure_hits >= 1)

    score = 0
    score += 2 if reward_hits >= 2 else (1 if reward_hits >= 1 else 0)
    score += 1 if reaction_hits >= 1 else 0
    score += 1 if pressure_hits >= 1 else 0
    score += 1 if public_subject_hits >= 1 else 0
    score += 1 if progress_clear else 0
    score += 1 if visibility_fit else 0

    if selected_level == "strong":
        level = "high" if score >= 6 else ("medium" if score >= 4 else "low")
    else:
        level = "high" if score >= 5 else ("medium" if score >= 3 else "low")

    missed_targets: list[str] = []
    if reward_hits < 1:
        missed_targets.append("回报落袋不够明确")
    if visibility in {"public", "semi_public"} and reaction_hits < 1:
        missed_targets.append("外部反应显影不足")
    if pressure_hits < 1:
        missed_targets.append("后续压力偏弱")
    if not progress_clear:
        missed_targets.append("结果句不够清晰")

    if level == "high":
        verdict = "兑现扎实"
        runtime_note = "这章爽点已经落地，读者能看到主角拿回了什么，也能看到后续麻烦。"
    elif level == "medium":
        verdict = "兑现到位但还可更狠"
        runtime_note = "这章已经有回报，但外部显影或后续压力还可以再压实一格。"
    else:
        verdict = "兑现偏虚"
        runtime_note = "这章计划里说要爽，但正文里的回报、显影或后患还不够硬。"

    summary_lines = [
        f"兑现判断：{verdict}（score={score}，reward={reward_hits}，reaction={reaction_hits}，pressure={pressure_hits}）。",
        f"显影要求：{visibility or 'auto'}；公开反应命中 {public_subject_hits} 处；结果证据 {int(progress_metrics.get('progress_sentence_hits') or 0)} 句。",
        runtime_note,
    ]
    if missed_targets:
        summary_lines.append("待补点：" + "、".join(missed_targets[:3]) + "。")

    return {
        "title": title,
        "selected_level": selected_level,
        "selected_visibility": visibility or None,
        "delivery_score": score,
        "delivery_level": level,
        "verdict": verdict,
        "reward_hits": reward_hits,
        "reaction_hits": reaction_hits,
        "pressure_hits": pressure_hits,
        "public_subject_hits": public_subject_hits,
        "visibility_fit": visibility_fit,
        "progress_clear": progress_clear,
        "progress_metrics": progress_metrics,
        "reward_hints": hints["reward"],
        "reaction_hints": hints["reaction"],
        "pressure_hints": hints["pressure"],
        "missed_targets": missed_targets,
        "runtime_note": runtime_note,
        "summary_lines": summary_lines,
    }


def _default_payoff_compensation(local_review: dict[str, Any], chapter_plan: dict[str, Any] | None = None) -> dict[str, Any]:
    review = local_review or {}
    selected_level = str(review.get("selected_level") or (chapter_plan or {}).get("payoff_level") or "medium").strip().lower()
    delivery_level = str(review.get("delivery_level") or "medium").strip().lower()
    should_compensate = delivery_level == "low" or (delivery_level == "medium" and selected_level == "strong")
    if delivery_level == "low":
        priority = "high"
        note = "上一章兑现偏虚，下一章优先补一次明确落袋与外部显影，不要继续只蓄压。"
    elif should_compensate:
        priority = "medium"
        note = "上一章有回报但还不够扎实，下一章最好再补一次可感兑现。"
    else:
        priority = "low"
        note = "当前兑现不需要额外追账，下一章按正常节奏推进即可。"
    return {
        "should_compensate_next_chapter": should_compensate,
        "compensation_priority": priority,
        "compensation_note": note,
    }



def _payoff_ai_review_trigger_reasons(local_review: dict[str, Any], chapter_plan: dict[str, Any] | None = None) -> list[str]:
    if not bool(getattr(settings, "payoff_ai_delivery_review_enabled", True)):
        return []
    review = local_review or {}
    reasons: list[str] = []
    delivery_level = str(review.get("delivery_level") or "").strip().lower()
    selected_level = str(review.get("selected_level") or (chapter_plan or {}).get("payoff_level") or "").strip().lower()
    if delivery_level == "low":
        reasons.append("delivery_low")
    if delivery_level == "medium" and selected_level == "strong":
        reasons.append("strong_plan_but_medium_delivery")
    if not bool(review.get("visibility_fit", True)):
        reasons.append("visibility_mismatch")
    if len(review.get("missed_targets") or []) >= 2:
        reasons.append("multiple_missed_targets")
    return reasons



def _normalize_payoff_delivery_ai_payload(data: dict[str, Any] | None, *, local_review: dict[str, Any], chapter_plan: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = data or {}
    merged = dict(local_review or {})
    level = str(payload.get("delivery_level") or merged.get("delivery_level") or "medium").strip().lower()
    if level not in {"low", "medium", "high"}:
        level = str(merged.get("delivery_level") or "medium").strip().lower() or "medium"
    merged["delivery_level"] = level
    merged["verdict"] = str(payload.get("verdict") or merged.get("verdict") or "兑现到位但还可更狠").strip()
    merged["runtime_note"] = str(payload.get("runtime_note") or merged.get("runtime_note") or "").strip()
    ai_missed = [str(item).strip() for item in (payload.get("missed_targets") or []) if str(item).strip()]
    if ai_missed:
        merged["missed_targets"] = ai_missed[:4]
    summary_lines = [str(item).strip() for item in (payload.get("summary_lines") or []) if str(item).strip()]
    if summary_lines:
        merged["summary_lines"] = summary_lines[:5]
    comp = _default_payoff_compensation(merged, chapter_plan=chapter_plan)
    should_compensate = payload.get("should_compensate_next_chapter")
    if should_compensate is None:
        should_compensate = comp["should_compensate_next_chapter"]
    merged["should_compensate_next_chapter"] = bool(should_compensate)
    priority = str(payload.get("compensation_priority") or comp["compensation_priority"] or "low").strip().lower()
    if priority not in {"high", "medium", "low"}:
        priority = comp["compensation_priority"]
    merged["compensation_priority"] = priority
    merged["compensation_note"] = str(payload.get("compensation_note") or comp["compensation_note"] or "").strip()
    return merged



def review_payoff_delivery_with_ai(
    *,
    title: str,
    content: str,
    chapter_plan: dict[str, Any] | None,
    local_review: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(local_review or {})
    triggers = _payoff_ai_review_trigger_reasons(merged, chapter_plan=chapter_plan)
    defaults = _default_payoff_compensation(merged, chapter_plan=chapter_plan)
    merged.update(defaults)
    merged["review_source"] = "local"
    merged["ai_review_used"] = False
    merged["ai_review_trigger_reasons"] = triggers
    if not triggers:
        return merged
    if not is_openai_enabled():
        _raise_ai_required_error(
            stage="payoff_delivery_review",
            message="爽点兑现复核需要可用的 AI，当前已停止生成",
            detail_reason="当前没有可用的 AI 配置或密钥。",
            retryable=False,
        )
    try:
        data = call_json_response(
            stage="payoff_delivery_review",
            system_prompt=payoff_delivery_review_system_prompt(),
            user_prompt=payoff_delivery_review_user_prompt(
                title=title,
                content=content,
                chapter_plan=chapter_plan or {},
                local_review=merged,
            ),
            max_output_tokens=max(int(getattr(settings, "payoff_ai_delivery_review_max_output_tokens", 520) or 520), 260),
            timeout_seconds=max(int(getattr(settings, "payoff_ai_delivery_review_timeout_seconds", 14) or 14), 8),
        )
        merged = _normalize_payoff_delivery_ai_payload(data if isinstance(data, dict) else {}, local_review=merged, chapter_plan=chapter_plan)
        merged["review_source"] = "ai_rechecked"
        merged["ai_review_used"] = True
        merged["ai_review_trigger_reasons"] = triggers
        return merged
    except GenerationError:
        raise
    except Exception as exc:
        _raise_ai_required_error(
            stage="payoff_delivery_review",
            message="爽点兑现复核失败，已停止生成",
            detail_reason=str(exc),
            retryable=True,
        )



def _paragraph_window(text: str, *, limit: int = 2) -> str:
    paragraphs = _non_empty_paragraphs(text)
    return "\n".join(paragraphs[: max(limit, 1)]).strip()


def _scene_hint_candidates(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    hints: list[str] = []
    for value in values:
        raw = str(value or "").strip()
        if not raw:
            continue
        if len(raw) <= 18 and raw not in seen:
            seen.add(raw)
            hints.append(raw)
        for token in re.findall(r"[一-鿿A-Za-z0-9]{2,8}", raw):
            token = token.strip()
            if len(token) < 2 or token in SCENE_HINT_STOPWORDS:
                continue
            if token not in seen:
                seen.add(token)
                hints.append(token)
            if len(hints) >= 16:
                return hints
    return hints[:16]


def _scene_overlap_hits(text: str, hints: Iterable[str]) -> list[str]:
    source = str(text or "")
    hits: list[str] = []
    seen: set[str] = set()
    for hint in hints:
        token = str(hint or "").strip()
        if len(token) < 2 or token in seen:
            continue
        if token in source:
            seen.add(token)
            hits.append(token)
        if len(hits) >= 6:
            break
    return hits


def _contains_time_skip_anchor(text: str) -> bool:
    source = str(text or "")
    return any(marker in source for marker in TIME_SKIP_STRONG_MARKERS)


def _count_scene_transition_cues(text: str) -> tuple[int, list[str]]:
    paragraphs = _non_empty_paragraphs(text)
    hits: list[str] = []
    for paragraph in paragraphs[1:]:
        if any(re.search(pattern, paragraph) for pattern in SCENE_TRANSITION_PATTERNS):
            hits.append((paragraph[:41] + "…") if len(paragraph) > 42 else paragraph)
        if len(hits) >= 4:
            break
    return len(hits), hits


def assess_scene_continuity(
    *,
    content: str,
    serialized_last: dict[str, Any] | None = None,
    execution_brief: dict[str, Any] | None = None,
) -> dict[str, Any]:
    bridge = ((serialized_last or {}).get("continuity_bridge") or {}) if isinstance((serialized_last or {}).get("continuity_bridge"), dict) else {}
    handoff = (bridge.get("scene_handoff_card") or {}) if isinstance(bridge.get("scene_handoff_card"), dict) else {}
    scene_card = ((execution_brief or {}).get("scene_execution_card") or {}) if isinstance((execution_brief or {}).get("scene_execution_card"), dict) else {}
    scene_plan = ((execution_brief or {}).get("scene_sequence_plan") or []) if isinstance((execution_brief or {}).get("scene_sequence_plan"), list) else []
    scene_count = max(int(scene_card.get("scene_count") or len(scene_plan) or 0), 0)
    transition_mode = str(scene_card.get("transition_mode") or "").strip()
    opening = _paragraph_window(content, limit=2)
    opening_anchor = str(handoff.get("next_opening_anchor") or bridge.get("opening_anchor") or "").strip()
    unresolved = [str(item).strip() for item in (bridge.get("unresolved_action_chain") or []) if str(item).strip()]
    carry_over = [str(item).strip() for item in (handoff.get("carry_over_items") or bridge.get("carry_over_clues") or []) if str(item).strip()]
    onstage = [str(item).strip() for item in (bridge.get("onstage_characters") or []) if str(item).strip()]
    last_scene = (bridge.get("last_scene_card") or {}) if isinstance(bridge.get("last_scene_card"), dict) else {}
    hint_tokens = _scene_hint_candidates(unresolved + carry_over + onstage + [last_scene.get("main_scene")])
    opening_overlap_hits = _scene_overlap_hits(opening, hint_tokens)
    opening_anchor_similarity = 0.0
    if opening_anchor and opening:
        opening_anchor_similarity = round(SequenceMatcher(None, _normalize_line(opening)[:180], _normalize_line(opening_anchor)[:180]).ratio(), 4)
    must_continue_same_scene = bool(scene_card.get("must_continue_same_scene")) or bool(handoff.get("must_continue_same_scene")) or str(handoff.get("scene_status_at_end") or "").strip() in {"open", "interrupted"}
    time_skip_allowed = str(handoff.get("allowed_transition") or scene_card.get("allowed_transition") or "").strip() in {"time_skip", "time_skip_allowed"}
    time_anchor_present = _contains_time_skip_anchor(opening)
    transition_cue_count, transition_cues = _count_scene_transition_cues(content)
    expected_transition_count = max(scene_count - 1, 0)

    payload = {
        "scene_count": scene_count,
        "scene_transition_mode": transition_mode or None,
        "scene_opening_anchor": opening_anchor or None,
        "scene_opening_anchor_similarity": opening_anchor_similarity,
        "scene_opening_overlap_tokens": opening_overlap_hits,
        "scene_opening_overlap_hits": len(opening_overlap_hits),
        "scene_time_anchor_present": time_anchor_present,
        "scene_transition_cue_count": transition_cue_count,
        "scene_expected_transition_count": expected_transition_count,
        "scene_transition_cues": transition_cues,
        "must_continue_same_scene": must_continue_same_scene,
    }

    if not bridge and not scene_card:
        return {"ok": True, **payload}

    issue = None
    message = ""
    if must_continue_same_scene and time_anchor_present:
        issue = "abrupt_scene_cut"
        message = "上一章场景还没收住，这一章却在开头直接跳时段/跳场，承接断了。"
    elif must_continue_same_scene and opening_anchor_similarity < 0.12 and not opening_overlap_hits:
        issue = "missing_opening_continuation"
        message = "上一章明明还挂着旧场景，这一章开头却没有先吃掉旧场景的动作后果或关键承接物。"
    elif time_skip_allowed and not time_anchor_present:
        issue = "time_skip_without_anchor"
        message = "这章允许时间跳转，但开头没有写出明确时间锚点，场景切换像偷偷滑过去了。"
    elif scene_count >= 3 and transition_mode in {"soft_cut", "multi_scene_chain", "time_skip_allowed"} and transition_cue_count < 1:
        issue = "scene_transition_not_visible"
        message = "本章有多段场景链，但正文里几乎看不见切场过渡，场景像被直接传送。"

    if issue:
        return {"ok": False, "scene_continuity_issue": issue, "message": message, **payload}
    return {"ok": True, **payload}


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
        "repeated_sentence_ratio", "repeated_opening_groups", "repeated_opening_hits", "repeated_openings",
        "repeated_ending_groups", "repeated_ending_hits", "repeated_endings", "style_clue_hits",
        "style_clue_total", "style_clue_kinds", "messy_score", "scene_count", "scene_transition_mode",
        "scene_continuity_issue", "scene_opening_anchor", "scene_opening_anchor_similarity",
        "scene_opening_overlap_hits", "scene_opening_overlap_tokens", "scene_time_anchor_present",
        "scene_transition_cue_count", "scene_expected_transition_count", "scene_transition_cues",
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
        ai_review = details.get("ai_style_review") if isinstance(details.get("ai_style_review"), dict) else {}
        messy_metrics = details.get("messy_metrics") if isinstance(details.get("messy_metrics"), dict) else {}
        if ai_review:
            for label in ai_review.get("problem_types") or []:
                add_check(str(label).strip() or "写法重复")
            if not feedback["failed_checks"]:
                add_check("写法和结构重复过密")
            repair_brief = str(ai_review.get("repair_brief") or "").strip()
            if repair_brief:
                add_suggestion(repair_brief)
            for item in ai_review.get("must_change") or []:
                add_suggestion(str(item).strip())
            for item in ai_review.get("avoid") or []:
                tip = str(item).strip()
                if tip:
                    add_suggestion(f"避免再写成：{tip}")
        elif messy_metrics:
            add_check("写法和结构重复过密")
            if float(messy_metrics.get("repeated_sentence_ratio") or 0) >= MESSY_SENTENCE_REPEAT_RATIO:
                add_suggestion("减少近似重复句，改掉同一判断句反复出现的写法。")
            if int(messy_metrics.get("repeated_opening_groups") or 0) > 0:
                add_suggestion("把句子开头拆开，不要连续几句都用同一种起手动作或判断。")
            if int(messy_metrics.get("repeated_ending_groups") or 0) > 0:
                add_suggestion("收句方式换档，别让几个句子都落在同一种尾音和结论上。")
            if not feedback["suggestions"]:
                add_suggestion("减少模板回环，换动作链、换判断方式、换句子开合。")
        else:
            add_check("文本噪音过多")
            add_suggestion("清掉 JSON、元提示、重复句或结构化残留，只保留正文。")
    elif exc.code == ErrorCodes.CHAPTER_TOO_SIMILAR:
        add_check("与近章过于相似")
        add_suggestion("更换开场动作、核心矛盾或收尾方式，避免重复最近章节的桥段和句式。")
    elif exc.code == ErrorCodes.CHAPTER_PROGRESS_TOO_WEAK:
        if details.get("scene_continuity_issue"):
            issue = str(details.get("scene_continuity_issue") or "").strip()
            add_check("场景承接/切换不稳")
            if issue == "abrupt_scene_cut":
                add_suggestion("上一章旧场景还没收住时，下一章开头先续接原场景，别直接跳到次日或新地点。")
            elif issue == "missing_opening_continuation":
                add_suggestion("开头两段先吃掉上一章的动作后果、关键人物或携带物，再决定是否切场。")
            elif issue == "time_skip_without_anchor":
                add_suggestion("允许时间跳转时，前两段要明写时间锚点，并带上上一章留下的关键物或结果。")
            else:
                add_suggestion("一章内多场景切换时，把过渡写成可见动作链或时间/地点变化，别让场景像被传送。")
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
    serialized_last: dict[str, Any] | None = None,
    execution_brief: dict[str, Any] | None = None,
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

    messy_metrics = _messy_structure_metrics(text)
    if bool(messy_metrics.get("needs_ai_review")):
        ai_style_review = _messy_ai_review(title, text, messy_metrics)
        if ai_style_review and str(ai_style_review.get("verdict") or "") == "messy":
            raise GenerationError(
                code=ErrorCodes.CHAPTER_TOO_MESSY,
                message="正文在写法和结构层面重复偏多，读感发机械，AI 痕迹仍然偏重。",
                stage="chapter_quality",
                retryable=True,
                http_status=422,
                details={"title": title, **messy_metrics, "messy_metrics": messy_metrics, "ai_style_review": ai_style_review},
            )
        if ai_style_review and str(ai_style_review.get("verdict") or "") == "ok":
            messy_metrics["ai_review_verdict"] = "ok"
        elif bool(messy_metrics.get("hard_fail")) or (
            int(messy_metrics.get("repeated_opening_hits") or 0) >= 5
            and int(messy_metrics.get("repeated_ending_hits") or 0) >= 5
        ):
            raise GenerationError(
                code=ErrorCodes.CHAPTER_TOO_MESSY,
                message="正文在句式和结构上重复过密，整体读感接近模板拼接，不适合直接入库。",
                stage="chapter_quality",
                retryable=True,
                http_status=422,
                details={"title": title, **messy_metrics, "messy_metrics": messy_metrics},
            )
    elif bool(messy_metrics.get("hard_fail")):
        raise GenerationError(
            code=ErrorCodes.CHAPTER_TOO_MESSY,
            message="正文在句式和结构上重复过密，整体读感接近模板拼接，不适合直接入库。",
            stage="chapter_quality",
            retryable=True,
            http_status=422,
            details={"title": title, **messy_metrics, "messy_metrics": messy_metrics},
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

    if bool(getattr(settings, "chapter_scene_continuity_check_enabled", True)):
        scene_continuity = assess_scene_continuity(
            content=text,
            serialized_last=serialized_last,
            execution_brief=execution_brief,
        )
        if not bool(scene_continuity.get("ok", True)):
            raise GenerationError(
                code=ErrorCodes.CHAPTER_PROGRESS_TOO_WEAK,
                message=str(scene_continuity.get("message") or "本章场景承接或切换不稳，读感发断。"),
                stage="chapter_quality",
                retryable=True,
                http_status=422,
                details={"title": title, **scene_continuity},
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
