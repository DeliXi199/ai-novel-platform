from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.services.generation_exceptions import ErrorCodes, GenerationError
from app.services.openai_story_engine import extend_chapter_text


@dataclass(slots=True)
class ChapterRepairAction:
    repair_type: str
    strategy_id: str
    execution_mode: str
    reason: str
    retry_plan: dict[str, Any] | None = None
    delay_ms: int = 0
    ending_issue: str | None = None
    repair_attempt_no: int = 1
    previous_modes: list[str] | None = None


@dataclass(slots=True)
class ChapterRepairResult:
    content: str
    strategy_id: str
    repair_type: str


TRANSITION_ENDING_STYLES = {"平稳过渡", "余味收束"}


def _split_paragraphs(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"\n+", (text or "").strip()) if item.strip()]


def _dedupe_prefix_overlap(base: str, addition: str, *, min_overlap: int = 8, max_overlap: int = 120) -> str:
    base_text = base or ""
    extra = addition or ""
    if not base_text or not extra:
        return extra
    limit = min(len(base_text), len(extra), max_overlap)
    for size in range(limit, min_overlap - 1, -1):
        if base_text[-size:] == extra[:size]:
            return extra[size:]
    return extra


def _merge_inline_tail(base: str, addition: str) -> str:
    base_text = (base or "").rstrip()
    extra = (addition or "").strip()
    if not extra:
        return base_text
    if not base_text:
        return extra
    if extra in base_text[-max(len(extra) + 24, 220):]:
        return base_text
    extra = _dedupe_prefix_overlap(base_text, extra).lstrip()
    if not extra:
        return base_text
    return f"{base_text}{extra}".strip()


def _replace_tail_paragraphs(base: str, replacement: str, *, paragraph_count: int) -> str:
    base_paragraphs = _split_paragraphs(base)
    replacement_paragraphs = _split_paragraphs(replacement)
    if not replacement_paragraphs:
        return (base or "").strip()
    keep = base_paragraphs[:-paragraph_count] if len(base_paragraphs) > paragraph_count else []
    merged = keep + replacement_paragraphs
    return "\n\n".join(merged).strip()


def _make_too_short_retry_plan(plan: dict[str, Any], *, visible_chars: int, target_min: int, target_max: int) -> dict[str, Any]:
    note = (plan.get("writing_note") or "").strip()
    retry_note = (
        f"上一篇草稿只有约 {visible_chars} 个可见字符，明显偏短。"
        f"这次必须补足到完整一章的体量，尽量写到 {target_min}-{target_max} 个可见中文字符左右。"
        "务必补出开场动作、一次中段受阻、一次具体发现和一个结尾收束，"
        "把人物试探、对话、动作因果和场景细节写完整，不要匆忙收尾。"
    )
    merged_note = f"{note}；{retry_note}" if note else retry_note
    retry_plan = dict(plan)
    retry_plan["writing_note"] = merged_note
    retry_plan["retry_prompt_mode"] = "compact"
    retry_plan["length_retry"] = {"reason": "too_short", "previous_visible_chars": visible_chars}
    return retry_plan


def _infer_stronger_hook_style(plan: dict[str, Any], ending_pattern: str) -> str:
    current = str(plan.get("hook_style") or "").strip()
    if current and current not in TRANSITION_ENDING_STYLES:
        return current
    hook_kind = str(plan.get("hook_kind") or "").strip()
    if any(token in hook_kind for token in ["新威胁", "暴露", "危险", "隐患"]):
        return "危险逼近"
    if any(token in hook_kind for token in ["新发现", "更大谜团", "异常"]):
        return "信息反转"
    if ending_pattern in {"soft_transition", "summary_wrap"}:
        return "人物选择"
    return "危险逼近"


