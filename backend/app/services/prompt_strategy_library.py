from __future__ import annotations

from typing import Any

from app.services.story_blueprint_builders import build_flow_templates


def _text(value: Any) -> str:
    return str(value or "").strip()


def _truncate(value: Any, limit: int) -> str:
    text = _text(value)
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    if limit == 1:
        return text[:1]
    return text[: limit - 1].rstrip() + "…"


FLOW_CHILD_VARIANTS: tuple[dict[str, str], ...] = (
    {
        "suffix": "direct_push",
        "label": "先手直推",
        "summary": "把母流程卡写成主角先手推动局势的版本，开局就见动作。",
        "opening": "开场就让主角先试探、先压价、先验证或先改条件，不要先解释。",
        "mid": "中段必须出现一次受阻后换法推进，让流程真正动起来。",
        "ending": "结尾落在这次先手带来的直接结果、代价或新问题上。",
        "avoid": "不要只是重复流程名字，不要让主角只观察不施加影响。",
    },
    {
        "suffix": "blocked_shift",
        "label": "受阻变招",
        "summary": "突出‘先推进 -> 被拦一下 -> 立刻换招’的中段结构。",
        "opening": "开场先落一个小动作或小条件，让局势有明确切入口。",
        "mid": "第一次推进不要直接成功，要让对方遮掩、压价、误导或顶回去，再让主角变招。",
        "ending": "结尾落在变招后的阶段性收获，或者确认当前旧办法已经不够。",
        "avoid": "不要把受阻写成纯心理波动，也不要一受阻就停住。",
    },
    {
        "suffix": "aftershock_bind",
        "label": "结果带后患",
        "summary": "强调阶段结果和后续绑定一起到来，避免单纯小结。",
        "opening": "开场先把当前需求和当前代价摆上桌，让这章一开始就有账可算。",
        "mid": "中段让人情、筹码、身份、秘密或退路重新排位。",
        "ending": "结尾必须把结果和后患一起落地，不能只有抽象感受。",
        "avoid": "不要把结尾写成松口气式平收，也不要只挂空钩子。",
    },
    {
        "suffix": "reveal_lock",
        "label": "先证后亮",
        "summary": "强调先确认一条关键事实，再把结果亮到台面上，适合验证后翻局。",
        "opening": "开场先给一个可验证的小点，不要上来就喊大结论。",
        "mid": "中段先把证据、口风或异常坐实，再顺势把局面掀开。",
        "ending": "结尾落在‘证据已经成立，所以后果开始生效’上。",
        "avoid": "不要跳过验证直接给结果，也不要把证据写成说明书。",
    },
    {
        "suffix": "borrow_force",
        "label": "借势推进",
        "summary": "把母流程卡写成借外力、借规矩、借旁人动作推进的版本。",
        "opening": "开场先把可借的势摆出来：人、规矩、时限或对手漏洞。",
        "mid": "中段让主角借势一次成功，再因为借势带来新的束缚或对价。",
        "ending": "结尾落在‘借来的势已经生效，但账也跟着来了’上。",
        "avoid": "不要把借势写成纯运气，更不要让外力直接替主角完成全部推进。",
    },
    {
        "suffix": "retreat_reframe",
        "label": "以退换位",
        "summary": "先退一步或先认一小口，再换到更好的站位继续推进。",
        "opening": "开场先给一个看似退让的小动作，让对手或局面先松一寸。",
        "mid": "中段利用这一步退让换出新的切口、人位或话语权。",
        "ending": "结尾落在‘看似退了，实则换到了更好的推进位置’上。",
        "avoid": "不要把退让写成真吃亏，也不要退了之后没有第二步。",
    },
    {
        "suffix": "witness_confirm",
        "label": "旁证坐实",
        "summary": "让旁人、旧物或环境反应成为坐实结果的第二锤。",
        "opening": "开场先让一个旁证点入场，不要只靠主角单口判断。",
        "mid": "中段让旁证和主线动作互相印证，抬高可信度。",
        "ending": "结尾落在‘旁证已经坐实，所以后果开始扩散’上。",
        "avoid": "不要把旁证写成突然天降解释，也不要只给一锤没有回响。",
    },
)


