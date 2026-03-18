import pytest

from app.services.chapter_quality import build_quality_feedback, validate_chapter_content
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


WORD_REPETITION_BUT_NOT_STRUCTURAL_MESS_TEXT = """
方尘先按住石面，又侧耳去听墙外的风声，确认那点温差是不是错位的风口。
石下果然透出一缕微弱凉意，但他没有急着拆开，而是先把碎屑扫到一边，又抬手摸了一遍边缘，免得留下明显痕迹。
他又换了个角度按下去，这次仍只有微弱触感顺着指腹滑过，像是底下另有夹层，逼得他把短刀翻出来慢慢试探。
等院外脚步声逼近，他立刻抬刀沿着裂缝慢慢撬开，终于看见一张被潮气浸得发皱的油纸角。
他刚把油纸抽出来，墙外便响起一声短促的咳嗽，让他立刻意识到这里未必只有自己发现了这道暗缝，也知道今晚不能再按原路退走。
""".strip()


def test_validate_chapter_content_does_not_reject_single_word_repetition_alone() -> None:
    validate_chapter_content(
        title="第10章",
        content=WORD_REPETITION_BUT_NOT_STRUCTURAL_MESS_TEXT,
        min_visible_chars=80,
        hard_min_visible_chars=60,
        target_visible_chars_max=420,
        hook_style="信息反转",
        chapter_plan={"progress_kind": "信息推进", "event_type": "发现类"},
        recent_plan_meta=[{"event_type": "试探类"}, {"event_type": "资源获取类"}],
    )


STRUCTURALLY_MESSY_TEXT = """
他没有立刻，而是先看着桌上的旧铜牌，像是非要把上面的裂痕看清。
他没有立刻，而是先看着掌心的旧铜牌，像是非要把上面的裂痕看清。
他没有立刻，而是先看着袖里的旧铜牌，像是非要把上面的裂痕看清。
他没有立刻，而是先看着柜角的旧铜牌，像是非要把上面的裂痕看清。
他没有立刻，而是先看着案边的旧铜牌，像是非要把上面的裂痕看清。
""".strip()


def test_validate_chapter_content_rejects_structural_repetition_as_too_messy(monkeypatch) -> None:
    monkeypatch.setattr("app.services.chapter_quality._messy_ai_review", lambda *args, **kwargs: None)
    with pytest.raises(GenerationError) as exc_info:
        validate_chapter_content(
            title="第11章",
            content=STRUCTURALLY_MESSY_TEXT,
            min_visible_chars=20,
            hard_min_visible_chars=20,
            target_visible_chars_max=320,
            hook_style="信息反转",
        )
    assert exc_info.value.code == ErrorCodes.CHAPTER_TOO_MESSY
    assert "messy_metrics" in (exc_info.value.details or {})


CONTINUATION_BROKEN_TEXT = """
次日清晨，方尘已经回到住处，把药包摊在桌上慢慢拆开。
他先把窗纸掀开一角，又把铜钱压在纸边，免得晨风把那层药屑吹散。
等他比对完药渣颜色，才意识到自己昨夜根本没来得及处理门外那个人，可眼前这堆东西又逼得他不得不停下来继续验。
他翻出短刀刮下一层药粉，指腹刚一碰到那股涩意，心里便更加确定掌柜背后还有另一条线。
可他还没来得及细想，院外便忽然响起一声极轻的咳嗽，让这间安静住处也骤然生出被人盯上的意味。
""".strip()


