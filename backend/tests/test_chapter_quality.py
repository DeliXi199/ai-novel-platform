import pytest

from app.services.chapter_quality import build_quality_feedback, repair_incomplete_ending, validate_chapter_content
from app.services.generation_exceptions import ErrorCodes, GenerationError


GOOD_TEXT = """
林玄推开药铺后门时，先用指节轻轻敲了两下木框，确认无人应声，才侧身钻进雨后的潮气里。
院角那口旧缸沿着裂痕往下渗水，他蹲下去摸了一把，指腹立刻觉出一丝不该有的温差，像是缸底另藏着什么东西。
他没有立刻动手，而是先把门栓重新卡紧，又把案上的药包换了个位置，免得掌柜回来后一眼看出院里有人翻找过。
等脚步声彻底远了，他才把缸挪开半寸，果然在青砖缝里摸到一张被油纸裹住的薄页；纸面发硬，边角却残留着新近折开的痕迹。
他刚把薄页抽出来，外头巷口便传来短促的犬吠，紧跟着又是一阵压得很低的说话声，让他立刻意识到这东西未必只是旧物那么简单。
""".strip()


BAD_DUPLICATE = """
林玄蹲在墙角摸索砖缝时，先抬手按住呼吸，再把袖口往里一卷，免得灰末沾到掌心的湿汗。
林玄蹲在墙角摸索砖缝时，先抬手按住呼吸，再把袖口往里一卷，免得灰末沾到掌心的湿汗。
他听见门外木板被风吹得轻轻一响，却没有立刻退开，只是顺着缝隙继续往里摸，想确认那点异样到底是什么。
他听见门外木板被风吹得轻轻一响，却没有立刻退开，只是顺着缝隙继续往里摸，想确认那点异样到底是什么。
""".strip()


def test_validate_chapter_content_accepts_complete_text() -> None:
    validate_chapter_content(
        title="第1章",
        content=GOOD_TEXT,
        min_visible_chars=80,
        hard_min_visible_chars=60,
        target_visible_chars_max=400,
        hook_style="危险逼近",
    )


def test_validate_chapter_content_rejects_duplicate_paragraphs() -> None:
    with pytest.raises(GenerationError) as exc_info:
        validate_chapter_content(
            title="第2章",
            content=BAD_DUPLICATE,
            min_visible_chars=20,
            hard_min_visible_chars=20,
            target_visible_chars_max=300,
            hook_style="危险逼近",
        )
    assert exc_info.value.code == ErrorCodes.CHAPTER_DUPLICATED_PARAGRAPHS


WEAK_PASSIVE_TEXT = """
方尘站在门边，没有动，也没有开口，只是听着屋外的风声。
他没有立刻做什么，只觉得事情没有那么简单。
过了一会儿，他还是没有动，只把这个念头压了下去。
夜色沉沉，这件事暂时告一段落。
""".strip()


def test_validate_chapter_content_rejects_passive_and_weak_hook() -> None:
    with pytest.raises(GenerationError) as exc_info:
        validate_chapter_content(
            title="第3章",
            content=WEAK_PASSIVE_TEXT,
            min_visible_chars=20,
            hard_min_visible_chars=20,
            target_visible_chars_max=300,
            hook_style="危险逼近",
            chapter_plan={"proactive_move": "主动试探他人", "progress_kind": "信息推进", "event_type": "试探类"},
            recent_plan_meta=[{"event_type": "发现类"}, {"event_type": "资源获取类"}],
        )
    assert exc_info.value.code == ErrorCodes.CHAPTER_PROGRESS_TOO_WEAK


def test_validate_chapter_content_rejects_third_same_event_type() -> None:
    with pytest.raises(GenerationError) as exc_info:
        validate_chapter_content(
            title="第4章",
            content=GOOD_TEXT,
            min_visible_chars=80,
            hard_min_visible_chars=60,
            target_visible_chars_max=400,
            hook_style="危险逼近",
            chapter_plan={"proactive_move": "主动试探他人", "progress_kind": "信息推进", "event_type": "试探类"},
            recent_plan_meta=[{"event_type": "试探类"}, {"event_type": "试探类"}],
        )
    assert exc_info.value.code == ErrorCodes.CHAPTER_PROGRESS_TOO_WEAK


