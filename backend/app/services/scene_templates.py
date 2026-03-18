
from __future__ import annotations

from copy import deepcopy
from difflib import SequenceMatcher
from typing import Any


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default



def _safe_list(values: Any) -> list[str]:
    if isinstance(values, list):
        return [str(item).strip() for item in values if str(item or "").strip()]
    return []



def _truncate_text(value: Any, limit: int) -> str:
    text = _text(value)
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 0)].rstrip() + ("…" if limit > 0 else "")



def build_scene_templates() -> list[dict[str, Any]]:
    return [
        {
            "scene_id": "same_scene_continuation",
            "name": "同场景续接场",
            "scene_role": "opening",
            "entry_modes": ["紧接上一章最后动作", "继续同一冲突链"],
            "best_for": ["承接未完动作", "防止章间硬切", "先收束再换挡"],
            "compatible_event_types": ["冲突类", "调查类", "试探类", "危机类", "交易类"],
            "compatible_progress_kinds": ["风险升级", "信息推进", "关系推进", "资源推进"],
            "compatible_payoff_modes": ["明确兑现", "险中见利", "捡漏反压"],
            "default_purpose": "先吃掉上一章没落地的动作链，再决定是否切场。",
            "transition_rule": "第一段必须承接 opening_anchor 或 last_two_paragraphs 的动作后果。",
        },
        {
            "scene_id": "bridge_settlement",
            "name": "承接收束场",
            "scene_role": "opening",
            "entry_modes": ["先收尾再开新局", "把上章余波压实"],
            "best_for": ["化解跳场", "给旧场景一个阶段结果"],
            "compatible_event_types": ["调查类", "关系类", "交易类", "日常推进"],
            "compatible_progress_kinds": ["信息推进", "关系推进", "资源推进"],
            "compatible_payoff_modes": ["明确兑现", "余波带压"],
            "default_purpose": "先把上一场的余波落地，再把叙事推向新动作。",
            "transition_rule": "若要切场，必须先给出阶段性结果或明确过渡。",
        },
        {
            "scene_id": "probe_negotiation",
            "name": "交易试探场",
            "scene_role": "main",
            "entry_modes": ["带目的进入", "边谈边套话"],
            "best_for": ["调查类", "试探类", "资源交换"],
            "compatible_event_types": ["调查类", "试探类", "交易类", "关系类"],
            "compatible_progress_kinds": ["信息推进", "资源推进", "关系推进"],
            "compatible_payoff_modes": ["明确兑现", "捡漏反压", "低调增益"],
            "default_purpose": "让人物在交易、问答或条件拉扯里得到信息、资源或态度变化。",
            "transition_rule": "中段至少出现一次试探受阻、价码变化或旁人介入。",
        },
        {
            "scene_id": "pressure_collision",
            "name": "压迫对峙场",
            "scene_role": "main",
            "entry_modes": ["冲突顶脸", "强势角色压迫"],
            "best_for": ["矛盾升级", "主角反压", "高张力对话"],
            "compatible_event_types": ["冲突类", "危机类", "试探类"],
            "compatible_progress_kinds": ["风险升级", "关系推进", "实力推进"],
            "compatible_payoff_modes": ["捡漏反压", "险中见利", "明确兑现"],
            "default_purpose": "让人物在对峙里交锋，逼出底牌、态度或新风险。",
            "transition_rule": "必须有可感知的压迫变化，不能全靠嘴上僵持。",
        },
        {
            "scene_id": "clue_verification",
            "name": "线索验证场",
            "scene_role": "main",
            "entry_modes": ["追着疑点去验证", "用动作确认真假"],
            "best_for": ["调查推进", "把怀疑变成结果"],
            "compatible_event_types": ["调查类", "探索类", "试探类"],
            "compatible_progress_kinds": ["信息推进", "风险升级"],
            "compatible_payoff_modes": ["明确兑现", "余波带压"],
            "default_purpose": "通过试验、比对、追踪或观察，让线索状态发生变化。",
            "transition_rule": "结尾必须给出真伪判断、半验证结果或更明确的新疑点。",
        },
        {
            "scene_id": "resource_exchange",
            "name": "资源争取场",
            "scene_role": "main",
            "entry_modes": ["为资源开口", "拿筹码换条件"],
            "best_for": ["资源推进", "交易类", "求助与换利"],
            "compatible_event_types": ["交易类", "资源类", "关系类"],
            "compatible_progress_kinds": ["资源推进", "关系推进"],
            "compatible_payoff_modes": ["明确兑现", "低调增益", "险中见利"],
            "default_purpose": "把资源、代价、条件和后手写成看得见的交换。",
            "transition_rule": "至少让读者看见一次得失或价码变化。",
        },
        {
            "scene_id": "private_alignment",
            "name": "私下结盟场",
            "scene_role": "main",
            "entry_modes": ["关起门来谈", "关系试探后站队"],
            "best_for": ["关系推进", "拉拢", "同伴绑定"],
            "compatible_event_types": ["关系类", "试探类", "调查类"],
            "compatible_progress_kinds": ["关系推进", "信息推进"],
            "compatible_payoff_modes": ["明确兑现", "低调增益"],
            "default_purpose": "让关系往前一步，确定靠近、交换秘密或达成临时合作。",
            "transition_rule": "不要空谈感情，必须通过条件、风险或共同目标立住关系变化。",
        },
        {
            "scene_id": "travel_insert",
            "name": "赶路插事场",
            "scene_role": "bridge",
            "entry_modes": ["路上遇事", "移动中补推进"],
            "best_for": ["换地图", "中途遭遇", "衔接主线"],
            "compatible_event_types": ["探索类", "危机类", "调查类", "日常推进"],
            "compatible_progress_kinds": ["风险升级", "信息推进", "关系推进"],
            "compatible_payoff_modes": ["余波带压", "险中见利"],
            "default_purpose": "在切地点时不空转，让赶路本身也带事件和结果。",
            "transition_rule": "切地图时最好把风险、线索或关系推进一起带走。",
        },
        {
            "scene_id": "tail_followup",
            "name": "尾随反查场",
            "scene_role": "bridge",
            "entry_modes": ["被盯梢", "主角反手追查"],
            "best_for": ["章间续接", "危险感", "中段提速"],
            "compatible_event_types": ["危机类", "调查类", "冲突类"],
            "compatible_progress_kinds": ["风险升级", "信息推进"],
            "compatible_payoff_modes": ["险中见利", "捡漏反压"],
            "default_purpose": "把被动威胁写成主动反查，让局势自己长腿。",
            "transition_rule": "至少让主角做一次主动反手，而不是只感到不安。",
        },
        {
            "scene_id": "repair_recovery",
            "name": "修整复盘场",
            "scene_role": "bridge",
            "entry_modes": ["打完收束", "喘口气但不松线"],
            "best_for": ["战后消化", "关系缓和", "下章准备"],
            "compatible_event_types": ["日常推进", "关系类", "资源类"],
            "compatible_progress_kinds": ["资源推进", "关系推进", "信息推进"],
            "compatible_payoff_modes": ["低调增益", "明确兑现", "余波带压"],
            "default_purpose": "在修整中处理得失、伤势、资源和判断，不写成空白喘息。",
            "transition_rule": "修整也要落结果，至少明确下一步准备、代价或判断。",
        },
        {
            "scene_id": "small_payoff",
            "name": "小胜兑现场",
            "scene_role": "bridge",
            "entry_modes": ["先给回报", "把读者该拿的爽点落地"],
            "best_for": ["兑现爽点", "补偿前章欠账"],
            "compatible_event_types": ["资源类", "关系类", "调查类", "冲突类"],
            "compatible_progress_kinds": ["资源推进", "关系推进", "信息推进", "实力推进"],
            "compatible_payoff_modes": ["明确兑现", "低调增益", "捡漏反压"],
            "default_purpose": "让成果先被看见，再把余波或代价接上。",
            "transition_rule": "兑现不能只是一句总结，必须写成具体可感的回报。",
        },
        {
            "scene_id": "public_showcase",
            "name": "公开显影场",
            "scene_role": "bridge",
            "entry_modes": ["旁人看见", "结果外显"],
            "best_for": ["public/semi_public 爽点", "社会反应"],
            "compatible_event_types": ["冲突类", "关系类", "资源类"],
            "compatible_progress_kinds": ["关系推进", "实力推进", "资源推进"],
            "compatible_payoff_modes": ["明确兑现", "捡漏反压"],
            "default_purpose": "让外界看见这次变化，形成舆论、嫉恨、忌惮或跟风。",
            "transition_rule": "必须写出旁人反应，不能只有主角自己知道。",
        },
        {
            "scene_id": "suspicion_hook",
            "name": "疑点悬停场",
            "scene_role": "ending",
            "entry_modes": ["结尾留一个带方向的新疑点", "把问题往下一章送"],
            "best_for": ["谜团钩子", "调查线延伸"],
            "compatible_event_types": ["调查类", "试探类", "探索类"],
            "compatible_progress_kinds": ["信息推进", "风险升级"],
            "compatible_payoff_modes": ["余波带压", "明确兑现"],
            "default_purpose": "在结果落地后再抬出一个更窄、更具体的新问题。",
            "transition_rule": "钩子要来自当前场景结果，不要平地起雷。",
        },
        {
            "scene_id": "hanging_pressure",
            "name": "压力悬停场",
            "scene_role": "ending",
            "entry_modes": ["危险逼近", "后患现身"],
            "best_for": ["危机钩子", "敌意反应", "追更拉力"],
            "compatible_event_types": ["冲突类", "危机类", "调查类"],
            "compatible_progress_kinds": ["风险升级", "关系推进"],
            "compatible_payoff_modes": ["余波带压", "捡漏反压", "险中见利"],
            "default_purpose": "把本章行动惹出的后患掀开一角，逼下一章承接。",
            "transition_rule": "必须能看出压力从哪来，不要只写气氛词。",
        },
        {
            "scene_id": "aftermath_review",
            "name": "余波判断场",
            "scene_role": "ending",
            "entry_modes": ["结果已出", "主角做下一步判断"],
            "best_for": ["平稳收束", "章节结算", "留准备型钩子"],
            "compatible_event_types": ["日常推进", "资源类", "关系类", "调查类"],
            "compatible_progress_kinds": ["信息推进", "资源推进", "关系推进"],
            "compatible_payoff_modes": ["明确兑现", "低调增益", "余波带压"],
            "default_purpose": "把结果、判断和下一步准备绑在一起，形成干净章尾。",
            "transition_rule": "收束可以平，但不能空，必须带着结果或准备离场。",
        },
        {
            "scene_id": "battle_aftermath",
            "name": "战后收束场",
            "scene_role": "ending",
            "entry_modes": ["打后清场", "数代价与所得"],
            "best_for": ["冲突后处理", "清点损失", "翻出新问题"],
            "compatible_event_types": ["冲突类", "危机类"],
            "compatible_progress_kinds": ["资源推进", "风险升级", "关系推进"],
            "compatible_payoff_modes": ["险中见利", "明确兑现", "余波带压"],
            "default_purpose": "把一场冲突的代价、收益、伤势和后续麻烦落到具体画面里。",
            "transition_rule": "至少交代一个成本和一个收获。",
        },
        {
            "scene_id": "secret_probe",
            "name": "潜入偷听场",
            "scene_role": "main",
            "entry_modes": ["暗中接近", "低声侦听"],
            "best_for": ["调查推进", "风险提拉", "信息窃取"],
            "compatible_event_types": ["调查类", "危机类", "探索类"],
            "compatible_progress_kinds": ["信息推进", "风险升级"],
            "compatible_payoff_modes": ["险中见利", "明确兑现"],
            "default_purpose": "在不正面碰撞的情况下拿到关键线索或确认敌意。",
            "transition_rule": "不能全靠偷听内容，最好有暴露风险或临场判断。",
        },
        {
            "scene_id": "trial_advancement",
            "name": "试炼推进场",
            "scene_role": "main",
            "entry_modes": ["硬闯一步", "能力验证"],
            "best_for": ["实力推进", "考核", "任务线推进"],
            "compatible_event_types": ["任务类", "冲突类", "探索类"],
            "compatible_progress_kinds": ["实力推进", "风险升级", "资源推进"],
            "compatible_payoff_modes": ["明确兑现", "险中见利"],
            "default_purpose": "让主角通过行动验证能力边界，同时换来资格、经验或新限制。",
            "transition_rule": "推进必须通过动作和代价落地，不能只说更强了。",
        },
        {
            "scene_id": "misunderstanding_shift",
            "name": "误会翻向场",
            "scene_role": "bridge",
            "entry_modes": ["态度突然偏转", "关系发生意外变化"],
            "best_for": ["关系推进", "群像互动", "立人物"],
            "compatible_event_types": ["关系类", "冲突类", "日常推进"],
            "compatible_progress_kinds": ["关系推进", "风险升级"],
            "compatible_payoff_modes": ["低调增益", "余波带压"],
            "default_purpose": "让一句话、一个动作或一个误会把人物关系推到新位置。",
            "transition_rule": "变化要有触发点，不能凭空突然和好或翻脸。",
        },
        {
            "scene_id": "hooked_departure",
            "name": "带钩离场",
            "scene_role": "ending",
            "entry_modes": ["准备离开", "临门再见异动"],
            "best_for": ["章末提拉", "场景切换前留后劲"],
            "compatible_event_types": ["调查类", "任务类", "关系类", "资源类"],
            "compatible_progress_kinds": ["信息推进", "风险升级", "关系推进"],
            "compatible_payoff_modes": ["余波带压", "明确兑现"],
            "default_purpose": "让人物看似要离开时，再给出一个迫使下一章继续的入口。",
            "transition_rule": "最后一钩最好来自刚刚的结果，而不是无关旁枝。",
        },
    ]



