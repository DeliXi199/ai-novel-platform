from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.services.generation_exceptions import ErrorCodes, GenerationError
from app.services.llm_runtime import call_json_response, is_openai_enabled, provider_name
from app.services.prompt_templates import payoff_card_selector_system_prompt, payoff_card_selector_user_prompt


RISK_TOKENS: tuple[str, ...] = (
    "暴露", "盯上", "追查", "危机", "退路", "后患", "代价", "限制", "麻烦", "围堵", "起疑", "压价", "逼近", "受挫", "失手",
)
PAYOFF_TOKENS: tuple[str, ...] = (
    "拿到", "换到", "确认", "得手", "松口", "答应", "落袋", "保住", "压住", "反手", "突破", "掌握", "翻盘", "到手",
)
PUBLIC_SCENE_HINTS: tuple[str, ...] = (
    "黑市", "坊市", "市集", "街", "大厅", "堂", "拍卖", "擂台", "广场", "众人", "人群", "当众", "宗门", "码头",
)
PRIVATE_SCENE_HINTS: tuple[str, ...] = (
    "房", "屋", "院", "密室", "角落", "山洞", "识海", "梦", "暗格", "后巷", "偏厅", "床边", "牢房",
)




def _raise_ai_required_error(*, stage: str, message: str, detail_reason: str = "", retryable: bool = True) -> None:
    raise GenerationError(
        code=ErrorCodes.AI_REQUIRED_UNAVAILABLE,
        message=f"{message}{('：' + detail_reason) if detail_reason else ''}",
        stage=stage,
        retryable=retryable,
        http_status=503,
        provider=provider_name(),
        details={"reason": detail_reason} if detail_reason else None,
    )

def _text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback



def _truncate_text(value: Any, limit: int) -> str:
    text = _text(value)
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    if limit == 1:
        return text[:1]
    return text[: limit - 1].rstrip() + "…"



def _unique_texts(values: list[Any] | None, *, limit: int, item_limit: int = 24) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
    for value in values or []:
        text = _truncate_text(value, item_limit)
        norm = "".join(text.split())
        if not norm or norm in seen:
            continue
        seen.add(norm)
        items.append(text)
        if len(items) >= limit:
            break
    return items



