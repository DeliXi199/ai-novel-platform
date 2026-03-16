from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.schemas.novel import NovelCreate
from app.services.resource_card_support import build_resource_card, normalize_resource_refs
from app.services.core_cast_support import build_core_cast_state
from app.services.story_character_support import _safe_list, _text


def _slugify(value: str, *, fallback: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in value.strip())
    cleaned = "_".join(part for part in cleaned.split("_") if part)
    return cleaned or fallback



def _sell_line(payload: NovelCreate) -> str:
    style = payload.style_preferences or {}
    sell_point = _text(style.get("sell_point"))
    if sell_point:
        return sell_point
    premise = _text(payload.premise)
    protagonist = _text(payload.protagonist_name, "主角")
    if "修" in premise or "仙" in payload.genre:
        return f"{protagonist}在‘{premise}’中低调求生、稳扎稳打，靠有限手段一步步撬开更大的修真局。"
    return f"{protagonist}围绕‘{premise}’展开持续升级的连载故事。"



def _one_line_intro(payload: NovelCreate, title: str) -> str:
    style = payload.style_preferences or {}
    if style.get("one_line_intro"):
        return _text(style.get("one_line_intro"))
    return f"《{title}》讲的是{payload.protagonist_name}在‘{payload.premise}’之中一边求生、一边逼近真相的故事。"



def _golden_finger(payload: NovelCreate) -> str:
    style = payload.style_preferences or {}
    return _text(style.get("golden_finger"), "尚未明示的异常线索 / 核心机缘，需要通过试探逐步兑现。")



def _fallback_story_engine_profile(payload: NovelCreate) -> dict[str, Any]:
    story_text = f"{payload.genre} {payload.premise} {_text((payload.style_preferences or {}).get('story_engine'))}".lower()
    if any(token in story_text for token in ["宗门", "学院", "试炼", "大比"]):
        subgenres = ["宗门成长流", "竞争升级流"]
        primary = "身份成长 + 同辈竞争 + 阶段胜负"
        secondary = "师承与站队变化"
    elif any(token in story_text for token in ["金手指", "机缘", "外挂", "神器"]):
        subgenres = ["机缘兑现流", "升级反馈流"]
        primary = "机缘试错 + 能力兑现 + 代价上升"
        secondary = "异常线索慢展开"
    elif any(token in story_text for token in ["黑暗", "诡异", "污染", "禁忌"]):
        subgenres = ["黑暗修仙", "诡异修仙"]
        primary = "认知风险 + 代价成长 + 真相逼近"
        secondary = "规则扭曲下的求生"
    else:
        subgenres = ["凡人苟道修仙", "资源求生流"]
        primary = "低位求生 + 资源争取 + 谨慎试探"
        secondary = "异常线索慢兑现"
    return {
        "story_subgenres": subgenres,
        "primary_story_engine": primary,
        "secondary_story_engine": secondary,
        "opening_drive": _text((payload.style_preferences or {}).get("opening_goal"), "前期先钉牢处境、目标、代价与可持续推进入口。"),
        "early_hook_focus": "前10章要给出题材辨识度、现实压力和第一轮有效收益。",
        "protagonist_action_logic": _text((payload.style_preferences or {}).get("temperament"), "先判断，再行动，关键时必须主动做决定。"),
        "pacing_profile": _text((payload.style_preferences or {}).get("opening_pace"), "稳中有推进，章章有结果。"),
        "world_reveal_strategy": "先讲主角眼下用得上的局部规则，再逐步抬到更高层势力与地图。",
        "power_growth_strategy": "成长必须绑定资源、代价、风险和后果，不走纯数值冲级。",
        "early_must_haves": ["明确现实压力", "第一轮有效收益", "可持续主线入口"],
        "avoid_tropes": ["固定药铺/坊市/残页组合", "连续多章只围着同一线索试探", "重复被怀疑后被动应付"],
        "differentiation_focus": ["把题材真正的独特卖点写进前10章的推进方式"],
        "must_establish_relationships": ["核心绑定角色", "长期压迫源", "阶段合作对象"],
        "tone_keywords": ["克制", "具体", "有代价"],
    }


def _fallback_first_30_engine(payload: NovelCreate) -> dict[str, Any]:
    protagonist = _text(payload.protagonist_name, "主角")
    return {
        "story_promise": f"前30章要让读者明确感到：{protagonist}不是在重复试探，而是在一步步换取更大的行动空间。",
        "strategic_premise": f"围绕‘{payload.premise}’，让{protagonist}在现实压力、关系绑定和阶段破局中持续向上。",
        "main_conflict_axis": "立足需求与暴露风险的长期拉扯。",
        "first_30_mainline_summary": _text((payload.style_preferences or {}).get("first_30_chapter_mainline"), "前30章围绕立足、试错、关系绑定与阶段破局推进，不让同一桥段垄断。"),
        "chapter_1_to_10": {
            "range": "1-10",
            "stage_mission": "先用题材最有辨识度的推进方式抓住读者。",
            "reader_hook": "给出第一轮具体收益、代价和继续追更的理由。",
            "frequent_elements": ["现实压力", "主动试探", "具体结果"],
            "limited_elements": ["重复盘问", "连续隐藏同一秘密"],
            "relationship_tasks": ["建立一条会长期变化的关键关系"],
            "phase_result": "主角拿到第一阶段立足资本。",
        },
        "chapter_11_to_20": {
            "range": "11-20",
            "stage_mission": "扩大地图、对手和关系压力。",
            "reader_hook": "阶段收益之后出现更高位风险或更大诱惑。",
            "frequent_elements": ["关系变化", "资源争夺", "局势升级"],
            "limited_elements": ["原地踏步试探"],
            "relationship_tasks": ["让关键配角关系发生第一次实质变化"],
            "phase_result": "主角失去一部分原有安全区，但获得新的行动空间。",
        },
        "chapter_21_to_30": {
            "range": "21-30",
            "stage_mission": "做出阶段高潮并确认下一层故事方向。",
            "reader_hook": "更大的地图、规则或敌意被清楚打开。",
            "frequent_elements": ["阶段破局", "主动布局", "关系站队"],
            "limited_elements": ["只靠气氛拖章"],
            "relationship_tasks": ["把至少一条关系推入不可逆的新状态"],
            "phase_result": "主角从开书状态进入新的故事层级。",
        },
        "frequent_event_types": ["资源获取类", "关系推进类", "反制类"],
        "limited_event_types": ["连续被怀疑后被动应付"],
        "must_establish_relationships": ["核心绑定角色", "长期压迫源", "阶段合作对象"],
        "escalation_path": ["处境压力", "局部破局", "关系重组", "阶段高潮"],
        "anti_homogenization_rules": ["不要让前30章只围着一个物件打转", "每个阶段都要换推进重心"],
    }


def _mid_term_direction(global_outline: dict[str, Any]) -> str:
    acts = _safe_list(global_outline.get("acts"))
    if len(acts) >= 2:
        return _text(acts[1].get("summary"), "中期进入更高层的资源、势力与真相博弈。")
    if acts:
        return _text(acts[-1].get("summary"), "中期扩大地图、势力与冲突层级。")
    return "中期扩大地图、势力与冲突层级。"



def _endgame_direction(global_outline: dict[str, Any], payload: NovelCreate) -> str:
    acts = _safe_list(global_outline.get("acts"))
    if acts:
        return _text(acts[-1].get("summary"), f"围绕‘{payload.premise}’收束主线、人物与主题。")
    return f"围绕‘{payload.premise}’收束主线、人物与主题。"



def _target_end(acts: list[dict[str, Any]], idx: int) -> int:
    act = acts[idx]
    raw = int(act.get("target_chapter_end", 0) or 0)
    if raw > 0:
        return raw
    return (idx + 1) * 12