def ensure_scene_template_library(story_bible: dict[str, Any]) -> list[dict[str, Any]]:
    template_library = story_bible.setdefault("template_library", {})
    scene_templates = template_library.get("scene_templates")
    if not isinstance(scene_templates, list) or not scene_templates:
        scene_templates = build_scene_templates()
        template_library["scene_templates"] = scene_templates
    roadmap = template_library.setdefault("roadmap", {})
    roadmap.setdefault("scene_template_target_count", 20)
    roadmap["current_scene_template_count"] = len(scene_templates)
    return scene_templates



def _dedupe_texts(values: list[str], *, limit: int, item_limit: int) -> list[str]:
    result: list[str] = []
    for value in values:
        text_value = _truncate_text(value, item_limit)
        if text_value and text_value not in result:
            result.append(text_value)
        if len(result) >= limit:
            break
    return result



def _contains_any(text_blob: str, needles: list[str]) -> bool:
    blob = _text(text_blob)
    if not blob:
        return False
    return any(token for token in needles if token and token in blob)



def _compact_scene_handoff_card(raw: dict[str, Any] | None) -> dict[str, Any]:
    payload = raw or {}
    compact = {
        "scene_status_at_end": _truncate_text(payload.get("scene_status_at_end"), 16),
        "must_continue_same_scene": bool(payload.get("must_continue_same_scene")),
        "allowed_transition": _truncate_text(payload.get("allowed_transition"), 16),
        "next_opening_anchor": _truncate_text(payload.get("next_opening_anchor"), 120),
        "final_scene_name": _truncate_text(payload.get("final_scene_name"), 24),
        "final_scene_role": _truncate_text(payload.get("final_scene_role"), 16),
        "carry_over_items": _dedupe_texts(_safe_list(payload.get("carry_over_items")), limit=4, item_limit=56),
        "carry_over_people": _dedupe_texts(_safe_list(payload.get("carry_over_people")), limit=5, item_limit=20),
        "unfinished_actions": _dedupe_texts(_safe_list(payload.get("unfinished_actions")), limit=4, item_limit=64),
        "forbidden_openings": _dedupe_texts(_safe_list(payload.get("forbidden_openings")), limit=3, item_limit=40),
        "handoff_note": _truncate_text(payload.get("handoff_note"), 84),
        "next_scene_candidates": [
            {
                "scene_template_id": _truncate_text(item.get("scene_template_id"), 32),
                "scene_name": _truncate_text(item.get("scene_name"), 24),
                "score": round(float(item.get("score", 0.0) or 0.0), 2),
                "reason": _truncate_text(item.get("reason"), 56),
            }
            for item in (payload.get("next_scene_candidates") or [])[:3]
            if isinstance(item, dict) and (_text(item.get("scene_template_id")) or _text(item.get("scene_name")))
        ],
    }
    return {key: value for key, value in compact.items() if value not in (None, "", [], {})}