WRITING_CHILD_VARIANTS: dict[str, list[dict[str, str]]] = {
    "continuity_guard": [
        {
            "suffix": "tail_carry",
            "label": "尾钩续接",
            "summary": "优先吃掉上一章末尾动作链或同场景压力。",
            "focus": "开头两段先兑现 opening_anchor / unresolved_action_chain，再转推进。",
            "opening": "第一场必须沿着上一章残留动作继续，不要重开话题。",
            "mid": "中段再把承接到的新问题推深一步。",
            "ending": "结尾给下一章留自然接力点，而不是硬断。",
            "avoid": "不要边承接边复述全书。",
        },
        {
            "suffix": "bridge_lock",
            "label": "桥接锁定",
            "summary": "优先保证最近两三章动作链不断裂。",
            "focus": "最近 continuity plan 里的 carry_in / bridge 要在本章真落地。",
            "opening": "先吃当前桥接点，再转新推进。",
            "mid": "中段补清最近链条里还欠着的一格。",
            "ending": "收尾时别让新桥和旧桥互相打架。",
            "avoid": "不要只拿‘承接’当借口拖慢节奏。",
        },
    ],
    "proactive_drive": [
        {
            "suffix": "visible_first_move",
            "label": "先手显形",
            "summary": "把主角先手动作写得更可见、更早出现。",
            "focus": "前两段内必须有动作、试探、设问、换价或表态。",
            "opening": "不要先站着看，先让主角动一下。",
            "mid": "受阻后再追一步。",
            "ending": "结尾最好直接由先手动作引发变化。",
            "avoid": "不要把主动写成纯心理活动。",
        },
        {
            "suffix": "blocked_repush",
            "label": "受阻再压",
            "summary": "强调‘先手 -> 反应 -> 再压一手’。",
            "focus": "中段要看到主角调整或加码，不许原地挨着。",
            "opening": "先手要具体。",
            "mid": "第二步要比第一步更有针对性。",
            "ending": "让读者看见这次再压出来了什么。",
            "avoid": "不要一碰壁就把节奏收回总结腔。",
        },
    ],
    "relationship_pressure": [
        {
            "suffix": "stance_shift",
            "label": "立场松动",
            "summary": "把态度变化和试探让步写得更明显。",
            "focus": "至少出现一次具体来回：试探、松口、顶回、改称呼、变位置。",
            "opening": "开场先让关系双方在一句话或一个动作上露差。",
            "mid": "中段让关系发生一次看得见的小位移。",
            "ending": "结尾落在关系重排或新边界生效上。",
            "avoid": "不要让配角只负责说明剧情。",
        },
        {
            "suffix": "misread_then_correct",
            "label": "误判修正",
            "summary": "先让人物互相误判，再修正其中一层。",
            "focus": "关系推进不靠喊话，而靠误会、纠偏和条件重写。",
            "opening": "开场先埋一个错位判断。",
            "mid": "中段让错位显形。",
            "ending": "结尾落在新的关系读法上。",
            "avoid": "不要一章内把关系推得过满。",
        },
    ],
    "resource_precision": [
        {
            "suffix": "cost_visible",
            "label": "代价显形",
            "summary": "把资源消耗、获得和限制写清。",
            "focus": "资源进出要有数、有单位、有后果。",
            "opening": "开场先交代眼下手里有什么、缺什么。",
            "mid": "中段动用资源时写清限制。",
            "ending": "结尾落在剩余量、冷却或欠账上。",
            "avoid": "不要把资源写成无边界外挂。",
        },
        {
            "suffix": "capability_boundary",
            "label": "能力边界",
            "summary": "把能力的可做/不可做写实，防止跳级。",
            "focus": "能力使用必须伴随条件、代价或冷却。",
            "opening": "开场先用一个小动作确认边界。",
            "mid": "中段别超边界硬解题。",
            "ending": "结尾留下能力边界带来的新限制。",
            "avoid": "不要临场升格成功能泛化。",
        },
    ],
    "payoff_delivery": [
        {
            "suffix": "reward_then_aftershock",
            "label": "回报后震",
            "summary": "把爽点兑现和后续余震写成一条完整链。",
            "focus": "reader_payoff -> external_reaction -> aftershock。",
            "opening": "开场尽早把欠账对象摆出来。",
            "mid": "中段完成一次明确兑现。",
            "ending": "结尾接上余震，别只爽完就收。",
            "avoid": "不要只预热不落袋。",
        },
        {
            "suffix": "public_display",
            "label": "显影给人看",
            "summary": "把本章兑现写成旁人可感的变化。",
            "focus": "要有人看见、误判、忌惮、改口或记账。",
            "opening": "开场先把见证人或对照面摆进场。",
            "mid": "中段让兑现被看见。",
            "ending": "结尾写清别人怎么重新评估主角。",
            "avoid": "不要只写主角自己心里痛快。",
        },
    ],
    "mystery_probe": [
        {
            "suffix": "detail_verify",
            "label": "细节验证",
            "summary": "通过小异常、小验证把信息自然补出来。",
            "focus": "优先用试探、错位、旁人反应补设定。",
            "opening": "开场先钉一个具体异常。",
            "mid": "中段用一次验证或受挫确认异常不是错觉。",
            "ending": "结尾落在新线索或新疑点上。",
            "avoid": "不要写成百科说明。",
        },
        {
            "suffix": "half_truth",
            "label": "半真消息",
            "summary": "让信息只揭开一层，逼主角继续追。",
            "focus": "先拿到半个答案，再意识到答案不完整。",
            "opening": "开场先围着一个具体问题打转。",
            "mid": "中段确认答案有缺口。",
            "ending": "结尾把缺口变成下章入口。",
            "avoid": "不要一章内全讲透。",
        },
    ],
    "danger_pressure": [
        {
            "suffix": "deadline_close",
            "label": "时限压近",
            "summary": "把风险写成逼近中的具体变化。",
            "focus": "时限、盯梢、暴露、退路变少必须具体。",
            "opening": "开场先落一个坏消息或限制。",
            "mid": "中段再削一层退路。",
            "ending": "结尾必须让下一步更难。",
            "avoid": "不要只写抽象不安。",
        },
        {
            "suffix": "watcher_present",
            "label": "有人盯上",
            "summary": "让危险来自可感的人和目光，而不是概念。",
            "focus": "让施压者、盯梢者或追查者具象出现。",
            "opening": "开场先给危险一个来源。",
            "mid": "中段让来源更贴近主角。",
            "ending": "结尾落在‘已经被看见/记住/列账’上。",
            "avoid": "不要把危险只写成环境氛围。",
        },
    ],
    "scene_compactness": [
        {
            "suffix": "single_scene_pressure",
            "label": "单场压实",
            "summary": "尽量用一场把主要结果写扎实。",
            "focus": "少切场，多把一个场面写到底。",
            "opening": "开场直接落在主场景动作里。",
            "mid": "中段在场内完成转折。",
            "ending": "结尾在同场景里落结果或切出。",
            "avoid": "不要无意义闪切。",
        },
        {
            "suffix": "result_before_transition",
            "label": "先结果后切场",
            "summary": "每次切场前都先给阶段结果。",
            "focus": "切场必须服务推进，不服务逃避。",
            "opening": "第一场先把当下事办起来。",
            "mid": "要切场时先落一格结果。",
            "ending": "结尾别用切场代替收束。",
            "avoid": "不要场景多、结果少。",
        },
    ],

    "evidence_density": [
        {
            "suffix": "detail_chain",
            "label": "细节连证",
            "summary": "让关键判断由两到三个小细节串起来，而不是只靠一句说明。",
            "focus": "同一结论最好由动作、物件、反应三类证据里至少两类支撑。",
            "opening": "开场先给一个具体细节，不先给结论。",
            "mid": "中段再补第二个能互相照应的细节。",
            "ending": "结尾让这些细节指向一个更清楚的判断。",
            "avoid": "不要堆满线索却不收束，也不要只写抽象推测。",
        },
        {
            "suffix": "reaction_proof",
            "label": "反应作证",
            "summary": "让旁人反应、停顿、改口或回避成为信息证据的一部分。",
            "focus": "重要信息不必直说，可以让人物反应先把它托出来。",
            "opening": "开场先给一处看似轻微但不自然的反应。",
            "mid": "中段把反应和当前问题勾上。",
            "ending": "结尾落在‘反应本身已经说明问题’上。",
            "avoid": "不要让所有人都只会明说答案。",
        },
    ],
    "emotional_undertow": [
        {
            "suffix": "emotion_under_surface",
            "label": "情绪藏面下",
            "summary": "让情绪主要附着在动作、停顿和措辞变化上，而不是大段直抒。",
            "focus": "情绪要可感，但不抢走事件推进。",
            "opening": "开场先给一个带情绪的动作或微反应。",
            "mid": "中段让情绪影响一次判断或措辞。",
            "ending": "结尾落在没说破但已经改变关系的情绪余波上。",
            "avoid": "不要一章内反复自白同一种情绪。",
        },
        {
            "suffix": "emotion_costs_action",
            "label": "情绪带动作代价",
            "summary": "让情绪不是装饰，而是确实让角色付出一点动作代价或选择偏差。",
            "focus": "情绪要改变说法、顺序、让步幅度或冒险程度。",
            "opening": "开场先让情绪影响一个微动作。",
            "mid": "中段因为情绪多迈一步或少退一步。",
            "ending": "结尾明确这次情绪留下了后续代价。",
            "avoid": "不要把情绪写成与剧情无关的背景色。",
        },
    ],
    "dialogue_tension": [
        {
            "suffix": "question_pressure",
            "label": "问答压强",
            "summary": "通过问答回合、追问和换说法让对话本身承担推进。",
            "focus": "对话不只是传信息，还要形成压迫、试探与位移。",
            "opening": "开场先抛一个具体问题或条件。",
            "mid": "中段让回答不完整，再追问或换法追。",
            "ending": "结尾落在一句重新定价的话上。",
            "avoid": "不要把对话写成平铺说明。",
        },
        {
            "suffix": "pause_and_reprice",
            "label": "停顿改价",
            "summary": "让停顿、沉默和改口形成对话里的真实张力。",
            "focus": "关键句之前最好有停顿或犹疑，之后让条件重新排位。",
            "opening": "开场先让一句话顶住局面。",
            "mid": "中段通过沉默、改口或反问重排筹码。",
            "ending": "结尾把新的价码或边界落清。",
            "avoid": "不要所有人都连珠炮式把话说满。",
        },
    ],
    "aftermath_binding": [
        {
            "suffix": "result_binds_next",
            "label": "结果绑下一步",
            "summary": "让本章结果天然把下一步行动绑出来，减少硬钩子感。",
            "focus": "收获、损失、关系变化都要自动推着下一步走。",
            "opening": "开场先把当下这步和下一步之间的账摆出来。",
            "mid": "中段让结果和后续绑定关系显形。",
            "ending": "结尾直接落在‘因此下一步只能这样走’上。",
            "avoid": "不要结尾另起炉灶换一个无关钩子。",
        },
        {
            "suffix": "aftermath_reorders_people",
            "label": "余波重排人位",
            "summary": "把结果的余波写成人物站位、话语权和边界重排。",
            "focus": "同一事件结束后，谁更靠前、谁更被防、谁更有资格要变得可见。",
            "opening": "开场先给出当前人位差。",
            "mid": "中段让一次结果改变人位。",
            "ending": "结尾落在新的站位结构上。",
            "avoid": "不要结果出来后人物关系像什么都没发生。",
        },
    ],
    "goal_chain_clarity": [
        {
            "suffix": "micro_goal_visible",
            "label": "小目标显形",
            "summary": "把本章每一小段在争什么写清楚，减少空转。",
            "focus": "每个阶段都让读者知道眼前要拿到什么或避免什么。",
            "opening": "开场先钉住眼前最小目标。",
            "mid": "中段让目标升级或改写。",
            "ending": "结尾落在目标完成、失败或被替换后的下一步。",
            "avoid": "不要让场面很热闹但看不出在争什么。",
        },
        {
            "suffix": "result_retarget",
            "label": "结果改目标",
            "summary": "让阶段结果立刻改写下一步目标，形成目标链。",
            "focus": "一个目标解决后，下一目标要自然冒出来。",
            "opening": "先把当前目标与下一目标的潜在线连上。",
            "mid": "中段让结果迫使目标切换。",
            "ending": "结尾要让新目标已经接棒。",
            "avoid": "不要每段像新开副本。",
        },
    ],
    "bystander_reflection": [
        {
            "suffix": "crowd_mirror",
            "label": "旁观成镜",
            "summary": "用旁观者、对照者或见证者把主角变化照出来。",
            "focus": "让别人怎么看、怎么改口、怎么迟疑成为显影层。",
            "opening": "开场先把一个能看见主角的人摆进来。",
            "mid": "中段让这个旁观视角发生变化。",
            "ending": "结尾把旁观变化绑定成新的局面反馈。",
            "avoid": "不要让旁人只负责喊‘好厉害’。",
        },
        {
            "suffix": "foil_shift",
            "label": "对照位移",
            "summary": "找一个原本高/低于主角的人做对照，放大落差。",
            "focus": "同一场景里主角和对照者的境遇、话语权或判断出现位移。",
            "opening": "先摆清谁原本更占位。",
            "mid": "中段让位移发生。",
            "ending": "结尾落在新对照关系上。",
            "avoid": "不要硬插一个无关对照角色。",
        },
    ],
    "hidden_info_control": [
        {
            "suffix": "reveal_slice_only",
            "label": "只掀一层",
            "summary": "控制信息释放量，只揭当前最该揭的一层。",
            "focus": "给读者有效新知，但保留更大的未解部分。",
            "opening": "开场先钉住这章只处理哪个问题层级。",
            "mid": "中段允许补证，但不跳级解释。",
            "ending": "结尾留下可追缺口，而不是解释完毕。",
            "avoid": "不要一章把三层谜面一起摊开。",
        },
        {
            "suffix": "answer_with_gap",
            "label": "给答留缺",
            "summary": "给出一个可用答案，但明确留着关键缺口。",
            "focus": "让答案既能推动当前章，又能吊住后续。",
            "opening": "先把真正要问的问题说清。",
            "mid": "中段给出半个有效答案。",
            "ending": "结尾点明还缺哪一格。",
            "avoid": "不要只留谜不答，也不要答得一干二净。",
        },
    ],
    "sensory_anchor": [
        {
            "suffix": "object_anchor",
            "label": "物锚定场",
            "summary": "用物件、环境细节或触感锚定场面，让切场和推进更稳。",
            "focus": "关键场景要有可记住的物件、气味、光线或触感。",
            "opening": "开场先给一个能抓住人的场景物锚。",
            "mid": "中段让物锚参与推进或转折。",
            "ending": "结尾让物锚和结果发生关联。",
            "avoid": "不要只堆砌景物词。",
        },
        {
            "suffix": "body_feedback",
            "label": "身体回声",
            "summary": "用呼吸、手势、疼痛、停顿等身体反馈让场面更有实感。",
            "focus": "情绪、压力和代价最好都在身体层有回应。",
            "opening": "开场先给一个身体上的小反馈。",
            "mid": "中段让身体反馈和判断绑定。",
            "ending": "结尾让这种反馈带出余波。",
            "avoid": "不要全靠抽象情绪词。",
        },
    ],
}


