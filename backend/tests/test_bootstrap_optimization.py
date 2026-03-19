from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.schemas.novel import NovelCreate
from app.services import llm_runtime
from app.services.novel_lifecycle import create_bootstrap_placeholder_novel, run_bootstrap_pipeline


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def _payload() -> NovelCreate:
    return NovelCreate(
        genre="凡人流修仙",
        premise="主角在边镇矿场夹缝求生。",
        protagonist_name="陈砚",
        style_preferences={"tone": "克制", "story_engine": "先立足再破局"},
    )


def test_story_engine_strategy_stage_counts_as_bootstrap() -> None:
    assert llm_runtime.is_bootstrap_stage("story_engine_strategy_generation") is True
    assert llm_runtime.is_bootstrap_stage("story_engine_diagnosis") is True
    assert llm_runtime.is_bootstrap_stage("story_strategy_generation") is True
    assert llm_runtime.is_bootstrap_stage("bootstrap_intent_parse") is True
    assert llm_runtime.is_bootstrap_stage("bootstrap_story_review") is True
    assert llm_runtime.is_bootstrap_stage("bootstrap_execution_profile_generation") is True
    assert llm_runtime.is_bootstrap_stage("title_generation") is True


def test_run_bootstrap_pipeline_uses_ai_first_bootstrap_design(monkeypatch) -> None:
    payload = _payload()
    calls = {"design": 0, "title": 0, "review": 0}

    def _design(*_args, **_kwargs):
        calls["design"] += 1
        return {
            "intent_packet": {
                "story_promise": "凡人求生里不断拿到可感收益",
                "protagonist_core_drive": "先活下来再抢主动权",
                "core_conflict": "立足与暴露的拉扯",
                "expected_payoffs": ["有效收益", "局势升级"],
                "pacing_mode": "稳推",
                "world_reveal_mode": "局部先行",
                "first_ten_chapter_tasks": ["建立处境", "钉牢主线入口"],
                "major_risks": ["重复盘问"],
            },
            "strategy_candidates": {
                "candidates": [
                    {"candidate_id": "A", "design_focus": "更偏资源求生"},
                    {"candidate_id": "B", "design_focus": "更偏异常暗线"},
                ]
            },
            "strategy_arbitration": {
                "selected_candidate_id": "A",
                "selection_reason": "更适合长篇连载",
                "merge_notes": ["吸收暗线候选的悬念布局"],
            },
            "story_engine_diagnosis": {
                "story_subgenres": ["凡人苟道修仙", "资源求生流"],
                "primary_story_engine": "低位求生 + 资源争取",
                "secondary_story_engine": "异常线索慢兑现",
                "opening_drive": "先立足再试探。",
                "early_hook_focus": "现实压力 + 第一轮有效收益",
                "protagonist_action_logic": "先判断再出手",
                "pacing_profile": "稳中有推进",
                "world_reveal_strategy": "先局部后整体",
                "power_growth_strategy": "成长绑定代价",
                "early_must_haves": ["现实压力", "有效收益"],
                "avoid_tropes": ["固定药铺残页组合"],
                "differentiation_focus": ["前10章写出边镇夹缝求生味"],
                "must_establish_relationships": ["长期牵引关系"],
                "tone_keywords": ["克制", "具体"],
            },
            "story_strategy_card": {
                "story_promise": "有辨识度的凡人求生推进",
                "strategic_premise": "围绕资源和风险升级",
                "main_conflict_axis": "立足与暴露的拉扯",
                "first_30_mainline_summary": "前30章围绕立足、关系绑定和阶段破局",
                "chapter_1_to_10": {
                    "range": "1-10",
                    "stage_mission": "先抓住读者",
                    "reader_hook": "第一轮有效收益",
                    "frequent_elements": ["现实压力", "具体结果"],
                    "limited_elements": ["重复盘问"],
                    "relationship_tasks": ["建立关键关系"],
                    "phase_result": "拿到立足资本",
                },
                "chapter_11_to_20": {
                    "range": "11-20",
                    "stage_mission": "扩大地图和压力",
                    "reader_hook": "更高位风险",
                    "frequent_elements": ["关系变化", "资源争夺"],
                    "limited_elements": ["原地试探"],
                    "relationship_tasks": ["关键关系变化"],
                    "phase_result": "失去安全区但有新空间",
                },
                "chapter_21_to_30": {
                    "range": "21-30",
                    "stage_mission": "阶段高潮",
                    "reader_hook": "更大局势打开",
                    "frequent_elements": ["阶段破局", "主动布局"],
                    "limited_elements": ["只靠气氛拖章"],
                    "relationship_tasks": ["关系进入不可逆状态"],
                    "phase_result": "进入新层级",
                },
                "frequent_event_types": ["资源获取类", "关系推进类"],
                "limited_event_types": ["连续被怀疑后被动应付"],
                "must_establish_relationships": ["核心绑定角色"],
                "escalation_path": ["处境压力", "局部破局"],
                "anti_homogenization_rules": ["不要围着单一物件打转"],
            },
            "project_intent_card": {
                "story_promise": "凡人求生里不断拿到可感收益",
                "protagonist_core_drive": "先活下来再抢主动权",
            },
            "template_pool_profile": {
                "pool_id": "cultivation_default_pool_v1",
                "all_templates_active": True,
            },
            "book_execution_profile": {
                "positioning_summary": "以低位求生和资源争取为主轴使用整套修仙模板池。",
                "flow_family_priority": {"high": ["成长", "冲突"], "medium": ["探查"], "low": ["铺垫"]},
                "payoff_priority": {"high": ["捡漏反压"], "medium": ["身份露边"], "low": ["公开打脸"]},
                "rhythm_bias": {"opening_pace": "稳推", "world_reveal_density": "中低", "relationship_weight": "中", "hook_strength": "中强", "payoff_interval": "中短", "pressure_curve": "渐压"},
            },
        }

    monkeypatch.setattr("app.services.novel_lifecycle.generate_bootstrap_design_packet", _design)
    monkeypatch.setattr(
        "app.services.novel_lifecycle.generate_global_story_outline",
        lambda *_args, **_kwargs: {
            "acts": [{"act_no": 1, "title": "入局", "purpose": "建立处境", "target_chapter_end": 12, "summary": "卷入更大局势"}]
        },
    )
    monkeypatch.setattr(
        "app.services.novel_lifecycle.generate_arc_outline_bundle",
        lambda *_args, **_kwargs: {
            "arc_no": 1,
            "start_chapter": 1,
            "end_chapter": 7,
            "focus": "起势",
            "bridge_note": "承上启下",
            "chapters": [{"chapter_no": 1, "title": "开局", "goal": "立足", "ending_hook": "风险浮出"}],
        },
    )

    def _title(*_args, **_kwargs):
        calls["title"] += 1
        return "矿火问道"

    monkeypatch.setattr("app.services.novel_lifecycle.generate_title", _title)

    class _Review:
        def model_dump(self, mode="python"):
            return {
                "status": "repair",
                "summary": "首章目标可以更硬一点。",
                "strengths": ["主线清楚"],
                "risks": ["首章抓力略弱"],
                "must_fix": ["强化首章回报"],
                "arc_adjustments": [
                    {"chapter_no": 1, "field": "goal", "value": "先拿到立足资本", "reason": "开局抓力更强"},
                    {"chapter_no": 1, "field": "payoff_or_pressure", "value": "首章必须先给一次可感收益", "reason": "回报更明确"},
                ],
            }

    def _review(*_args, **_kwargs):
        calls["review"] += 1
        return _Review()

    monkeypatch.setattr("app.services.novel_lifecycle.review_bootstrap_story_package", _review)

    db = TestingSessionLocal()
    try:
        novel = create_bootstrap_placeholder_novel(payload)
        db.add(novel)
        db.commit()
        db.refresh(novel)

        result = run_bootstrap_pipeline(db, novel=novel, payload=payload)
        assert result.status == "planning_ready"
        assert calls["design"] == 1
        assert calls["title"] == 1
        assert calls["review"] == 1
        assert result.story_bible["story_engine_diagnosis"]["primary_story_engine"] == "低位求生 + 资源争取"
        assert result.story_bible["story_strategy_card"]["chapter_1_to_10"]["stage_mission"] == "先抓住读者"
        assert result.story_bible["bootstrap_intent_packet"]["protagonist_core_drive"] == "先活下来再抢主动权"
        assert result.story_bible["project_intent_card"]["protagonist_core_drive"] == "先活下来再抢主动权"
        assert result.story_bible["template_pool_profile"]["pool_id"] == "cultivation_default_pool_v1"
        assert "positioning_summary" in result.story_bible["book_execution_profile"]
        assert result.story_bible["bootstrap_review"]["status"] == "repair"
        assert result.story_bible["active_arc"]["chapters"][0]["goal"] == "先拿到立足资本"
        assert result.story_bible["active_arc"]["chapters"][0]["payoff_or_pressure"] == "首章必须先给一次可感收益"
        assert result.title == "矿火问道"
    finally:
        db.close()