def _scene_handoff_status(*, plan: dict[str, Any], scene_execution_card: dict[str, Any], final_scene: dict[str, Any], unresolved: list[str], tail_excerpt: str) -> str:
    tail = _text(tail_excerpt)
    if _contains_any(tail, ["却在这时", "可就在这时", "忽然", "猛地", "未等", "还未", "正要", "门外", "脚步声"]):
        return "interrupted"
    if bool(scene_execution_card.get("must_continue_same_scene")) and unresolved:
        return "open"
    if len(unresolved) >= 2:
        return "open"
    if unresolved:
        return "soft_closed"
    final_scene_id = _text(final_scene.get("scene_template_id"))
    hook_style = _text(plan.get("hook_style"))
    if hook_style in {"危险逼近", "更大谜团", "反转下压", "余波扩散"} or final_scene_id in {"hanging_pressure", "suspicion_hook", "hooked_departure"}:
        return "soft_closed"
    return "closed"



def _scene_handoff_allowed_transition(scene_status: str, final_scene: dict[str, Any]) -> str:
    if scene_status in {"open", "interrupted"}:
        return "none"
    if scene_status == "soft_closed":
        return "soft_cut"
    final_scene_id = _text(final_scene.get("scene_template_id"))
    if final_scene_id in {"aftermath_review", "repair_recovery", "battle_aftermath"}:
        return "time_skip"
    return "soft_cut"



