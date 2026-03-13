from __future__ import annotations

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


@dataclass(slots=True)
class ChapterRepairResult:
    content: str
    strategy_id: str
    repair_type: str


TRANSITION_ENDING_STYLES = {"平稳过渡", "余味收束"}


def _append_extension(base: str, addition: str) -> str:
    base_text = (base or "").rstrip()
    extra = (addition or "").strip()
    if not extra:
        return base_text
    if not base_text:
        return extra
    if extra in base_text[-max(len(extra) + 20, 200):]:
        return base_text
    separator = "\n\n" if not base_text.endswith("\n") else "\n"
    return f"{base_text}{separator}{extra}".strip()


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


def classify_chapter_repair(
    exc: GenerationError,
    *,
    attempt_plan: dict[str, Any],
    targets: dict[str, int | str],
) -> ChapterRepairAction | None:
    details = exc.details if isinstance(exc.details, dict) else {}

    if exc.code == ErrorCodes.CHAPTER_ENDING_INCOMPLETE:
        ending_issue = str(details.get("ending_issue") or "").strip() or "incomplete_ending"
        return ChapterRepairAction(
            repair_type="ending_incomplete",
            strategy_id="llm_append_tail",
            execution_mode="append_extension",
            reason=f"补齐截断结尾并自然收束（问题：{ending_issue}）",
            delay_ms=max(int(getattr(settings, "chapter_tail_fix_delay_ms", 0) or 0), 0),
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
    if action.execution_mode != "append_extension":
        return None

    addition = extend_chapter_text(
        chapter_plan=plan,
        existing_content=content,
        reason=action.reason,
        target_visible_chars_min=int(targets["target_visible_chars_min"]),
        target_visible_chars_max=int(targets["target_visible_chars_max"]),
        request_timeout_seconds=request_timeout_seconds,
    )
    merged = _append_extension(content, addition)
    if merged == content:
        return None
    return ChapterRepairResult(content=merged, strategy_id=action.strategy_id, repair_type=action.repair_type)
