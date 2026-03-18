from pathlib import Path

from app.services.ai_capability_audit import build_repo_ai_fallback_audit, build_story_bible_ai_audit


def test_story_bible_ai_audit_ok_with_preparation_diagnostics() -> None:
    story_bible = {
        "workflow_mode": {"strict_manual_pipeline": True},
        "quality_guardrails": {"forbid_silent_fallback": True},
        "story_engine_diagnosis": {"primary_story_engine": "资源争夺"},
        "story_strategy_card": {"story_promise": "前30章要持续推进"},
        "story_workspace": {
            "current_execution_packet": {
                "selection_runtime": {
                    "selection_mode": "ai_multistage_compressed_selection",
                    "parallel_enabled": True,
                    "assembly_rule": "本地只负责压缩、合法性校验与拼装；所有主筛选与统一仲裁均由 AI 完成，失败即停止生成。",
                },
                "preparation_selection": {
                    "diagnostics": {
                        "pipeline_totals": {"llm_calls": 6},
                    }
                },
            }
        },
    }
    payload = build_story_bible_ai_audit(story_bible)
    assert payload["status"] == "ok"
    assert payload["warning_count"] == 0
    assert payload["preparation_checks"]["preparation_llm_calls"] == 6


def test_story_bible_ai_audit_warns_on_missing_strict_flags() -> None:
    payload = build_story_bible_ai_audit({
        "workflow_mode": {"strict_manual_pipeline": False},
        "quality_guardrails": {"forbid_silent_fallback": False},
        "story_workspace": {
            "current_execution_packet": {
                "selection_runtime": {"selection_mode": "legacy_local"},
            }
        },
    })
    assert payload["status"] == "warning"
    assert payload["warning_count"] >= 4
    assert any("forbid_silent_fallback" in item for item in payload["warnings"])
    assert payload["preparation_checks"]["selection_mode"] == "legacy_local"


def test_repo_ai_fallback_audit_can_scan_custom_base_dir(tmp_path: Path) -> None:
    services = tmp_path / "app" / "services"
    services.mkdir(parents=True)
    (services / "story_blueprint_builders.py").write_text("_fallback_story_engine_profile\n", encoding="utf-8")
    (services / "chapter_title_service.py").write_text('"source": "local_fallback"\n', encoding="utf-8")
    (services / "constraint_reasoning.py").write_text("safe\n", encoding="utf-8")

    payload = build_repo_ai_fallback_audit(base_dir=tmp_path)
    assert payload["status"] == "warning"
    assert payload["finding_count"] == 2
    assert payload["missing_file_count"] == 0