def _scene_handoff_candidates(*, templates: list[dict[str, Any]], plan: dict[str, Any], final_scene: dict[str, Any], scene_status: str) -> list[dict[str, Any]]:
    template_map = {
        _text(item.get("scene_id")): item
        for item in templates
        if isinstance(item, dict) and _text(item.get("scene_id"))
    }
    candidate_ids: list[tuple[str, str, float]] = []
    hook_style = _text(plan.get("hook_style"))
    event_type = _text(plan.get("event_type"))
    progress_kind = _text(plan.get("progress_kind"))
    payoff_mode = _text(plan.get("payoff_mode"))

    if scene_status in {"open", "interrupted"}:
        candidate_ids.append(("same_scene_continuation", "上一场还没收住，下一章先续接旧场景。", 1.0))
        if scene_status == "interrupted":
            candidate_ids.append(("tail_followup", "本章被外力打断，下一章适合立刻追查或反手处理。", 0.88))
        else:
            candidate_ids.append(("bridge_settlement", "先把旧场景的阶段结果压实，再决定是否换挡。", 0.84))
    else:
        if hook_style in {"危险逼近", "反转下压", "余波扩散"}:
            candidate_ids.append(("tail_followup", "章尾压力还在，下一章适合先处理尾随、追查或逼近风险。", 0.86))
        if hook_style == "更大谜团" or event_type in {"调查类", "探索类"}:
            candidate_ids.append(("clue_verification", "线索已经露头，下一章适合继续验证或追索。", 0.82))
        if payoff_mode in {"明确兑现", "低调增益"}:
            candidate_ids.append(("aftermath_review", "本章已有结果，下一章可先消化收益、判断代价和下一步。", 0.78))
        if progress_kind == "资源推进":
            candidate_ids.append(("resource_exchange", "资源线正在推进，下一章适合把条件、代价和兑现写实。", 0.75))
        if progress_kind == "关系推进":
            candidate_ids.append(("private_alignment", "关系线已经被拨动，下一章适合让人物站队或谈条件。", 0.74))

    final_scene_id = _text(final_scene.get("scene_template_id"))
    if final_scene_id == "travel_insert":
        candidate_ids.append(("travel_insert", "当前已进入地图切换或赶路段，下一章可顺着路上事件往下推。", 0.72))
    if final_scene_id == "small_payoff":
        candidate_ids.append(("public_showcase", "若成果开始外显，下一章适合让旁人看到变化并给出反应。", 0.68))

    seen: set[str] = set()
    payload: list[dict[str, Any]] = []
    for template_id, reason, score in candidate_ids:
        if template_id in seen:
            continue
        template = template_map.get(template_id)
        if not template:
            continue
        seen.add(template_id)
        payload.append(
            {
                "scene_template_id": template_id,
                "scene_name": _text(template.get("name")),
                "score": round(score, 2),
                "reason": reason,
            }
        )
        if len(payload) >= 3:
            break
    return payload



def build_scene_handoff_card(
    *,
    story_bible: dict[str, Any],
    plan: dict[str, Any],
    scene_runtime: dict[str, Any] | None,
    summary: Any,
    content: str,
    protagonist_name: str | None = None,
) -> dict[str, Any]:
    templates = ensure_scene_template_library(story_bible)
    runtime = scene_runtime or {}
    scene_sequence_plan = runtime.get("scene_sequence_plan") or []
    scene_execution_card = runtime.get("scene_execution_card") or {}
    final_scene = scene_sequence_plan[-1] if scene_sequence_plan and isinstance(scene_sequence_plan[-1], dict) else {}
    open_hooks = _safe_list(getattr(summary, "open_hooks", []) if summary is not None else [])
    new_clues = _safe_list(getattr(summary, "new_clues", []) if summary is not None else [])
    character_updates = getattr(summary, "character_updates", {}) if summary is not None else {}
    carry_over_people = [protagonist_name, plan.get("supporting_character_focus")]
    if isinstance(character_updates, dict):
        carry_over_people.extend(list(character_updates.keys())[:4])
    carry_over_people = [name for name in carry_over_people if _text(name) and _text(name) != "notes"]
    tail_excerpt = _truncate_text((content or "")[-180:], 180)
    scene_status = _scene_handoff_status(
        plan=plan,
        scene_execution_card=scene_execution_card if isinstance(scene_execution_card, dict) else {},
        final_scene=final_scene if isinstance(final_scene, dict) else {},
        unresolved=open_hooks,
        tail_excerpt=tail_excerpt,
    )
    allowed_transition = _scene_handoff_allowed_transition(scene_status, final_scene if isinstance(final_scene, dict) else {})
    must_continue_same_scene = scene_status in {"open", "interrupted"}
    carry_over_items = _dedupe_texts(
        _safe_list((final_scene if isinstance(final_scene, dict) else {}).get("must_carry_over")) + open_hooks + new_clues,
        limit=4,
        item_limit=56,
    )
    unfinished_actions = _dedupe_texts(open_hooks, limit=4, item_limit=64)
    next_opening_anchor = _truncate_text(
        tail_excerpt or _text((scene_execution_card or {}).get("opening_anchor")) or _text(plan.get("ending_hook") or plan.get("closing_image")),
        120,
    )
    forbidden_openings: list[str] = []
    if must_continue_same_scene:
        forbidden_openings.extend(["直接回家总结", "突然切到第二天日常", "无过渡换到无关新地点"])
    elif allowed_transition == "time_skip":
        forbidden_openings.append("不写时间锚点就直接跳到新一天")
    next_scene_candidates = _scene_handoff_candidates(
        templates=templates,
        plan=plan,
        final_scene=final_scene if isinstance(final_scene, dict) else {},
        scene_status=scene_status,
    )
    note_map = {
        "open": "本章最后一个场景还没收住，下一章第一场应先续接旧动作链。",
        "interrupted": "本章在外力打断中收尾，下一章应先处理打断后的直接后果。",
        "soft_closed": "本章主动作已有阶段结果，但余波和后果还要继续带着走。",
        "closed": "本章最后一个场景已阶段闭合，下一章可以带过渡自由换挡。",
    }
    return _compact_scene_handoff_card(
        {
            "scene_status_at_end": scene_status,
            "must_continue_same_scene": must_continue_same_scene,
            "allowed_transition": allowed_transition,
            "next_opening_anchor": next_opening_anchor,
            "final_scene_no": int((final_scene or {}).get("scene_no", len(scene_sequence_plan)) or len(scene_sequence_plan) or 1),
            "final_scene_template_id": _text((final_scene or {}).get("scene_template_id")),
            "final_scene_name": _text((final_scene or {}).get("scene_name")),
            "final_scene_role": _text((final_scene or {}).get("scene_role")),
            "carry_over_items": carry_over_items,
            "carry_over_people": _dedupe_texts(carry_over_people, limit=5, item_limit=20),
            "unfinished_actions": unfinished_actions,
            "forbidden_openings": forbidden_openings,
            "next_scene_candidates": next_scene_candidates,
            "handoff_note": note_map.get(scene_status, "下一章应先检查上一场是否真正收束。"),
        }
    )