def _make_weak_ending_retry_plan(plan: dict[str, Any], *, ending_pattern: str) -> dict[str, Any]:
    note = (plan.get("writing_note") or "").strip()
    payoff = str(plan.get("payoff_or_pressure") or "").strip()
    ending_hook = str(plan.get("ending_hook") or "").strip()
    closing_image = str(plan.get("closing_image") or ending_hook or "").strip()
    stronger_hook_style = _infer_stronger_hook_style(plan, ending_pattern)
    retry_note = (
        f"上一版草稿的最后一段收得太虚（ending_pattern={ending_pattern}）。"
        "这次不要再用‘先回去/之后再说/暂且按下/夜色渐深’这类平钩子收束。"
        f"章末必须落在具体变化上：{payoff or ending_hook or '人物做出选择，或风险真实压近'}。"
        "最后两段要形成‘动作或判断 -> 新变化/新压力 -> 章末落点’的链条，"
        "不要只做气氛收束或总结式收尾。"
    )
    merged_note = f"{note}；{retry_note}" if note else retry_note
    retry_plan = dict(plan)
    retry_plan["writing_note"] = merged_note
    retry_plan["retry_prompt_mode"] = "compact"
    retry_plan["hook_style"] = stronger_hook_style
    if closing_image:
        retry_plan["closing_image"] = f"{closing_image}；最后一段必须落在可见变化、危险逼近或人物选择上，不能虚收。"
    retry_plan["ending_retry"] = {
        "reason": "weak_ending",
        "ending_pattern": ending_pattern,
        "strategy": stronger_hook_style,
    }
    return retry_plan


def _make_scene_continuity_retry_plan(plan: dict[str, Any], *, details: dict[str, Any]) -> dict[str, Any]:
    note = (plan.get("writing_note") or "").strip()
    issue = str(details.get("scene_continuity_issue") or "scene_continuity").strip()
    opening_anchor = str(details.get("scene_opening_anchor") or "").strip()
    carry_over = [str(item).strip() for item in (details.get("scene_opening_overlap_tokens") or details.get("must_carry_over") or []) if str(item).strip()]
    transition_mode = str(details.get("scene_transition_mode") or "").strip()
    expected_transitions = int(details.get("scene_expected_transition_count") or 0)

    if issue == "abrupt_scene_cut":
        focus = "上一章场景还没收住，这次开头必须先续接原场景，不能直接跳到次日或新地点。"
    elif issue == "missing_opening_continuation":
        focus = "开头两段必须吃掉上一章的动作后果、悬着的问题或携带物，别把旧场景当没发生过。"
    elif issue == "time_skip_without_anchor":
        focus = "既然允许时间跳转，就要在前两段写明时间锚点和承接物，别偷偷切到新时段。"
    else:
        focus = "一章内多个场景切换时，必须把切场写成可见过渡，至少交代时间、地点或动作链的变化。"

    carry_text = f"必须带上这些承接点：{'、'.join(carry_over[:4])}。" if carry_over else ""
    anchor_text = f"开章优先承接：{opening_anchor}。" if opening_anchor else ""
    transition_text = ""
    if transition_mode:
        transition_text = f"本章当前场景模式是 {transition_mode}；"
    if expected_transitions > 0:
        transition_text += f"正文里至少写出 {expected_transitions} 次可见过渡或阶段换挡。"

    retry_note = (focus + anchor_text + carry_text + transition_text +
        "场景切换时要先给阶段结果，再切时间/地点/人物重心，不要像被传送。")
    merged_note = f"{note}；{retry_note}" if note else retry_note
    retry_plan = dict(plan)
    retry_plan["writing_note"] = merged_note
    retry_plan["retry_prompt_mode"] = "compact"
    retry_plan["retry_focus"] = "scene_continuity"
    retry_plan["scene_continuity_retry"] = {
        "reason": issue,
        "opening_anchor": opening_anchor,
        "must_carry_over": carry_over[:4],
        "transition_mode": transition_mode,
        "expected_transition_count": expected_transitions,
    }
    return retry_plan