def build_prompt_strategy_library() -> list[dict[str, Any]]:
    return [
        {
            "strategy_id": "continuity_guard",
            "name": "连续性优先",
            "summary": "优先吃掉上一章尾巴、本章承接点和最近未回收链条，先接上再推进。",
            "use_when": ["上一章尾钩很强", "本章必须同场景续接", "最近两章动作链不能断"],
            "avoid_when": ["本章本来就是全新独立任务开场"],
            "writing_directive": "开头两段先兑现 opening_anchor / unresolved_action_chain，再转入本章推进。",
        },
        {
            "strategy_id": "proactive_drive",
            "name": "主角先手",
            "summary": "把主角先手、再追一步、再逼出反应写得更硬，防止正文空转。",
            "use_when": ["本章容易写成观察与犹豫", "目标和冲突都清楚"],
            "avoid_when": ["只需要温和过渡的短收束章"],
            "writing_directive": "前两段就给主角可见动作/判断，中段受阻后必须再追一步。",
        },
        {
            "strategy_id": "relationship_pressure",
            "name": "关系推进显性化",
            "summary": "把人物来回、态度变化、试探和微妙让步写得更可感。",
            "use_when": ["本章主推进在人物关系", "需要让配角不再像工具人"],
            "avoid_when": ["纯资源任务或纯战斗爆发章"],
            "writing_directive": "重点关系至少出现一次具体来回：试探、让步、误判、互惠、戒备或撕裂。",
        },
        {
            "strategy_id": "resource_precision",
            "name": "资源与能力精确化",
            "summary": "把资源数量、代价、能力边界写实，避免万能外挂味。",
            "use_when": ["本章会动用关键资源或能力", "资源变化本身是推进结果"],
            "avoid_when": ["资源只是背景陪衬"],
            "writing_directive": "资源的获得、消耗、限制、冷却和代价都要在正文里交代清楚。",
        },
        {
            "strategy_id": "payoff_delivery",
            "name": "爽点落袋",
            "summary": "把回报、显影和后患写成完整链条，不只做情绪预热。",
            "use_when": ["本章有明确 payoff card", "最近两章欠账偏多"],
            "avoid_when": ["本章就是刻意压低输出的蓄压章"],
            "writing_directive": "至少兑现一次 reader_payoff -> external_reaction -> new_pressure/aftershock 的完整链条。",
        },
        {
            "strategy_id": "mystery_probe",
            "name": "谜团试探",
            "summary": "用验证、试错、旁人反应和异常细节自然补设定与线索。",
            "use_when": ["本章要补世界/势力/等级信息", "发现线索比硬说明更重要"],
            "avoid_when": ["这章主要是正面冲突和爆发"],
            "writing_directive": "通过试探、交易、受挫或旁人评价自然补信息，不写成说明书。",
        },
        {
            "strategy_id": "danger_pressure",
            "name": "压力逼近",
            "summary": "让风险、盯梢、代价和暴露感逐步压近，结尾留下可追的后患。",
            "use_when": ["hook_style 偏危险逼近/反转下压", "本章需要收强钩"],
            "avoid_when": ["本章应以清晰收束和小胜落袋为主"],
            "writing_directive": "结尾要把压力写成具体变化，而不是空泛不安。",
        },
        {
            "strategy_id": "scene_compactness",
            "name": "场景紧凑",
            "summary": "减少无效切场，把一两个场景写扎实，让结果更集中。",
            "use_when": ["本章目标单一", "最近容易写散"],
            "avoid_when": ["本章必须跨两三段场景推进"],
            "writing_directive": "每次切场前先给阶段结果或明确的时间/地点/动作过渡。",
        },

        {
            "strategy_id": "evidence_density",
            "name": "证据密度提升",
            "summary": "让关键判断由多个可见细节托起来，减少空口结论感。",
            "use_when": ["这章要让判断更可信", "信息和判断推进比动作更重要"],
            "avoid_when": ["本章更适合强爆发直给"],
            "writing_directive": "关键判断最好由两个以上不同来源的细节支撑，别只靠一句话说明。",
        },
        {
            "strategy_id": "emotional_undertow",
            "name": "情绪暗流显影",
            "summary": "把情绪压进动作、停顿和说法里，让情感线既在场又不抢戏。",
            "use_when": ["关系线在推进", "人物嘴上不说但心里很重"],
            "avoid_when": ["纯说明性过渡章"],
            "writing_directive": "情绪要通过动作和措辞显形，并至少影响一次判断或让步。",
        },
        {
            "strategy_id": "dialogue_tension",
            "name": "对话压强",
            "summary": "让问答、改口、停顿和反问承担推进，提升谈判与试探场的咬合力。",
            "use_when": ["本章主要靠对话推进", "人物之间有试探、谈价、套话"],
            "avoid_when": ["纯外部动作场"],
            "writing_directive": "对话要形成回合与压强，不许只是轮流讲设定。",
        },
        {
            "strategy_id": "aftermath_binding",
            "name": "后果绑定",
            "summary": "把本章结果直接绑到下一步行动和人物站位上，减少虚悬空钩。",
            "use_when": ["这章会出阶段结果", "结尾需要自然推到下一章"],
            "avoid_when": ["本章就是纯悬停蓄压"],
            "writing_directive": "阶段结果出来后，要立刻写清它怎样重排下一步动作和人位。",
        },
        {
            "strategy_id": "goal_chain_clarity",
            "name": "目标链清晰化",
            "summary": "把每一段眼前目标和下一步接棒写清楚，减少热闹但发虚。",
            "use_when": ["本章容易写散", "一章里有一到两次推进目标改写"],
            "avoid_when": ["纯气氛蓄压章"],
            "writing_directive": "让本章小目标显形，并在阶段结果出现后自然改写下一步目标。",
        },
        {
            "strategy_id": "bystander_reflection",
            "name": "旁人显影",
            "summary": "借旁观者、见证者和对照位，把主角变化与结果照出来。",
            "use_when": ["本章有公开或半公开结果", "想让爽点、关系变化更可见"],
            "avoid_when": ["纯私密独白场"],
            "writing_directive": "至少安排一个见证位，让旁人态度变化成为结果的外显层。",
        },
        {
            "strategy_id": "hidden_info_control",
            "name": "隐信息控制",
            "summary": "控制一章内的信息释放层级，只揭本章最该揭的一层。",
            "use_when": ["本章涉及伏笔、谜团或真相推进", "担心一章说太满"],
            "avoid_when": ["这章就是完整揭秘章"],
            "writing_directive": "答案可以给，但要保留关键缺口，避免多层谜面同章讲穿。",
        },
        {
            "strategy_id": "sensory_anchor",
            "name": "画面锚定",
            "summary": "用物锚、身体反馈和环境触感把场面钉实，让切场和余波更可感。",
            "use_when": ["这章容易抽象化", "需要提升场面质感和记忆点"],
            "avoid_when": ["说明性极强的短总结章"],
            "writing_directive": "关键场景至少用一个物锚或身体回声把压力、代价或关系变化落到可感层。",
        },
    ]