def _match_score(text_blob: str, keywords: list[str]) -> float:
    text_blob = _text(text_blob).lower()
    if not text_blob or not keywords:
        return 0.0
    score = 0.0
    for key in keywords:
        token = _text(key).lower()
        if token and token in text_blob:
            score += 1.0
    return score



def _similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()



def _determine_scene_count(plan: dict[str, Any], *, must_continue_same_scene: bool) -> int:
    count = 1
    if _text(plan.get("mid_turn")):
        count += 1
    if _text(plan.get("closing_image") or plan.get("ending_hook")):
        count += 1
    if _text(plan.get("hook_style")) in {"危险逼近", "更大谜团", "反转下压", "余波扩散"}:
        count = max(count, 2)
    if must_continue_same_scene:
        count = max(count, 2)
    return min(max(count, 1), 3)



def _continuation_needed(plan: dict[str, Any], bridge: dict[str, Any]) -> bool:
    handoff = (bridge.get("scene_handoff_card") or {}) if isinstance(bridge.get("scene_handoff_card"), dict) else {}
    if bool(handoff.get("must_continue_same_scene")):
        return True
    if _text(handoff.get("scene_status_at_end")) in {"open", "interrupted"}:
        return True
    unresolved = _safe_list(bridge.get("unresolved_action_chain"))
    if len(unresolved) >= 2:
        return True
    last_scene = (bridge.get("last_scene_card") or {}) if isinstance(bridge.get("last_scene_card"), dict) else {}
    current_main_scene = _text(plan.get("main_scene"))
    previous_main_scene = _text(last_scene.get("main_scene"))
    if unresolved and current_main_scene and previous_main_scene and _similarity(current_main_scene, previous_main_scene) >= 0.38:
        return True
    opening_blob = " ".join([_text(plan.get("opening_beat")), _text(plan.get("goal")), _text(plan.get("conflict"))])
    if unresolved and _match_score(opening_blob, ["继续", "承接", "紧接", "追上", "收尾", "对峙", "跟上"]) >= 1:
        return True
    return False



def _build_continuation_scene(bridge: dict[str, Any]) -> dict[str, Any]:
    last_scene = (bridge.get("last_scene_card") or {}) if isinstance(bridge.get("last_scene_card"), dict) else {}
    handoff = (bridge.get("scene_handoff_card") or {}) if isinstance(bridge.get("scene_handoff_card"), dict) else {}
    unresolved = _safe_list(bridge.get("unresolved_action_chain"))[:3]
    carry_over = _safe_list(bridge.get("carry_over_clues"))[:3]
    handoff_items = _safe_list(handoff.get("carry_over_items"))[:3]
    purpose_bits = _safe_list(handoff.get("unfinished_actions"))[:2] or unresolved[:2] or [last_scene.get("chapter_hook") or "先把上一章吊着的动作链落地"]
    return {
        "scene_no": 1,
        "scene_template_id": "same_scene_continuation",
        "scene_name": "同场景续接场",
        "scene_role": "opening",
        "source": "continuity_bridge",
        "is_continuation": True,
        "purpose": _truncate_text("；".join([item for item in purpose_bits if item]), 84),
        "entry_mode": "紧接上一章最后动作或局势变化",
        "transition_in": _truncate_text(handoff.get("next_opening_anchor") or bridge.get("opening_anchor") or (last_scene.get("ending") or "顺着上一章收尾继续"), 84),
        "target_result": _truncate_text(last_scene.get("ending") or last_scene.get("chapter_hook") or "把旧场景的阶段结果写出来", 72),
        "must_carry_over": _dedupe_texts(unresolved + carry_over + handoff_items, limit=4, item_limit=56),
        "transition_rule": "先承接、再决策，不能一开头直接硬切到无关新场景。",
    }