def _make_too_messy_retry_plan(plan: dict[str, Any], details: dict[str, Any]) -> dict[str, Any]:
    note = (plan.get("writing_note") or "").strip()
    ai_review = details.get("ai_style_review") if isinstance(details.get("ai_style_review"), dict) else {}
    messy_metrics = details.get("messy_metrics") if isinstance(details.get("messy_metrics"), dict) else details
    repeated_sentence_ratio = float(messy_metrics.get("repeated_sentence_ratio") or 0)
    repeated_openings = messy_metrics.get("repeated_openings") or {}
    repeated_endings = messy_metrics.get("repeated_endings") or {}
    style_clues = messy_metrics.get("style_clue_hits") or {}

    problem_types = [str(item).strip() for item in (ai_review.get("problem_types") or []) if str(item).strip()]
    evidence = [str(item).strip() for item in (ai_review.get("evidence") or []) if str(item).strip()]
    must_change = [str(item).strip() for item in (ai_review.get("must_change") or []) if str(item).strip()]
    avoid = [str(item).strip() for item in (ai_review.get("avoid") or []) if str(item).strip()]
    repair_brief = str(ai_review.get("repair_brief") or "").strip()

    local_notes: list[str] = []
    if repeated_sentence_ratio > 0:
        local_notes.append(f"重复句比例偏高（repeated_sentence_ratio={repeated_sentence_ratio:.2f}）")
    if repeated_openings:
        local_notes.append(f"句子开头回环明显：{', '.join(list(repeated_openings)[:3])}")
    if repeated_endings:
        local_notes.append(f"句尾落点太像：{', '.join(list(repeated_endings)[:3])}")
    if style_clues:
        local_notes.append(f"安全表达偏密：{', '.join(list(style_clues)[:4])}")

    correction_parts: list[str] = []
    if problem_types:
        correction_parts.append(f"上一版草稿主要问题：{'、'.join(problem_types[:4])}。")
    if evidence:
        correction_parts.append(f"编辑判断：{'；'.join(evidence[:3])}。")
    if repair_brief:
        correction_parts.append(repair_brief)
    correction_parts.extend(local_notes[:3])
    if must_change:
        correction_parts.append(f"这次必须改：{'；'.join(must_change[:3])}。")
    if avoid:
        correction_parts.append(f"这次不要再写成：{'；'.join(avoid[:3])}。")
    if not correction_parts:
        correction_parts.append("上一版草稿句式回环太重。这次必须换句子开合、换动作链、换收句方式，不要重复上一版的判断句模板。")

    correction_parts.append(
        "重写时要拉开句子起手、动作推进和收句方式：别连续几句都用同一类判断句或同一类氛围句；"
        "把抽象感受改成更具体的动作、触感、物件、阻力和即时判断。"
    )

    retry_note = "".join(correction_parts)
    merged_note = f"{note}；{retry_note}" if note else retry_note
    retry_plan = dict(plan)
    retry_plan["writing_note"] = merged_note
    retry_plan["retry_prompt_mode"] = "compact"
    retry_plan["retry_focus"] = "style_cleanup"
    retry_plan["retry_feedback"] = {
        "problem": "上一版草稿写法和结构重复偏多",
        "problem_types": problem_types,
        "evidence": evidence,
        "must_change": must_change or local_notes,
        "avoid": avoid,
        "repair_brief": repair_brief or "换句式、换动作链、换收句方式，别再让同一种判断句连着撞车。",
    }
    return retry_plan


def _count_repair_attempts(repair_trace: list[dict[str, Any]] | None, *, repair_type: str, attempt_no: int | None = None) -> tuple[int, list[str]]:
    count = 0
    modes: list[str] = []
    for item in repair_trace or []:
        if item.get("repair_type") != repair_type:
            continue
        if attempt_no is not None and int(item.get("attempt_no") or -1) != int(attempt_no):
            continue
        count += 1
        mode = str(item.get("strategy_id") or "").strip()
        if mode:
            modes.append(mode)
    return count, modes


