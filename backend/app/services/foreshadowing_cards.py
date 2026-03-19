from __future__ import annotations

from copy import deepcopy
from typing import Any
import re


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        clean = value.strip()
        return clean or default
    if isinstance(value, (int, float)):
        return str(value)
    return str(value).strip() or default


def _truncate_text(value: Any, limit: int = 80) -> str:
    text = _text(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


def _safe_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return []


def _unique_texts(items: list[Any], *, limit: int = 6, item_limit: int = 64) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in items or []:
        text = _truncate_text(item, item_limit)
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
        if len(output) >= limit:
            break
    return output


def _slugify(text: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", _text(text).lower()).strip("-")
    return base[:36] or "hook"


def _foreshadowing_candidate_signature(item: dict[str, Any]) -> str:
    action_type = _text(item.get("action_type"))
    parent_id = _text(item.get("parent_card_id"))
    child_id = _text(item.get("child_card_id"))
    source_hook = _slugify(_text(item.get("source_hook")))
    return "|".join([action_type, parent_id, child_id, source_hook])


def _foreshadowing_candidate_id(position: int) -> str:
    return f"fcand_{max(int(position or 0), 0):03d}"


def _foreshadowing_action_label(action_type: str) -> str:
    mapping = {
        "plant": "新埋",
        "touch": "轻碰",
        "deepen": "加深",
        "verify": "验证",
        "partial_payoff": "部分回收",
        "full_payoff": "完整回收",
        "misdirect": "误导遮掩",
    }
    return mapping.get(_text(action_type), _text(action_type) or "推进")


def _foreshadowing_display_label(action_type: str, source_hook: str, child_name: str) -> str:
    action_label = _foreshadowing_action_label(action_type)
    hook = _text(source_hook)
    child = _text(child_name)
    if hook and child:
        return f"{action_label}：{hook}（{child}）"
    if hook:
        return f"{action_label}：{hook}"
    if child:
        return f"{action_label}：{child}"
    return action_label


def _foreshadowing_instance_id(candidate_id: str, position: int) -> str:
    base = re.sub(r"[^a-zA-Z0-9_]+", "_", _text(candidate_id)).strip("_")
    if not base:
        base = f"fcand_{max(int(position or 0), 0):03d}"
    return f"finst_{base}"


FORESHADOWING_PARENT_CARDS: list[dict[str, Any]] = [
    {
        "card_id": "f_parent_identity_truth",
        "name": "身份真相型",
        "scope": "long",
        "core_purpose": "通过细节异常、他人反应或信息缺口，逐步逼近真实身份、真实关系或隐藏来历。",
        "best_for": "人物背景暗线、旧账、来历、师承、伪装与认知错位。",
        "action_bias": ["plant", "touch", "deepen", "partial_payoff", "full_payoff"],
        "risk": "过早点透、碰得太硬、解释味太重。",
        "keywords": ["身份", "来历", "旧账", "隐瞒", "认出"],
    },
    {
        "card_id": "f_parent_rule_abnormality",
        "name": "规则异常型",
        "scope": "mid",
        "core_purpose": "通过规则漏洞、资格异常、制度缺口或程序不对劲，制造后续追查动力。",
        "best_for": "资格争夺、门规、试炼、阵法、流程、交易条件异常。",
        "action_bias": ["plant", "touch", "verify", "partial_payoff", "full_payoff"],
        "risk": "只说不证、异常太泛、拖太久不验证。",
        "keywords": ["规则", "资格", "异常", "门规", "条件"],
    },
    {
        "card_id": "f_parent_relation_shift",
        "name": "关系失衡型",
        "scope": "mid",
        "core_purpose": "通过让步、误解、试探、欠账或不对等合作，留下关系层面的潜伏变化。",
        "best_for": "暧昧、防备、试探同盟、师徒、同门、合作中的暗流。",
        "action_bias": ["plant", "touch", "deepen", "misdirect", "partial_payoff"],
        "risk": "只写心情不写行为、关系变化不可感。",
        "keywords": ["关系", "误会", "让步", "防备", "人情"],
    },
    {
        "card_id": "f_parent_hidden_scheme",
        "name": "幕后筹谋型",
        "scope": "long",
        "core_purpose": "通过碎片线索、旁人失言和局势错位，暗示幕后有人布局或多线联动。",
        "best_for": "阴谋线、势力博弈、有人提前布置、黑手未现身。",
        "action_bias": ["plant", "touch", "deepen", "verify", "partial_payoff"],
        "risk": "信息过散、每次都只空泛加压。",
        "keywords": ["幕后", "布置", "黑手", "提前", "联动"],
    },
    {
        "card_id": "f_parent_cost_shadow",
        "name": "代价阴影型",
        "scope": "mid",
        "core_purpose": "让资源、能力、承诺或选择背后的隐藏代价慢慢显影。",
        "best_for": "资源使用、能力突破、交易、人情、承诺、赌注。",
        "action_bias": ["plant", "touch", "deepen", "verify", "full_payoff"],
        "risk": "只喊代价不落具体后果。",
        "keywords": ["代价", "后患", "透支", "赌注", "承诺"],
    },
    {
        "card_id": "f_parent_danger_approach",
        "name": "危险逼近型",
        "scope": "short",
        "core_purpose": "让新危险或旧威胁逐步逼近，形成短周期追更压力。",
        "best_for": "追查、暴露风险、敌人靠近、时间截止、危机前夜。",
        "action_bias": ["plant", "touch", "deepen", "partial_payoff"],
        "risk": "连续几章只逼近不爆。",
        "keywords": ["危险", "追查", "逼近", "暴露", "期限"],
    },
    {
        "card_id": "f_parent_information_gap",
        "name": "信息缺口型",
        "scope": "short",
        "core_purpose": "让读者和主角都知道缺了一块关键信息，推动后续验证。",
        "best_for": "半真消息、关键人没说全、地图/地点/名单缺一角。",
        "action_bias": ["plant", "touch", "verify", "partial_payoff", "full_payoff"],
        "risk": "缺口太多导致读者疲劳。",
        "keywords": ["没说全", "半真", "缺口", "验证", "线索"],
    },
    {
        "card_id": "f_parent_promise_payoff",
        "name": "承诺待兑现型",
        "scope": "short",
        "core_purpose": "把已经说出口的承诺、约定、赌约或回收点挂起来，等待后续兑现。",
        "best_for": "约定、赌约、答应的帮助、下一步见面、阶段回收。",
        "action_bias": ["plant", "touch", "partial_payoff", "full_payoff"],
        "risk": "挂了就忘、兑现时缺前置。",
        "keywords": ["约定", "承诺", "赌约", "回头", "兑现"],
    },

    {
        "card_id": "f_parent_faction_fracture",
        "name": "势力裂缝型",
        "scope": "long",
        "core_purpose": "通过站队细节、口风差异和行动不一致，暗示一个势力内部已经出现裂缝或多股力量。",
        "best_for": "宗门、家族、组织、联盟、长老层、执事层内部并非一心。",
        "action_bias": ["plant", "touch", "deepen", "verify", "partial_payoff"],
        "risk": "只说势力复杂，却不给可见裂痕。",
        "keywords": ["势力", "裂缝", "站队", "内部分裂", "两派"],
    },
    {
        "card_id": "f_parent_object_origin",
        "name": "异物来历型",
        "scope": "mid",
        "core_purpose": "通过物件、遗留痕迹或特殊资源的异常来历，牵出旧事、旧地或旧人。",
        "best_for": "旧物、玉简、令牌、残图、兵器、材料来历不明。",
        "action_bias": ["plant", "touch", "verify", "partial_payoff", "full_payoff"],
        "risk": "只强调神秘，不让物件真参与推进。",
        "keywords": ["旧物", "令牌", "来历", "残图", "兵器"],
    },
    {
        "card_id": "f_parent_motive_concealment",
        "name": "动机遮蔽型",
        "scope": "mid",
        "core_purpose": "让角色的真实动机被表层说法遮住，后续通过偏差和反常一点点显出来。",
        "best_for": "看似帮忙、看似阻拦、看似中立，其实另有动机。",
        "action_bias": ["plant", "touch", "deepen", "misdirect", "partial_payoff"],
        "risk": "动机永远只藏不露，读者会失去抓手。",
        "keywords": ["动机", "另有目的", "遮掩", "借口", "表面"],
    },
    {
        "card_id": "f_parent_timeline_mismatch",
        "name": "时间错位型",
        "scope": "long",
        "core_purpose": "通过时间顺序、先后关系或旧事时间线的不一致，埋入更大的真相缺口。",
        "best_for": "旧案、旧史、师承顺序、谁先知道什么、事件发生时间不对。",
        "action_bias": ["plant", "touch", "verify", "partial_payoff", "full_payoff"],
        "risk": "时间线太绕，读者只感到混乱。",
        "keywords": ["时间", "先后", "旧案", "时间线", "不对"],
    },
    {
        "card_id": "f_parent_place_memory",
        "name": "地点旧痕型",
        "scope": "mid",
        "core_purpose": "通过旧地重访、地点异常、环境旧痕或空间记忆，牵出被压住的旧事和旧关系。",
        "best_for": "旧地、旧宅、禁地、遗迹、曾经发生过事的地点再次出现。",
        "action_bias": ["plant", "touch", "verify", "partial_payoff"],
        "risk": "只把地点写成背景，不让旧痕真正推动判断。",
        "keywords": ["旧地", "地点", "旧痕", "遗迹", "曾经发生过"],
    },
    {
        "card_id": "f_parent_name_taboo",
        "name": "名字忌讳型",
        "scope": "long",
        "core_purpose": "通过某个名字、称呼、代号或不敢直呼的对象，埋入禁忌、旧案或高位存在的暗线。",
        "best_for": "不敢提的名字、改称呼、代号异常、提名即变色的局面。",
        "action_bias": ["plant", "touch", "deepen", "verify"],
        "risk": "只强调神秘，不让名字禁忌产生现实后果。",
        "keywords": ["名字", "称呼", "代号", "不敢提", "忌讳"],
    },
    {
        "card_id": "f_parent_contract_constraint",
        "name": "契约束缚型",
        "scope": "mid",
        "core_purpose": "让誓约、契约、门规绑定、欠条或约束条件在后续慢慢显形，形成压制和回收空间。",
        "best_for": "交易、盟约、门规绑定、师徒约束、欠条与承诺。",
        "action_bias": ["plant", "touch", "deepen", "partial_payoff", "full_payoff"],
        "risk": "只提有约束，不写约束如何具体起作用。",
        "keywords": ["契约", "约束", "誓约", "绑定", "欠条"],
    },
    {
        "card_id": "f_parent_objective_divergence",
        "name": "目标分叉型",
        "scope": "mid",
        "core_purpose": "通过表面同路、实际不同目标的细节，让同伴、势力或合作者的路线分叉提前显影。",
        "best_for": "合作中暗藏分歧、目标重叠但终点不同、一路人未必是一条心。",
        "action_bias": ["plant", "touch", "deepen", "misdirect", "partial_payoff"],
        "risk": "只喊‘各有目的’，却没有具体分叉动作。",
        "keywords": ["目标不同", "分叉", "同路不同心", "终点不同", "暗分歧"],
    },
]


FORESHADOWING_CHILD_CARDS: list[dict[str, Any]] = [
    {
        "child_id": "f_child_identity_anomaly_only",
        "parent_id": "f_parent_identity_truth",
        "name": "只露异常不露答案",
        "action_type": "plant",
        "horizon": "long",
        "micro_pattern": "先让读者感觉身份或来历不对，但不直接点破答案。",
        "fit_when": "本章更适合埋长期暗线，不适合完整解释。",
        "opening_move": "通过措辞、称呼、反应或旧物异常露一条缝。",
        "mid_shift": "再给一个与表面认知不完全对得上的细节。",
        "ending_drop": "结尾只留怀疑，不给定论。",
        "avoid": "直接解释真相、把长期伏笔写成即时揭秘。",
    },
    {
        "child_id": "f_child_identity_half_verify",
        "parent_id": "f_parent_identity_truth",
        "name": "局部验证仍留核心未揭",
        "action_type": "partial_payoff",
        "horizon": "long",
        "micro_pattern": "验证一小块真实信息，但把核心真相继续压住。",
        "fit_when": "长期身份伏笔需要回声，但还不到完全揭示窗口。",
        "opening_move": "先让主角或旁人验证一项可测细节。",
        "mid_shift": "验证结果坐实异常。",
        "ending_drop": "只扩大真相范围，不给最终答案。",
        "avoid": "一步到位把身份讲穿。",
    },
    {
        "child_id": "f_child_rule_gap_flag",
        "parent_id": "f_parent_rule_abnormality",
        "name": "只露规则缺口",
        "action_type": "plant",
        "horizon": "short",
        "micro_pattern": "让角色意识到规则、流程、资格条件里少了一环或不对劲。",
        "fit_when": "本章适合抛出后续追查入口。",
        "opening_move": "先触到规则表面。",
        "mid_shift": "通过对照、试探或旁人反应发现缺口。",
        "ending_drop": "把问题挂起，逼后续验证。",
        "avoid": "异常说得太空、没有可追方向。",
    },
    {
        "child_id": "f_child_rule_verify_partial",
        "parent_id": "f_parent_rule_abnormality",
        "name": "先证一条，再留更大问号",
        "action_type": "verify",
        "horizon": "mid",
        "micro_pattern": "先验证其中一条异常成立，再引出更大的结构性问题。",
        "fit_when": "已有规则缺口，当前章需要明确推进但不适合一次讲透。",
        "opening_move": "锁定一个可验证点。",
        "mid_shift": "验证成立。",
        "ending_drop": "把更大的异常挂到下一步。",
        "avoid": "验证后什么都没变。",
    },
    {
        "child_id": "f_child_relation_light_touch",
        "parent_id": "f_parent_relation_shift",
        "name": "轻碰关系失衡",
        "action_type": "touch",
        "horizon": "mid",
        "micro_pattern": "用一句回避、一次让步或一次多余的在意，轻轻碰一下关系暗流。",
        "fit_when": "本章主线不在关系，但关系线不能完全断。",
        "opening_move": "动作或语气先露一点差别。",
        "mid_shift": "让对方给出对应反应。",
        "ending_drop": "不总结，只留下关系位置微变。",
        "avoid": "大段抒情或直接表白。",
    },
    {
        "child_id": "f_child_relation_deepen_unequal",
        "parent_id": "f_parent_relation_shift",
        "name": "把合作写成不对等",
        "action_type": "deepen",
        "horizon": "mid",
        "micro_pattern": "把表面合作推进一格，但同时埋入欠账、防备或不对等。",
        "fit_when": "人物开始靠近，但仍不适合真正确认立场。",
        "opening_move": "先让一方给出帮助或让步。",
        "mid_shift": "另一方接受后，露出代价或戒备。",
        "ending_drop": "关系更近，但更不稳。",
        "avoid": "写成单纯升温。",
    },
    {
        "child_id": "f_child_hidden_scheme_fragment",
        "parent_id": "f_parent_hidden_scheme",
        "name": "碎片化暗示幕后联动",
        "action_type": "touch",
        "horizon": "long",
        "micro_pattern": "不给主谋名字，只让读者意识到多件事背后可能有同一只手。",
        "fit_when": "长线阴谋需要保持存在感，但不适合揭主谋。",
        "opening_move": "先出现一处和旧线索相互照应的异常。",
        "mid_shift": "让角色意识到两件事并非偶然。",
        "ending_drop": "结尾只落到“有人提前布置过”。",
        "avoid": "直接点名幕后黑手。",
    },
    {
        "child_id": "f_child_cost_aftershock_visible",
        "parent_id": "f_parent_cost_shadow",
        "name": "让代价先显一角",
        "action_type": "touch",
        "horizon": "mid",
        "micro_pattern": "通过一个具体后果，让隐藏代价开始可感。",
        "fit_when": "前面已有资源/能力/承诺伏笔，这章需要提醒它并非白赚。",
        "opening_move": "先出现轻微不适、额外消耗或外部反馈。",
        "mid_shift": "把代价和过去动作勾上。",
        "ending_drop": "结尾说明代价还没完。",
        "avoid": "只抽象说有代价。",
    },
    {
        "child_id": "f_child_danger_countdown",
        "parent_id": "f_parent_danger_approach",
        "name": "把危险写成倒计时",
        "action_type": "deepen",
        "horizon": "short",
        "micro_pattern": "让危险具体到期限、距离或即将撞上的节点。",
        "fit_when": "短期钩子不能再只是模糊威胁。",
        "opening_move": "先给出可量化逼近。",
        "mid_shift": "让角色必须调整计划。",
        "ending_drop": "结尾压一个更紧的时间点。",
        "avoid": "危险逼近却不影响行动。",
    },
    {
        "child_id": "f_child_info_gap_half_truth",
        "parent_id": "f_parent_information_gap",
        "name": "给半真消息，不给完整答案",
        "action_type": "plant",
        "horizon": "short",
        "micro_pattern": "让角色先拿到半真消息，再逼后续验证。",
        "fit_when": "本章需要留钩子，但不能只空挂。",
        "opening_move": "先得到一点可用信息。",
        "mid_shift": "发现其中明显缺一块。",
        "ending_drop": "把下一步验证方向落出来。",
        "avoid": "只挂问号没有前进。",
    },
    {
        "child_id": "f_child_promise_payoff_collect",
        "parent_id": "f_parent_promise_payoff",
        "name": "把旧约定部分兑现",
        "action_type": "partial_payoff",
        "horizon": "short",
        "micro_pattern": "把前面挂起的承诺或约定回收一半，让读者拿到阶段结果。",
        "fit_when": "短期伏笔到了该回声的时候。",
        "opening_move": "先接回旧约定。",
        "mid_shift": "兑现一半，留下另一半或更大代价。",
        "ending_drop": "让这次兑现转成新问题。",
        "avoid": "答应了却仍毫无结果。",
    },

    {
        "child_id": "f_child_faction_split_hint",
        "parent_id": "f_parent_faction_fracture",
        "name": "同势力不同口风",
        "action_type": "plant",
        "horizon": "long",
        "micro_pattern": "让同一势力内部两拨人对同一件事说法不一致，先露裂缝。",
        "fit_when": "本章适合先让读者意识到这个势力并非铁板一块。",
        "opening_move": "先让一方给出官方口径。",
        "mid_shift": "再让另一方不完全接这个口径。",
        "ending_drop": "结尾落在‘内部并不齐心’上。",
        "avoid": "不要只写抽象内斗，不给可感差异。",
    },
    {
        "child_id": "f_child_faction_split_verify",
        "parent_id": "f_parent_faction_fracture",
        "name": "裂缝被坐实",
        "action_type": "verify",
        "horizon": "long",
        "micro_pattern": "通过一次站队、转述或执行偏差，把势力裂缝从猜测推到坐实。",
        "fit_when": "前面已经埋过站队或口风差异，这章需要推进一格。",
        "opening_move": "先接上前一次口风差。",
        "mid_shift": "让执行结果证明两边不真站一条线。",
        "ending_drop": "结尾把裂缝的后续危险挂出来。",
        "avoid": "不要坐实之后仍像什么都没变。",
    },
    {
        "child_id": "f_child_object_origin_anomaly",
        "parent_id": "f_parent_object_origin",
        "name": "旧物异常先露",
        "action_type": "plant",
        "horizon": "mid",
        "micro_pattern": "让物件先通过纹路、反应或识别方式露出‘来历不普通’。",
        "fit_when": "本章可以先让旧物真正进入视野，但还不适合讲透来历。",
        "opening_move": "先让物件在场。",
        "mid_shift": "通过识别、反应或使用异样露一条缝。",
        "ending_drop": "结尾只说明它不是表面身份。",
        "avoid": "不要把物件只当背景摆件。",
    },
    {
        "child_id": "f_child_object_origin_partial_trace",
        "parent_id": "f_parent_object_origin",
        "name": "追到半条来路",
        "action_type": "partial_payoff",
        "horizon": "mid",
        "micro_pattern": "顺着物件追到半条来路，给出新的方向但仍不交最终出处。",
        "fit_when": "旧物伏笔需要真推进，但不适合完整回收。",
        "opening_move": "先沿物件特征找线。",
        "mid_shift": "确认一段旧联系或旧地名。",
        "ending_drop": "结尾把更深来路挂给下一步。",
        "avoid": "不要追了半天仍没有新信息。",
    },
    {
        "child_id": "f_child_motive_cover_story",
        "parent_id": "f_parent_motive_concealment",
        "name": "表面理由先站住",
        "action_type": "plant",
        "horizon": "mid",
        "micro_pattern": "先给角色一个看起来说得通的表面理由，同时在细节里留下不合处。",
        "fit_when": "这章适合让角色表面上看起来合理。",
        "opening_move": "先让角色说一个可接受的理由。",
        "mid_shift": "再让动作或反应露出不完全匹配。",
        "ending_drop": "结尾落在‘理由也许不是全部’上。",
        "avoid": "不要表面理由一眼就假。",
    },
    {
        "child_id": "f_child_motive_bias_exposed",
        "parent_id": "f_parent_motive_concealment",
        "name": "动机偏差露边",
        "action_type": "deepen",
        "horizon": "mid",
        "micro_pattern": "让角色在关键选择上偏离表面立场，暴露真实动机的一角。",
        "fit_when": "前面已经有表面理由，这章适合露一点偏差。",
        "opening_move": "先接上那套表面说法。",
        "mid_shift": "在关键节点让角色做出不完全符合表面立场的动作。",
        "ending_drop": "结尾把偏差挂成新的怀疑点。",
        "avoid": "不要一偏就把真实动机全交底。",
    },
    {
        "child_id": "f_child_timeline_small_mismatch",
        "parent_id": "f_parent_timeline_mismatch",
        "name": "先后细节对不上",
        "action_type": "plant",
        "horizon": "long",
        "micro_pattern": "通过一句旧事、一段经历或一条传闻的先后关系不对，埋时间错位。",
        "fit_when": "本章适合轻埋大线，不宜直接解释。",
        "opening_move": "先给一个看似正常的旧事说法。",
        "mid_shift": "再补一个与之不完全相容的时间细节。",
        "ending_drop": "结尾只让人意识到时间顺序可能不对。",
        "avoid": "不要把时间线写得太绕太乱。",
    },
    {
        "child_id": "f_child_timeline_verify_gap",
        "parent_id": "f_parent_timeline_mismatch",
        "name": "时间缺口被证实",
        "action_type": "verify",
        "horizon": "long",
        "micro_pattern": "通过文书、记忆、证词或地点痕迹，证实时间线上确实缺了一段。",
        "fit_when": "长期旧案或旧史需要回声时。",
        "opening_move": "先锁定一个可查的时间点。",
        "mid_shift": "查证后发现时间对不上。",
        "ending_drop": "结尾把‘为什么会缺这一段’挂成更大的问题。",
        "avoid": "不要验证完只停在混乱，没有新方向。",
    },
    {
        "child_id": "f_child_place_trace_only",
        "parent_id": "f_parent_place_memory",
        "name": "旧地先露痕",
        "action_type": "plant",
        "horizon": "mid",
        "micro_pattern": "先让地点本身露出旧痕、旧习惯或环境不对，让人意识到这地方记着事。",
        "fit_when": "这章适合借地点发暗线，但还不适合讲旧事全貌。",
        "opening_move": "开场先给一个地点细节异常。",
        "mid_shift": "中段再由人物反应确认这不是错觉。",
        "ending_drop": "结尾把旧地和旧事勾连起来。",
        "avoid": "不要只写氛围，不给可追的痕。",
    },
    {
        "child_id": "f_child_place_memory_verify",
        "parent_id": "f_parent_place_memory",
        "name": "旧地反证旧事",
        "action_type": "verify",
        "horizon": "mid",
        "micro_pattern": "通过旧地、旧物摆位或环境残痕，反证一段旧事确实发生过。",
        "fit_when": "地点线已经埋过，现在需要轻度坐实。",
        "opening_move": "先指出地点与旧说法对不上。",
        "mid_shift": "中段找到能坐实的痕迹。",
        "ending_drop": "结尾确认旧事不是传言。",
        "avoid": "不要把验证写成一眼看穿。",
    },
    {
        "child_id": "f_child_name_cannot_be_said",
        "parent_id": "f_parent_name_taboo",
        "name": "提名即变色",
        "action_type": "plant",
        "horizon": "long",
        "micro_pattern": "某个名字一被提起，场上立刻出现不自然反应，说明这名字背后有禁忌或旧案。",
        "fit_when": "需要埋更高层存在、禁忌对象或不敢碰的话题。",
        "opening_move": "先让名字在边缘被提到。",
        "mid_shift": "中段用反应确认这名字不能随便说。",
        "ending_drop": "结尾只留‘为何不能提’。",
        "avoid": "不要立刻解释名字背后的全部真相。",
    },
    {
        "child_id": "f_child_alias_mismatch",
        "parent_id": "f_parent_name_taboo",
        "name": "称呼对不上人",
        "action_type": "touch",
        "horizon": "long",
        "micro_pattern": "同一个人被不同人用不同称呼指向，暴露其真实位置或旧身份不简单。",
        "fit_when": "人物身份、地位或旧关系需要轻碰。",
        "opening_move": "先出现一个不该有的称呼。",
        "mid_shift": "中段再让另一个人使用不同叫法。",
        "ending_drop": "结尾把称呼错位挂起来。",
        "avoid": "不要当章直接解释清楚。",
    },
    {
        "child_id": "f_child_contract_clause_appears",
        "parent_id": "f_parent_contract_constraint",
        "name": "约束条款露边",
        "action_type": "plant",
        "horizon": "mid",
        "micro_pattern": "先让契约、誓约或绑定条款露出一角，让读者知道后面会起作用。",
        "fit_when": "交易、合作或承诺刚建立，需要提前埋约束。",
        "opening_move": "开场先点出一个看似小的限制。",
        "mid_shift": "中段让这条限制开始影响选择。",
        "ending_drop": "结尾确认这不是口头装饰。",
        "avoid": "不要把条款写得像法律条文说明书。",
    },
    {
        "child_id": "f_child_contract_bites_back",
        "parent_id": "f_parent_contract_constraint",
        "name": "约束开始咬人",
        "action_type": "partial_payoff",
        "horizon": "mid",
        "micro_pattern": "原本埋着的约束在本章第一次真正咬回来，迫使角色付出代价或改动作。",
        "fit_when": "前面已有绑定，现在需要让其开始生效。",
        "opening_move": "先触到原本约束。",
        "mid_shift": "中段约束真正发作。",
        "ending_drop": "结尾把更大的束缚感挂出来。",
        "avoid": "不要让约束发作得毫无铺垫。",
    },
    {
        "child_id": "f_child_goal_same_road_diff_end",
        "parent_id": "f_parent_objective_divergence",
        "name": "同路不同终点",
        "action_type": "plant",
        "horizon": "mid",
        "micro_pattern": "表面一起往前走，但一句目标表述或一个选择偏向就露出终点并不一样。",
        "fit_when": "合作还没破，但分歧应该开始留影。",
        "opening_move": "先把共同目标摆出来。",
        "mid_shift": "中段让某个细节露出不同终点。",
        "ending_drop": "结尾只确认‘这条路不是一起走到头’。",
        "avoid": "不要当章直接彻底翻脸。",
    },
    {
        "child_id": "f_child_goal_diverge_choice",
        "parent_id": "f_parent_objective_divergence",
        "name": "关键处先分叉",
        "action_type": "deepen",
        "horizon": "mid",
        "micro_pattern": "在一个关键判断上出现明确分叉，让目标不一致从暗流变成可见裂纹。",
        "fit_when": "分歧已经埋过，现在要更清楚一点。",
        "opening_move": "先给一个必须选边的点。",
        "mid_shift": "中段让双方做不同选择。",
        "ending_drop": "结尾把分叉带成后续账。",
        "avoid": "不要让分叉没有后果。",
    },
]

PARENT_BY_ID = {item["card_id"]: item for item in FORESHADOWING_PARENT_CARDS}
CHILD_BY_ID = {item["child_id"]: item for item in FORESHADOWING_CHILD_CARDS}


def build_foreshadowing_parent_card_index(story_bible: dict[str, Any] | None) -> list[dict[str, Any]]:
    return [
        {
            "card_id": item["card_id"],
            "name": item["name"],
            "scope": item["scope"],
            "core_purpose": _truncate_text(item["core_purpose"], 72),
            "best_for": _truncate_text(item["best_for"], 64),
            "action_bias": list(item.get("action_bias") or [])[:5],
            "risk": _truncate_text(item.get("risk"), 56),
            "keywords": _unique_texts(item.get("keywords") or [], limit=5, item_limit=16),
        }
        for item in FORESHADOWING_PARENT_CARDS
    ]


def build_foreshadowing_child_card_index(story_bible: dict[str, Any] | None) -> list[dict[str, Any]]:
    return [
        {
            "child_id": item["child_id"],
            "parent_id": item["parent_id"],
            "name": item["name"],
            "action_type": item["action_type"],
            "horizon": item["horizon"],
            "micro_pattern": _truncate_text(item["micro_pattern"], 72),
            "fit_when": _truncate_text(item["fit_when"], 64),
            "opening_move": _truncate_text(item["opening_move"], 42),
            "mid_shift": _truncate_text(item["mid_shift"], 42),
            "ending_drop": _truncate_text(item["ending_drop"], 42),
            "avoid": _truncate_text(item.get("avoid"), 40),
        }
        for item in FORESHADOWING_CHILD_CARDS
    ]


def _classify_parent_id(text: str) -> str:
    lower = _text(text).lower()
    keyword_map = [
        ("f_parent_rule_abnormality", ["资格", "规则", "门规", "试炼", "条件", "流程", "阵法"]),
        ("f_parent_identity_truth", ["身份", "来历", "认出", "旧账", "师承", "血脉", "真名"]),
        ("f_parent_relation_shift", ["关系", "让步", "防备", "暧昧", "人情", "信任", "误会"]),
        ("f_parent_hidden_scheme", ["幕后", "布置", "黑手", "暗中", "联动", "提前"]),
        ("f_parent_cost_shadow", ["代价", "后患", "消耗", "透支", "赌注", "反噬"]),
        ("f_parent_danger_approach", ["危险", "追查", "暴露", "逼近", "期限", "追兵"]),
        ("f_parent_promise_payoff", ["约定", "承诺", "赌约", "回头", "兑现"]),
        ("f_parent_information_gap", ["没说全", "半真", "缺口", "线索", "消息", "地点", "名单"]),
        ("f_parent_faction_fracture", ["势力", "裂缝", "两派", "站队", "内部分裂", "不同口风"]),
        ("f_parent_object_origin", ["旧物", "令牌", "残图", "兵器", "来历", "玉简"]),
        ("f_parent_motive_concealment", ["动机", "借口", "表面", "另有目的", "遮掩"]),
        ("f_parent_timeline_mismatch", ["时间", "先后", "旧案", "时间线", "不对", "前后矛盾"]),
        ("f_parent_place_memory", ["旧地", "遗迹", "旧痕", "地点", "旧宅", "曾经发生"]),
        ("f_parent_name_taboo", ["名字", "代号", "不敢提", "称呼", "忌讳"]),
        ("f_parent_contract_constraint", ["契约", "约束", "誓约", "绑定", "欠条", "门规绑定"]),
        ("f_parent_objective_divergence", ["目标不同", "分叉", "同路不同心", "终点不同", "暗分歧"]),
    ]
    for parent_id, words in keyword_map:
        if any(word in lower for word in words):
            return parent_id
    return "f_parent_information_gap"


def _default_child_for(parent_id: str, *, action_type: str) -> dict[str, Any]:
    action_type = _text(action_type, "touch")
    candidates = [item for item in FORESHADOWING_CHILD_CARDS if item.get("parent_id") == parent_id and _text(item.get("action_type")) == action_type]
    if not candidates:
        candidates = [item for item in FORESHADOWING_CHILD_CARDS if item.get("parent_id") == parent_id]
    return deepcopy(candidates[0] if candidates else FORESHADOWING_CHILD_CARDS[0])


def _chapter_no_from_plan(plan: dict[str, Any] | None) -> int:
    try:
        return int((plan or {}).get("chapter_no") or 0)
    except Exception:
        return 0


def build_foreshadowing_candidate_index(
    *,
    story_bible: dict[str, Any] | None,
    plan: dict[str, Any] | None,
    recent_summaries: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    story_bible = story_bible or {}
    plan = plan or {}
    workspace = (story_bible.get("story_workspace") or {}) if isinstance(story_bible, dict) else {}
    existing = [item for item in (workspace.get("foreshadowing") or []) if isinstance(item, dict)]
    open_items = [item for item in existing if _text(item.get("status"), "open") != "closed"]
    chapter_no = _chapter_no_from_plan(plan)
    ending_hook = _text(plan.get("ending_hook"))
    hook_kind = _text(plan.get("hook_kind") or plan.get("hook_style"))
    plan_goal = _text(plan.get("goal"))
    plan_conflict = _text(plan.get("conflict"))
    recent_open_hooks = _unique_texts([hook for summary in (recent_summaries or [])[-3:] if isinstance(summary, dict) for hook in (summary.get("open_hooks") or [])], limit=6)

    candidates: list[dict[str, Any]] = []
    parent_hits: set[str] = set()
    child_hits: set[str] = set()

    for item in open_items[:12]:
        surface = _text(item.get("surface_info") or item.get("name"))
        if not surface:
            continue
        parent_id = _text(item.get("parent_card_id")) or _classify_parent_id(surface)
        horizon = _text(item.get("horizon") or item.get("scope"), PARENT_BY_ID.get(parent_id, {}).get("scope", "mid"))
        introduced = int(item.get("introduced_in_chapter") or 0)
        gap = max(chapter_no - introduced, 0) if chapter_no else 0
        touch_action = "touch"
        if horizon == "short" and gap >= 2:
            touch_action = "partial_payoff"
        elif horizon == "mid" and gap >= 4:
            touch_action = "deepen"
        elif horizon == "long" and gap >= 6:
            touch_action = "partial_payoff"
        touch_child = _default_child_for(parent_id, action_type=touch_action)
        resolve_child = _default_child_for(parent_id, action_type="full_payoff")
        legacy_touch_id = f"touch::{_slugify(surface)}"
        legacy_resolve_id = f"resolve::{_slugify(surface)}"
        for legacy_candidate_id, action_type, child in [
            (legacy_touch_id, touch_action, touch_child),
            (legacy_resolve_id, "full_payoff", resolve_child),
        ]:
            parent_hits.add(parent_id)
            child_hits.add(_text(child.get("child_id")))
            child_name = _text(child.get("name"))
            candidates.append(
                {
                    "legacy_candidate_id": legacy_candidate_id,
                    "action_type": action_type,
                    "parent_card_id": parent_id,
                    "parent_card_name": _text(PARENT_BY_ID.get(parent_id, {}).get("name")),
                    "child_card_id": _text(child.get("child_id")),
                    "child_card_name": child_name,
                    "horizon": horizon,
                    "source_hook": surface,
                    "introduced_in_chapter": introduced,
                    "age_in_chapters": gap,
                    "fit_reason": _truncate_text(f"已有伏笔：{surface}；当前适合{action_type}。", 80),
                    "micro_pattern": _truncate_text(child.get("micro_pattern"), 72),
                    "opening_move": _truncate_text(child.get("opening_move"), 42),
                    "mid_shift": _truncate_text(child.get("mid_shift"), 42),
                    "ending_drop": _truncate_text(child.get("ending_drop"), 42),
                    "avoid": _truncate_text(child.get("avoid"), 36),
                    "display_label": _foreshadowing_display_label(action_type, surface, child_name),
                }
            )

    if ending_hook or hook_kind:
        hook_text = ending_hook or hook_kind or plan_goal or plan_conflict or "本章新问题"
        parent_id = _classify_parent_id(f"{hook_text} {plan_goal} {plan_conflict}")
        child = _default_child_for(parent_id, action_type="plant")
        parent_hits.add(parent_id)
        child_hits.add(_text(child.get("child_id")))
        child_name = _text(child.get("name"))
        candidates.append(
            {
                "legacy_candidate_id": f"plant::{_slugify(hook_text)}",
                "action_type": "plant",
                "parent_card_id": parent_id,
                "parent_card_name": _text(PARENT_BY_ID.get(parent_id, {}).get("name")),
                "child_card_id": _text(child.get("child_id")),
                "child_card_name": child_name,
                "horizon": _text(PARENT_BY_ID.get(parent_id, {}).get("scope"), "mid"),
                "source_hook": hook_text,
                "introduced_in_chapter": chapter_no,
                "age_in_chapters": 0,
                "fit_reason": _truncate_text(f"本章章末钩子/冲突适合新埋：{hook_text}", 80),
                "micro_pattern": _truncate_text(child.get("micro_pattern"), 72),
                "opening_move": _truncate_text(child.get("opening_move"), 42),
                "mid_shift": _truncate_text(child.get("mid_shift"), 42),
                "ending_drop": _truncate_text(child.get("ending_drop"), 42),
                "avoid": _truncate_text(child.get("avoid"), 36),
                "display_label": _foreshadowing_display_label("plant", hook_text, child_name),
            }
        )

    deduped: list[dict[str, Any]] = []
    seen_signatures: set[str] = set()
    for item in candidates:
        signature = _foreshadowing_candidate_signature(item)
        if not signature or signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        row = dict(item)
        row["candidate_id"] = _foreshadowing_candidate_id(len(deduped) + 1)
        row.setdefault("selector_key", f"foreshadow_{len(deduped) + 1:03d}")
        row.setdefault("selector_index", len(deduped) + 1)
        row.setdefault("selector_label", row.get("display_label") or row.get("source_hook") or row["candidate_id"])
        deduped.append(row)

    return {
        "diagnostics": {
            "chapter_no": chapter_no,
            "open_foreshadowing_count": len(open_items),
            "recent_open_hook_count": len(recent_open_hooks),
            "ending_hook": _truncate_text(ending_hook, 64),
            "hook_kind": _truncate_text(hook_kind, 32),
            "compression_mode": "compact_foreshadowing_index",
            "selection_rule": "先给 AI 看伏笔母卡/子卡与章节级候选压缩索引，再由 AI 决定本章埋哪条、碰哪条、回哪条。",
        },
        "parent_cards": [item for item in build_foreshadowing_parent_card_index(story_bible) if item.get("card_id") in parent_hits] or build_foreshadowing_parent_card_index(story_bible)[:4],
        "child_cards": [item for item in build_foreshadowing_child_card_index(story_bible) if item.get("child_id") in child_hits] or build_foreshadowing_child_card_index(story_bible)[:6],
        "candidates": deduped[:14],
    }


def realize_foreshadowing_selection_from_index(
    *,
    story_bible: dict[str, Any] | None,
    plan: dict[str, Any] | None,
    foreshadowing_candidate_index: dict[str, Any] | None,
    selected_primary_candidate_id: str | None,
    selected_supporting_candidate_ids: list[str] | None,
    selection_note: str | None = None,
) -> dict[str, Any]:
    candidate_index = foreshadowing_candidate_index or {}
    candidates = [item for item in (candidate_index.get("candidates") or []) if isinstance(item, dict)]
    by_id = { _text(item.get("candidate_id")): item for item in candidates if _text(item.get("candidate_id")) }
    primary = deepcopy(by_id.get(_text(selected_primary_candidate_id))) if _text(selected_primary_candidate_id) else None
    supporting: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in selected_supporting_candidate_ids or []:
        cid = _text(item)
        if not cid or cid in seen or cid == _text(selected_primary_candidate_id):
            continue
        row = by_id.get(cid)
        if not row:
            continue
        supporting.append(deepcopy(row))
        seen.add(cid)
        if len(supporting) >= 2:
            break
    instance_cards: list[dict[str, Any]] = []
    for index, item in enumerate(([primary] if isinstance(primary, dict) else []) + supporting):
        if not isinstance(item, dict):
            continue
        instance_cards.append(
            {
                "instance_id": _foreshadowing_instance_id(_text(item.get('candidate_id')), index + 1),
                "priority": "primary" if index == 0 else "supporting",
                "action_type": _text(item.get("action_type")),
                "parent_card_id": _text(item.get("parent_card_id")),
                "parent_card_name": _text(item.get("parent_card_name")),
                "child_card_id": _text(item.get("child_card_id")),
                "child_card_name": _text(item.get("child_card_name")),
                "source_hook": _text(item.get("source_hook")),
                "execution_hint": _truncate_text(
                    "{}：围绕‘{}’，按\"{} -> {} -> {}\"落地。".format(
                        _text(item.get("action_type")),
                        _text(item.get("source_hook")),
                        _text(item.get("opening_move")),
                        _text(item.get("mid_shift")),
                        _text(item.get("ending_drop")),
                    ),
                    120,
                ),
                "avoid": _text(item.get("avoid")),
            }
        )
    return {
        "selected_primary_candidate": primary or {},
        "selected_supporting_candidates": supporting,
        "selected_instance_cards": instance_cards,
        "selection_note": _truncate_text(selection_note, 120),
        "selector_mode": "ai_compressed_index",
        "candidate_count": len(candidates),
        "diagnostics": candidate_index.get("diagnostics") or {},
    }


__all__ = [
    "build_foreshadowing_parent_card_index",
    "build_foreshadowing_child_card_index",
    "build_foreshadowing_candidate_index",
    "realize_foreshadowing_selection_from_index",
]
