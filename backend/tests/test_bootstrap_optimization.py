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


def test_run_bootstrap_pipeline_uses_combined_story_engine_bundle(monkeypatch) -> None:
    payload = _payload()
    calls = {"combined": 0, "title": 0}

    def _combined(*_args, **_kwargs):
        calls["combined"] += 1
        return (
            {
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
            {
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
        )

    monkeypatch.setattr("app.services.novel_lifecycle.generate_story_engine_strategy_bundle", _combined)
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
        return "问仙纪：陈砚的故事"

    monkeypatch.setattr("app.services.novel_lifecycle.generate_title", _title)

    db = TestingSessionLocal()
    try:
        novel = create_bootstrap_placeholder_novel(payload)
        db.add(novel)
        db.commit()
        db.refresh(novel)

        result = run_bootstrap_pipeline(db, novel=novel, payload=payload)
        assert result.status == "planning_ready"
        assert calls["combined"] == 1
        assert calls["title"] == 1
        assert result.story_bible["story_engine_diagnosis"]["primary_story_engine"] == "低位求生 + 资源争取"
        assert result.story_bible["story_strategy_card"]["chapter_1_to_10"]["stage_mission"] == "先抓住读者"
    finally:
        db.close()