def _latest_repair_entry(repair_trace: list[dict[str, Any]] | None, *, attempt_no: int | None = None) -> dict[str, Any] | None:
    for item in reversed(repair_trace or []):
        if attempt_no is not None and int(item.get("attempt_no") or -1) != int(attempt_no):
            continue
        return item
    return None


def _build_incomplete_ending_action(*, ending_issue: str, prior_repairs: int, previous_modes: list[str]) -> ChapterRepairAction:
    if prior_repairs <= 0:
        return ChapterRepairAction(
            repair_type="ending_incomplete",
            strategy_id="ai_append_inline_tail",
            execution_mode="append_inline_tail",
            reason=f"顺着残句补齐尾部并自然收束（问题：{ending_issue}）",
            delay_ms=max(int(getattr(settings, "chapter_tail_fix_delay_ms", 0) or 0), 0),
            ending_issue=ending_issue,
            repair_attempt_no=1,
            previous_modes=previous_modes,
        )
    if prior_repairs == 1:
        return ChapterRepairAction(
            repair_type="ending_incomplete",
            strategy_id="ai_rewrite_last_paragraph",
            execution_mode="replace_last_paragraph",
            reason=f"上一轮补尾仍未闭合，改为重写最后一段并对齐本章收束点（问题：{ending_issue}）",
            delay_ms=max(int(getattr(settings, "chapter_tail_fix_delay_ms", 0) or 0), 0),
            ending_issue=ending_issue,
            repair_attempt_no=2,
            previous_modes=previous_modes,
        )
    return ChapterRepairAction(
        repair_type="ending_incomplete",
        strategy_id="ai_rewrite_last_two_paragraphs",
        execution_mode="replace_last_two_paragraphs",
        reason=f"尾部多次修复仍失败，重写最后两段并保留前文事实（问题：{ending_issue}）",
        delay_ms=max(int(getattr(settings, "chapter_tail_fix_delay_ms", 0) or 0), 0),
        ending_issue=ending_issue,
        repair_attempt_no=prior_repairs + 1,
        previous_modes=previous_modes,
    )