def build_payoff_cards() -> list[dict[str, Any]]:
    return [
        {
            "card_id": "payoff_hidden_snatch",
            "name": "捡漏反压",
            "family": "资源",
            "payoff_mode": "捡漏反压",
            "payoff_level": "medium",
            "payoff_visibility": "semi_public",
            "execution_cost": "low",
            "applicable_event_types": ["资源获取类", "交易类", "反制类"],
            "applicable_progress_kinds": ["资源推进", "信息推进"],
            "compatible_flows": ["resource_gain", "small_win_trap", "probe_gain"],
            "applicable_stages": ["opening", "early_mid", "mid"],
            "scene_visibility": ["public", "semi_public"],
            "protagonist_positions": ["weak", "balanced"],
            "requires_pressure_debt": False,
            "keyword_hints": ["低估", "压价", "换到", "捡漏", "落袋"],
            "reader_payoff": "主角以更低代价拿到关键资源或情报。",
            "new_pressure": "交易对象或旁观者开始重新估价主角。",
            "aftershock": "对方事后起疑，准备追查来路。",
            "external_reaction": "至少让一个旁人改口、迟疑或变脸。",
            "anti_repeat_key": "resource_reverse",
        },
        {
            "card_id": "payoff_public_face_slap",
            "name": "公开打脸",
            "family": "实力",
            "payoff_mode": "借势立威",
            "payoff_level": "strong",
            "payoff_visibility": "public",
            "execution_cost": "medium",
            "applicable_event_types": ["冲突类", "反制类", "关系推进类"],
            "applicable_progress_kinds": ["实力推进", "关系推进", "风险升级"],
            "compatible_flows": ["small_win_trap", "situation_flip", "breakthrough_grow"],
            "applicable_stages": ["early_mid", "mid", "late"],
            "scene_visibility": ["public"],
            "protagonist_positions": ["balanced", "strong"],
            "requires_pressure_debt": True,
            "keyword_hints": ["当众", "压住", "变脸", "场面", "不敢再"],
            "reader_payoff": "主角在公开场合压住轻视者，让场面转向自己。",
            "new_pressure": "更高位的人开始留意主角。",
            "aftershock": "风头抬高，后续盯防也会更紧。",
            "external_reaction": "必须写出人群、旁观者或对手的即时反应。",
            "anti_repeat_key": "public_face_slap",
        },
        {
            "card_id": "payoff_hidden_edge",
            "name": "藏锋显边",
            "family": "实力",
            "payoff_mode": "隐藏实力小爆",
            "payoff_level": "medium",
            "payoff_visibility": "semi_public",
            "execution_cost": "low",
            "applicable_event_types": ["试探类", "发现类", "冲突类"],
            "applicable_progress_kinds": ["实力推进", "信息推进"],
            "compatible_flows": ["probe_gain", "breakthrough_grow", "situation_flip"],
            "applicable_stages": ["opening", "early_mid", "mid"],
            "scene_visibility": ["semi_public", "private"],
            "protagonist_positions": ["weak", "balanced"],
            "requires_pressure_debt": False,
            "keyword_hints": ["藏着", "试出", "显出", "一手", "没想到"],
            "reader_payoff": "主角只露一线锋芒，就把局势拨向有利方向。",
            "new_pressure": "知道的人不多，但关键人开始提高警惕。",
            "aftershock": "后续必须更小心掩饰底牌。",
            "external_reaction": "至少让一个关键人意识到自己先前判断错了。",
            "anti_repeat_key": "hidden_edge",
        },
        {
            "card_id": "payoff_rule_loophole",
            "name": "借规矩反赢",
            "family": "智谋",
            "payoff_mode": "借势立威",
            "payoff_level": "medium",
            "payoff_visibility": "public",
            "execution_cost": "medium",
            "applicable_event_types": ["交易类", "外部任务类", "反制类"],
            "applicable_progress_kinds": ["信息推进", "关系推进", "资源推进"],
            "compatible_flows": ["forced_choice", "situation_flip", "resource_gain"],
            "applicable_stages": ["opening", "early_mid", "mid", "late"],
            "scene_visibility": ["public", "semi_public"],
            "protagonist_positions": ["weak", "balanced"],
            "requires_pressure_debt": False,
            "keyword_hints": ["规矩", "条件", "话头", "名分", "借着"],
            "reader_payoff": "主角借对方自己立下的规矩反手占到便宜。",
            "new_pressure": "对方嘴上不好反悔，只能转去暗地里找补。",
            "aftershock": "表面赢了规矩，私下会多出新敌意。",
            "external_reaction": "对手必须出现噎住、改口或强行找台阶的反应。",
            "anti_repeat_key": "rule_loophole",
        },
        {
            "card_id": "payoff_old_debt_reverse",
            "name": "旧账反收",
            "family": "关系",
            "payoff_mode": "旧账反收",
            "payoff_level": "strong",
            "payoff_visibility": "semi_public",
            "execution_cost": "medium",
            "applicable_event_types": ["关系推进类", "反制类", "冲突类"],
            "applicable_progress_kinds": ["关系推进", "风险升级"],
            "compatible_flows": ["relationship_crack", "small_win_trap", "situation_flip"],
            "applicable_stages": ["early_mid", "mid", "late"],
            "scene_visibility": ["semi_public", "private"],
            "protagonist_positions": ["weak", "balanced", "strong"],
            "requires_pressure_debt": True,
            "keyword_hints": ["旧账", "还回来", "先前", "记着", "逼回去"],
            "reader_payoff": "主角把前面积下的一口气连本带利收回来。",
            "new_pressure": "旧怨真正坐实，关系很难回到原点。",
            "aftershock": "对方会把这笔账记得更死。",
            "external_reaction": "必须让对方或旁人意识到局面已经反过来。",
            "anti_repeat_key": "old_debt_reverse",
        },
        {
            "card_id": "payoff_small_win_mine",
            "name": "小胜埋雷",
            "family": "综合",
            "payoff_mode": "小胜埋雷",
            "payoff_level": "medium",
            "payoff_visibility": "semi_public",
            "execution_cost": "low",
            "applicable_event_types": ["资源获取类", "反制类", "发现类"],
            "applicable_progress_kinds": ["资源推进", "风险升级", "信息推进"],
            "compatible_flows": ["small_win_trap", "probe_gain", "resource_gain"],
            "applicable_stages": ["opening", "early_mid", "mid", "late"],
            "scene_visibility": ["public", "semi_public", "private"],
            "protagonist_positions": ["weak", "balanced"],
            "requires_pressure_debt": False,
            "keyword_hints": ["得手", "后患", "记住", "隐患", "先赢一手"],
            "reader_payoff": "主角先赢到一手实在好处，本章读感不能只有吃压。",
            "new_pressure": "好处刚落袋，后患就开始抬头。",
            "aftershock": "下一章能自然接到追查、盯梢或代价抬高。",
            "external_reaction": "至少写出一处“别人开始注意/起疑/记住主角”的显影。",
            "anti_repeat_key": "small_win_mine",
        },
        {
            "card_id": "payoff_set_trap_collect",
            "name": "设局回收",
            "family": "智谋",
            "payoff_mode": "设局反收",
            "payoff_level": "strong",
            "payoff_visibility": "semi_public",
            "execution_cost": "high",
            "applicable_event_types": ["反制类", "发现类", "冲突类"],
            "applicable_progress_kinds": ["信息推进", "关系推进", "风险升级"],
            "compatible_flows": ["situation_flip", "forced_choice", "small_win_trap"],
            "applicable_stages": ["mid", "late"],
            "scene_visibility": ["semi_public", "private"],
            "protagonist_positions": ["balanced", "strong"],
            "requires_pressure_debt": True,
            "keyword_hints": ["故意", "留口", "套出", "回收", "反手"],
            "reader_payoff": "主角前面埋的小局在本章回收，读者能感到‘原来早有准备’。",
            "new_pressure": "对手会意识到自己被试探过。",
            "aftershock": "信息差优势暴露，后续对手会更谨慎。",
            "external_reaction": "必须让对手出现说漏嘴、失衡或补救过晚。",
            "anti_repeat_key": "set_trap_collect",
        },
        {
            "card_id": "payoff_trade_crush",
            "name": "压价反杀",
            "family": "资源",
            "payoff_mode": "压价反杀",
            "payoff_level": "medium",
            "payoff_visibility": "public",
            "execution_cost": "low",
            "applicable_event_types": ["交易类", "资源获取类"],
            "applicable_progress_kinds": ["资源推进", "关系推进"],
            "compatible_flows": ["resource_gain", "small_win_trap", "probe_gain"],
            "applicable_stages": ["opening", "early_mid", "mid"],
            "scene_visibility": ["public", "semi_public"],
            "protagonist_positions": ["weak", "balanced"],
            "requires_pressure_debt": False,
            "keyword_hints": ["还价", "压价", "筹码", "交易", "换手"],
            "reader_payoff": "主角在交易桌上不靠硬打，靠判断把价码压回来了。",
            "new_pressure": "掌柜或对手会重新评估主角的分量。",
            "aftershock": "这条交易线会从此带上戒心。",
            "external_reaction": "让对方改口、迟疑、沉默，或转而试探主角底细。",
            "anti_repeat_key": "trade_crush",
        },
        {
            "card_id": "payoff_misjudge_flip",
            "name": "误判翻盘",
            "family": "综合",
            "payoff_mode": "误判翻盘",
            "payoff_level": "strong",
            "payoff_visibility": "public",
            "execution_cost": "medium",
            "applicable_event_types": ["冲突类", "试探类", "发现类"],
            "applicable_progress_kinds": ["信息推进", "实力推进", "关系推进"],
            "compatible_flows": ["situation_flip", "probe_gain", "small_win_trap"],
            "applicable_stages": ["opening", "early_mid", "mid", "late"],
            "scene_visibility": ["public", "semi_public"],
            "protagonist_positions": ["weak", "balanced"],
            "requires_pressure_debt": True,
            "keyword_hints": ["看低", "误判", "翻过来", "没想到", "改口"],
            "reader_payoff": "别人按旧判断来压主角，结果被主角顺手翻了回来。",
            "new_pressure": "对手会调整打法，不再按原来的轻视方式行动。",
            "aftershock": "主角的‘不好惹’开始扩散。",
            "external_reaction": "必须让至少一个人承认或体现出‘先前看走眼了’。",
            "anti_repeat_key": "misjudge_flip",
        },
        {
            "card_id": "payoff_relation_reverse",
            "name": "态度逆转",
            "family": "关系",
            "payoff_mode": "关系倒转",
            "payoff_level": "medium",
            "payoff_visibility": "semi_public",
            "execution_cost": "low",
            "applicable_event_types": ["关系推进类", "交易类", "发现类"],
            "applicable_progress_kinds": ["关系推进", "信息推进"],
            "compatible_flows": ["relationship_warm", "probe_gain", "forced_choice"],
            "applicable_stages": ["opening", "early_mid", "mid", "late"],
            "scene_visibility": ["semi_public", "private"],
            "protagonist_positions": ["weak", "balanced", "strong"],
            "requires_pressure_debt": False,
            "keyword_hints": ["改观", "松口", "另眼相看", "不再", "态度"],
            "reader_payoff": "一个原本不愿站队的人，在本章明显改了态度。",
            "new_pressure": "关系一旦偏转，新的期待与风险也会跟着来。",
            "aftershock": "主角接下来要承担更多被期待或被怀疑的重量。",
            "external_reaction": "让称呼、语气、站位或让利出现可见变化。",
            "anti_repeat_key": "relation_reverse",
        },
        {
            "card_id": "payoff_borrow_force",
            "name": "借势反打",
            "family": "智谋",
            "payoff_mode": "借势立威",
            "payoff_level": "medium",
            "payoff_visibility": "public",
            "execution_cost": "medium",
            "applicable_event_types": ["反制类", "外部任务类", "关系推进类"],
            "applicable_progress_kinds": ["关系推进", "风险升级", "信息推进"],
            "compatible_flows": ["forced_choice", "situation_flip", "pressure_close"],
            "applicable_stages": ["early_mid", "mid", "late"],
            "scene_visibility": ["public", "semi_public"],
            "protagonist_positions": ["weak", "balanced"],
            "requires_pressure_debt": False,
            "keyword_hints": ["借着", "规矩", "长辈", "名头", "势头"],
            "reader_payoff": "主角不靠蛮力，借外部规则或人情把局面拨过来。",
            "new_pressure": "借来的势也会反过来约束主角。",
            "aftershock": "后续得还人情，或被更高位的人记住。",
            "external_reaction": "至少让对手出现‘明知不爽也得收手’的反应。",
            "anti_repeat_key": "borrow_force",
        },
        {
            "card_id": "payoff_one_move_silence",
            "name": "一手镇场",
            "family": "实力",
            "payoff_mode": "一手镇场",
            "payoff_level": "strong",
            "payoff_visibility": "public",
            "execution_cost": "medium",
            "applicable_event_types": ["冲突类", "危机爆发", "反制类"],
            "applicable_progress_kinds": ["实力推进", "风险升级"],
            "compatible_flows": ["breakthrough_grow", "small_win_trap", "situation_flip"],
            "applicable_stages": ["mid", "late"],
            "scene_visibility": ["public"],
            "protagonist_positions": ["balanced", "strong"],
            "requires_pressure_debt": True,
            "keyword_hints": ["安静", "压住", "不敢再", "场面", "镇住"],
            "reader_payoff": "主角只用一手就让场面安静下来，获得短暂主导权。",
            "new_pressure": "风头太显，后续压力也会更集中。",
            "aftershock": "更强的对手会更快找上门。",
            "external_reaction": "必须写出现场人声、动作或态度的收紧。",
            "anti_repeat_key": "one_move_silence",
        },
        {
            "card_id": "payoff_small_gain_big_echo",
            "name": "小收获大回响",
            "family": "资源",
            "payoff_mode": "小胜放大",
            "payoff_level": "medium",
            "payoff_visibility": "public",
            "execution_cost": "low",
            "applicable_event_types": ["发现类", "资源获取类", "关系推进类"],
            "applicable_progress_kinds": ["资源推进", "信息推进", "关系推进"],
            "compatible_flows": ["probe_gain", "resource_gain", "calm_hidden_needle"],
            "applicable_stages": ["opening", "early_mid", "mid"],
            "scene_visibility": ["public", "semi_public"],
            "protagonist_positions": ["weak", "balanced"],
            "requires_pressure_debt": False,
            "keyword_hints": ["一点", "却", "反应", "回响", "连锁"],
            "reader_payoff": "主角拿到的好处不算巨大，但引发的回响明显高于预期。",
            "new_pressure": "更多人因此开始注意这条线。",
            "aftershock": "下一章自然会有更高位的试探或觊觎。",
            "external_reaction": "至少让一个原本无关的人因此改变态度或插手。",
            "anti_repeat_key": "small_gain_big_echo",
        },
        {
            "card_id": "payoff_private_confirm",
            "name": "私下坐实",
            "family": "信息",
            "payoff_mode": "验证坐实",
            "payoff_level": "medium",
            "payoff_visibility": "private",
            "execution_cost": "low",
            "applicable_event_types": ["发现类", "试探类", "外部任务类"],
            "applicable_progress_kinds": ["信息推进", "实力推进"],
            "compatible_flows": ["probe_gain", "prepare_first", "calm_hidden_needle"],
            "applicable_stages": ["opening", "early_mid", "mid", "late"],
            "scene_visibility": ["private", "semi_public"],
            "protagonist_positions": ["weak", "balanced", "strong"],
            "requires_pressure_debt": False,
            "keyword_hints": ["确认", "印证", "对上", "坐实", "验证"],
            "reader_payoff": "主角亲手把一个关键判断坐实，读者获得明确进展。",
            "new_pressure": "知道得更清楚，也意味着退路更窄。",
            "aftershock": "下一章必须围绕这条坐实结果推进。",
            "external_reaction": "即便是暗爽，也要让主角的后续动作立刻发生变化。",
            "anti_repeat_key": "private_confirm",
        },
        {
            "card_id": "payoff_counter_offer",
            "name": "反手加码",
            "family": "交易",
            "payoff_mode": "反手加码",
            "payoff_level": "medium",
            "payoff_visibility": "semi_public",
            "execution_cost": "low",
            "applicable_event_types": ["交易类", "关系推进类"],
            "applicable_progress_kinds": ["资源推进", "关系推进"],
            "compatible_flows": ["forced_choice", "resource_gain", "relationship_warm"],
            "applicable_stages": ["opening", "early_mid", "mid", "late"],
            "scene_visibility": ["semi_public", "public"],
            "protagonist_positions": ["weak", "balanced"],
            "requires_pressure_debt": False,
            "keyword_hints": ["加码", "条件", "反手", "换一个", "筹码"],
            "reader_payoff": "对方以为主角只能答应，结果主角反手改了条件。",
            "new_pressure": "谈判门槛被抬高，关系也变得更微妙。",
            "aftershock": "后续合作或对立都会更有火药味。",
            "external_reaction": "让对方出现短暂停顿、迟疑或重新审视主角。",
            "anti_repeat_key": "counter_offer",
        },
        {
            "card_id": "payoff_reverse_pressure_choice",
            "name": "逆压硬吃",
            "family": "抉择",
            "payoff_mode": "逆压硬吃",
            "payoff_level": "strong",
            "payoff_visibility": "semi_public",
            "execution_cost": "high",
            "applicable_event_types": ["危机爆发", "外部任务类", "冲突类"],
            "applicable_progress_kinds": ["风险升级", "实力推进", "关系推进"],
            "compatible_flows": ["forced_choice", "pressure_close", "breakthrough_grow"],
            "applicable_stages": ["mid", "late"],
            "scene_visibility": ["public", "semi_public", "private"],
            "protagonist_positions": ["balanced", "strong"],
            "requires_pressure_debt": True,
            "keyword_hints": ["硬着头皮", "退路", "扛下", "索性", "押上"],
            "reader_payoff": "主角明知代价更重，还是反手把被动局吃成自己的节奏。",
            "new_pressure": "这一步虽然值，但后续代价会真的落下来。",
            "aftershock": "章末要让代价或后患冒头，别写成白赚。",
            "external_reaction": "让周围人意识到主角不是被推着走，而是在主动选更狠的路。",
            "anti_repeat_key": "reverse_pressure_choice",
        },
        {
            "card_id": "payoff_partner_shift",
            "name": "搭档换挡",
            "family": "关系",
            "payoff_mode": "搭档提档",
            "payoff_level": "medium",
            "payoff_visibility": "semi_public",
            "execution_cost": "low",
            "applicable_event_types": ["关系推进类", "外部任务类", "发现类"],
            "applicable_progress_kinds": ["关系推进", "信息推进"],
            "compatible_flows": ["relationship_warm", "prepare_first", "probe_gain"],
            "applicable_stages": ["opening", "early_mid", "mid"],
            "scene_visibility": ["semi_public", "private"],
            "protagonist_positions": ["weak", "balanced", "strong"],
            "requires_pressure_debt": False,
            "keyword_hints": ["搭手", "帮忙", "换他来", "第一次", "配合"],
            "reader_payoff": "一个配角不再只是工具人，而是在关键处真正接住了主角。",
            "new_pressure": "关系一旦变深，就更怕之后失去或背刺。",
            "aftershock": "把这条绑定关系推入更难回头的新阶段。",
            "external_reaction": "通过分工、站位或一句关键表态体现关系升级。",
            "anti_repeat_key": "partner_shift",
        },
        {
            "card_id": "payoff_enemy_miscalc",
            "name": "敌手吃瘪",
            "family": "反制",
            "payoff_mode": "让对手吃瘪",
            "payoff_level": "medium",
            "payoff_visibility": "public",
            "execution_cost": "medium",
            "applicable_event_types": ["反制类", "冲突类", "发现类"],
            "applicable_progress_kinds": ["关系推进", "风险升级", "信息推进"],
            "compatible_flows": ["small_win_trap", "situation_flip", "pressure_close"],
            "applicable_stages": ["opening", "early_mid", "mid", "late"],
            "scene_visibility": ["public", "semi_public"],
            "protagonist_positions": ["weak", "balanced"],
            "requires_pressure_debt": True,
            "keyword_hints": ["吃瘪", "算错", "落空", "扑空", "没占到"],
            "reader_payoff": "对手来压一手，结果这一下没压成，还反过来掉了面子。",
            "new_pressure": "对手吃瘪后会更认真，也会更记恨。",
            "aftershock": "下一章要让对方的反扑可能性存在。",
            "external_reaction": "不能只写主角爽，要写对手没拿到预期结果的狼狈。",
            "anti_repeat_key": "enemy_miscalc",
        },
        {
            "card_id": "payoff_identity_glint",
            "name": "身份露边",
            "family": "身份",
            "payoff_mode": "真实价值露边",
            "payoff_level": "medium",
            "payoff_visibility": "public",
            "execution_cost": "medium",
            "applicable_event_types": ["发现类", "关系推进类", "冲突类"],
            "applicable_progress_kinds": ["关系推进", "信息推进", "风险升级"],
            "compatible_flows": ["situation_flip", "relationship_warm", "small_win_trap"],
            "applicable_stages": ["early_mid", "mid", "late"],
            "scene_visibility": ["public", "semi_public"],
            "protagonist_positions": ["weak", "balanced"],
            "requires_pressure_debt": False,
            "keyword_hints": ["身份", "来路", "认出", "不简单", "另眼相看"],
            "reader_payoff": "主角的真实价值被人瞥见一角，读者能感到地位开始变化。",
            "new_pressure": "被认出的风险也会随之升高。",
            "aftershock": "这条身份线后续会引出更高层人物或更深追查。",
            "external_reaction": "让旁人称呼、语气或警惕程度出现明显变化。",
            "anti_repeat_key": "identity_glint",
        },
        {
            "card_id": "payoff_resource_protect",
            "name": "保住底牌",
            "family": "资源",
            "payoff_mode": "保住关键资源",
            "payoff_level": "medium",
            "payoff_visibility": "private",
            "execution_cost": "low",
            "applicable_event_types": ["危机爆发", "反制类", "外部任务类"],
            "applicable_progress_kinds": ["资源推进", "风险升级"],
            "compatible_flows": ["pressure_close", "resource_loss", "forced_choice"],
            "applicable_stages": ["opening", "early_mid", "mid", "late"],
            "scene_visibility": ["private", "semi_public"],
            "protagonist_positions": ["weak", "balanced", "strong"],
            "requires_pressure_debt": True,
            "keyword_hints": ["保住", "没丢", "藏下", "护住", "底牌"],
            "reader_payoff": "本章不是大赚，而是把关键底牌险险保住，读者应感到值。",
            "new_pressure": "资源虽然保住了，但使用空间会更小。",
            "aftershock": "后续要么尽快转移，要么接受更高风险。",
            "external_reaction": "即便是暗爽，也要通过主角立刻调整后续动作来显影。",
            "anti_repeat_key": "resource_protect",
        },
        {
            "card_id": "payoff_breakthrough_echo",
            "name": "突破回响",
            "family": "实力",
            "payoff_mode": "突破回响",
            "payoff_level": "strong",
            "payoff_visibility": "semi_public",
            "execution_cost": "high",
            "applicable_event_types": ["资源获取类", "危机爆发", "外部任务类"],
            "applicable_progress_kinds": ["实力推进", "风险升级"],
            "compatible_flows": ["breakthrough_grow", "prepare_first", "small_win_trap"],
            "applicable_stages": ["early_mid", "mid", "late"],
            "scene_visibility": ["semi_public", "private", "public"],
            "protagonist_positions": ["balanced", "strong"],
            "requires_pressure_debt": True,
            "keyword_hints": ["突破", "稳住", "更进一步", "回响", "新边界"],
            "reader_payoff": "主角这次变强不是空涨数值，而是立刻改变了本章局面。",
            "new_pressure": "新能力带来的边界、代价或被注意风险也同步出现。",
            "aftershock": "结尾要让‘变强后的新麻烦’冒头。",
            "external_reaction": "至少写出自己或他人对这次变化的即时判断改变。",
            "anti_repeat_key": "breakthrough_echo",
        },
        {
            "card_id": "payoff_quiet_settle",
            "name": "静里落袋",
            "family": "信息",
            "payoff_mode": "暗爽落袋",
            "payoff_level": "medium",
            "payoff_visibility": "private",
            "execution_cost": "low",
            "applicable_event_types": ["发现类", "关系推进类", "日常类"],
            "applicable_progress_kinds": ["信息推进", "资源推进", "关系推进"],
            "compatible_flows": ["calm_hidden_needle", "prepare_first", "probe_gain"],
            "applicable_stages": ["opening", "early_mid", "mid", "late"],
            "scene_visibility": ["private", "semi_public"],
            "protagonist_positions": ["weak", "balanced", "strong"],
            "requires_pressure_debt": False,
            "keyword_hints": ["落袋", "记下", " quietly", "收好", "先藏"],
            "reader_payoff": "本章可以不炸场，但要让主角悄悄拿到真东西。",
            "new_pressure": "东西是拿到了，可还没到能公开的时候。",
            "aftershock": "后续围绕隐藏、使用和暴露风险继续推进。",
            "external_reaction": "暗爽也要写出主角立刻改变路线、计划或态度。",
            "anti_repeat_key": "quiet_settle",
        },
    ]