def build_prompt_strategy_index() -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for item in build_prompt_strategy_library():
        summary = _truncate(item.get("summary"), 72)
        use_when = [_truncate(value, 24) for value in (item.get("use_when") or [])[:3]]
        avoid_when = [_truncate(value, 24) for value in (item.get("avoid_when") or [])[:2]]
        strategy_id = _text(item.get("strategy_id"))
        payload.append(
            {
                "strategy_id": strategy_id,
                "type": "writing_card",
                "card_type": "writing_card",
                "card_level": "parent",
                "card_id": strategy_id,
                "source_key": "prompt_strategy",
                "title": _text(item.get("name")),
                "name": _text(item.get("name")),
                "summary": summary,
                "chapter_use": "；".join(use_when[:2]) if use_when else summary,
                "constraint": "；".join(avoid_when[:2]),
                "priority_hint": "medium",
                "use_when": use_when,
                "avoid_when": avoid_when,
                "writing_directive": _truncate(item.get("writing_directive"), 88),
                "compression": {
                    "core_shape": summary,
                    "best_for": use_when,
                    "risk": avoid_when,
                },
            }
        )
    return payload


def build_flow_template_index(story_bible: dict[str, Any] | None) -> list[dict[str, Any]]:
    template_library = (story_bible or {}).get("template_library") or {}
    flow_templates = template_library.get("flow_templates") or []
    source = [item for item in flow_templates if isinstance(item, dict) and _text(item.get("flow_id"))] or build_flow_templates()
    payload: list[dict[str, Any]] = []
    for item in source:
        when_to_use = _truncate(item.get("when_to_use"), 56)
        variation = _truncate(item.get("variation_notes"), 72)
        flow_id = _text(item.get("flow_id"))
        payload.append(
            {
                "flow_id": flow_id,
                "type": "flow_card",
                "card_type": "flow_card",
                "card_level": "parent",
                "card_id": flow_id,
                "flow_card_id": flow_id,
                "source_key": "flow_template",
                "title": _truncate(item.get("name"), 20),
                "quick_tag": _truncate(item.get("quick_tag"), 12),
                "name": _truncate(item.get("name"), 20),
                "family": _truncate(item.get("family"), 12),
                "summary": when_to_use,
                "chapter_use": when_to_use,
                "constraint": variation,
                "priority_hint": "medium",
                "when_to_use": when_to_use,
                "preferred_event_types": [_truncate(value, 12) for value in (item.get("preferred_event_types") or [])[:3]],
                "preferred_progress_kinds": [_truncate(value, 12) for value in (item.get("preferred_progress_kinds") or [])[:3]],
                "preferred_hook_styles": [_truncate(value, 12) for value in (item.get("preferred_hook_styles") or [])[:2]],
                "turning_points": [_truncate(value, 22) for value in (item.get("turning_points") or [])[:3]],
                "variation_notes": variation,
                "compression": {
                    "core_shape": when_to_use,
                    "best_for": [_truncate(value, 24) for value in (item.get("preferred_progress_kinds") or [])[:2]],
                    "risk": [_truncate(item.get("variation_notes"), 32)],
                },
            }
        )
    return payload


