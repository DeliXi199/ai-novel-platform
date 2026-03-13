from app.services.chapter_quality import validate_chapter_content
from app.services.generation_exceptions import GenerationError, ErrorCodes
from app.services.prompt_templates import chapter_extension_user_prompt


def _valid_base_text() -> str:
    return (
        "天色擦黑时，李墨带着方尘回到旧井旁。\n\n"
        "他先把地图摊在石面上，对照水痕和风向重新辨了一遍路。\n\n"
        "方尘低声报出两处异常脚印，李墨当场改了原先的绕行打算。\n\n"
        "两人沿着塌墙后的窄路摸过去，在墙根下翻出一截刚折断的木签。\n\n"
        "李墨把木签收进袖中，只说先回去再拆，夜风已经把井口边的草吹得一阵阵伏低。"
    )


def test_agency_quality_check_removed() -> None:
    content = _valid_base_text()
    plan = {
        "title": "任务指派",
        "proactive_move": "主动设问试探并当场验证异常",
        "agency_mode": "transactional_push",
        "agency_mode_label": "交易改规型",
    }
    try:
        validate_chapter_content(
            title="任务指派",
            content=content,
            chapter_plan=plan,
            min_visible_chars=120,
            target_visible_chars_max=5000,
            hard_min_visible_chars=100,
        )
    except GenerationError as exc:
        # 允许被别的质量关卡拦住，但不应再出现“主角主动性不足”的单独拦截。
        assert exc.code in {ErrorCodes.CHAPTER_PROGRESS_TOO_WEAK, ErrorCodes.CHAPTER_TOO_MESSY, ErrorCodes.CHAPTER_ENDING_INCOMPLETE}
        assert "主动性不足" not in str(exc.message)
        details = exc.details or {}
        assert "proactive_hits" not in details
        assert "agency_fit_hits" not in details
        assert "passive_drift_hits" not in details
    else:
        assert True


def test_incomplete_ending_still_rejected() -> None:
    try:
        validate_chapter_content(
            title="任务指派",
            content='李墨停在岔路口，回头说：“分两组。我和方尘走右边，你们俩走左边。一个时辰后，回这里汇合。',
            chapter_plan={"title": "任务指派"},
            min_visible_chars=20,
            target_visible_chars_max=5000,
            hard_min_visible_chars=10,
        )
    except GenerationError as exc:
        assert exc.code == ErrorCodes.CHAPTER_ENDING_INCOMPLETE
        assert exc.details["ending_issue"] in {"unclosed_quote", "missing_terminal_punctuation"}
    else:
        raise AssertionError("expected incomplete ending rejection")


def test_extension_prompt_is_tail_only() -> None:
    prompt = chapter_extension_user_prompt(
        chapter_plan={"title": "任务指派", "hook_style": "soft_transition"},
        existing_content='李墨停在岔路口，回头说：“分两组。',
        reason="补齐截断结尾并自然收束（问题：unclosed_quote）",
        target_visible_chars_min=1800,
        target_visible_chars_max=2600,
    )
    assert "只做“补尾”" in prompt
    assert "先把这一半句补完整" in prompt
    assert "若已有正文已经接近完整，只需补 80-220 字" in prompt
