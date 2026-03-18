from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.config import BACKEND_DIR
from app.services.ai_capability_policy import build_llm_policy_report


_RISK_MARKERS: dict[str, list[tuple[str, str]]] = {
    "app/services/story_blueprint_builders.py": [
        ("_fallback_story_engine_profile", "创建阶段仍保留本地 story_engine_diagnosis 兜底。"),
        ("_fallback_first_30_engine", "创建阶段仍保留本地 story_strategy_card 兜底。"),
    ],
    "app/services/chapter_title_service.py": [
        ('"source": "local_fallback"', "标题精修仍会补充本地 fallback 候选。"),
    ],
    "app/services/constraint_reasoning.py": [
        ("【本地回退结果】", "约束推理 prompt 里仍显式携带本地回退结果。"),
    ],
}



def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default



def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value or 0)
    except Exception:
        return default



def _bool(value: Any) -> bool:
    return bool(value)



def _find_preparation_packet(story_bible: dict[str, Any]) -> dict[str, Any]:
    workspace = (story_bible or {}).get("story_workspace") or {}
    for key in ["current_execution_packet", "next_chapter_preview_packet", "last_completed_execution_packet"]:
        packet = workspace.get(key)
        if isinstance(packet, dict) and packet:
            return packet
    return {}



def build_story_bible_ai_audit(story_bible: dict[str, Any] | None) -> dict[str, Any]:
    policy = build_llm_policy_report()
    payload = story_bible or {}
    warnings: list[str] = []
    notices: list[str] = []

    workflow_mode = (payload.get("workflow_mode") or {}) if isinstance(payload, dict) else {}
    quality_guardrails = (payload.get("quality_guardrails") or {}) if isinstance(payload, dict) else {}
    diagnosis = (payload.get("story_engine_diagnosis") or {}) if isinstance(payload, dict) else {}
    strategy = (payload.get("story_strategy_card") or {}) if isinstance(payload, dict) else {}

    if not _bool(quality_guardrails.get("forbid_silent_fallback")):
        warnings.append("quality_guardrails.forbid_silent_fallback 未明确开启。")
    if not _bool(workflow_mode.get("strict_manual_pipeline")):
        warnings.append("workflow_mode.strict_manual_pipeline 未开启，当前系统不够严格。")
    if not isinstance(diagnosis, dict) or not diagnosis:
        warnings.append("story_engine_diagnosis 缺失，创建阶段 AI 画像未写入。")
    if not isinstance(strategy, dict) or not strategy:
        warnings.append("story_strategy_card 缺失，创建阶段 AI 策略卡未写入。")

    packet = _find_preparation_packet(payload)
    selection_runtime = (packet.get("selection_runtime") or {}) if isinstance(packet, dict) else {}
    preparation_selection = (packet.get("preparation_selection") or {}) if isinstance(packet, dict) else {}
    diagnostics = {}
    if isinstance(preparation_selection.get("diagnostics"), dict):
        diagnostics = preparation_selection.get("diagnostics") or {}
    elif isinstance(selection_runtime.get("diagnostics"), dict):
        diagnostics = selection_runtime.get("diagnostics") or {}

    if packet:
        selection_mode = _text(selection_runtime.get("selection_mode"))
        if selection_mode != "ai_multistage_compressed_selection":
            warnings.append(f"章节准备 selection_mode 不是 ai_multistage_compressed_selection，而是 {selection_mode or '空值'}。")
        assembly_rule = _text(selection_runtime.get("assembly_rule"))
        if "失败即停止" not in assembly_rule:
            warnings.append("章节准备 assembly_rule 未明确写出‘失败即停止’。")
        if not diagnostics:
            warnings.append("检测到章节准备包，但没有 preparation diagnostics。")
        else:
            llm_calls = _int(((diagnostics.get("pipeline_totals") or {}).get("llm_calls")))
            if llm_calls <= 0:
                warnings.append("章节准备 diagnostics 存在，但未记录到 LLM 调用次数。")
            notices.append(f"章节准备阶段累计 LLM 调用 {llm_calls} 次。")
    else:
        notices.append("当前没有可审计的章节准备包，通常意味着还没进入准备/生成阶段。")

    story_bible_checks = {
        "forbid_silent_fallback": _bool(quality_guardrails.get("forbid_silent_fallback")),
        "strict_manual_pipeline": _bool(workflow_mode.get("strict_manual_pipeline")),
        "has_story_engine_diagnosis": bool(diagnosis),
        "has_story_strategy_card": bool(strategy),
    }
    preparation_checks = {
        "has_packet": bool(packet),
        "selection_mode": _text(selection_runtime.get("selection_mode")),
        "parallel_enabled": _bool(selection_runtime.get("parallel_enabled")),
        "has_diagnostics": bool(diagnostics),
        "preparation_llm_calls": _int(((diagnostics.get("pipeline_totals") or {}).get("llm_calls"))),
    }
    required_flags_missing = [
        label
        for label, ok in {
            "forbid_silent_fallback": story_bible_checks["forbid_silent_fallback"],
            "strict_manual_pipeline": story_bible_checks["strict_manual_pipeline"],
            "story_engine_diagnosis": story_bible_checks["has_story_engine_diagnosis"],
            "story_strategy_card": story_bible_checks["has_story_strategy_card"],
        }.items()
        if not ok
    ]
    summary_lines = [
        f"核心规则：{_text((policy.get('summary') or {}).get('core_rule'))}",
        (
            "运行态审计："
            + ("发现风险项。" if warnings else "当前未发现明显策略漂移。")
        ),
        (
            "关键状态："
            f"forbid_silent_fallback={story_bible_checks['forbid_silent_fallback']}，"
            f"strict_manual_pipeline={story_bible_checks['strict_manual_pipeline']}。"
        ),
    ]
    return {
        "policy_version": policy.get("policy_version"),
        "status": "warning" if warnings else "ok",
        "runtime_policy_ok": not warnings,
        "warning_count": len(warnings),
        "notice_count": len(notices),
        "warnings": warnings,
        "notices": notices,
        "required_flags_missing": required_flags_missing,
        "summary_lines": summary_lines,
        "story_bible_checks": story_bible_checks,
        "preparation_checks": preparation_checks,
    }



def build_repo_ai_fallback_audit(base_dir: str | Path | None = None) -> dict[str, Any]:
    root = Path(base_dir or BACKEND_DIR).resolve()
    findings: list[dict[str, Any]] = []
    missing_files: list[str] = []
    for relative_path, markers in _RISK_MARKERS.items():
        path = root / relative_path
        if not path.exists():
            missing_files.append(relative_path)
            continue
        text = path.read_text(encoding="utf-8")
        for marker, description in markers:
            if marker in text:
                findings.append(
                    {
                        "path": relative_path,
                        "marker": marker,
                        "description": description,
                    }
                )
    summary_lines = [
        "静态审计会扫描关键服务文件里仍可能代表‘旧式本地兜底’的标记。",
        ("当前仍发现需要复核的 fallback 痕迹。" if findings else "当前扫描范围内未发现高风险 fallback 标记。"),
        f"已扫描 {len(_RISK_MARKERS)} 个关键文件，命中 {len(findings)} 项。",
    ]
    return {
        "status": "warning" if findings or missing_files else "ok",
        "scanned_files": len(_RISK_MARKERS),
        "finding_count": len(findings),
        "missing_file_count": len(missing_files),
        "findings": findings,
        "missing_files": missing_files,
        "summary_lines": summary_lines,
    }