def build_flow_child_card_index(story_bible: dict[str, Any] | None) -> list[dict[str, Any]]:
    parents = build_flow_template_index(story_bible)
    payload: list[dict[str, Any]] = []
    for parent in parents:
        parent_id = _text(parent.get("flow_id"))
        parent_name = _text(parent.get("name"))
        when = _text(parent.get("when_to_use")) or _text(parent.get("summary"))
        turning_points = [str(item or "").strip() for item in (parent.get("turning_points") or []) if str(item or "").strip()]
        turning_hint = " / ".join(turning_points[:2]) if turning_points else when
        for variant in FLOW_CHILD_VARIANTS:
            child_id = f"{parent_id}__{variant['suffix']}"
            payload.append(
                {
                    "child_id": child_id,
                    "card_id": child_id,
                    "parent_id": parent_id,
                    "parent_flow_id": parent_id,
                    "type": "flow_child_card",
                    "card_type": "flow_child_card",
                    "card_level": "child",
                    "title": f"{parent_name}·{variant['label']}",
                    "name": f"{parent_name}·{variant['label']}",
                    "summary": _truncate(f"{variant['summary']} 贴合场景：{when}", 88),
                    "micro_pattern": _truncate(f"沿着{parent_name}这条大结构推进，但更强调：{variant['label']}。当前母卡常见拍点：{turning_hint}", 96),
                    "fit_when": _truncate(when, 72),
                    "opening_move": _truncate(variant['opening'], 88),
                    "mid_shift": _truncate(variant['mid'], 88),
                    "ending_drop": _truncate(variant['ending'], 88),
                    "avoid": _truncate(variant['avoid'], 72),
                    "signal": [variant['label'], _text(parent.get('quick_tag')) or parent_name],
                    "compression": {
                        "micro_pattern": _truncate(variant['summary'], 48),
                        "fit_when": _truncate(when, 40),
                        "opening": _truncate(variant['opening'], 36),
                        "mid": _truncate(variant['mid'], 36),
                        "ending": _truncate(variant['ending'], 36),
                    },
                }
            )
    return payload