def _score_scene_template(template: dict[str, Any], *, role: str, plan: dict[str, Any], bridge: dict[str, Any], selected_ids: set[str]) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    if _text(template.get("scene_role")) == role:
        score += 4.0
        reasons.append("role_match")
    elif role == "bridge" and _text(template.get("scene_role")) in {"main", "ending"}:
        score += 1.0
    if _text(template.get("scene_id")) in selected_ids:
        score -= 1.5
    event_type = _text(plan.get("event_type"))
    progress_kind = _text(plan.get("progress_kind"))
    payoff_mode = _text(plan.get("payoff_mode"))
    hook_style = _text(plan.get("hook_style"))
    scene_blob = " ".join(
        [
            _text(plan.get("main_scene")),
            _text(plan.get("goal")),
            _text(plan.get("conflict")),
            _text(plan.get("opening_beat")),
            _text(plan.get("mid_turn")),
            _text(plan.get("closing_image")),
            _text(plan.get("ending_hook")),
            " ".join(_safe_list(bridge.get("unresolved_action_chain"))),
            " ".join(_safe_list(bridge.get("carry_over_clues"))),
        ]
    )
    if event_type and event_type in _safe_list(template.get("compatible_event_types")):
        score += 3.0
        reasons.append("event_type")
    if progress_kind and progress_kind in _safe_list(template.get("compatible_progress_kinds")):
        score += 2.0
        reasons.append("progress_kind")
    if payoff_mode and payoff_mode in _safe_list(template.get("compatible_payoff_modes")):
        score += 2.0
        reasons.append("payoff_mode")
    keyword_hits = _match_score(scene_blob, _safe_list(template.get("best_for")))
    if keyword_hits:
        score += min(keyword_hits, 3.0)
        reasons.append("best_for")
    if role == "ending":
        if hook_style in {"危险逼近", "更大谜团", "反转下压", "余波扩散"} and _text(template.get("scene_id")) in {"hanging_pressure", "suspicion_hook", "hooked_departure"}:
            score += 2.5
            reasons.append("hook_style")
        if payoff_mode in {"明确兑现", "低调增益"} and _text(template.get("scene_id")) in {"aftermath_review", "small_payoff", "battle_aftermath"}:
            score += 1.5
    if role == "opening" and _text(template.get("scene_id")) == "bridge_settlement" and _safe_list(bridge.get("unresolved_action_chain")):
        score += 2.0
    return score, reasons



def _pick_best_scene_template(
    templates: list[dict[str, Any]],
    *,
    role: str,
    plan: dict[str, Any],
    bridge: dict[str, Any],
    selected_ids: set[str],
    fallback_id: str,
) -> dict[str, Any]:
    best: dict[str, Any] | None = None
    best_score = float("-inf")
    best_reasons: list[str] = []
    for template in templates:
        if not isinstance(template, dict):
            continue
        score, reasons = _score_scene_template(template, role=role, plan=plan, bridge=bridge, selected_ids=selected_ids)
        if score > best_score:
            best = template
            best_score = score
            best_reasons = reasons
    if best is None:
        for template in templates:
            if _text(template.get("scene_id")) == fallback_id:
                best = template
                break
    payload = deepcopy(best or {})
    if payload:
        payload["selection_score"] = round(best_score if best_score != float("-inf") else 0.0, 2)
        payload["selection_reasons"] = best_reasons
    return payload



def _instantiate_scene(template: dict[str, Any], *, scene_no: int, plan: dict[str, Any], bridge: dict[str, Any], role: str) -> dict[str, Any]:
    role_label = _text(template.get("scene_role")) or role
    purpose_source = {
        "opening": _text(plan.get("opening_beat") or plan.get("goal") or template.get("default_purpose")),
        "bridge": _text(plan.get("mid_turn") or plan.get("conflict") or template.get("default_purpose")),
        "ending": _text(plan.get("closing_image") or plan.get("ending_hook") or template.get("default_purpose")),
        "main": _text(plan.get("mid_turn") or plan.get("goal") or template.get("default_purpose")),
    }
    transition_source = {
        "opening": _text(bridge.get("opening_anchor") or plan.get("opening_beat") or plan.get("main_scene")),
        "bridge": _text(plan.get("mid_turn") or plan.get("conflict") or plan.get("main_scene")),
        "ending": _text(plan.get("closing_image") or plan.get("ending_hook") or plan.get("hook_style")),
        "main": _text(plan.get("mid_turn") or plan.get("goal")),
    }
    target_source = {
        "opening": _text(plan.get("goal") or plan.get("conflict") or template.get("default_purpose")),
        "bridge": _text(plan.get("mid_turn") or plan.get("conflict") or plan.get("payoff_or_pressure")),
        "ending": _text(plan.get("ending_hook") or plan.get("closing_image") or template.get("default_purpose")),
        "main": _text(plan.get("payoff_or_pressure") or plan.get("goal") or template.get("default_purpose")),
    }
    carry_over = []
    if scene_no == 1:
        carry_over.extend(_safe_list(bridge.get("unresolved_action_chain"))[:2])
        carry_over.extend(_safe_list(bridge.get("carry_over_clues"))[:2])
    return {
        "scene_no": scene_no,
        "scene_template_id": _text(template.get("scene_id")),
        "scene_name": _text(template.get("name")),
        "scene_role": role_label,
        "source": "scene_template_library",
        "is_continuation": False,
        "purpose": _truncate_text(purpose_source.get(role_label) or purpose_source.get(role) or template.get("default_purpose"), 84),
        "entry_mode": _truncate_text((_safe_list(template.get("entry_modes")) or ["自然切入当前动作"])[0], 40),
        "transition_in": _truncate_text(transition_source.get(role_label) or transition_source.get(role) or template.get("default_purpose"), 84),
        "target_result": _truncate_text(target_source.get(role_label) or target_source.get(role) or template.get("default_purpose"), 72),
        "must_carry_over": carry_over[:3],
        "transition_rule": _truncate_text(template.get("transition_rule"), 84),
    }