def test_validate_chapter_content_rejects_abrupt_scene_cut_when_previous_scene_must_continue() -> None:
    with pytest.raises(GenerationError) as exc_info:
        validate_chapter_content(
            title="第12章",
            content=CONTINUATION_BROKEN_TEXT,
            min_visible_chars=80,
            hard_min_visible_chars=60,
            target_visible_chars_max=420,
            hook_style="危险逼近",
            chapter_plan={"progress_kind": "信息推进", "event_type": "调查类"},
            serialized_last={
                "continuity_bridge": {
                    "opening_anchor": "门外的脚步声停在门槛前，掌柜的手还压着那包药渣。",
                    "unresolved_action_chain": ["门外盯梢者还没处理", "药渣来源尚未验证"],
                    "carry_over_clues": ["异常药包"],
                    "scene_handoff_card": {"scene_status_at_end": "open", "must_continue_same_scene": True},
                }
            },
            execution_brief={
                "scene_execution_card": {"must_continue_same_scene": True, "scene_count": 2, "transition_mode": "continue_same_scene"},
                "scene_sequence_plan": [{"scene_no": 1, "scene_name": "同场景续接场"}, {"scene_no": 2, "scene_name": "压力悬停场"}],
            },
        )
    assert exc_info.value.code == ErrorCodes.CHAPTER_PROGRESS_TOO_WEAK
    assert (exc_info.value.details or {}).get("scene_continuity_issue") == "abrupt_scene_cut"


TIME_SKIP_WITHOUT_ANCHOR_TEXT = """
方尘推门进屋后先把袖里的药包压在桌上，又把沾湿的外衣随手搭到椅背。
他拆开油纸，一层层比对药渣和旧账册上的记号，试着把昨夜听来的只言片语重新拼到一起。
等他终于确认账册上的缺口和药包来路相扣，才意识到这条线已经从药铺一路延到了西巷背后的旧仓。
他顺手把账册塞回怀里，盘算要不要立刻去旧仓看一眼，却又被窗外忽然掠过的黑影逼得先按住冲动。
那影子只停了一息便消失在墙头，让他明白自己今晚未必还能按原来的路数慢慢查下去。
""".strip()


def test_validate_chapter_content_rejects_time_skip_without_time_anchor() -> None:
    with pytest.raises(GenerationError) as exc_info:
        validate_chapter_content(
            title="第13章",
            content=TIME_SKIP_WITHOUT_ANCHOR_TEXT,
            min_visible_chars=80,
            hard_min_visible_chars=60,
            target_visible_chars_max=420,
            hook_style="危险逼近",
            chapter_plan={"progress_kind": "信息推进", "event_type": "调查类"},
            serialized_last={
                "continuity_bridge": {
                    "carry_over_clues": ["异常药包"],
                    "scene_handoff_card": {
                        "scene_status_at_end": "closed",
                        "must_continue_same_scene": False,
                        "allowed_transition": "time_skip",
                        "next_opening_anchor": "次日清晨，桌上的药包还带着昨夜的潮气。",
                    },
                }
            },
            execution_brief={
                "scene_execution_card": {"must_continue_same_scene": False, "scene_count": 2, "transition_mode": "soft_cut", "allowed_transition": "time_skip_allowed"},
                "scene_sequence_plan": [{"scene_no": 1, "scene_name": "修整复盘场"}, {"scene_no": 2, "scene_name": "疑点悬停场"}],
            },
        )
    assert exc_info.value.code == ErrorCodes.CHAPTER_PROGRESS_TOO_WEAK
    assert (exc_info.value.details or {}).get("scene_continuity_issue") == "time_skip_without_anchor"


def test_build_quality_feedback_reports_scene_continuity_issue() -> None:
    exc = GenerationError(
        code=ErrorCodes.CHAPTER_PROGRESS_TOO_WEAK,
        message="上一章场景还没收住，这一章却在开头直接跳时段/跳场，承接断了。",
        stage="chapter_quality",
        retryable=True,
        http_status=422,
        details={
            "title": "第14章",
            "scene_continuity_issue": "abrupt_scene_cut",
            "scene_transition_mode": "continue_same_scene",
            "scene_count": 2,
        },
    )
    feedback = build_quality_feedback(exc)
    assert "场景承接/切换不稳" in feedback["failed_checks"]
    assert any("先续接原场景" in item for item in feedback["suggestions"])