def build_writing_child_card_index() -> list[dict[str, Any]]:
    library = {item["strategy_id"]: item for item in build_prompt_strategy_library() if _text(item.get("strategy_id"))}
    payload: list[dict[str, Any]] = []
    for strategy_id, children in WRITING_CHILD_VARIANTS.items():
        parent = library.get(strategy_id, {})
        parent_name = _text(parent.get("name")) or strategy_id
        for child in children:
            child_id = f"{strategy_id}__{child['suffix']}"
            payload.append(
                {
                    "child_id": child_id,
                    "card_id": child_id,
                    "parent_id": strategy_id,
                    "parent_strategy_id": strategy_id,
                    "type": "writing_child_card",
                    "card_type": "writing_child_card",
                    "card_level": "child",
                    "title": f"{parent_name}·{child['label']}",
                    "name": f"{parent_name}·{child['label']}",
                    "summary": _truncate(child['summary'], 88),
                    "directive_focus": _truncate(child['focus'], 88),
                    "opening_focus": _truncate(child['opening'], 72),
                    "mid_focus": _truncate(child['mid'], 72),
                    "ending_focus": _truncate(child['ending'], 72),
                    "avoid": _truncate(child['avoid'], 64),
                    "signal": [parent_name, child['label']],
                    "compression": {
                        "focus": _truncate(child['focus'], 42),
                        "opening": _truncate(child['opening'], 36),
                        "mid": _truncate(child['mid'], 36),
                        "ending": _truncate(child['ending'], 36),
                    },
                }
            )
    return payload