def classify_chapter_repair(
    exc: GenerationError,
    *,
    attempt_plan: dict[str, Any],
    targets: dict[str, int | str],
    repair_trace: list[dict[str, Any]] | None = None,
    attempt_no: int | None = None,
) -> ChapterRepairAction | None:
    details = exc.details if isinstance(exc.details, dict) else {}

    if exc.code == ErrorCodes.CHAPTER_ENDING_INCOMPLETE:
        ending_issue = str(details.get("ending_issue") or "").strip() or "incomplete_ending"
        prior_repairs, previous_modes = _count_repair_attempts(
            repair_trace,
            repair_type="ending_incomplete",
            attempt_no=attempt_no,
        )
        return _build_incomplete_ending_action(
            ending_issue=ending_issue,
            prior_repairs=prior_repairs,
            previous_modes=previous_modes,
        )

    if exc.code == ErrorCodes.CHAPTER_TOO_MESSY:
        latest_entry = _latest_repair_entry(repair_trace, attempt_no=attempt_no)
        if latest_entry and latest_entry.get("repair_type") == "ending_incomplete":
            prior_repairs, previous_modes = _count_repair_attempts(
                repair_trace,
                repair_type="ending_incomplete",
                attempt_no=attempt_no,
            )
            return _build_incomplete_ending_action(
                ending_issue=str(details.get("ending_issue") or "style_overuse_after_tail_fix"),
                prior_repairs=prior_repairs,
                previous_modes=previous_modes,
            )
        return ChapterRepairAction(
            repair_type="too_messy",
            strategy_id="regenerate_style_rewritten_draft",
            execution_mode="insert_retry_attempt",
            reason="上一版草稿写法重复偏重，重生一版真正换句式和动作链的正文",
            retry_plan=_make_too_messy_retry_plan(attempt_plan, details),
            delay_ms=max(int(getattr(settings, "chapter_too_messy_retry_delay_ms", 0) or 0), 0),
        )

    if exc.code == ErrorCodes.CHAPTER_TOO_SHORT:
        visible_chars = int(details.get("visible_chars") or 0)
        return ChapterRepairAction(
            repair_type="too_short",
            strategy_id="regenerate_expanded_draft",
            execution_mode="insert_retry_attempt",
            reason="篇幅偏短，重生更完整版本",
            retry_plan=_make_too_short_retry_plan(
                attempt_plan,
                visible_chars=visible_chars,
                target_min=int(targets["target_visible_chars_min"]),
                target_max=int(targets["target_visible_chars_max"]),
            ),
            delay_ms=max(int(getattr(settings, "chapter_too_short_retry_delay_ms", 0) or 0), 0),
        )

    if exc.code == ErrorCodes.CHAPTER_PROGRESS_TOO_WEAK and details.get("scene_continuity_issue"):
        issue = str(details.get("scene_continuity_issue") or "scene_continuity").strip()
        return ChapterRepairAction(
            repair_type="scene_continuity",
            strategy_id="regenerate_scene_continuity_fixed_draft",
            execution_mode="insert_retry_attempt",
            reason=f"场景承接或切场过渡不稳，重生一版把场景链接实（问题：{issue}）",
            retry_plan=_make_scene_continuity_retry_plan(attempt_plan, details=details),
            delay_ms=max(int(getattr(settings, "chapter_scene_continuity_retry_delay_ms", 0) or 0), 0),
        )

    if exc.code == ErrorCodes.CHAPTER_PROGRESS_TOO_WEAK and details.get("ending_pattern"):
        ending_pattern = str(details.get("ending_pattern") or "").strip() or "weak_ending"
        return ChapterRepairAction(
            repair_type="weak_ending",
            strategy_id="regenerate_stronger_ending",
            execution_mode="insert_retry_attempt",
            reason=f"最后一段太虚，重生更有落点的收尾（模式：{ending_pattern}）",
            retry_plan=_make_weak_ending_retry_plan(attempt_plan, ending_pattern=ending_pattern),
            delay_ms=max(int(getattr(settings, "chapter_weak_ending_retry_delay_ms", 0) or 0), 0),
        )

    return None


def execute_llm_repair(
    action: ChapterRepairAction,
    *,
    title: str,
    content: str,
    plan: dict[str, Any],
    targets: dict[str, int | str],
    request_timeout_seconds: int | None,
) -> ChapterRepairResult | None:
    if action.execution_mode not in {"append_inline_tail", "replace_last_paragraph", "replace_last_two_paragraphs"}:
        return None

    addition = extend_chapter_text(
        chapter_plan=plan,
        existing_content=content,
        reason=action.reason,
        target_visible_chars_min=int(targets["target_visible_chars_min"]),
        target_visible_chars_max=int(targets["target_visible_chars_max"]),
        repair_mode=action.execution_mode,
        ending_issue=action.ending_issue,
        repair_attempt_no=action.repair_attempt_no,
        previous_repair_modes=action.previous_modes or [],
        request_timeout_seconds=request_timeout_seconds,
    )
    if action.execution_mode == "append_inline_tail":
        merged = _merge_inline_tail(content, addition)
    elif action.execution_mode == "replace_last_paragraph":
        merged = _replace_tail_paragraphs(content, addition, paragraph_count=1)
    else:
        merged = _replace_tail_paragraphs(content, addition, paragraph_count=2)
    if merged == (content or "").strip():
        return None
    return ChapterRepairResult(content=merged, strategy_id=action.strategy_id, repair_type=action.repair_type)