ACTIVE_WITHOUT_EXPLICIT_PROACTIVE_WORD = """
方尘贴着门框停了一息，先把药包塞进袖里，又故意把桌角的铜钱拨落两枚。
屋里那人果然偏头去看，他便顺势抢前半步，笑着替对方捡起铜钱，嘴上却像闲聊似的问起昨夜谁来过后院。
对方神色一变，答得含糊，他没有松口，反而借着递钱的动作按住对方手背，逼得那人把袖中的木牌露出半角。
方尘心里立刻有了数，面上却只把铜钱拍回桌上，转身时已经记清木牌缺口的形状，知道自己终于摸到了这条线真正的入口。
""".strip()


def test_validate_chapter_content_accepts_active_chain_without_literal_zhudong_word() -> None:
    validate_chapter_content(
        title="第5章",
        content=ACTIVE_WITHOUT_EXPLICIT_PROACTIVE_WORD,
        min_visible_chars=80,
        hard_min_visible_chars=60,
        target_visible_chars_max=400,
        hook_style="信息反转",
        chapter_plan={"proactive_move": "主动递话设问并交换条件", "progress_kind": "信息推进", "event_type": "关系推进类"},
        recent_plan_meta=[{"event_type": "发现类"}, {"event_type": "资源获取类"}],
    )


STRATEGIC_ACTIVE_TEXT = """
方尘进门时先把袖里的木牌露出半角，又像是不经意地把茶盏推偏了一寸。
对面那人果然下意识去看木牌，他便顺势笑了笑，装作只是在问路，话里却故意把昨夜的时辰说错半刻。
那人立即纠正，语气压得很低，偏偏把自己去过后院的事也一并带了出来。
方尘没有追着逼问，只借着添茶的动作把桌上的灰痕一抹，心里立刻对上了先前那串脚印的方向，知道自己埋下的钩子终于钓到了真正的鱼。
""".strip()


def test_validate_chapter_content_accepts_strategic_setup_agency_mode() -> None:
    validate_chapter_content(
        title="第6章",
        content=STRATEGIC_ACTIVE_TEXT,
        min_visible_chars=80,
        hard_min_visible_chars=60,
        target_visible_chars_max=400,
        hook_style="信息反转",
        chapter_plan={
            "proactive_move": "主动埋下条件并诱导对方先露破绽",
            "progress_kind": "信息推进",
            "event_type": "反制类",
            "agency_mode": "strategic_setup",
            "agency_mode_label": "谋划设局型",
        },
        recent_plan_meta=[{"event_type": "发现类"}, {"event_type": "资源获取类"}],
    )

RISK_UPGRADE_WITH_RESULT_TEXT = """
方尘把旧账册往柜台上一推，却没有立刻多说，只抬眼看着那掌柜指尖的细小停顿。
对方嘴上还在敷衍，目光却已经往他袖口那枚旧铜牌上滑了一下，像是终于把人和某段旧事对上了。
方尘顺势把铜牌收回袖里，笑着改口说只是来问个价，可那掌柜反而压低声音，提醒他这几日最好别再从西巷走。
他走出门时才真正明白，旧债并没有烂在账本里，而是让认得那块铜牌的人起了疑心；原本还能当作寻常路过的西巷，如今只剩一条更绕、更窄的退路。
""".strip()