def build_volume_cards(global_outline: dict[str, Any], first_arc: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    acts = _safe_list(global_outline.get("acts"))
    cards: list[dict[str, Any]] = []
    start = 1
    first_arc_focus = _text((first_arc or {}).get("focus"), "确认线索、避免暴露、获取立足资源")
    for idx, act in enumerate(acts, start=1):
        end = _target_end(acts, idx - 1)
        cards.append(
            {
                "volume_no": idx,
                "volume_name": _text(act.get("title"), f"第{idx}卷"),
                "start_chapter": start,
                "end_chapter": end,
                "volume_goal": _text(act.get("purpose"), "推进当前主线并建立更高层局势。"),
                "main_conflict": _text(act.get("summary"), "主角在更大的压力与真相前被迫行动。"),
                "cool_point": first_arc_focus if idx == 1 else "资源争夺、势力试探与阶段性破局。",
                "major_crisis": "暴露风险抬高、主角失去原有安全区，必须用更主动的方式破局。",
                "volume_result": "主角获得新的立足资本、情报或关系位阶。",
                "volume_loss": "付出资源、时间、名声、退路或信任代价。",
                "next_hook": "卷尾将主角推向更高层的地图、规则或敌意。",
                "status": "planned",
            }
        )
        start = end + 1
    if not cards:
        cards.append(
            {
                "volume_no": 1,
                "volume_name": "第一卷",
                "start_chapter": 1,
                "end_chapter": max(int((first_arc or {}).get("end_chapter", 0) or 10), 10),
                "volume_goal": "建立主角处境、异常线索与早期生存压力。",
                "main_conflict": "主角必须在谨慎求生与主动试探之间找到平衡。",
                "cool_point": first_arc_focus,
                "major_crisis": "一旦暴露底牌，主角会迅速失去当前立足点。",
                "volume_result": "拿到第一份立足资本。",
                "volume_loss": "失去原本平静或退路。",
                "next_hook": "更大的局势开始显影。",
                "status": "planned",
            }
        )
    return cards



def _default_world_bible(payload: NovelCreate) -> dict[str, Any]:
    return {
        "world_scale": _text(payload.style_preferences.get("world_scale"), "先以当前活动区域为主，逐步扩展到更高层地图。"),
        "mortals_vs_cultivators": _text(payload.style_preferences.get("mortals_vs_cultivators"), "凡人与修士存在明显权力与资源差距，凡人区是风险缓冲层也是压迫来源。"),
        "resource_controllers": _text(payload.style_preferences.get("resource_controllers"), "宗门、地头势力、家族或黑市掌控关键资源。"),
        "factions": _safe_list(payload.style_preferences.get("factions")) or ["宗门", "世家", "散修", "黑市/帮派", "妖魔或异类势力"],
        "higher_world_exists": bool(payload.style_preferences.get("higher_world_exists", True)),
    }



def _default_cultivation_system(payload: NovelCreate) -> dict[str, Any]:
    return {
        "realms": _safe_list(payload.style_preferences.get("realms")) or ["炼气", "筑基", "金丹", "元婴"],
        "gap_rules": _text(payload.style_preferences.get("gap_rules"), "小境界可凭准备、地形、信息差与底牌拉扯；大境界压制原则上不可硬跨。"),
        "breakthrough_conditions": _text(payload.style_preferences.get("breakthrough_conditions"), "需要资源、时机、心境与风险承受能力，不是纯数字累加。"),
        "combat_styles": _text(payload.style_preferences.get("combat_styles"), "不同境界不仅数值更高，还体现在信息掌控、法器质量、持续力与战斗方式差异上。"),
        "cross_realm_rule": _text(payload.style_preferences.get("cross_realm_rule"), "越阶战必须靠准备、代价、环境和对手失误成立，不能常态化。"),
    }



def build_power_system(payload: NovelCreate, cultivation_system: dict[str, Any] | None = None) -> dict[str, Any]:
    cultivation = cultivation_system or _default_cultivation_system(payload)
    realms = [str(item).strip() for item in _safe_list(cultivation.get("realms")) if str(item).strip()]
    realm_cards = []
    for idx, realm in enumerate(realms, start=1):
        lower = "凡俗/未入门" if idx == 1 else realms[idx - 2]
        upper = realms[idx] if idx < len(realms) else "更高位未知境界"
        realm_cards.append(
            {
                "realm_name": realm,
                "order": idx,
                "positioning": "起步自保阶段" if idx == 1 else f"比{lower}更高一层的体系位阶",
                "typical_capability": f"{realm}阶段会在资源掌控、战法熟练度与抗风险能力上明显强于{lower}。",
                "resource_need": "需要稳定资源、外部环境与持续积累，不可能靠单次运气永久跨过。",
                "breakthrough_risk": "突破意味着消耗、暴露和失败成本，绝不是纯数值涨点。",
                "cross_realm_note": _text(cultivation.get("cross_realm_rule"), "越阶战必须靠准备、代价、环境和对手失误成立，不能常态化。"),
                "next_realm_hint": upper,
            }
        )
    return {
        "system_name": _text(payload.style_preferences.get("power_system_name"), "主修力量体系"),
        "realm_system": {
            "realms": realms,
            "realm_cards": realm_cards,
            "current_reference_realm": _text(payload.style_preferences.get("initial_realm"), realms[0] if realms else "低阶求生阶段"),
        },
        "power_rules": {
            "gap_rules": _text(cultivation.get("gap_rules")),
            "breakthrough_conditions": _text(cultivation.get("breakthrough_conditions")),
            "cross_realm_rule": _text(cultivation.get("cross_realm_rule")),
            "core_limitations": [
                "高阶压制长期有效，不能写成只有开局有用。",
                "负伤、消耗、底牌损耗必须在后续状态里留下痕迹。",
                "低阶主角的反杀要绑定环境、信息差、代价与后果。",
            ],
        },
        "combat_rules": {
            "combat_styles": _text(cultivation.get("combat_styles")),
            "same_realm_layers": "同境界内也要区分准备程度、经验、法器与心理状态。",
            "forbidden_patterns": [
                "不能把大境界差距写成一两句狠话就抹平。",
                "不能连续多次靠同一种临时爆种硬吃更高位敌人。",
            ],
        },
    }



def build_opening_constraints(payload: NovelCreate, global_outline: dict[str, Any] | None = None) -> dict[str, Any]:
    style = payload.style_preferences or {}
    first_twenty_targets = [
        "逐步讲清主角当前生存处境与第一层现实压力。",
        "逐步交代世界背景的局部规则，而不是一股脑灌设定。",
        "逐步显影主要势力格局与资源控制方式。",
        "逐步建立修炼/力量体系与实力等级边界，让读者看懂强弱差。",
        "逐步兑现第一轮异常线索、金手指试探或关键悬念。",
    ]
    return {
        "opening_phase_chapter_range": [1, 20],
        "must_gradually_explain": first_twenty_targets,
        "background_delivery": {
            "world_background": _text(style.get("opening_world_delivery"), "前20章以内把世界背景拆成局部常识、利益规则与压迫来源慢慢说清。"),
            "faction_landscape": _text(style.get("opening_faction_delivery"), "先交代和主角切身相关的势力，再逐步抬到更高层。"),
            "power_system": _text(style.get("opening_power_delivery"), "先解释主角眼下看得见、用得上的规则，再逐步引出更高境界与跨境差距。"),
        },
        "pace_rules": {
            "first_three_chapters": _text(style.get("opening_first_three"), "前三章先钉牢主角处境、目标、风险与异常线索入口。"),
            "first_fifteen_chapters": _text(style.get("opening_first_fifteen"), "前15章内持续轮换资源、关系、风险、局势与世界认知推进。"),
            "first_twenty_chapters": _text(style.get("opening_first_twenty"), "前20章内要把世界、势力与实力等级体系的基础认知逐步交代清楚，但必须靠场景、对话、试错和代价来显影。"),
            "forbidden_shortcuts": [
                "不要在前几章过快跳到宏大地图中心。",
                "不要让主角在体系边界未清楚前就随意碾压高位者。",
                "不要只靠说明文把世界背景和等级体系塞完。",
            ],
        },
        "foundation_reveal_schedule": [
            {
                "window": [1, 5],
                "focus": ["主角当前处境", "最基础的强弱判断", "当前立足环境的生存规则"],
                "power_system_focus": ["主角所处基础层级", "高一层带来的直观差距", "外界如何判断强弱"],
                "delivery_rule": "通过眼前压迫、旁人态度、一次试探或一次失败，把基础强弱规则落给读者。",
            },
            {
                "window": [6, 10],
                "focus": ["局部势力分工", "资源门槛", "修炼/力量体系的日常代价"],
                "power_system_focus": ["小境界差异", "资源与提升门槛", "同层级内的差别来源"],
                "delivery_rule": "通过交易、训练、争资源、受限条件和他人评价补中层规则，不要写说明书。",
            },
            {
                "window": [11, 15],
                "focus": ["主要势力格局", "大境界或大层级的分水岭", "规则与身份的捆绑关系"],
                "power_system_focus": ["跨级压制为什么成立", "势力/功法/资源如何影响战力", "主角当前缺口在哪"],
                "delivery_rule": "通过冲突、旁观强者、失败代价或准入门槛，把体系边界写实。",
            },
            {
                "window": [16, 20],
                "focus": ["更高层天花板", "后续地图压力", "主流体系之外的偏门或代价"],
                "power_system_focus": ["更高境界轮廓", "未来突破代价", "主角将面对的上限压力"],
                "delivery_rule": "给读者稳定的未来天花板感，但只亮轮廓，不要一口气透底全貌。",
            },
        ],
        "power_system_reveal_plan": [
            {
                "window": [1, 5],
                "reveal_topics": ["当前境界/层级名称", "最直观的强弱差", "主角为什么不能乱越级"],
                "reader_visible_goal": "读者知道主角现在大概在哪一层，抬头会撞到什么天花板。",
            },
            {
                "window": [6, 10],
                "reveal_topics": ["小层级差别", "突破或成长需要什么资源/条件", "普通人和宗门/体系内成员的差距"],
                "reader_visible_goal": "读者看懂同层级也有差距，成长不是空喊升级。",
            },
            {
                "window": [11, 15],
                "reveal_topics": ["跨级压制规则", "战力不只看境界，还看功法/资源/经验", "主角当前差距如何体现"],
                "reader_visible_goal": "读者看懂大层级边界和越级代价，不会把战力看成橡皮筋。",
            },
            {
                "window": [16, 20],
                "reveal_topics": ["更高境界轮廓", "突破代价与风险", "后续地图里的强者标准"],
                "reader_visible_goal": "读者对后续力量天花板有轮廓感，并知道主角未来压力从哪来。",
            },
        ],
        "long_term_mainline": {
            "opening_goal": _text(style.get("opening_goal"), "先活下去，再拿到第一份立足资本与可信情报。"),
            "mid_term_hint": _mid_term_direction(global_outline or {}),
            "endgame_hint": _endgame_direction(global_outline or {}, payload),
        },
    }



def build_character_templates(payload: NovelCreate) -> list[dict[str, Any]]:
    protagonist = _text(payload.protagonist_name, "主角")
    templates = [
        {
            "template_id": "starter_cautious_observer",
            "name": "谨慎观察型",
            "personality": ["克制", "耐心", "防备心强"],
            "speech_style": "话少，留余地，不轻易把真实判断一次说满。",
            "behavior_mode": "先看局，再试探，再动手。",
            "core_value": "先活下来，再争主动权。",
            "pressure_response": "受压时会先降速，迅速找退路和盲区。",
            "small_tell": "想到关键处会停半拍，视线先扫出口与人手。",
            "taboo": "最忌被人逼着当场摊牌。",
            "decision_logic": "先确认底牌和代价，再决定是否出手。",
            "keywords": ["谨慎", "观察", "试探", "低调", "求生", "主角"],
            "recommended_for": [protagonist, "低阶求生型主角"],
        },
        {
            "template_id": "starter_smiling_information_broker",
            "name": "笑面套话型",
            "personality": ["表面温和", "实际精于权衡", "善于听风向"],
            "speech_style": "顺着话头接，但总会在关键处套信息。",
            "behavior_mode": "先安抚局势，再试探底线。",
            "core_value": "体面和信息都不能丢。",
            "pressure_response": "越有风险越会先把话说圆，再悄悄试探对方底牌。",
            "small_tell": "笑意不变，但会在关键句前轻轻顿一下。",
            "taboo": "最怕自己先把底交出去。",
            "decision_logic": "先探情报密度，再决定卖人情还是卖消息。",
            "keywords": ["掌柜", "掮客", "套话", "笑面", "消息"],
            "recommended_for": ["掌柜", "掮客", "消息灵通配角"],
        },
        {
            "template_id": "starter_hard_shell_soft_core",
            "name": "嘴硬护短型",
            "personality": ["外硬内软", "行动派", "有边界感"],
            "speech_style": "嘴上顶人，关键时候反而会出手。",
            "behavior_mode": "先把人推远，确认可信后再帮。",
            "core_value": "自己的人不能白丢。",
            "pressure_response": "情绪起得快，但会把火气先砸在动作上。",
            "small_tell": "说狠话前会先咬字、皱眉或把物件捏紧。",
            "taboo": "最烦别人拿情义当筹码逼他表态。",
            "decision_logic": "先护住底线，再决定要不要多走一步。",
            "keywords": ["护短", "嘴硬", "伙伴", "敌转友", "外冷内热"],
            "recommended_for": ["敌转友", "护短型伙伴"],
        },
        {
            "template_id": "starter_pragmatic_small_boss",
            "name": "务实小头目型",
            "personality": ["现实", "看重成本", "轻易不翻脸"],
            "speech_style": "直接谈条件，不爱空话。",
            "behavior_mode": "先算账，后站队。",
            "core_value": "有利才合作，但也怕输过头。",
            "pressure_response": "一旦局势失衡，会立刻改条件或改口风。",
            "small_tell": "谈到赔本买卖时会下意识敲桌算数。",
            "taboo": "最怕被拖进一场看不到回报的烂局。",
            "decision_logic": "先算成本收益，再决定是合作、观望还是抽身。",
            "keywords": ["头目", "小老板", "算账", "务实", "站队"],
            "recommended_for": ["地头蛇", "中层势力联系人"],
        },
        {
            "template_id": "righteous_slow_burn_guardian",
            "name": "慢热守义型",
            "personality": ["稳", "讲分寸", "重承诺"],
            "speech_style": "不多话，但答应了就会说到做到。",
            "behavior_mode": "先看人值不值得护，再把事情担下来。",
            "core_value": "承诺一旦出口，就不能轻易折。",
            "pressure_response": "越危险越沉得住，不肯在乱局里失了准头。",
            "small_tell": "做决定前会先把呼吸放稳，再把话说得很短。",
            "taboo": "最忌自己失约或看见弱者被随手牺牲。",
            "decision_logic": "先确认底线，再决定自己要担多大责任。",
            "keywords": ["守义", "护卫", "慢热", "可靠", "承诺"],
            "recommended_for": ["长期伙伴", "护道人", "靠谱师兄"],
        },
        {
            "template_id": "quiet_obsessive_researcher",
            "name": "安静钻研型",
            "personality": ["专注", "偏执", "对细节敏感"],
            "speech_style": "平时寡言，一谈到擅长领域就会突然细起来。",
            "behavior_mode": "先收集样本和细节，再试着推断规律。",
            "core_value": "规律比面子重要，真相比姿态重要。",
            "pressure_response": "受压时会更死盯细节，像抓住一根针不放。",
            "small_tell": "想到关键处会无意识地重复摩挲纸角或器物边缘。",
            "taboo": "最烦别人让他在证据不够时下结论。",
            "decision_logic": "先验证，再判断；验证不够就不轻易站队。",
            "keywords": ["研究", "丹师", "阵师", "学者", "推演"],
            "recommended_for": ["研究型配角", "阵法师", "炼丹师"],
        },
        {
            "template_id": "reckless_hot_blooded_youngster",
            "name": "热血冒进型",
            "personality": ["冲劲大", "不服输", "讲义气"],
            "speech_style": "说话快，容易先把情绪顶上来。",
            "behavior_mode": "想到就冲，撞了墙才学会换路。",
            "core_value": "不认命，输了也得先冲过再说。",
            "pressure_response": "越被压越想正面顶回去。",
            "small_tell": "激动时会先上前半步，语速立刻变快。",
            "taboo": "最受不了被当成没资格上桌的人。",
            "decision_logic": "先求机会，再补后果；但认定的人会护到底。",
            "keywords": ["热血", "年轻", "冒进", "不服", "少年"],
            "recommended_for": ["年轻同伴", "冲动师弟", "少年对手"],
        },
        {
            "template_id": "cold_rule_bound_executor",
            "name": "冷规执法型",
            "personality": ["自持", "重规矩", "不轻信"],
            "speech_style": "语气冷平，句子短，像在给结论。",
            "behavior_mode": "先对照规矩，再决定怎么处理人。",
            "core_value": "秩序不能被随意踩烂。",
            "pressure_response": "压力越大，越会把情绪压进规则条目里。",
            "small_tell": "准备动手前会先把袖口理平或把话说得更慢。",
            "taboo": "最厌恶别人拿关系和人情砸规矩。",
            "decision_logic": "先看证据和越线程度，再决定给活路还是直接收网。",
            "keywords": ["执法", "规矩", "律令", "审问", "冷"],
            "recommended_for": ["执事", "审查者", "执法堂角色"],
        },
        {
            "template_id": "wounded_pride_rival",
            "name": "伤自尊对手型",
            "personality": ["骄傲", "敏感", "不愿服输"],
            "speech_style": "话里总带一点顶劲，越在意越显得冷。",
            "behavior_mode": "先维持体面，再想办法把场子找回来。",
            "core_value": "输一时可以，不能一直被人踩着看。",
            "pressure_response": "被戳中短处时会先收紧表情，再想更狠的回敬。",
            "small_tell": "提到失败时会先移开视线，像不愿让人看见裂缝。",
            "taboo": "最怕被人用同情的口气看待。",
            "decision_logic": "先保脸面，再决定是继续较劲还是被迫合作。",
            "keywords": ["对手", "骄傲", "不服", "竞争", "较劲"],
            "recommended_for": ["长期对手", "同辈竞争者"],
        },
        {
            "template_id": "indebted_loyal_retainer",
            "name": "记恩追随型",
            "personality": ["沉默", "认人", "能忍"],
            "speech_style": "不爱多说，但记人情，也记得清楚谁帮过自己。",
            "behavior_mode": "平时低调，一到关键处会站到该站的人身后。",
            "core_value": "欠过的恩要还，认过的人不轻易变。",
            "pressure_response": "真正急的时候会把话说得更直，像终于不想藏了。",
            "small_tell": "遇到旧恩旧债的话题会下意识低头或停顿。",
            "taboo": "最痛恨被人说成只会卖命的狗。",
            "decision_logic": "先看对方值不值得追随，再决定自己肯不肯把命压上去。",
            "keywords": ["恩", "追随", "旧债", "忠", "仆从"],
            "recommended_for": ["旧部", "追随者", "报恩角色"],
        },
        {
            "template_id": "fox_like_social_climber",
            "name": "狐系攀升型",
            "personality": ["灵活", "识趣", "野心细长"],
            "speech_style": "很会顺坡下驴，也很会把场面话说得让人舒服。",
            "behavior_mode": "先试探风向，再挑最稳的梯子往上爬。",
            "core_value": "往上走才有安全感。",
            "pressure_response": "一旦失势会立刻换姿态，绝不在原地陪葬。",
            "small_tell": "看见更高位人物时眼神会先亮一下，再迅速收住。",
            "taboo": "最怕被人钉死在原来的低位上。",
            "decision_logic": "先判断谁更有前途，再分配自己的热情和忠诚。",
            "keywords": ["攀升", "上位", "八面玲珑", "野心", "狐"],
            "recommended_for": ["外门弟子", "城府型配角"],
        },
        {
            "template_id": "resource_hungry_scavenger",
            "name": "饥饿捡漏型",
            "personality": ["机警", "耐饿", "对资源极敏感"],
            "speech_style": "开口先问值不值，三句话离不开价和命。",
            "behavior_mode": "先捡漏、先保命、先把能拿的拿到手。",
            "core_value": "资源就是活路，错过就是被人踩死。",
            "pressure_response": "一受压就会本能地盘点手里还剩什么能换命。",
            "small_tell": "谈到资源时眼神会先扫袋口、袖口和退路。",
            "taboo": "最恨别人拿穷和窘迫羞辱自己。",
            "decision_logic": "先活下来，再谈体面和道义。",
            "keywords": ["资源", "捡漏", "穷", "黑市", "活路"],
            "recommended_for": ["散修", "黑市混子", "拾荒型配角"],
        },
        {
            "template_id": "ceremonial_face_saver",
            "name": "讲排场体面型",
            "personality": ["看重场面", "习惯维持秩序", "不愿失仪"],
            "speech_style": "说话讲究分寸和排场，喜欢先把礼数铺开。",
            "behavior_mode": "先稳住场面，再在体面的框架里做决定。",
            "core_value": "场面一乱，权威就先折一半。",
            "pressure_response": "真正恼了也不会先吼，而是先把话压冷。",
            "small_tell": "不快时会先把衣摆、杯盏或座次整理得更端正。",
            "taboo": "最怕当众丢体面。",
            "decision_logic": "先看这件事会不会毁场，再决定该护谁、压谁。",
            "keywords": ["体面", "礼数", "排场", "主事", "门面"],
            "recommended_for": ["长老", "家主", "掌柜", "主事者"],
        },
        {
            "template_id": "patient_trap_setter",
            "name": "耐心布套型",
            "personality": ["沉住气", "会算时机", "擅长埋线"],
            "speech_style": "话不多，常把真正的刀留到最后一两句。",
            "behavior_mode": "先放线，再等人自己踩进来。",
            "core_value": "最稳的胜法，是让对手自己走进错误里。",
            "pressure_response": "越危险越不着急，甚至会故意更慢半拍。",
            "small_tell": "真正看见机会时反而会安静得像没动念头。",
            "taboo": "最讨厌被人逼着提前掀牌。",
            "decision_logic": "先埋伏笔，再判断何时收网才最省力。",
            "keywords": ["陷阱", "套", "收网", "布局", "耐心"],
            "recommended_for": ["幕后手", "钓鱼执法型角色"],
        },
        {
            "template_id": "half_true_confessor",
            "name": "半真半假倾诉型",
            "personality": ["懂利用脆弱感", "会示弱", "边说边试探"],
            "speech_style": "会讲真话，但只讲到刚好够换取信任那一步。",
            "behavior_mode": "先放出一段半真故事，再看对方怎么接。",
            "core_value": "情感和信息都可以是筹码。",
            "pressure_response": "被逼急时会拿更私密的一层真话来换空间。",
            "small_tell": "提到真正痛处时语速会慢下来，像刻意压住。",
            "taboo": "最怕别人完全不吃自己的情绪牌。",
            "decision_logic": "先给一点真心当钩，再看值不值得继续给。",
            "keywords": ["倾诉", "示弱", "真话", "隐痛", "套近乎"],
            "recommended_for": ["复杂盟友", "有旧伤的配角"],
        },
        {
            "template_id": "old_debt_cynic",
            "name": "旧债凉心型",
            "personality": ["心冷", "记账", "对情义不轻信"],
            "speech_style": "话里常带点旧账味，像不相信事情会无代价地变好。",
            "behavior_mode": "先防重演，再考虑要不要给人第二次机会。",
            "core_value": "吃过的亏不能白吃两次。",
            "pressure_response": "触到旧伤时会立刻把姿态收硬，宁可先翻脸。",
            "small_tell": "一提旧事，手指会先收紧，像身体先记起来了。",
            "taboo": "最怕自己又回到曾经任人摆布的位置。",
            "decision_logic": "先确认这次会不会重演旧债，再决定要不要押上信任。",
            "keywords": ["旧债", "凉", "不信", "背叛", "教训"],
            "recommended_for": ["旧识", "背叛幸存者"],
        },
        {
            "template_id": "merciful_healer_with_edges",
            "name": "有棱角医修型",
            "personality": ["心软有边界", "讲条件", "不愿白救"],
            "speech_style": "语气平静，但不容别人把善意当理所当然。",
            "behavior_mode": "能救会救，但会先问后果和代价。",
            "core_value": "救人不是给人拿捏的理由。",
            "pressure_response": "越被道德绑架，越会把边界讲得更明白。",
            "small_tell": "不高兴时会先把药瓶或器具摆回原位，再抬眼看人。",
            "taboo": "最恨别人拿病痛和性命逼她无条件让步。",
            "decision_logic": "先评估救人值不值、代价谁来背，再决定出手几分。",
            "keywords": ["医", "疗", "丹", "善意", "边界"],
            "recommended_for": ["医修", "治疗者", "丹师"],
        },
        {
            "template_id": "zealous_believer",
            "name": "信念炽硬型",
            "personality": ["笃信", "能忍苦", "极有行动力"],
            "speech_style": "说话常带一种不容怀疑的确信感。",
            "behavior_mode": "先看一件事是否符合信念，再决定投入多少。",
            "core_value": "只要信念没塌，代价都能忍。",
            "pressure_response": "越受压越会把自己往信念里钉得更死。",
            "small_tell": "提到信奉之物时目光会立刻定住，像整个人被拉直。",
            "taboo": "最怕自己信奉的东西被证明是假的。",
            "decision_logic": "先问这件事是否违背信念，再决定有没有回旋余地。",
            "keywords": ["信念", "宗教", "教义", "执拗", "笃信"],
            "recommended_for": ["狂热追随者", "执念型角色"],
        },
        {
            "template_id": "tired_schemer_elder",
            "name": "疲惫老谋型",
            "personality": ["见多", "耐烦", "不再轻信热血"],
            "speech_style": "不急不慢，像每一句都在给年轻人留余味。",
            "behavior_mode": "先看人心和时势，再决定怎么挪棋。",
            "core_value": "活得久不是赢，是少犯致命错。",
            "pressure_response": "真正危险时会忽然把废话全收掉，只剩最硬的指令。",
            "small_tell": "听人说话时常半垂着眼，像在算更远的账。",
            "taboo": "最怕年轻人拿一腔血气去补本可避免的坑。",
            "decision_logic": "先看时势，再决定谁该被保护、谁该被牺牲。",
            "keywords": ["长老", "老谋", "疲惫", "前辈", "见多"],
            "recommended_for": ["老前辈", "长老", "幕后指路人"],
        },
        {
            "template_id": "hidden_soft_spot_enforcer",
            "name": "藏软肋打手型",
            "personality": ["硬", "认规则", "不爱解释"],
            "speech_style": "话少，刀子嘴，讨厌无谓争辩。",
            "behavior_mode": "先按命令做事，但会在真正看不过眼时悄悄偏一点。",
            "core_value": "手上脏可以，心里不能全烂。",
            "pressure_response": "越被催着往死里做，越容易露出一丝犹豫。",
            "small_tell": "动手前会先活动手指或沉一下肩。",
            "taboo": "最怕自己真的变成只会执行的钝器。",
            "decision_logic": "先执行，再判断是否还能偷偷留人一线。",
            "keywords": ["打手", "执行", "护短", "狠", "执令"],
            "recommended_for": ["执事手下", "外冷内有底线角色"],
        },
        {
            "template_id": "calculating_trade_partner",
            "name": "算牌交易型",
            "personality": ["理性", "守边界", "擅长交换"],
            "speech_style": "不绕情绪，直接把筹码和条件摊出来。",
            "behavior_mode": "先谈交换，再谈信任。",
            "core_value": "所有合作都要有可以落账的筹码。",
            "pressure_response": "局势失控时会迅速把谈判改成止损。",
            "small_tell": "谈到关键筹码会轻轻点一下桌面或指节。",
            "taboo": "最烦别人想白拿或想空手套合作。",
            "decision_logic": "先看有没有公平交换的空间，再决定要不要加码。",
            "keywords": ["交易", "合作", "筹码", "商量", "互换"],
            "recommended_for": ["交易伙伴", "合作盟友"],
        },
        {
            "template_id": "chaotic_problem_solver",
            "name": "野路解题型",
            "personality": ["跳脱", "反应快", "敢走偏门"],
            "speech_style": "说话不按常理来，但总能突然戳到问题核心。",
            "behavior_mode": "先找最歪却最有效的解法。",
            "core_value": "能活、能赢、能破局，比姿势漂亮重要。",
            "pressure_response": "越乱越兴奋，像脑子终于有地方撒欢。",
            "small_tell": "想到怪点子时眼尾会先亮一下。",
            "taboo": "最讨厌别人拿“规矩就该这样”堵住所有路。",
            "decision_logic": "先看有没有旁门解法，再决定要不要回主路。",
            "keywords": ["野路子", "偏门", "怪招", "灵机", "解题"],
            "recommended_for": ["奇招型同伴", "问题解决者"],
        },
        {
            "template_id": "bookish_rule_hacker",
            "name": "书卷拆规型",
            "personality": ["爱钻缝", "逻辑强", "不迷信权威"],
            "speech_style": "说话像在拆条文，会指出别人没看见的缝隙。",
            "behavior_mode": "先找规则漏洞，再把漏洞变成路。",
            "core_value": "规则不是用来跪的，是用来看清边界后利用的。",
            "pressure_response": "越被压制，越会本能地找条文和结构里的缝。",
            "small_tell": "听到规则时会下意识重复关键词，像在脑子里拆句法。",
            "taboo": "最烦别人一句“历来如此”就想堵死讨论。",
            "decision_logic": "先拆规则，再决定要不要顺规矩还是借规矩反打。",
            "keywords": ["规则", "条文", "书卷", "漏洞", "拆"],
            "recommended_for": ["师爷型", "智囊型角色"],
        },
        {
            "template_id": "suspicious_survivor",
            "name": "多疑幸存型",
            "personality": ["警惕", "会藏", "擅长活下来"],
            "speech_style": "永远留一手，连感谢都像带着试探。",
            "behavior_mode": "先怀疑，再验证，最后才给一点信任。",
            "core_value": "活过的人不是最强的，是最少给错信任的。",
            "pressure_response": "一有风吹草动就会先撤半步，把自己从局里抽出来看。",
            "small_tell": "被问到核心问题时会先沉默，像在试图确认陷阱在哪。",
            "taboo": "最怕自己再次因为信错人而没退路。",
            "decision_logic": "先保密，再交换，再考虑结盟。",
            "keywords": ["多疑", "幸存", "怀疑", "藏", "退路"],
            "recommended_for": ["幸存者", "旧伤型盟友"],
        },
        {
            "template_id": "slow_to_trust_craftsperson",
            "name": "手艺慢信型",
            "personality": ["讲究", "慢热", "重手上活"],
            "speech_style": "不爱说虚的，更相信做出来的东西。",
            "behavior_mode": "先做事看手，再看人值不值得深交。",
            "core_value": "手艺不会骗人，人会。",
            "pressure_response": "真正急时会让动作更稳，像把心绪压进手上。",
            "small_tell": "思考时会反复摸工具、纹路或材料边角。",
            "taboo": "最受不了别人糟蹋手艺和长期积累。",
            "decision_logic": "先看对方懂不懂珍惜，再决定要不要帮到底。",
            "keywords": ["手艺", "工匠", "炼器", "慢热", "作品"],
            "recommended_for": ["工匠", "炼器师", "匠人型配角"],
        },
        {
            "template_id": "ambitious_outer_disciple",
            "name": "外门上爬型",
            "personality": ["咬牙", "会看阶层", "忍得住委屈"],
            "speech_style": "表面规矩，话里却总有一点想往上争的劲。",
            "behavior_mode": "先在规则内抢名额，再在规则外找机会。",
            "core_value": "不往上爬，就永远只是被挑剩的那批人。",
            "pressure_response": "被压阶时会更拼命证明自己值更高位置。",
            "small_tell": "碰到上升机会时会先挺直背，再把声音压稳。",
            "taboo": "最怕自己一辈子困在底层门槛外。",
            "decision_logic": "先看这一步能不能换到更高层位置，再决定押多大。",
            "keywords": ["外门", "上爬", "名额", "晋升", "门槛"],
            "recommended_for": ["宗门配角", "野心型弟子"],
        },
        {
            "template_id": "suppressed_noble_outcast",
            "name": "压抑贵胄流亡型",
            "personality": ["自持", "隐忍", "骨子里有旧习"],
            "speech_style": "刻意压平，但偶尔会露出不属于当前处境的精细和教养。",
            "behavior_mode": "先藏身份，再借旧经验看局。",
            "core_value": "再落魄，也不能彻底忘了自己是谁。",
            "pressure_response": "被逼到身份边缘时会突然显出训练过的冷静。",
            "small_tell": "紧张时会下意识用旧习惯整理衣角、站姿或称呼。",
            "taboo": "最怕身份暴露在自己还没准备好的时候。",
            "decision_logic": "先压住身份，再判断何时该借旧背景翻盘。",
            "keywords": ["贵胄", "流亡", "身份", "旧习", "隐藏"],
            "recommended_for": ["落难贵族", "隐藏背景角色"],
        },
        {
            "template_id": "dry_humor_teammate",
            "name": "冷幽默搭子型",
            "personality": ["嘴损", "稳", "擅长降压"],
            "speech_style": "话不多，但会用干巴巴的冷话把气氛往回拉。",
            "behavior_mode": "先吐槽拆压，再把正事接住。",
            "core_value": "慌没用，先把人稳住再想办法。",
            "pressure_response": "越紧张越会吐出一两句很干的废话来维持心跳。",
            "small_tell": "危险越近，越像无所谓，只有眼神会更专注。",
            "taboo": "最怕所有人一起慌成一锅。",
            "decision_logic": "先稳住人心，再决定自己去顶哪一块压力。",
            "keywords": ["幽默", "搭子", "吐槽", "稳", "队友"],
            "recommended_for": ["固定搭档", "轻松位配角"],
        },
        {
            "template_id": "fatalistic_watcher",
            "name": "认命旁观型",
            "personality": ["悲观", "看得透", "不轻易投入"],
            "speech_style": "常把最坏结果先说出来，像提前给人打预防针。",
            "behavior_mode": "先旁观看局，确认不是必死局才参与。",
            "core_value": "命运大多不讲理，先少赔一点。",
            "pressure_response": "越危险越不做多余动作，像怕一步错满盘死。",
            "small_tell": "听到大计划时会先沉默，再很轻地叹一口气。",
            "taboo": "最怕自己又被热血和希望骗一次。",
            "decision_logic": "先算最坏结局，再决定自己要不要伸手。",
            "keywords": ["旁观", "悲观", "认命", "叹气", "看透"],
            "recommended_for": ["观望者", "被生活磨旧的角色"],
        },
        {
            "template_id": "precision_sniper_mindset",
            "name": "精确猎手型",
            "personality": ["冷静", "耐心", "目标感强"],
            "speech_style": "不浪费字，话总像在瞄准一个点。",
            "behavior_mode": "先找最关键的一击点，再把动作压到最省。",
            "core_value": "不求多，只求最准。",
            "pressure_response": "越危险越会把注意力缩成一点，像世界只剩目标位。",
            "small_tell": "锁定目标时呼吸会刻意放慢。",
            "taboo": "最怕被无意义的喧闹和情绪带偏准头。",
            "decision_logic": "先找破口，再决定何时开口、何时出手。",
            "keywords": ["猎手", "精准", "瞄准", "刺杀", "弓"],
            "recommended_for": ["猎人", "远程型角色", "刺客"],
        },
        {
            "template_id": "performative_hero",
            "name": "表演式英雄型",
            "personality": ["要强", "爱面子", "需要被看见"],
            "speech_style": "说话带一种主动承担的味道，也带一点演给人看的光亮。",
            "behavior_mode": "先顶上去，再想后果能不能圆。",
            "core_value": "不能让人看见自己退。",
            "pressure_response": "越多人看着，越不肯示弱。",
            "small_tell": "被赞许时脊背会更直，被质疑时笑意会更用力。",
            "taboo": "最怕在重要场合露怯或丢脸。",
            "decision_logic": "先把场接住，再考虑自己扛不扛得住。",
            "keywords": ["英雄", "出头", "逞强", "面子", "舞台"],
            "recommended_for": ["高光型配角", "爱出头同辈"],
        },
        {
            "template_id": "deep_cover_double_face",
            "name": "双面潜伏型",
            "personality": ["能演", "记忆好", "心里分层很清"],
            "speech_style": "对不同人会用不同口径，说法切得很干净。",
            "behavior_mode": "先保住伪装层，再寻找真正目的的切入口。",
            "core_value": "活在两面之间，最要紧的是别让两面撞车。",
            "pressure_response": "一旦有人逼近真相，会立刻切换成更安全的人设。",
            "small_tell": "真正紧张时反而会笑得更合适，像把每个动作都练过。",
            "taboo": "最怕自己两套身份在同一场里打架。",
            "decision_logic": "先保伪装，再推进目标；目标再重要也不能先露底。",
            "keywords": ["潜伏", "双面", "伪装", "身份", "卧底"],
            "recommended_for": ["卧底", "双面人", "伪装型角色"],
        },
        {
            "template_id": "hungry_opportunist",
            "name": "饿狼机会型",
            "personality": ["敏锐", "贪生路", "胆子忽大忽小"],
            "speech_style": "一闻到机会味就会立刻热络起来。",
            "behavior_mode": "机会来了先扑，但真见血会立刻衡量值不值继续。",
            "core_value": "抓到一个向上的口子，比守着旧坑更重要。",
            "pressure_response": "局势失控时会先想跑，但只要看见大利又会回头。",
            "small_tell": "看见机会时眼神会先发亮，随后才装得若无其事。",
            "taboo": "最怕错过一次可能改命的窗口。",
            "decision_logic": "先扑机会，再用最快速度判断要不要退。",
            "keywords": ["机会", "饿狼", "改命", "扑", "投机"],
            "recommended_for": ["投机者", "小角色上位苗子"],
        },
        {
            "template_id": "ceremonial_loyalist",
            "name": "礼法忠簇型",
            "personality": ["守序", "讲上下", "习惯服从正统"],
            "speech_style": "说话有明显的上下尊卑感，习惯把位置摆对。",
            "behavior_mode": "先看名分和次序，再决定是否表态。",
            "core_value": "名分不稳，很多事就都不稳。",
            "pressure_response": "被迫违礼时会明显不适，像脚下站不住。",
            "small_tell": "说到上下尊卑时会先正身，语气自然更谨慎。",
            "taboo": "最怕秩序塌得太快，自己不知道该向哪边站。",
            "decision_logic": "先看正统和名分，再决定忠诚往哪边压。",
            "keywords": ["礼法", "忠", "名分", "正统", "侍从"],
            "recommended_for": ["侍从", "家臣", "守旧派角色"],
        },
        {
            "template_id": "silken_negotiator",
            "name": "柔滑谈判型",
            "personality": ["圆融", "擅长交换立场", "很少把话说死"],
            "speech_style": "会给每个人都留台阶，但真正要的东西藏得很深。",
            "behavior_mode": "先铺缓冲，再一点点把局面导向自己要的方向。",
            "core_value": "最好的赢法，是让所有人都以为自己没输。",
            "pressure_response": "越被逼，越会把话说得轻软，却把边界收得更紧。",
            "small_tell": "要收口时会忽然把称呼和语气都放得更轻。",
            "taboo": "最怕局面被人一把掀成非此即彼。",
            "decision_logic": "先给台阶，再设边界，最后让人自己走到选项里。",
            "keywords": ["谈判", "台阶", "圆融", "柔", "说和"],
            "recommended_for": ["使者", "中间人", "谈判者"],
        },
    ]
    templates[0]["recommended_for"] = [protagonist, "低阶求生型主角", "谨慎型主角"]
    return templates



def build_flow_templates() -> list[dict[str, Any]]:
    return [
        {
            "flow_id": "probe_gain",
            "quick_tag": "试一试",
            "name": "试探获益",
            "family": "成长",
            "when_to_use": "主角刚接触新机会、新能力或新地方。",
            "applicable_scenes": ["第一次试错", "异常刚露头", "低成本试探"],
            "sequence": ["先试探", "拿到一点成果", "发现后果或隐患"],
            "turning_points": ["主角先试探", "拿到一点收益", "好处背后露出代价"],
            "resource_nodes": ["小资源", "线索碎片"],
            "relation_nodes": ["旁人留意", "潜在盟友起疑"],
            "preferred_event_types": ["试探类", "发现类"],
            "preferred_progress_kinds": ["信息推进", "资源推进"],
            "preferred_hook_styles": ["信息反转", "危险逼近"],
            "keyword_hints": ["试探", "尝试", "摸索", "验证", "第一次"],
            "closing_feel": "有收获，但不安稳。",
            "variation_notes": "重点是小收益，不要写成直接开挂。",
        },
        {
            "flow_id": "probe_loss",
            "quick_tag": "试失败",
            "name": "试探受挫",
            "family": "成长",
            "when_to_use": "主角想试一下，但实力、信息或时机还不够。",
            "applicable_scenes": ["贸然试探", "经验不足", "规则没摸透"],
            "sequence": ["先尝试", "失败或吃亏", "知道差距"],
            "turning_points": ["主角出手试错", "过程吃亏或暴露", "明确短板在哪里"],
            "resource_nodes": ["损耗资源", "教训成本"],
            "relation_nodes": ["旁人看低", "提醒或警告出现"],
            "preferred_event_types": ["试探类", "危机爆发"],
            "preferred_progress_kinds": ["风险升级", "信息推进"],
            "preferred_hook_styles": ["危险逼近", "余味收束"],
            "keyword_hints": ["失败", "受挫", "吃亏", "不够", "失手", "差距"],
            "closing_feel": "输了这一下，但方向更清楚。",
            "variation_notes": "重点是受挫后知道缺口，不要只写倒霉。",
        },
        {
            "flow_id": "forced_choice",
            "quick_tag": "二选一",
            "name": "被迫选择",
            "family": "抉择",
            "when_to_use": "两条路都不完美，主角必须立刻选。",
            "applicable_scenes": ["两难局面", "代价交换", "保这个丢那个"],
            "sequence": ["压力出现", "权衡利弊", "做出选择", "留下后果"],
            "turning_points": ["局面逼迫", "主角快速判断", "选择带来后遗症"],
            "resource_nodes": ["得失交换", "保命筹码"],
            "relation_nodes": ["立场变化", "有人因此改观或失望"],
            "preferred_event_types": ["危机爆发", "外部任务类", "交易类"],
            "preferred_progress_kinds": ["风险升级", "关系推进"],
            "preferred_hook_styles": ["人物选择", "危险逼近"],
            "keyword_hints": ["选择", "只能", "两难", "取舍", "抉择"],
            "closing_feel": "决定已经做了，代价开始追上来。",
            "variation_notes": "不要写成空想心理戏，必须落到具体取舍。",
        },
        {
            "flow_id": "small_win_trap",
            "quick_tag": "赢一点",
            "name": "小胜埋雷",
            "family": "冲突",
            "when_to_use": "本章要给爽点，但不能让局势太顺。",
            "applicable_scenes": ["短胜", "抢到先手", "暂时压住对手"],
            "sequence": ["拿到小胜", "成果落袋", "暗处埋下麻烦"],
            "turning_points": ["主角赢一手", "短期成果可见", "新的盯梢或隐患出现"],
            "resource_nodes": ["战利品", "暂时优势"],
            "relation_nodes": ["对手更记恨", "旁观者开始注意"],
            "preferred_event_types": ["冲突类", "资源获取类", "反制类"],
            "preferred_progress_kinds": ["资源推进", "风险升级"],
            "preferred_hook_styles": ["危险逼近", "信息反转"],
            "keyword_hints": ["赢", "得手", "小胜", "压住", "收获"],
            "closing_feel": "看似赚了，实际上留了后患。",
            "variation_notes": "小胜要真落地，但不能把危险写没。",
        },
        {
            "flow_id": "pressure_close",
            "quick_tag": "麻烦近",
            "name": "压力逼近",
            "family": "危机",
            "when_to_use": "需要拉紧张感，让下一章必须处理问题。",
            "applicable_scenes": ["追查加重", "时限逼近", "坏消息连着来"],
            "sequence": ["坏消息出现", "压力加重", "主角先稳住"],
            "turning_points": ["新风险落地", "退路变少", "主角勉强顶住一轮"],
            "resource_nodes": ["时间", "退路", "遮掩手段"],
            "relation_nodes": ["施压者逼近", "同伴出现不同意见"],
            "preferred_event_types": ["危机爆发", "外部任务类", "逃避类"],
            "preferred_progress_kinds": ["风险升级"],
            "preferred_hook_styles": ["危险逼近", "余味收束"],
            "keyword_hints": ["逼近", "追查", "围堵", "时限", "麻烦", "压力"],
            "closing_feel": "眼前还能撑，但下一步更难。",
            "variation_notes": "重点是压迫感，不要写成无意义惊吓。",
        },
        {
            "flow_id": "conflict_upgrade",
            "quick_tag": "矛盾大",
            "name": "冲突升级",
            "family": "冲突",
            "when_to_use": "敌意、竞争或立场分裂继续加深。",
            "applicable_scenes": ["小摩擦放大", "硬碰前夜", "态度彻底变硬"],
            "sequence": ["小摩擦", "正面冲突", "双方立场更硬"],
            "turning_points": ["矛盾显形", "场面顶上去", "后续更大冲突不可避"],
            "resource_nodes": ["底牌消耗", "立场筹码"],
            "relation_nodes": ["仇怨加深", "关系恶化"],
            "preferred_event_types": ["冲突类", "反制类"],
            "preferred_progress_kinds": ["风险升级", "关系推进"],
            "preferred_hook_styles": ["危险逼近", "人物选择"],
            "keyword_hints": ["冲突", "对峙", "硬碰", "矛盾", "升级"],
            "closing_feel": "这口气已经顶上去了。",
            "variation_notes": "要让冲突前后有层级变化，不要原地吵架。",
        },
        {
            "flow_id": "conflict_bond",
            "quick_tag": "打出缘",
            "name": "冲突结缘",
            "family": "关系",
            "when_to_use": "适合敌转友、互相试探、关键配角第一次立住。",
            "applicable_scenes": ["不打不相识", "竞争后改观", "被迫并肩"],
            "sequence": ["先冲突", "看见对方价值", "留合作可能"],
            "turning_points": ["两边先起硬碰", "过程中看见对方底色", "关系从敌对变复杂"],
            "resource_nodes": ["共同目标", "共享风险"],
            "relation_nodes": ["敌意下降", "尊重萌芽"],
            "preferred_event_types": ["冲突类", "关系推进类"],
            "preferred_progress_kinds": ["关系推进"],
            "preferred_hook_styles": ["人物选择", "余味收束"],
            "keyword_hints": ["并肩", "改观", "结缘", "同路", "不打不相识"],
            "closing_feel": "还没成朋友，但线已经牵上。",
            "variation_notes": "不要一章内直接从敌人跳成铁哥们。",
        },
        {
            "flow_id": "cooperate_break",
            "quick_tag": "一起上",
            "name": "合作破局",
            "family": "关系",
            "when_to_use": "单靠主角搞不定，需要借人、借力、借路。",
            "applicable_scenes": ["联手破题", "互补配合", "临时搭伙"],
            "sequence": ["遇到难题", "找人合作", "一起解决"],
            "turning_points": ["单人方案不够", "合作形成", "局面被撬开"],
            "resource_nodes": ["协作资源", "互补能力"],
            "relation_nodes": ["信任增加", "新盟友出现"],
            "preferred_event_types": ["关系推进类", "外部任务类"],
            "preferred_progress_kinds": ["关系推进", "资源推进"],
            "preferred_hook_styles": ["平稳过渡", "危险逼近"],
            "keyword_hints": ["合作", "联手", "一起", "帮忙", "搭伙"],
            "closing_feel": "问题破开了，关系也留下余波。",
            "variation_notes": "合作要有分工，不要写成旁人来替主角办事。",
        },
        {
            "flow_id": "trade_exchange",
            "quick_tag": "做交换",
            "name": "交易交换",
            "family": "资源",
            "when_to_use": "适合资源、情报、利益交换。",
            "applicable_scenes": ["谈价", "换消息", "条件置换"],
            "sequence": ["提出需求", "谈条件", "完成交换", "留下不平衡"],
            "turning_points": ["交易需求明确", "价码被抬高或改变", "交换后出现新绑定"],
            "resource_nodes": ["交换物", "代价物"],
            "relation_nodes": ["利益绑定", "信任未稳"],
            "preferred_event_types": ["交易类", "关系推进类"],
            "preferred_progress_kinds": ["资源推进", "关系推进"],
            "preferred_hook_styles": ["信息反转", "余味收束"],
            "keyword_hints": ["交易", "交换", "谈条件", "谈价", "买卖"],
            "closing_feel": "东西换到了，但账没算完。",
            "variation_notes": "交易要写清拿什么换什么，别空泛。",
        },
        {
            "flow_id": "infiltrate_probe",
            "quick_tag": "偷查探",
            "name": "潜入探查",
            "family": "探查",
            "when_to_use": "需要拿情报、偷看情况、提前布局。",
            "applicable_scenes": ["暗查", "摸进目标点", "跟踪探路"],
            "sequence": ["接近目标", "小心探查", "得到关键情报", "差点暴露"],
            "turning_points": ["接近时先压风险", "中段拿到关键情报", "尾部出现暴露边缘"],
            "resource_nodes": ["隐藏手段", "情报线索"],
            "relation_nodes": ["被监视可能", "新嫌疑形成"],
            "preferred_event_types": ["潜入类", "发现类"],
            "preferred_progress_kinds": ["信息推进", "风险升级"],
            "preferred_hook_styles": ["危险逼近", "信息反转"],
            "keyword_hints": ["潜入", "暗查", "偷看", "跟踪", "探查"],
            "closing_feel": "查到了，但可能已经被看见。",
            "variation_notes": "不要全程安全潜入，至少要有一处险些露馅。",
        },
        {
            "flow_id": "discover_secret",
            "quick_tag": "挖真相",
            "name": "发现秘密",
            "family": "揭秘",
            "when_to_use": "适合揭露设定、人物真相、隐藏规则。",
            "applicable_scenes": ["线索拼上", "秘密露头", "真相掀角"],
            "sequence": ["线索积累", "真相露头", "主角理解改变"],
            "turning_points": ["旧线索被重新解释", "秘密露出一角", "认知随之改变"],
            "resource_nodes": ["关键信息", "被隐藏的旧物"],
            "relation_nodes": ["人物印象改变", "信任或怀疑重排"],
            "preferred_event_types": ["发现类"],
            "preferred_progress_kinds": ["信息推进"],
            "preferred_hook_styles": ["信息反转", "余味收束"],
            "keyword_hints": ["真相", "秘密", "线索", "发现", "异样"],
            "closing_feel": "知道得更多了，但还远没全知道。",
            "variation_notes": "不要一口气全抖完，真相只掀开一层。",
        },
        {
            "flow_id": "misunderstanding_deepen",
            "quick_tag": "看错了",
            "name": "误会加深",
            "family": "关系",
            "when_to_use": "人物关系需要拉扯、错位、偏判。",
            "applicable_scenes": ["信息不对称", "各怀心思", "站位错开"],
            "sequence": ["信息不全", "产生误会", "双方判断偏掉"],
            "turning_points": ["一句话或一个动作被看错", "误会被坐实", "后续代价开始形成"],
            "resource_nodes": ["错位情报"],
            "relation_nodes": ["关系变差", "立场错位"],
            "preferred_event_types": ["关系推进类", "冲突类"],
            "preferred_progress_kinds": ["关系推进", "风险升级"],
            "preferred_hook_styles": ["信息反转", "危险逼近"],
            "keyword_hints": ["误会", "误判", "看错", "误解", "错判"],
            "closing_feel": "话没说开，问题变大了。",
            "variation_notes": "误会必须有具体触发点，别硬拧。",
        },
        {
            "flow_id": "relationship_warm",
            "quick_tag": "更亲近",
            "name": "关系升温",
            "family": "关系",
            "when_to_use": "培养伙伴、感情线、信任线。",
            "applicable_scenes": ["共同经历", "互相托底", "看见优点"],
            "sequence": ["一起经历事", "看见彼此优点", "关系变近"],
            "turning_points": ["先有并肩场面", "再有理解或照应", "关系明显近一步"],
            "resource_nodes": ["共同秘密", "彼此交底"],
            "relation_nodes": ["信任增加", "合作更顺"],
            "preferred_event_types": ["关系推进类"],
            "preferred_progress_kinds": ["关系推进"],
            "preferred_hook_styles": ["平稳过渡", "余味收束"],
            "keyword_hints": ["信任", "靠近", "亲近", "升温", "理解"],
            "closing_feel": "关系更近，也更容易受伤。",
            "variation_notes": "升温要靠事，不要只靠嘴上互夸。",
        },
        {
            "flow_id": "relationship_crack",
            "quick_tag": "闹掰了",
            "name": "关系裂开",
            "family": "关系",
            "when_to_use": "伙伴矛盾、利益冲突、理念不合。",
            "applicable_scenes": ["小分歧变硬", "互不相让", "信任滑坡"],
            "sequence": ["小分歧", "触发冲突", "关系出现裂痕"],
            "turning_points": ["分歧露头", "关键一击把话说死", "裂痕留下"],
            "resource_nodes": ["共用资源分配", "站队筹码"],
            "relation_nodes": ["信任下降", "站队倾向出现"],
            "preferred_event_types": ["关系推进类", "冲突类"],
            "preferred_progress_kinds": ["关系推进", "风险升级"],
            "preferred_hook_styles": ["人物选择", "危险逼近"],
            "keyword_hints": ["裂", "翻脸", "闹掰", "失望", "站队"],
            "closing_feel": "问题没有解决，只是撕开了。",
            "variation_notes": "裂开也要保留后续修补或继续恶化的空间。",
        },
        {
            "flow_id": "resource_gain",
            "quick_tag": "拿资源",
            "name": "资源到手",
            "family": "资源",
            "when_to_use": "主角需要明显成长、补给或渠道。",
            "applicable_scenes": ["抢到资源", "买到资源", "解锁新渠道"],
            "sequence": ["发现机会", "争取资源", "成功拿到", "引出后续"],
            "turning_points": ["机会出现", "争取过程有阻力", "资源真正落袋"],
            "resource_nodes": ["钱", "宝物", "功法", "材料"],
            "relation_nodes": ["有人羡慕或盯上", "交易关系形成"],
            "preferred_event_types": ["资源获取类", "交易类"],
            "preferred_progress_kinds": ["资源推进"],
            "preferred_hook_styles": ["意外收获隐患", "危险逼近"],
            "keyword_hints": ["资源", "灵石", "材料", "药", "功法", "到手"],
            "closing_feel": "资源拿到了，但怎么用更关键。",
            "variation_notes": "资源要具体，不要写成笼统机缘。",
        },
        {
            "flow_id": "resource_loss",
            "quick_tag": "丢资源",
            "name": "资源流失",
            "family": "资源",
            "when_to_use": "让主角不至于太顺，逼他换打法。",
            "applicable_scenes": ["资源被夺", "底牌暴露", "关键耗尽"],
            "sequence": ["出现问题", "资源流失", "被迫调整"],
            "turning_points": ["资源出事", "损失落地", "主角必须改策略"],
            "resource_nodes": ["被夺资源", "耗损底牌"],
            "relation_nodes": ["同伴分歧", "对手趁势压上"],
            "preferred_event_types": ["危机爆发", "反制类"],
            "preferred_progress_kinds": ["风险升级", "资源推进"],
            "preferred_hook_styles": ["危险逼近", "余味收束"],
            "keyword_hints": ["丢", "失去", "消耗", "暴露", "被夺"],
            "closing_feel": "安全感少了一层。",
            "variation_notes": "资源流失后要写清局势怎么变难。",
        },
        {
            "flow_id": "prepare_first",
            "quick_tag": "先准备",
            "name": "闭关准备",
            "family": "成长",
            "when_to_use": "战前、修炼前、计划前的铺垫章。",
            "applicable_scenes": ["闭关", "布置", "筹备行动", "调整状态"],
            "sequence": ["明确目标", "做准备", "调整状态", "准备完成"],
            "turning_points": ["目标落清", "准备步骤展开", "下一步行动被顶到门口"],
            "resource_nodes": ["准备物资", "辅助条件"],
            "relation_nodes": ["托付", "临时分工"],
            "preferred_event_types": ["外部任务类", "试探类", "关系推进类"],
            "preferred_progress_kinds": ["实力推进", "地点推进", "信息推进"],
            "preferred_hook_styles": ["平稳过渡", "危险逼近"],
            "keyword_hints": ["准备", "闭关", "布置", "筹备", "调整"],
            "closing_feel": "这章不爆，但下一章该动手了。",
            "variation_notes": "准备章也要有明确结果，不能纯水。",
        },
        {
            "flow_id": "breakthrough_grow",
            "quick_tag": "变更强",
            "name": "突破变强",
            "family": "成长",
            "when_to_use": "境界提升、能力升级、关键成长。",
            "applicable_scenes": ["突破门槛", "掌握新能力", "战力跃迁"],
            "sequence": ["遇到门槛", "扛住压力", "完成突破", "看见新问题"],
            "turning_points": ["卡点明确", "过程吃力", "成功后代价或新麻烦出现"],
            "resource_nodes": ["突破资源", "新能力"],
            "relation_nodes": ["旁人重新估量", "旧关系受影响"],
            "preferred_event_types": ["资源获取类", "外部任务类", "危机爆发"],
            "preferred_progress_kinds": ["实力推进"],
            "preferred_hook_styles": ["人物选择", "危险逼近"],
            "keyword_hints": ["突破", "变强", "晋升", "掌握", "更强"],
            "closing_feel": "变强是真的，新麻烦也是真的。",
            "variation_notes": "突破不能只有数值，要带来新边界。",
        },
        {
            "flow_id": "calm_hidden_needle",
            "quick_tag": "先缓缓",
            "name": "平静藏针",
            "family": "铺垫",
            "when_to_use": "需要缓节奏，但不能水。",
            "applicable_scenes": ["短暂平静", "日常处理", "静里埋线"],
            "sequence": ["表面平静", "处理小事", "暗中埋线"],
            "turning_points": ["节奏放缓", "小事带出信息", "尾部埋下隐针"],
            "resource_nodes": ["日常资源", "旧物细节"],
            "relation_nodes": ["人物日常互动", "暗线变化"],
            "preferred_event_types": ["发现类", "关系推进类"],
            "preferred_progress_kinds": ["信息推进", "关系推进"],
            "preferred_hook_styles": ["平稳过渡", "余味收束"],
            "keyword_hints": ["平静", "日常", "缓", "小事", "暗藏"],
            "closing_feel": "表面没炸，底下已经埋了针。",
            "variation_notes": "平静章必须埋下一根具体针，不然就会水。",
        },
        {
            "flow_id": "situation_flip",
            "quick_tag": "反转了",
            "name": "局势翻面",
            "family": "反转",
            "when_to_use": "一章里需要明显转折，让旧判断失效。",
            "applicable_scenes": ["判断出错", "反转揭露", "局势倒拐"],
            "sequence": ["按旧判断行动", "发现判断错了", "局势反过来"],
            "turning_points": ["前半按旧逻辑推进", "中段发现关键误差", "后半局势翻面"],
            "resource_nodes": ["被误判的筹码", "新出现的限制"],
            "relation_nodes": ["敌我认知变化", "立场重新排序"],
            "preferred_event_types": ["反制类", "危机爆发", "发现类"],
            "preferred_progress_kinds": ["风险升级", "信息推进"],
            "preferred_hook_styles": ["信息反转", "危险逼近"],
            "keyword_hints": ["反转", "翻面", "判断错", "局势变了", "掉头"],
            "closing_feel": "原计划得推翻重来。",
            "variation_notes": "反转要建立在前文线索上，别硬拐。",
        },
    ]



def build_template_library(payload: NovelCreate) -> dict[str, Any]:
    character_templates = build_character_templates(payload)
    flow_templates = build_flow_templates()
    return {
        "character_templates": character_templates,
        "flow_templates": flow_templates,
        "roadmap": {
            "character_template_target_count": 40,
            "flow_template_target_count": 20,
            "current_character_template_count": len(character_templates),
            "current_flow_template_count": len(flow_templates),
            "status": "foundation_ready",
            "note": "人物模板库已扩到首批可用规模，后续继续补风格缝隙与题材特化模板。",
        },
    }



def build_story_domains(
    payload: NovelCreate,
    *,
    first_arc: dict[str, Any] | None = None,
    world_bible: dict[str, Any] | None = None,
    cultivation_system: dict[str, Any] | None = None,
) -> dict[str, Any]:
    style = payload.style_preferences or {}
    protagonist_name = _text(payload.protagonist_name, "主角")
    active_arc = first_arc or {}
    world = world_bible or _default_world_bible(payload)
    cultivation = cultivation_system or _default_cultivation_system(payload)
    protagonist_realm = _text(style.get("initial_realm"), (_safe_list(cultivation.get("realms")) or ["低阶求生阶段"])[0])
    protagonist_goal = _text(active_arc.get("focus"), "确认线索、避免暴露、拿到小资源。")
    protagonist_resource_inputs = [str(item).strip() for item in _safe_list(style.get("current_resources")) if str(item).strip()]
    protagonist_resources = normalize_resource_refs(protagonist_resource_inputs)

    characters = {
        protagonist_name: {
            "name": protagonist_name,
            "entity_type": "character",
            "role_type": "protagonist",
            "importance_tier": "核心主角",
            "protagonist_relation_level": "self",
            "narrative_priority": 100,
            "current_strength": protagonist_realm,
            "current_goal": protagonist_goal,
            "core_desire": _text(style.get("core_desire"), "活下去并掌握主动权。"),
            "core_fear": _text(style.get("core_fear"), "秘密暴露、失去退路、被更高位者盯上。"),
            "behavior_template_id": "starter_cautious_observer",
            "speech_style": "简短、留后手、尽量不把真实判断一次说满。",
            "work_style": "先观察和试探，再决定是否行动；轻易不把底牌摆到台面上。",
            "relationship_index": {},
            "resource_refs": protagonist_resources,
            "faction_refs": ["主角阵营"],
            "status": "active",
        }
    }

    resources: dict[str, dict[str, Any]] = {}
    for raw_name in protagonist_resource_inputs:
        name, card = build_resource_card(
            raw_name,
            owner=protagonist_name,
            resource_type="初始资源",
            status="持有中",
            rarity="普通/待判定",
            exposure_risk="低到中，取决于是否被外界注意。",
            narrative_role="主角当前立足资源。",
            recent_change="初始化写入。",
            source="story_domain_seed",
        )
        if name:
            resources.setdefault(name, card)

    factions = {
        "主角阵营": {
            "name": "主角阵营",
            "entity_type": "faction",
            "faction_level": "个人",
            "faction_type": "临时自保单元",
            "territory": "当前立足区域",
            "core_goal": "先活下去，再建立稳定立足点。",
            "relation_to_protagonist": "self",
            "resource_control": protagonist_resources,
            "key_characters": [protagonist_name],
        }
    }
    for item in _safe_list(world.get("factions")):
        name = _text(item)
        if not name:
            continue
        factions.setdefault(
            name,
            {
                "name": name,
                "entity_type": "faction",
                "faction_level": "地区级/待细化",
                "faction_type": "既有势力",
                "territory": "待后续章节补充",
                "core_goal": "控制资源、维持影响力并压住风险。",
                "relation_to_protagonist": "待观察",
                "resource_control": [],
                "key_characters": [],
            },
        )

    return {
        "characters": characters,
        "resources": resources,
        "relations": {},
        "factions": factions,
    }



def build_planner_state() -> dict[str, Any]:
    return {
        "recent_flow_usage": [],
        "chapter_element_selection": {},
        "resource_plan_cache": {},
        "resource_capability_plan_cache": {},
        "resource_plan_history": [],
        "resource_capability_history": [],
        "selected_entities_by_chapter": {},
        "continuity_packet_cache": {},
        "rolling_continuity_history": [],
        "last_planned_chapter": 0,
        "last_continuity_review_chapter": 0,
        "status": "foundation_ready",
    }



def build_core_cast_state_payload(payload: NovelCreate) -> dict[str, Any]:
    return build_core_cast_state(payload)


def build_retrospective_state() -> dict[str, Any]:
    return {
        "last_review_chapter": 0,
        "last_stage_review_chapter": 0,
        "pending_character_reviews": [],
        "relationship_watchlist": [],
        "scheduled_review_interval": 5,
        "last_review_notes": [],
        "latest_stage_character_review": {},
        "status": "foundation_ready",
    }



def build_flow_control() -> dict[str, Any]:
    return {
        "anti_repeat_window": 5,
        "recent_event_types": [],
        "recent_flow_ids": [],
        "consecutive_flow_penalty": 2,
        "status": "foundation_ready",
    }



def build_entity_registry() -> dict[str, Any]:
    return {
        "by_type": {
            "character": [],
            "resource": [],
            "relation": [],
            "faction": [],
        },
        "card_ids": {
            "character": {},
            "resource": {},
            "relation": {},
            "faction": {},
        },
        "next_seq": {
            "character": 1,
            "resource": 1,
            "relation": 1,
            "faction": 1,
        },
        "last_rebuilt_at": None,
    }



def build_project_card(
    payload: NovelCreate,
    title: str,
    global_outline: dict[str, Any],
    story_engine_diagnosis: dict[str, Any] | None = None,
    story_strategy_card: dict[str, Any] | None = None,
) -> dict[str, Any]:
    diagnosis = deepcopy(story_engine_diagnosis or _fallback_story_engine_profile(payload))
    strategy = deepcopy(story_strategy_card or _fallback_first_30_engine(payload))
    first_30_summary = _text(strategy.get("first_30_mainline_summary"), _text(payload.style_preferences.get("first_30_chapter_mainline"), "前30章围绕立足、关系绑定、阶段破局与更大局势展开。"))
    protagonist_defaults = {
        "name": _text(payload.protagonist_name),
        "core_desire": _text(payload.style_preferences.get("core_desire"), "先活下去，再争取更稳的立足点与主动权。"),
        "core_fear": _text(payload.style_preferences.get("core_fear"), "秘密暴露、失去退路、被更高位者盯上。"),
        "advantage": _text(payload.style_preferences.get("advantage"), "谨慎、耐心、肯观察，有能力从细节里找生机。"),
        "flaw": _text(payload.style_preferences.get("flaw"), "过度克制，容易把代价都压到自己身上。"),
    }
    return {
        "book_title": title,
        "genre_positioning": _text(payload.genre),
        "genre_subtypes": _safe_list(diagnosis.get("story_subgenres")),
        "core_sell_point": _sell_line(payload),
        "one_line_intro": _one_line_intro(payload, title),
        "protagonist": protagonist_defaults,
        "golden_finger": _golden_finger(payload),
        "story_engine_profile": diagnosis,
        "first_30_chapter_engine": strategy,
        "first_30_chapter_mainline": first_30_summary,
        "mid_term_direction": _mid_term_direction(global_outline),
        "endgame_direction": _endgame_direction(global_outline, payload),
    }


def build_control_console(payload: NovelCreate, first_arc: dict[str, Any] | None = None) -> dict[str, Any]:
    protagonist_name = _text(payload.protagonist_name)
    active_arc = first_arc or {}
    near_window = []
    for chapter in _safe_list(active_arc.get("chapters"))[:7]:
        near_window.append(
            {
                "chapter_no": int(chapter.get("chapter_no", 0) or 0),
                "title": _text(chapter.get("title"), f"第{chapter.get('chapter_no', '')}章"),
                "goal": _text(chapter.get("goal"), "推进当前主线"),
                "hook": _text(chapter.get("ending_hook"), "新问题浮出"),
                "event_type": _text(chapter.get("event_type"), "试探类"),
                "progress_kind": _text(chapter.get("progress_kind"), "信息推进"),
            }
        )
    return {
        "protagonist_state": {
            "current_realm": _text(payload.style_preferences.get("initial_realm"), "未显明确高阶境界，处于低阶求生阶段"),
            "combat_positioning": _text(payload.style_preferences.get("initial_combat_positioning"), "偏弱但谨慎，有特定场景下的应对手段。"),
            "main_skill": _text(payload.style_preferences.get("main_skill"), "观察、试探、藏拙、借力打力"),
            "core_methods": _safe_list(payload.style_preferences.get("core_methods")) or ["观察", "试探", "遮掩", "反击"],
            "ultimate_card": _text(payload.style_preferences.get("ultimate_card"), "尚未完全兑现的异常线索 / 核心机缘"),
            "current_limits": _text(payload.style_preferences.get("current_limits"), "资源少、力量弱、退路窄，不能轻易暴露。"),
            "current_resources": _safe_list(payload.style_preferences.get("current_resources")) or ["零碎资源", "有限情报", "尚未稳定的机缘"],
            "current_status": _text(payload.style_preferences.get("current_status"), "谨慎维持日常，边试探边隐藏。"),
            "current_goal": _text((active_arc or {}).get("focus"), "确认线索、避免暴露、拿到小资源。"),
            "main_enemy": _text(payload.style_preferences.get("initial_enemy"), "更高位的规则、资源压迫与潜在盯梢者。"),
            "exposure_risk": _text(payload.style_preferences.get("exposure_risk"), "异常一旦被看穿，主角会迅速失去安全区。"),
            "agency_cycle": {"recent_passive_chapters": 0, "force_proactive_before": 3},
        },
        "power_ledger": {
            "realm_weight_notes": "每个境界都要长期保持压迫感，不能前重后轻。",
            "same_realm_layers": "同境界内也分准备充分者、普通者、老手与天才。",
            "cross_realm_rules": _text(payload.style_preferences.get("cross_realm_rule"), "越阶战只能靠情报差、环境、代价与一次性底牌成立。"),
            "hard_no_cross_lines": ["大境界碾压不可常态硬跨", "受伤与消耗不能写了就忘"],
            "special_combat_features": _safe_list(payload.style_preferences.get("special_combat_features")) or ["信息差", "地形", "法器/材料", "时间差"],
        },
        "character_cards": {
            protagonist_name: {
                "name": protagonist_name,
                "role_type": "protagonist",
                "camp": "主角阵营",
                "current_strength": _text(payload.style_preferences.get("initial_realm"), "低阶求生阶段"),
                "core_desire": _text(payload.style_preferences.get("core_desire"), "活下去并掌握主动权。"),
                "core_fear": _text(payload.style_preferences.get("core_fear"), "秘密暴露、连累自己或身边人。"),
                "temperament": _text(payload.style_preferences.get("temperament"), "克制、警醒、耐心。"),
                "speech_style": "简短、留后手、尽量不把真实判断一次说满。",
                "work_style": "先观察和试探，再决定是否行动；轻易不把底牌摆到台面上。",
                "current_desire": _text(payload.style_preferences.get("core_desire"), "活下去并掌握主动权。"),
                "attitude_to_protagonist": "self",
                "recent_impact": "当前仍在为主线做出选择并承担代价。",
                "behavior_logic": "先观察和试探，再决定是否行动；轻易不把底牌摆到台面上。",
                "relationship_to_protagonist": "self",
                "hidden_secret": _golden_finger(payload),
                "current_plot_function": "推动视角、承接风险、做出选择。",
                "possible_change": "从被动求生转向更主动的布局。",
                "do_not_break": ["谨慎不等于停滞", "关键抉择时必须体现主动判断"],
            }
        },
        "relation_tracks": [],
        "foreshadowing": [],
        "timeline": [],
        "near_7_chapter_outline": near_window,
        "near_30_progress": {
            "current_position": "开书区 / 前30章",
            "current_volume_gap": "还在建立立足点与第一次上瘾点。",
            "next_big_payoff": _text((active_arc or {}).get("focus"), "第一次关键破局。"),
            "next_twist": _text((active_arc or {}).get("bridge_note"), "线索会把主角引向更危险的边缘试探。"),
        },
        "daily_workbench": {
            "yesterday_ending": "",
            "today_function": "",
            "three_line_outline": {"opening": "", "middle": "", "ending": ""},
            "tomorrow_hints": [],
        },
        "chapter_retrospectives": [],
        "volume_reviews": [],
    }