def ensure_payoff_library(story_bible: dict[str, Any]) -> list[dict[str, Any]]:
    template_library = story_bible.setdefault("template_library", {})
    payoff_cards = template_library.get("payoff_cards")
    if not isinstance(payoff_cards, list) or not payoff_cards:
        payoff_cards = build_payoff_cards()
        template_library["payoff_cards"] = payoff_cards
    roadmap = template_library.setdefault("roadmap", {})
    roadmap.setdefault("payoff_card_target_count", 20)
    roadmap["current_payoff_card_count"] = len(payoff_cards)
    return payoff_cards



def _chapter_stage(chapter_no: int) -> str:
    if chapter_no <= 15:
        return "opening"
    if chapter_no <= 40:
        return "early_mid"
    if chapter_no <= 80:
        return "mid"
    return "late"



def _infer_scene_visibility(plan: dict[str, Any]) -> str:
    text = " ".join(
        _text(plan.get(key)) for key in ["main_scene", "goal", "conflict", "ending_hook", "payoff_or_pressure"]
    )
    if any(token in text for token in PUBLIC_SCENE_HINTS):
        return "public"
    if any(token in text for token in PRIVATE_SCENE_HINTS):
        return "private"
    return "semi_public"



def _infer_protagonist_position(plan: dict[str, Any], chapter_no: int) -> str:
    progress_kind = _text(plan.get("progress_kind"))
    flow_id = _text(plan.get("flow_template_id"))
    if chapter_no <= 12 or flow_id in {"probe_loss", "pressure_close", "resource_loss"}:
        return "weak"
    if progress_kind == "实力推进" or flow_id in {"breakthrough_grow", "conflict_upgrade"}:
        return "strong"
    return "balanced"



