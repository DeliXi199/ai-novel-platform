from app.services import prompt_templates as pt


def test_prompt_template_facade_reexports_domain_prompts() -> None:
    assert callable(pt.global_outline_system_prompt)
    assert callable(pt.chapter_card_selector_system_prompt)
    assert callable(pt.chapter_body_draft_system_prompt)
    assert callable(pt.summary_title_package_system_prompt)


def test_prompt_template_facade_reexports_internal_helpers_used_by_tests() -> None:
    assert callable(pt._planning_payoff_compensation_prompt_payload)
    assert callable(pt._chapter_body_plan_packet_summary)
    assert callable(pt._chapter_body_plan_summary)