def test_validate_chapter_content_accepts_risk_upgrade_with_state_change_result() -> None:
    validate_chapter_content(
        title="第7章",
        content=RISK_UPGRADE_WITH_RESULT_TEXT,
        min_visible_chars=80,
        hard_min_visible_chars=60,
        target_visible_chars_max=420,
        hook_style="危险逼近",
        chapter_plan={
            "proactive_move": "主动递出旧账册试探对方反应",
            "progress_kind": "风险升级",
            "payoff_or_pressure": "有人因旧铜牌认出主角，西巷这条退路也变得不再安全",
            "ending_hook": "主角不得不改道，意味着旧债线已经开始顺藤摸瓜",
            "event_type": "试探类",
        },
        recent_plan_meta=[{"event_type": "发现类"}, {"event_type": "资源获取类"}],
    )



UNCLEAR_RESULT_BUT_STRUCTURALLY_OK_TEXT = """
方尘贴着后门停了一息，先抬手按住门框，又侧耳去听院里的水声。
他慢慢推开一道缝，借着墙角的暗影往里走了两步，鞋底轻轻擦过潮湿的砖面，竟听见缸后传来一记很轻的碰响。
他没有回头，只把案上的空碗挪开半寸，再俯身去摸那道裂缝；指尖碰到冷水时，他便察觉那里的温度和别处不太一样，却还说不上缘由。
等风从廊下穿过去，他才直起身，把门重新带上，心里把院中的几处异样默默排了一遍，准备下一次换个时辰再来试。
""".strip()


def test_validate_chapter_content_accepts_unclear_result_when_other_checks_pass() -> None:
    validate_chapter_content(
        title="第8章",
        content=UNCLEAR_RESULT_BUT_STRUCTURALLY_OK_TEXT,
        min_visible_chars=80,
        hard_min_visible_chars=60,
        target_visible_chars_max=420,
        hook_style="危险逼近",
        chapter_plan={"progress_kind": "实力推进", "event_type": "试探类"},
        recent_plan_meta=[{"event_type": "发现类"}, {"event_type": "资源获取类"}],
    )


def test_build_quality_feedback_no_longer_reports_unclear_progress_result() -> None:
    exc = GenerationError(
        code=ErrorCodes.CHAPTER_PROGRESS_TOO_WEAK,
        message="本章虽然成文，但事件推进不足，像片段或铺垫残段，不适合直接入库。",
        stage="chapter_quality",
        retryable=True,
        http_status=422,
        details={
            "title": "第9章",
            "paragraphs": 3,
            "action_hits": 2,
            "discovery_hits": 0,
            "hook_hits": 0,
            "progress_kind": "实力推进",
            "progress_score": 0,
            "progress_plan_cues": ["结果", "风险"],
        },
    )
    feedback = build_quality_feedback(exc)
    assert "事件推进不足" in feedback["failed_checks"]
    assert "推进结果不清晰" not in feedback["failed_checks"]
    assert all("结果线索" not in item for item in feedback["suggestions"])


TRUNCATED_ENDING_TEXT = """
林玄把那枚灰种压在掌心里，先没有急着继续催动，只把另一块灵石贴到指腹边缘。
灵石中那点淡薄灵气随即被牵出一缕，顺着经络往胸口探去。
灰种立刻有了反应。
他当即停住动作，把灵石按回袖里，生怕再慢半拍，掌心那点余温都会被一并抽走。
这一下虽短，却已经足够让他确认，灰种果然会吞掉外来的灵气。
抽吸感骤然加剧，灵石里的灵气被强行
""".strip()


def test_repair_incomplete_ending_trims_truncated_tail_to_last_complete_sentence() -> None:
    repaired = repair_incomplete_ending(TRUNCATED_ENDING_TEXT, ending_issue="missing_terminal_punctuation")
    assert repaired is not None
    assert repaired.endswith("。")
    assert "被强行" not in repaired
    assert repaired.splitlines()[-1] == "这一下虽短，却已经足够让他确认，灰种果然会吞掉外来的灵气。"


def test_repair_incomplete_ending_appends_terminal_punctuation_when_only_missing_period() -> None:
    text = "林玄把木匣重新收入袖中，心里已经记下那道细微裂痕"
    repaired = repair_incomplete_ending(text, ending_issue="missing_terminal_punctuation")
    assert repaired == text + "。"