def build_prompt_bundle_index(story_bible: dict[str, Any] | None) -> dict[str, Any]:
    flow_cards = build_flow_template_index(story_bible)
    writing_cards = build_prompt_strategy_index()
    flow_child_cards = build_flow_child_card_index(story_bible)
    writing_child_cards = build_writing_child_card_index()
    return {
        "flow_templates": flow_cards,
        "prompt_strategies": writing_cards,
        "flow_cards": flow_cards,
        "writing_cards": writing_cards,
        "flow_child_cards": flow_child_cards,
        "writing_child_cards": writing_child_cards,
    }


def build_writing_card_library() -> list[dict[str, Any]]:
    return build_prompt_strategy_library()


def build_writing_card_index() -> list[dict[str, Any]]:
    return build_prompt_strategy_index()


def build_flow_card_index(story_bible: dict[str, Any] | None) -> list[dict[str, Any]]:
    return build_flow_template_index(story_bible)


def _flow_child_lookup(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        _text(item.get("child_id") or item.get("card_id")): item
        for item in (packet.get("flow_child_card_index") or packet.get("flow_child_cards") or [])
        if isinstance(item, dict) and _text(item.get("child_id") or item.get("card_id"))
    }


def _writing_child_lookup(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        _text(item.get("child_id") or item.get("card_id")): item
        for item in (packet.get("writing_child_card_index") or packet.get("writing_child_cards") or [])
        if isinstance(item, dict) and _text(item.get("child_id") or item.get("card_id"))
    }


def _default_flow_child_id(packet: dict[str, Any], flow_id: str) -> str | None:
    if not flow_id:
        return None
    for item in (_flow_child_lookup(packet).values()):
        if _text(item.get("parent_flow_id") or item.get("parent_id")) == flow_id:
            return _text(item.get("child_id") or item.get("card_id")) or None
    return None


def _default_writing_child_ids(packet: dict[str, Any], strategy_ids: list[str]) -> list[str]:
    lookup = _writing_child_lookup(packet)
    selected: list[str] = []
    for strategy_id in strategy_ids:
        for item in lookup.values():
            if _text(item.get("parent_strategy_id") or item.get("parent_id")) == strategy_id:
                selected.append(_text(item.get("child_id") or item.get("card_id")))
                break
    return [item for item in selected if item]


def _derive_flow_instance_card(packet: dict[str, Any], flow_card: dict[str, Any] | None, flow_child_card: dict[str, Any] | None) -> dict[str, Any]:
    identity = packet.get("chapter_identity") or {}
    goal = _text(identity.get("goal"))
    conflict = _text(identity.get("conflict"))
    scene = _text(identity.get("main_scene"))
    chapter_no = _text(identity.get("chapter_no"))
    flow_name = _text((flow_card or {}).get("name") or identity.get("flow_template_name")) or "当前流程卡"
    child_name = _text((flow_child_card or {}).get("name")) or "当前流程子卡"
    opening = _text((flow_child_card or {}).get("opening_move"))
    middle = _text((flow_child_card or {}).get("mid_shift"))
    ending = _text((flow_child_card or {}).get("ending_drop"))
    summary = f"第{chapter_no}章围绕“{goal or conflict or flow_name}”推进，主结构采用{flow_name}，本章具体落法采用{child_name}。"
    return {
        "instance_id": f"{_text((flow_child_card or {}).get('child_id') or (flow_card or {}).get('flow_id'))}__chapter_{chapter_no or 'x'}",
        "title": f"{flow_name}·本章实例卡",
        "summary": _truncate(summary, 120),
        "chapter_goal": goal,
        "main_scene": scene,
        "opening_move": opening,
        "mid_shift": middle,
        "ending_drop": ending,
        "avoid": _text((flow_child_card or {}).get("avoid")),
    }