def build_scene_template_index(
    *,
    story_bible: dict[str, Any],
    plan: dict[str, Any],
    serialized_last: dict[str, Any] | None,
    recent_summaries: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    templates = ensure_scene_template_library(story_bible)
    bridge = ((serialized_last or {}).get("continuity_bridge") or {}) if isinstance((serialized_last or {}).get("continuity_bridge"), dict) else {}
    must_continue_same_scene = _continuation_needed(plan, bridge)
    scene_count = _determine_scene_count(plan, must_continue_same_scene=must_continue_same_scene)
    entries: list[dict[str, Any]] = []
    for template in templates:
        if not isinstance(template, dict):
            continue
        default_purpose = _truncate_text(template.get("default_purpose"), 72)
        transition_rule = _truncate_text(template.get("transition_rule"), 72)
        best_for = _safe_list(template.get("best_for"))[:4]
        entries.append(
            {
                "scene_template_id": _text(template.get("scene_id")),
                "type": "scene_template",
                "title": _text(template.get("name")),
                "name": _text(template.get("name")),
                "scene_role": _text(template.get("scene_role")),
                "summary": default_purpose,
                "chapter_use": "；".join(best_for[:2]) if best_for else default_purpose,
                "constraint": transition_rule,
                "priority_hint": "medium",
                "default_purpose": default_purpose,
                "best_for": best_for,
                "compatible_event_types": _safe_list(template.get("compatible_event_types"))[:4],
                "compatible_progress_kinds": _safe_list(template.get("compatible_progress_kinds"))[:4],
                "compatible_payoff_modes": _safe_list(template.get("compatible_payoff_modes"))[:4],
                "transition_rule": transition_rule,
            }
        )
    if must_continue_same_scene:
        continuation = _build_continuation_scene(bridge)
        continuation_purpose = _truncate_text(continuation.get("purpose"), 72)
        continuation_best_for = _safe_list(continuation.get("must_carry_over"))[:4]
        continuation_rule = _truncate_text(continuation.get("transition_rule"), 72)
        entries.insert(
            0,
            {
                "scene_template_id": _text(continuation.get("scene_template_id")),
                "type": "scene_template",
                "title": _text(continuation.get("scene_name")),
                "name": _text(continuation.get("scene_name")),
                "scene_role": "opening",
                "summary": continuation_purpose,
                "chapter_use": "；".join(continuation_best_for[:2]) if continuation_best_for else continuation_purpose,
                "constraint": continuation_rule,
                "priority_hint": "high",
                "default_purpose": continuation_purpose,
                "best_for": continuation_best_for,
                "compatible_event_types": [_text(plan.get("event_type"))] if _text(plan.get("event_type")) else [],
                "compatible_progress_kinds": [_text(plan.get("progress_kind"))] if _text(plan.get("progress_kind")) else [],
                "compatible_payoff_modes": [_text(plan.get("payoff_mode"))] if _text(plan.get("payoff_mode")) else [],
                "transition_rule": continuation_rule,
                "is_continuation": True,
            },
        )
    return {
        "scene_count": scene_count,
        "must_continue_same_scene": must_continue_same_scene,
        "bridge": {
            "opening_anchor": _truncate_text(bridge.get("opening_anchor"), 84),
            "unresolved_action_chain": _safe_list(bridge.get("unresolved_action_chain"))[:4],
            "carry_over_clues": _safe_list(bridge.get("carry_over_clues"))[:4],
            "scene_handoff": bridge.get("scene_handoff_card") or {},
        },
        "scene_templates": entries,
        "recent_scene_hints": [
            _truncate_text((_text(item.get("chapter_title")) + ": " + _text(item.get("event_summary"))), 84)
            for item in (recent_summaries or [])[-2:]
            if isinstance(item, dict)
        ],
    }


def realize_scene_sequence_from_selection(
    *,
    story_bible: dict[str, Any],
    plan: dict[str, Any],
    serialized_last: dict[str, Any] | None,
    recent_summaries: list[dict[str, Any]] | None,
    selected_scene_template_ids: list[str] | None,
) -> dict[str, Any]:
    templates = ensure_scene_template_library(story_bible)
    template_by_id = { _text(item.get("scene_id")): item for item in templates if isinstance(item, dict) and _text(item.get("scene_id")) }
    bridge = ((serialized_last or {}).get("continuity_bridge") or {}) if isinstance((serialized_last or {}).get("continuity_bridge"), dict) else {}
    must_continue_same_scene = _continuation_needed(plan, bridge)
    scene_count = _determine_scene_count(plan, must_continue_same_scene=must_continue_same_scene)
    normalized_ids = [str(item or "").strip() for item in (selected_scene_template_ids or []) if str(item or "").strip()]
    scenes: list[dict[str, Any]] = []
    roles = ["opening", "main", "ending"][:scene_count]
    for idx, role in enumerate(roles, start=1):
        template_id = normalized_ids[idx - 1] if idx - 1 < len(normalized_ids) else ""
        if idx == 1 and template_id == "same_scene_continuation":
            scenes.append(_build_continuation_scene(bridge))
            continue
        template = template_by_id.get(template_id or "")
        if template is None:
            fallback_id = "bridge_settlement" if role == "opening" else ("probe_negotiation" if role == "main" else "aftermath_review")
            template = next((item for item in templates if _text(item.get("scene_id")) == fallback_id), {})
        scenes.append(_instantiate_scene(template or {}, scene_no=idx, plan=plan, bridge=bridge, role=role))
    if must_continue_same_scene and scenes and scenes[0].get("scene_template_id") != "same_scene_continuation":
        scenes[0] = _build_continuation_scene(bridge)
    handoff = (bridge.get("scene_handoff_card") or {}) if isinstance(bridge.get("scene_handoff_card"), dict) else {}
    must_carry_over = []
    must_carry_over.extend(_safe_list(bridge.get("unresolved_action_chain"))[:2])
    must_carry_over.extend(_safe_list(bridge.get("carry_over_clues"))[:2])
    must_carry_over.extend(_safe_list(handoff.get("carry_over_items"))[:2])
    must_carry_over = _dedupe_texts(must_carry_over, limit=4, item_limit=56)
    transition_mode = "continue_same_scene" if must_continue_same_scene else ("soft_cut" if len(scenes) >= 2 else "single_scene")
    allowed_transition = "resolve_then_cut" if must_continue_same_scene else ("soft_cut_only" if len(scenes) >= 2 else "stay_in_scene")
    if _text(handoff.get("allowed_transition")) == "time_skip" and not must_continue_same_scene:
        allowed_transition = "time_skip_allowed"
    scene_execution_card = {
        "scene_count": len(scenes),
        "must_continue_same_scene": must_continue_same_scene,
        "transition_mode": transition_mode,
        "opening_anchor": _truncate_text(handoff.get("next_opening_anchor") or bridge.get("opening_anchor") or plan.get("opening_beat"), 120),
        "must_carry_over": must_carry_over,
        "first_scene_focus": _truncate_text((scenes[0].get("scene_name") if scenes else plan.get("main_scene")), 28),
        "allowed_transition": allowed_transition,
        "previous_scene_status": _truncate_text(handoff.get("scene_status_at_end"), 16),
        "sequence_note": _truncate_text(
            f"本章按 {len(scenes)} 段场景推进：" + " → ".join([_text(item.get('scene_name')) for item in scenes if _text(item.get('scene_name'))]),
            120,
        ),
    }
    return {
        "scene_sequence_plan": scenes,
        "scene_execution_card": scene_execution_card,
        "scene_templates_used": [
            {
                "scene_template_id": _text(item.get("scene_template_id")),
                "scene_name": _text(item.get("scene_name")),
                "scene_role": _text(item.get("scene_role")),
            }
            for item in scenes
        ],
        "recent_scene_hints": [
            _truncate_text((_text(item.get("chapter_title")) + ": " + _text(item.get("event_summary"))), 84)
            for item in (recent_summaries or [])[-2:]
            if isinstance(item, dict)
        ],
    }


def choose_scene_sequence_for_chapter(
    *,
    story_bible: dict[str, Any],
    plan: dict[str, Any],
    serialized_last: dict[str, Any] | None,
    recent_summaries: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    templates = ensure_scene_template_library(story_bible)
    bridge = ((serialized_last or {}).get("continuity_bridge") or {}) if isinstance((serialized_last or {}).get("continuity_bridge"), dict) else {}
    must_continue_same_scene = _continuation_needed(plan, bridge)
    scene_count = _determine_scene_count(plan, must_continue_same_scene=must_continue_same_scene)
    selected_ids: set[str] = set()
    scenes: list[dict[str, Any]] = []

    if must_continue_same_scene:
        first_scene = _build_continuation_scene(bridge)
        scenes.append(first_scene)
        selected_ids.add("same_scene_continuation")
    else:
        opening_template = _pick_best_scene_template(
            templates,
            role="opening",
            plan=plan,
            bridge=bridge,
            selected_ids=selected_ids,
            fallback_id="bridge_settlement",
        )
        scenes.append(_instantiate_scene(opening_template, scene_no=1, plan=plan, bridge=bridge, role="opening"))
        selected_ids.add(_text(opening_template.get("scene_id")))

    if scene_count >= 2:
        middle_template = _pick_best_scene_template(
            templates,
            role="main",
            plan=plan,
            bridge=bridge,
            selected_ids=selected_ids,
            fallback_id="probe_negotiation",
        )
        scenes.append(_instantiate_scene(middle_template, scene_no=len(scenes) + 1, plan=plan, bridge=bridge, role="main"))
        selected_ids.add(_text(middle_template.get("scene_id")))

    if scene_count >= 3:
        ending_template = _pick_best_scene_template(
            templates,
            role="ending",
            plan=plan,
            bridge=bridge,
            selected_ids=selected_ids,
            fallback_id="aftermath_review",
        )
        scenes.append(_instantiate_scene(ending_template, scene_no=len(scenes) + 1, plan=plan, bridge=bridge, role="ending"))
        selected_ids.add(_text(ending_template.get("scene_id")))

    if len(scenes) == 1:
        scenes[0]["scene_role"] = "main"
    elif len(scenes) == 2 and scenes[-1].get("scene_role") not in {"ending", "bridge"}:
        bridge_template = _pick_best_scene_template(
            templates,
            role="ending",
            plan=plan,
            bridge=bridge,
            selected_ids=selected_ids,
            fallback_id="aftermath_review",
        )
        scenes[-1] = _instantiate_scene(bridge_template, scene_no=2, plan=plan, bridge=bridge, role="ending")

    handoff = (bridge.get("scene_handoff_card") or {}) if isinstance(bridge.get("scene_handoff_card"), dict) else {}
    first_focus = _truncate_text((scenes[0].get("scene_name") if scenes else plan.get("main_scene")), 28)
    must_carry_over = []
    must_carry_over.extend(_safe_list(bridge.get("unresolved_action_chain"))[:2])
    must_carry_over.extend(_safe_list(bridge.get("carry_over_clues"))[:2])
    must_carry_over.extend(_safe_list(handoff.get("carry_over_items"))[:2])
    must_carry_over = _dedupe_texts(must_carry_over, limit=4, item_limit=56)

    transition_mode = "continue_same_scene" if must_continue_same_scene else ("multi_scene_chain" if len(scenes) >= 2 else "single_scene")
    if not must_continue_same_scene and len(scenes) >= 2:
        transition_mode = "soft_cut"
    allowed_transition = "resolve_then_cut" if must_continue_same_scene else ("soft_cut_only" if len(scenes) >= 2 else "stay_in_scene")
    if _text(handoff.get("allowed_transition")) == "time_skip" and not must_continue_same_scene:
        allowed_transition = "time_skip_allowed"
    scene_execution_card = {
        "scene_count": len(scenes),
        "must_continue_same_scene": must_continue_same_scene,
        "transition_mode": transition_mode,
        "opening_anchor": _truncate_text(handoff.get("next_opening_anchor") or bridge.get("opening_anchor") or plan.get("opening_beat"), 120),
        "must_carry_over": must_carry_over,
        "first_scene_focus": first_focus,
        "allowed_transition": allowed_transition,
        "previous_scene_status": _truncate_text(handoff.get("scene_status_at_end"), 16),
        "sequence_note": _truncate_text(
            f"本章按 {len(scenes)} 段场景推进：" + " → ".join([_text(item.get('scene_name')) for item in scenes if _text(item.get('scene_name'))]),
            120,
        ),
    }
    return {
        "scene_sequence_plan": scenes,
        "scene_execution_card": scene_execution_card,
        "scene_templates_used": [
            {
                "scene_template_id": _text(item.get("scene_template_id")),
                "scene_name": _text(item.get("scene_name")),
                "scene_role": _text(item.get("scene_role")),
            }
            for item in scenes
        ],
        "recent_scene_hints": [
            _truncate_text((_text(item.get("chapter_title")) + ": " + _text(item.get("event_summary"))), 84)
            for item in (recent_summaries or [])[-2:]
            if isinstance(item, dict)
        ],
    }