def _pressure_debt(recent_summaries: list[dict[str, Any]] | None) -> dict[str, Any]:
    summaries = list(recent_summaries or [])[-3:]
    risk_hits = 0
    payoff_hits = 0
    text_parts: list[str] = []
    for item in summaries:
        if not isinstance(item, dict):
            continue
        text = " ".join([_text(item.get("event_summary")), *[_text(x) for x in (item.get("open_hooks") or [])[:3]]])
        text_parts.append(text)
        risk_hits += sum(text.count(token) for token in RISK_TOKENS)
        payoff_hits += sum(text.count(token) for token in PAYOFF_TOKENS)
    open_hook_count = sum(len((item.get("open_hooks") or [])[:3]) for item in summaries if isinstance(item, dict))
    debt_score = max(risk_hits - payoff_hits, 0) + (2 if open_hook_count >= 4 else 0) + (1 if open_hook_count >= 2 else 0)
    return {
        "recent_text": _truncate_text(" | ".join(part for part in text_parts if part), 180),
        "risk_hits": risk_hits,
        "payoff_hits": payoff_hits,
        "open_hook_count": open_hook_count,
        "pressure_debt_score": debt_score,
    }



def _recent_payoff_patterns(recent_plan_meta: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    patterns: list[dict[str, str]] = []
    for item in list(recent_plan_meta or [])[-3:]:
        if not isinstance(item, dict):
            continue
        packet = item.get("planning_packet") or {}
        selected = (packet.get("selected_payoff_card") or {}) if isinstance(packet, dict) else {}
        patterns.append(
            {
                "card_id": _text(selected.get("card_id")),
                "family": _text(selected.get("family")),
                "payoff_mode": _text(selected.get("payoff_mode")),
                "payoff_visibility": _text(selected.get("payoff_visibility")),
            }
        )
    return [item for item in patterns if any(item.values())]


def _debt_level(debt_score: int) -> str:
    if debt_score >= 5:
        return "high"
    if debt_score >= 2:
        return "medium"
    return "low"



def _recommended_payoff_level(debt_score: int) -> str:
    if debt_score >= 5:
        return "strong"
    if debt_score >= 2:
        return "medium"
    return "flex"



def _repeat_risk(selected_card: dict[str, Any], recent_patterns: list[dict[str, str]]) -> str:
    if not selected_card or not recent_patterns:
        return "low"
    same_card = 0
    same_mode = 0
    same_family = 0
    same_visibility = 0
    selected_card_id = _text(selected_card.get("card_id"))
    selected_mode = _text(selected_card.get("payoff_mode"))
    selected_family = _text(selected_card.get("family"))
    selected_visibility = _text(selected_card.get("payoff_visibility"))
    for item in recent_patterns:
        if selected_card_id and _text(item.get("card_id")) == selected_card_id:
            same_card += 1
        if selected_mode and _text(item.get("payoff_mode")) == selected_mode:
            same_mode += 1
        if selected_family and _text(item.get("family")) == selected_family:
            same_family += 1
        if selected_visibility and _text(item.get("payoff_visibility")) == selected_visibility:
            same_visibility += 1
    if same_card >= 1 or same_mode >= 2 or same_family >= 3:
        return "high"
    if same_mode >= 1 or same_family >= 2 or same_visibility >= 2:
        return "medium"
    return "low"



def _pending_payoff_compensation(story_bible: dict[str, Any], *, chapter_no: int) -> dict[str, Any]:
    retrospective_state = (story_bible or {}).get("retrospective_state") or {}
    payload = retrospective_state.get("pending_payoff_compensation") or {}
    if not isinstance(payload, dict) or not payload:
        return {}
    if not bool(payload.get("enabled", True)):
        return {}
    chapter_biases = payload.get("chapter_biases") or []
    for item in chapter_biases:
        if not isinstance(item, dict):
            continue
        if int(item.get("chapter_no", 0) or 0) != int(chapter_no or 0):
            continue
        return {
            "enabled": True,
            "source_chapter_no": int(payload.get("source_chapter_no", 0) or 0),
            "target_chapter_no": chapter_no,
            "priority": _text(item.get("priority") or payload.get("priority"), "medium"),
            "reason": _text(item.get("note") or payload.get("reason")),
            "note": _text(item.get("note") or payload.get("note") or payload.get("reason")),
            "window_role": _text(item.get("bias") or item.get("window_role"), "primary_repay"),
            "window_end_chapter_no": int(payload.get("window_end_chapter_no", 0) or 0),
            "should_reduce_pressure": bool(payload.get("should_reduce_pressure", True)),
        }
    target_chapter_no = int(payload.get("target_chapter_no", 0) or 0)
    if target_chapter_no and target_chapter_no != chapter_no:
        return {}
    return {
        "enabled": True,
        "source_chapter_no": int(payload.get("source_chapter_no", 0) or 0),
        "target_chapter_no": target_chapter_no or chapter_no,
        "priority": _text(payload.get("priority"), "medium"),
        "reason": _text(payload.get("reason")),
        "note": _text(payload.get("note") or payload.get("reason")),
        "window_role": _text(payload.get("window_role"), "primary_repay"),
        "window_end_chapter_no": int(payload.get("window_end_chapter_no", 0) or 0),
        "should_reduce_pressure": bool(payload.get("should_reduce_pressure", True)),
    }



def _repeat_risk(selected_card: dict[str, Any], recent_patterns: list[dict[str, str]]) -> str:
    if not selected_card or not recent_patterns:
        return "low"
    same_card = 0
    same_mode = 0
    same_family = 0
    same_visibility = 0
    selected_card_id = _text(selected_card.get("card_id"))
    selected_mode = _text(selected_card.get("payoff_mode"))
    selected_family = _text(selected_card.get("family"))
    selected_visibility = _text(selected_card.get("payoff_visibility"))
    for item in recent_patterns:
        if selected_card_id and _text(item.get("card_id")) == selected_card_id:
            same_card += 1
        if selected_mode and _text(item.get("payoff_mode")) == selected_mode:
            same_mode += 1
        if selected_family and _text(item.get("family")) == selected_family:
            same_family += 1
        if selected_visibility and _text(item.get("payoff_visibility")) == selected_visibility:
            same_visibility += 1
    if same_card >= 1 or same_mode >= 2 or same_family >= 3:
        return "high"
    if same_mode >= 1 or same_family >= 2 or same_visibility >= 2:
        return "medium"
    return "low"



def _build_payoff_diagnostics(
    *,
    pressure_debt: dict[str, Any],
    recent_patterns: list[dict[str, str]],
    selected_card: dict[str, Any],
    compensation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    debt_score = int(pressure_debt.get("pressure_debt_score") or 0)
    debt_level = _debt_level(debt_score)
    repeat_risk = _repeat_risk(selected_card, recent_patterns)
    recommended_level = _recommended_payoff_level(debt_score)
    compensation = compensation or {}
    if compensation:
        recommended_level = "strong" if _text(compensation.get("priority")) == "high" else ("medium" if recommended_level == "flex" else recommended_level)
    recent_modes = _unique_texts([item.get("payoff_mode") for item in recent_patterns], limit=3, item_limit=12)
    recent_families = _unique_texts([item.get("family") for item in recent_patterns], limit=3, item_limit=8)
    selected_name = _text(selected_card.get("name") or selected_card.get("payoff_mode"), "本章爽点")
    debt_note = {
        "high": "最近几章偏欠账，这章要把回报写得更响一点。",
        "medium": "最近节奏略欠回报，这章至少要有一手可感兑现。",
        "low": "最近回报不算缺，这章可以更讲究控制强弱。",
    }[debt_level]
    repeat_note = {
        "high": "当前爽点和最近几章撞型风险高，正文要明显换显影方式。",
        "medium": "当前爽点有一定重复味，别再写成同一套围观反应。",
        "low": "当前爽点和最近几章差异还行，可以放心落地。",
    }[repeat_risk]
    level_note = {
        "strong": "建议本章至少做中强度以上兑现，别只留压力。",
        "medium": "建议本章做一次明确落袋，不要全靠章末钩子撑着。",
        "flex": "本章可以轻重自控，但仍要给读者一个真东西。",
    }[recommended_level]
    summary_lines = [
        f"最近爽点欠账：{debt_level}（分值 {debt_score}）。",
        f"重复风险：{repeat_risk}；入选卡：{selected_name}。",
        debt_note,
        repeat_note,
        level_note,
    ]
    if compensation:
        summary_lines.append(_truncate_text(f"追账补偿：{_text(compensation.get('note') or compensation.get('reason'), '上一章兑现偏虚，这章优先追回一次明确回报。')}", 80))
    return {
        "pressure_debt_score": debt_score,
        "pressure_debt_level": debt_level,
        "repeat_risk": repeat_risk,
        "recommended_level": recommended_level,
        "recent_modes": recent_modes,
        "recent_families": recent_families,
        "compensation": compensation,
        "summary_lines": summary_lines,
    }



def _keyword_hit_score(card: dict[str, Any], plan_blob: str) -> float:
    score = 0.0
    for token in card.get("keyword_hints") or []:
        clean = _text(token)
        if clean and clean in plan_blob:
            score += 4.0
    return min(score, 16.0)



def _execution_cost_penalty(card: dict[str, Any], plan: dict[str, Any]) -> float:
    cost = _text(card.get("execution_cost"))
    chapter_type = _text(plan.get("chapter_type"))
    event_type = _text(plan.get("event_type"))
    if cost == "high" and chapter_type not in {"turning_point", "高潮", "big_turn"} and event_type not in {"危机爆发", "冲突类"}:
        return -9.0
    if cost == "medium" and event_type in {"发现类"}:
        return -2.0
    return 0.0



def _repeat_penalty(card: dict[str, Any], recent_patterns: list[dict[str, str]]) -> float:
    penalty = 0.0
    for idx, item in enumerate(reversed(recent_patterns), start=1):
        weight = max(4 - idx, 1)
        if _text(item.get("card_id")) and _text(item.get("card_id")) == _text(card.get("card_id")):
            penalty += 18.0 * weight
        if _text(item.get("family")) and _text(item.get("family")) == _text(card.get("family")):
            penalty += 6.0 * weight
        if _text(item.get("payoff_mode")) and _text(item.get("payoff_mode")) == _text(card.get("payoff_mode")):
            penalty += 8.0 * weight
        if _text(item.get("payoff_visibility")) and _text(item.get("payoff_visibility")) == _text(card.get("payoff_visibility")):
            penalty += 3.0 * weight
    return penalty



def _compensation_adjustment(card: dict[str, Any], compensation: dict[str, Any] | None) -> tuple[float, str | None]:
    payload = compensation or {}
    if not payload:
        return 0.0, None
    priority = _text(payload.get("priority"), "medium")
    level = _text(card.get("payoff_level"))
    mode = _text(card.get("payoff_mode"))
    visibility = _text(card.get("payoff_visibility"))
    score = 0.0
    if priority == "high":
        if level == "strong":
            score += 16.0
        elif level == "medium":
            score += 10.0
        else:
            score -= 6.0
        if visibility in {"public", "semi_public"}:
            score += 4.0
        if mode in {"小胜埋雷", "暗爽落袋"}:
            score -= 8.0
        return score, "上一章兑现偏虚，这章要优先追回一次更明确的回报"
    if level in {"medium", "strong"}:
        score += 6.0
    if visibility in {"public", "semi_public"}:
        score += 2.0
    return score, "上一章回报偏弱，这章别继续只蓄压"



def _score_payoff_card(
    card: dict[str, Any],
    *,
    plan: dict[str, Any],
    chapter_stage: str,
    scene_visibility: str,
    protagonist_position: str,
    pressure_debt: dict[str, Any],
    recent_patterns: list[dict[str, str]],
    compensation: dict[str, Any] | None = None,
) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 0.0
    event_type = _text(plan.get("event_type"))
    progress_kind = _text(plan.get("progress_kind"))
    flow_id = _text(plan.get("flow_template_id"))
    payoff_line = _text(plan.get("payoff_or_pressure"))
    plan_blob = " ".join(
        _text(plan.get(key)) for key in ["goal", "conflict", "main_scene", "ending_hook", "supporting_character_focus", "payoff_or_pressure"]
    )

    if event_type and event_type in (card.get("applicable_event_types") or []):
        score += 24.0
        reasons.append(f"贴合{event_type}")
    if progress_kind and progress_kind in (card.get("applicable_progress_kinds") or []):
        score += 22.0
        reasons.append(f"贴合{progress_kind}")
    if flow_id and flow_id in (card.get("compatible_flows") or []):
        score += 16.0
        reasons.append(f"适配流程{flow_id}")
    if chapter_stage in (card.get("applicable_stages") or []):
        score += 8.0
    if scene_visibility in (card.get("scene_visibility") or []):
        score += 10.0
        reasons.append(f"更适合{scene_visibility}场面")
    if protagonist_position in (card.get("protagonist_positions") or []):
        score += 8.0

    debt_score = int(pressure_debt.get("pressure_debt_score") or 0)
    level = _text(card.get("payoff_level"))
    if debt_score >= 4 and level == "strong":
        score += 14.0
        reasons.append("最近几章欠账偏多，需要更强兑现")
    elif debt_score >= 2 and level in {"medium", "strong"}:
        score += 8.0
    elif debt_score == 0 and level == "strong":
        score -= 4.0

    if bool(card.get("requires_pressure_debt")) and debt_score == 0:
        score -= 10.0
    if payoff_line and any(token in payoff_line for token in ["盯上", "追查", "危机", "退路", "代价"]):
        if level in {"medium", "strong"}:
            score += 4.0
    if payoff_line and any(token in payoff_line for token in ["拿到", "确认", "换到", "松口", "答应"]):
        if _text(card.get("family")) in {"资源", "信息", "交易", "关系"}:
            score += 4.0

    comp_score, comp_reason = _compensation_adjustment(card, compensation)
    score += comp_score
    if comp_reason and comp_score > 0:
        reasons.append(comp_reason)
    elif comp_reason and comp_score < 0:
        reasons.append("这张卡对追账来说偏软")

    score += _keyword_hit_score(card, plan_blob)
    score += _execution_cost_penalty(card, plan)
    penalty = _repeat_penalty(card, recent_patterns)
    if penalty > 0:
        score -= penalty
        reasons.append("会和最近几章的爽点类型撞车")
    return score, _unique_texts(reasons, limit=4, item_limit=20)



def _candidate_payload(card: dict[str, Any], score: float, reasons: list[str]) -> dict[str, Any]:
    return {
        "card_id": _text(card.get("card_id")),
        "name": _text(card.get("name")),
        "family": _text(card.get("family")),
        "payoff_mode": _text(card.get("payoff_mode")),
        "payoff_level": _text(card.get("payoff_level")),
        "payoff_visibility": _text(card.get("payoff_visibility")),
        "reader_payoff": _truncate_text(card.get("reader_payoff"), 42),
        "new_pressure": _truncate_text(card.get("new_pressure"), 42),
        "aftershock": _truncate_text(card.get("aftershock"), 42),
        "why_fit": _unique_texts(reasons, limit=4, item_limit=18),
        "score": round(score, 2),
    }



def _selector_trigger_reasons(
    *,
    shortlist: list[dict[str, Any]],
    diagnostics: dict[str, Any],
    compensation: dict[str, Any] | None,
    plan: dict[str, Any],
) -> list[str]:
    if not bool(getattr(settings, "payoff_ai_selection_enabled", True)):
        return []
    if len(shortlist) < 2:
        return []
    reasons: list[str] = []
    try:
        top_gap = float(shortlist[0].get("score", 0.0) or 0.0) - float(shortlist[1].get("score", 0.0) or 0.0)
    except Exception:
        top_gap = 999.0
    if top_gap <= float(getattr(settings, "payoff_ai_selection_score_gap_threshold", 4.0) or 4.0):
        reasons.append("top_gap_small")
    if _text((diagnostics or {}).get("repeat_risk")) == "high":
        reasons.append("repeat_risk_high")
    if _text((diagnostics or {}).get("pressure_debt_level")) == "high":
        reasons.append("debt_high")
    if compensation:
        reasons.append("compensation_pending")
    if _text(plan.get("chapter_type")) in {"turning_point", "高潮", "big_turn"}:
        reasons.append("turning_point")
    if _text(plan.get("payoff_level")).lower() == "strong":
        reasons.append("planned_strong")
    return _unique_texts(reasons, limit=4, item_limit=24)



def _normalize_ai_selector_payload(
    data: dict[str, Any] | None,
    *,
    shortlist: list[dict[str, Any]],
    local_selected: dict[str, Any],
) -> dict[str, Any]:
    allowed_ids = {_text(item.get("card_id")) for item in shortlist if _text(item.get("card_id"))}
    local_id = _text(local_selected.get("card_id"))
    payload = data or {}
    selected_card_id = _text(payload.get("selected_card_id"))
    backup_card_id = _text(payload.get("backup_card_id"))
    if selected_card_id not in allowed_ids:
        selected_card_id = local_id
    if backup_card_id not in allowed_ids or backup_card_id == selected_card_id:
        backup_card_id = ""
    return {
        "selected_card_id": selected_card_id,
        "backup_card_id": backup_card_id,
        "reason": _truncate_text(payload.get("reason"), 96) or _truncate_text(local_selected.get("selection_reason"), 96) or "维持本地首选。",
        "execution_hint": _truncate_text(payload.get("execution_hint"), 96),
    }



def _select_payoff_card_with_ai(
    *,
    chapter_plan: dict[str, Any],
    shortlist: list[dict[str, Any]],
    local_selected: dict[str, Any],
    diagnostics: dict[str, Any],
    compensation: dict[str, Any] | None,
) -> dict[str, Any]:
    if not is_openai_enabled():
        _raise_ai_required_error(
            stage="payoff_card_selector",
            message="爽点卡终选需要可用的 AI，当前已停止生成",
            detail_reason="当前没有可用的 AI 配置或密钥。",
            retryable=False,
        )
    try:
        data = call_json_response(
            stage="payoff_card_selector",
            system_prompt=payoff_card_selector_system_prompt(),
            user_prompt=payoff_card_selector_user_prompt(
                chapter_plan=chapter_plan,
                payoff_candidates=shortlist,
                local_diagnostics=diagnostics,
                local_selected_card=local_selected,
                payoff_compensation=compensation or {},
            ),
            max_output_tokens=max(int(getattr(settings, "payoff_ai_selection_max_output_tokens", 420) or 420), 220),
            timeout_seconds=max(int(getattr(settings, "payoff_ai_selection_timeout_seconds", 12) or 12), 8),
        )
        if isinstance(data, dict):
            return _normalize_ai_selector_payload(data, shortlist=shortlist, local_selected=local_selected)
        raise GenerationError(
            code=ErrorCodes.MODEL_RESPONSE_INVALID,
            message="payoff_card_selector 失败：AI 未返回有效的爽点卡选择结果。",
            stage="payoff_card_selector",
            retryable=True,
            http_status=422,
            provider=provider_name(),
        )
    except GenerationError:
        raise
    except Exception as exc:
        _raise_ai_required_error(
            stage="payoff_card_selector",
            message="爽点卡终选失败，已停止生成",
            detail_reason=str(exc),
            retryable=True,
        )





def build_payoff_candidate_index(
    *,
    story_bible: dict[str, Any],
    plan: dict[str, Any],
    recent_summaries: list[dict[str, Any]] | None,
    recent_plan_meta: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    cards = ensure_payoff_library(story_bible)
    chapter_no = int(plan.get("chapter_no", 0) or 0)
    compensation = (plan.get("payoff_compensation") or {}) if isinstance(plan, dict) else {}
    if not compensation:
        compensation = _pending_payoff_compensation(story_bible, chapter_no=chapter_no)
    diagnostics = {
        "chapter_stage": _chapter_stage(chapter_no),
        "scene_visibility": _infer_scene_visibility(plan),
        "protagonist_position": _infer_protagonist_position(plan, chapter_no),
        "pressure_debt": _pressure_debt(recent_summaries),
        "recent_payoff_patterns": _recent_payoff_patterns(recent_plan_meta),
        "payoff_compensation": compensation,
    }
    candidates = []
    for card in cards:
        candidates.append(
            {
                "card_id": _text(card.get("card_id")),
                "name": _text(card.get("name")),
                "family": _text(card.get("family")),
                "payoff_mode": _text(card.get("payoff_mode")),
                "payoff_level": _text(card.get("payoff_level")),
                "payoff_visibility": _text(card.get("payoff_visibility")),
                "reader_payoff": _truncate_text(card.get("reader_payoff"), 42),
                "external_reaction": _truncate_text(card.get("external_reaction"), 42),
                "new_pressure": _truncate_text(card.get("new_pressure"), 42),
                "aftershock": _truncate_text(card.get("aftershock"), 42),
                "applicable_event_types": list(card.get("applicable_event_types") or [])[:4],
                "applicable_progress_kinds": list(card.get("applicable_progress_kinds") or [])[:4],
                "compatible_flows": list(card.get("compatible_flows") or [])[:3],
                "requires_pressure_debt": bool(card.get("requires_pressure_debt")),
            }
        )
    return {
        "diagnostics": diagnostics,
        "candidates": candidates,
    }


def realize_payoff_selection_from_index(
    *,
    story_bible: dict[str, Any],
    plan: dict[str, Any],
    selected_card_id: str | None,
    recent_summaries: list[dict[str, Any]] | None,
    recent_plan_meta: list[dict[str, Any]] | None = None,
    selection_note: str | None = None,
) -> dict[str, Any]:
    cards = ensure_payoff_library(story_bible)
    chapter_no = int(plan.get("chapter_no", 0) or 0)
    chapter_stage = _chapter_stage(chapter_no)
    scene_visibility = _infer_scene_visibility(plan)
    protagonist_position = _infer_protagonist_position(plan, chapter_no)
    pressure_debt = _pressure_debt(recent_summaries)
    recent_patterns = _recent_payoff_patterns(recent_plan_meta)
    compensation = (plan.get("payoff_compensation") or {}) if isinstance(plan, dict) else {}
    if not compensation:
        compensation = _pending_payoff_compensation(story_bible, chapter_no=chapter_no)
    selected_full = next((card for card in cards if _text(card.get("card_id")) == _text(selected_card_id)), {})
    if not selected_full and cards:
        selected_full = cards[0]
    selected_card = {
        "card_id": _text(selected_full.get("card_id")),
        "name": _text(selected_full.get("name")),
        "family": _text(selected_full.get("family")),
        "payoff_mode": _text(selected_full.get("payoff_mode")),
        "payoff_level": _text(selected_full.get("payoff_level")),
        "payoff_visibility": _text(selected_full.get("payoff_visibility")),
        "reader_payoff": _truncate_text(selected_full.get("reader_payoff"), 42),
        "external_reaction": _truncate_text(selected_full.get("external_reaction"), 56),
        "new_pressure": _truncate_text(selected_full.get("new_pressure"), 42),
        "aftershock": _truncate_text(selected_full.get("aftershock"), 42),
        "selection_reason": _truncate_text(selection_note or "本章爽点由 AI 基于全部压缩候选直接选定。", 96),
        "chapter_payoff_line": _truncate_text(
            f"{_text(selected_full.get('reader_payoff'))}；同时{_text(selected_full.get('new_pressure') or plan.get('payoff_or_pressure'))}",
            88,
        ) if selected_full else _truncate_text(plan.get("payoff_or_pressure"), 88),
    }
    diagnostics = _build_payoff_diagnostics(
        pressure_debt=pressure_debt,
        recent_patterns=recent_patterns,
        selected_card=selected_card,
        compensation=compensation,
    )
    diagnostics["selector_mode"] = "ai_direct"
    diagnostics["selector_trigger_reasons"] = ["all_candidates"]
    return {
        "chapter_stage": chapter_stage,
        "scene_visibility": scene_visibility,
        "protagonist_position": protagonist_position,
        "pressure_debt": pressure_debt,
        "recent_payoff_patterns": recent_patterns,
        "payoff_compensation": compensation,
        "payoff_diagnostics": diagnostics,
        "payoff_card_candidates": build_payoff_candidate_index(
            story_bible=story_bible,
            plan=plan,
            recent_summaries=recent_summaries,
            recent_plan_meta=recent_plan_meta,
        ).get("candidates") or [],
        "selected_payoff_card": selected_card if selected_full else {},
        "selection_note": _truncate_text(selection_note or "AI 已从全量爽点候选中直接选定本章执行卡。", 96),
        "selector_mode": "ai_direct",
        "selector_trigger_reasons": ["all_candidates"],
    }


def choose_payoff_card_for_chapter(
    *,
    story_bible: dict[str, Any],
    plan: dict[str, Any],
    recent_summaries: list[dict[str, Any]] | None,
    recent_plan_meta: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    raise RuntimeError(
        "旧的本地爽点选卡入口已移除。请改用章节准备阶段的 AI 多层筛选，并在终选后调用 realize_payoff_selection_from_index。"
    )