def _derive_writing_instance_cards(packet: dict[str, Any], writing_cards: list[dict[str, Any]], writing_child_cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    identity = packet.get("chapter_identity") or {}
    goal = _text(identity.get("goal"))
    scene = _text(identity.get("main_scene"))
    by_parent = { _text(item.get("parent_strategy_id") or item.get("parent_id")): item for item in writing_child_cards if isinstance(item, dict)}
    payload: list[dict[str, Any]] = []
    for card in writing_cards[:4]:
        strategy_id = _text(card.get("strategy_id") or card.get("card_id"))
        child = by_parent.get(strategy_id) or {}
        payload.append(
            {
                "instance_id": f"{strategy_id}__instance",
                "title": f"{_text(card.get('name'))}·本章实例卡",
                "summary": _truncate(f"围绕“{goal or scene or '当前目标'}”强化{_text(card.get('name'))}。{_text(child.get('directive_focus') or card.get('writing_directive'))}", 120),
                "directive": _text(child.get("directive_focus") or card.get("writing_directive")),
                "opening_focus": _text(child.get("opening_focus")),
                "mid_focus": _text(child.get("mid_focus")),
                "ending_focus": _text(child.get("ending_focus")),
                "avoid": _text(child.get("avoid")),
            }
        )
    return payload


def apply_prompt_strategy_selection_to_packet(
    packet: dict[str, Any],
    selected_strategy_ids: list[str] | None,
    *,
    selected_flow_template_id: str | None = None,
    selected_flow_child_card_id: str | None = None,
    selected_writing_child_card_ids: list[str] | None = None,
    selection_note: str | None = None,
) -> dict[str, Any]:
    if not isinstance(packet, dict):
        return packet
    ordered_ids = [str(item or "").strip() for item in (selected_strategy_ids or []) if str(item or "").strip()]
    clean_flow_id = _text(selected_flow_template_id)
    selection_note_text = _truncate(selection_note, 96)
    if not ordered_ids and not clean_flow_id:
        empty_selection = {
            "selected_flow_template_id": None,
            "selected_strategy_ids": [],
            "selection_note": selection_note_text,
        }
        packet["prompt_selection"] = empty_selection
        packet["writing_card_selection"] = {
            **empty_selection,
            "selected_flow_card_id": None,
            "selected_flow_child_card_id": None,
            "selected_writing_card_ids": [],
            "selected_writing_child_card_ids": [],
        }
        packet["selected_prompt_strategies"] = []
        packet["selected_writing_cards"] = []
        packet["selected_writing_child_cards"] = []
        packet["selected_writing_instance_cards"] = []
        packet["selected_flow_instance_card"] = {}
        return packet

    library = {item["strategy_id"]: item for item in build_prompt_strategy_library() if _text(item.get("strategy_id"))}
    selected = [library[item] for item in ordered_ids if item in library]
    flow_index = {item["flow_id"]: item for item in (packet.get("flow_template_index") or []) if _text(item.get("flow_id"))}
    selected_flow = flow_index.get(clean_flow_id) if clean_flow_id else None
    clean_flow_child_id = _text(selected_flow_child_card_id) or (_default_flow_child_id(packet, clean_flow_id) or "")
    child_ids = [str(item or "").strip() for item in (selected_writing_child_card_ids or []) if str(item or "").strip()] or _default_writing_child_ids(packet, ordered_ids)

    packet["prompt_selection"] = {
        "selected_flow_template_id": clean_flow_id or None,
        "selected_strategy_ids": ordered_ids,
        "selection_note": selection_note_text,
    }
    packet["writing_card_selection"] = {
        "selected_flow_template_id": clean_flow_id or None,
        "selected_flow_card_id": clean_flow_id or None,
        "selected_flow_child_card_id": clean_flow_child_id or None,
        "selected_strategy_ids": ordered_ids,
        "selected_writing_card_ids": ordered_ids,
        "selected_writing_child_card_ids": child_ids,
        "selection_note": selection_note_text,
    }
    packet["selected_prompt_strategies"] = selected[:4]
    packet["selected_writing_cards"] = selected[:4]

    flow_child = _flow_child_lookup(packet).get(clean_flow_child_id) if clean_flow_child_id else None
    if selected_flow:
        packet["selected_flow_template"] = selected_flow
        packet["selected_flow_card"] = selected_flow
        chapter_identity = packet.setdefault("chapter_identity", {})
        flow_plan = packet.setdefault("flow_plan", {})
        chapter_identity["flow_template_id"] = _text(selected_flow.get("flow_id"))
        chapter_identity["flow_template_tag"] = _text(selected_flow.get("quick_tag"))
        chapter_identity["flow_template_name"] = _text(selected_flow.get("name"))
        flow_plan["flow_template_id"] = _text(selected_flow.get("flow_id"))
        flow_plan["flow_template_tag"] = _text(selected_flow.get("quick_tag"))
        flow_plan["flow_template_name"] = _text(selected_flow.get("name"))
        flow_plan["turning_points"] = list(selected_flow.get("turning_points") or [])[:3]
        flow_plan["variation_note"] = _truncate(selected_flow.get("variation_notes"), 72)
    if flow_child:
        packet["selected_flow_child_card"] = flow_child
        packet.setdefault("flow_plan", {})["flow_child_card_id"] = _text(flow_child.get("child_id"))
        packet.setdefault("flow_plan", {})["flow_child_card_name"] = _text(flow_child.get("name"))
        packet.setdefault("flow_plan", {})["opening_move"] = _text(flow_child.get("opening_move"))
        packet.setdefault("flow_plan", {})["mid_shift"] = _text(flow_child.get("mid_shift"))
        packet.setdefault("flow_plan", {})["ending_drop"] = _text(flow_child.get("ending_drop"))

    writing_child_lookup = _writing_child_lookup(packet)
    selected_child_cards = [writing_child_lookup[item] for item in child_ids if item in writing_child_lookup][:4]
    packet["selected_writing_child_cards"] = selected_child_cards
    packet["selected_flow_instance_card"] = _derive_flow_instance_card(packet, selected_flow, flow_child)
    packet["selected_writing_instance_cards"] = _derive_writing_instance_cards(packet, selected[:4], selected_child_cards)

    input_policy = packet.setdefault("input_policy", {})
    input_policy["prompt_selection_rule"] = "AI 先从流程母卡、流程子卡、写法母卡、写法子卡压缩索引里选定本章写法，再把这些实例卡插入正文生成提示。"
    return packet
