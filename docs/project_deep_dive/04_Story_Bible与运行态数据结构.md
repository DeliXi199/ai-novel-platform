# 04 Story Bible 与运行态数据结构

这一份是整个项目最关键的一份。  
如果前面数据库表讲的是“正式对象”，那么这一份讲的是“真正驱动生成的运行大脑”。

---

## 1. 先说结论：`Novel.story_bible` 才是项目核心状态中心

数据库表保存的是“书、章、摘要、任务”这类稳定主实体。  
但真正决定下一章怎么写的，是 `story_bible` 里面的这些东西：

- 题材推进引擎；
- 全书总纲；
- 当前剧情弧；
- 待启用剧情弧；
- 近 7 章章节卡队列；
- 长期人物/资源/关系状态；
- 事实账本；
- 硬事实守卫；
- 连载发布状态；
- 工作流阶段；
- 上一章承接桥；
- 当前实时运行快照。

换句话说，`story_bible` 不是附属备注，而是**运行时真相**。

---

## 2. Story Bible 的顶层思路

这个项目当前把 Story Bible 组织成一种“分域大对象”。

可以把它粗分成几组：

### A. 创作定位层
决定这本书“是什么”的东西：

- `project_card`
- `story_engine_diagnosis`
- `story_strategy_card`
- `global_outline`
- `volume_cards`

### B. 世界与规则层
决定“世界怎么运转”的东西：

- `world_bible`
- `cultivation_system`
- `power_system`
- `opening_constraints`

### C. 叙事实体层
决定“谁在场、谁能用、谁互相关联”的东西：

- `story_domains`
- `entity_registry`
- `template_library`

### D. 规划与复盘层
决定“接下来写什么、之前写得怎样”的东西：

- `active_arc`
- `pending_arc`
- `outline_state`
- `planner_state`
- `retrospective_state`
- `flow_control`
- `planning_layers`

### E. 连载运行层
决定“当前供应链处于什么状态”的东西：

- `serial_rules`
- `serial_runtime`
- `long_term_state`
- `fact_ledger`
- `hard_fact_guard`

### F. 工作流与 UI 快照层
决定“前端工作台看到什么、系统当前跑到哪一步”的东西：

- `story_workspace`
- `workflow_state`
- `story_state`
- `daily_workflow`
- `initialization_packet`

---

## 3. Story Bible 的元信息：`story_bible_meta`

对应逻辑：`story_runtime_support.py`

这是 Story Bible 自己的版本信息。

### `schema_version`
当前 schema 版本。  
代码里是版本 8。  
它用来校验并补齐当前新系统需要的基础结构。

### `architecture`
当前架构标识。  
代码中是 `story_bible_v2_foundation`。  
这表示当前 Story Bible 已经是 V2 地基结构。

### `upgrade_history`
这里记录结构升级与补齐历史，方便追踪当前 Story Bible 的演化。

### `migration_notes`
迁移说明。  
用于说明当前 Story Bible 增加了哪些正式域，比如：

- `story_domains`
- `power_system`
- `opening_constraints`
- `template_library`
- `importance_state`
- `constraint_reasoning_state`
- `core_cast_state`


这部分的作用很像数据库 migration，但作用在 JSON 架构层。

---

## 4. 创作定位层

### 4.1 `story_engine_diagnosis`

这是初始化阶段生成的“题材推进引擎诊断”。

它包含的参数含义如下：

#### `story_subgenres`
子题材列表。  
用于更精准描述作品气质，而不是只说一个大题材。

#### `primary_story_engine`
主要推进引擎。  
比如“低位求生 + 资源争取 + 谨慎试探”这种，决定前期故事怎么有拉力。

#### `secondary_story_engine`
次推进引擎。  
给主推进模式补辅助轨道，避免一路单调。

#### `opening_drive`
开篇驱动力。  
告诉系统前期应该靠什么把读者拉住。

#### `early_hook_focus`
前期钩子重点。  
比如前 10 章到底要优先建立什么上瘾点。

#### `protagonist_action_logic`
主角行动逻辑。  
这会直接影响“主角应不应该主动出手、试探、布局”。

#### `pacing_profile`
节奏画像。  
决定前期应该稳推、快推，还是克制推进。

#### `world_reveal_strategy`
世界显影策略。  
告诉系统世界设定要怎么逐步露出来，避免一股脑讲设定。

#### `power_growth_strategy`
力量成长策略。  
定义成长必须绑定哪些代价、资源和后果。

#### `early_must_haves`
前期必须出现的要素列表。

#### `avoid_tropes`
需要回避的套路列表。

#### `differentiation_focus`
差异化焦点列表。  
避免写成千篇一律的同质化开局。

#### `must_establish_relationships`
前期必须建立的关键关系类型。

#### `tone_keywords`
语气关键词。

---

### 4.2 `story_strategy_card`

这是更具体的“前 30 章推进战略卡”。

#### `story_promise`
这本书前 30 章承诺给读者什么体验。

#### `strategic_premise`
把 premise 变成策略表达后的版本。

#### `main_conflict_axis`
主冲突轴。

#### `first_30_mainline_summary`
前 30 章主线摘要。

#### `chapter_1_to_10 / chapter_11_to_20 / chapter_21_to_30`
每一段都对应一个 `ThirtyChapterPhase`，里面有：

- `range`：章节区间；
- `stage_mission`：这一段的阶段任务；
- `reader_hook`：吸引读者的关键钩子；
- `frequent_elements`：应该频繁使用的元素；
- `limited_elements`：必须限制的元素；
- `relationship_tasks`：关系层面的推进任务；
- `phase_result`：这一段结束时应得到什么结果。

#### `frequent_event_types`
前 30 章优先使用的事件类型。

#### `limited_event_types`
需要少用或避免连用的事件类型。

#### `must_establish_relationships`
必须在前 30 章建立起来的关系。

#### `escalation_path`
升级路径。  
表示故事不是平推，而是一层层抬压强。

#### `anti_homogenization_rules`
反同质化规则。  
这是项目非常珍惜的一组约束，用来阻止“同一个桥段连写三章”。

---

### 4.3 `project_card`

这是全书的高层项目卡，相当于一本书的产品定义页。

#### `book_title`
书名。

#### `genre_positioning`
题材定位。

#### `genre_subtypes`
更细子类型。

#### `core_sell_point`
核心卖点。  
是给系统和工作台看的“这本书最该抓住什么”。

#### `one_line_intro`
一句话介绍。

#### `protagonist`
主角卡。里面会包含：
- 名字；
- 核心欲望；
- 核心恐惧；
- 优势；
- 缺陷。

#### `golden_finger`
金手指或核心异常线索说明。

#### `story_engine_profile`
对应前面的 diagnosis。

#### `first_30_chapter_engine`
对应前面的 strategy card。

#### `first_30_chapter_mainline`
前 30 章主线概述。

#### `mid_term_direction`
中期方向。

#### `endgame_direction`
终局方向。

这部分本质上是“总策划卡”。

---

### 4.4 `global_outline`

全书总纲。

#### `story_positioning`
对故事的整体定位说明。  
结构是字典，允许后续细化。

#### `acts`
故事阶段数组。每个元素是 `StoryAct`：

##### `act_no`
第几幕/第几段。

##### `title`
该阶段标题。

##### `purpose`
该阶段存在的目的。

##### `target_chapter_end`
这个阶段预计在第几章收束。

##### `summary`
该阶段概要。

---

### 4.5 `volume_cards`

卷卡列表。  
它是把全书总纲切成“连载可执行卷结构”的一层。

每张卷卡通常包含：

- `volume_no`：卷号；
- `volume_name`：卷名；
- `start_chapter` / `end_chapter`：卷范围；
- `volume_goal`：本卷目标；
- `main_conflict`：本卷主要冲突；
- `cool_point`：本卷爽点/卖点；
- `major_crisis`：本卷大危机；
- `volume_result`：卷尾得到什么；
- `volume_loss`：卷尾失去什么；
- `next_hook`：下一卷入口；
- `status`：planned / current / completed 之类状态。

---

## 5. 世界与规则层

### 5.1 `world_bible`

这是世界设定主字典。

#### `world_scale`
世界规模如何展开。  
强调是否先从局部地区入手，再逐步扩张。

#### `mortals_vs_cultivators`
凡人和修炼者/高位者之间的结构差。

#### `resource_controllers`
关键资源由谁控制。

#### `factions`
主要势力列表。

#### `higher_world_exists`
是否存在更高层世界或更高地图。

它的作用是告诉系统：这不是一片真空背景，资源、阶层、势力、地图是有结构的。

---

### 5.2 `cultivation_system`

虽然名字是修炼体系，但本质是“力量成长框架”。

#### `realms`
境界列表。

#### `gap_rules`
强弱差距规则。  
比如同境界、小境界、大境界之间怎么压制。

#### `breakthrough_conditions`
突破需要什么条件。

#### `combat_styles`
战斗差异不只是数值，还包含哪些维度。

#### `cross_realm_rule`
越级战的成立边界。

---

### 5.3 `power_system`

这是比 `cultivation_system` 更正式、更适合运行时使用的结构化力量体系。

#### `system_name`
力量体系名。

#### `realm_system`
里面包括：
- `realms`：境界列表；
- `realm_cards`：每个境界的说明卡；
- `current_reference_realm`：当前参考境界。

#### `power_rules`
里面包括：
- `gap_rules`：强弱差规则；
- `breakthrough_conditions`：突破条件；
- `cross_realm_rule`：越级规则；
- `core_limitations`：必须长期坚持的限制条件。

#### `combat_rules`
里面包括：
- `combat_styles`：战斗特征；
- `same_realm_layers`：同境界内部如何细分；
- `forbidden_patterns`：禁止写成什么样。

---

### 5.4 `opening_constraints`

这是项目非常有意思的设计：把“开书前 20 章该如何交代世界、势力、等级体系”显式写成结构。

#### `opening_phase_chapter_range`
开篇阶段范围。默认是 1 到 20 章。

#### `must_gradually_explain`
必须逐步交代的内容列表。  
例如世界背景、势力格局、力量边界、异常线索等。

#### `background_delivery`
告诉系统：
- 世界背景怎样慢慢讲；
- 势力格局怎样慢慢显影；
- 力量体系怎样慢慢被读者看懂。

#### `pace_rules`
对前 3 章、前 15 章、前 20 章的节奏要求。  
还包含 `forbidden_shortcuts`，防止过快跳地图、乱越级、用说明文灌设定。

#### `foundation_reveal_schedule`
按窗口划分的基础信息显影计划。

#### `power_system_reveal_plan`
力量体系该如何按章节窗口逐步曝光。

#### `long_term_mainline`
长线主线提示，包括：
- 开篇目标；
- 中期方向；
- 终局方向。

这是“开篇工程约束书”。

---

## 6. 叙事实体层

### 6.1 `story_domains`

这是 V2 Story Bible 新增的正式域之一。  
它把小说里的主要叙事实体分成四类：

- `characters`
- `resources`
- `relations`
- `factions`

#### `characters`
角色域，按角色名索引。  
每个角色卡一般会包含：

- `name`：名字；
- `entity_type`：实体类型，固定是角色；
- `role_type`：主角、配角等；
- `importance_tier`：重要层级；
- `protagonist_relation_level`：与主角关系级别；
- `narrative_priority`：叙事优先级；
- `current_strength`：当前强度；
- `current_goal`：当前目标；
- `core_desire`：核心欲望；
- `core_fear`：核心恐惧；
- `behavior_template_id`：行为模板 ID；
- `speech_style`：说话方式；
- `work_style`：做事方式；
- `relationship_index`：关系索引；
- `resource_refs`：关联资源；
- `faction_refs`：关联势力；
- `status`：当前状态。

这部分是真正的“运行角色卡”，不只是静态人设说明。

#### `resources`
资源域。  
记录资源是什么、归谁、状态如何、有什么叙事作用。  
这让“资源”从普通文本概念升级为可追踪实体。

#### `relations`
关系域。  
不是简单字符串，而是可持续维护的关系实体，适合做关系推进、关系排期、轻触/重推等。

#### `factions`
势力域。  
每个势力卡会描述：
- 名字；
- 实体类型；
- 势力层级；
- 势力类型；
- 领地；
- 核心目标；
- 与主角关系；
- 掌控资源；
- 核心角色。

---

### 6.2 `template_library`

模板库是为了让系统别每次都从零靠“灵感硬凑”。

它包含：

#### `character_templates`
角色行为模板库。  
定义某类人物的性格、说话方式、行事逻辑、压力反应、禁忌等。

#### `flow_templates`
流程模板库。  
定义一章的推进节奏与转折骨架。

#### `payoff_cards`
兑现模板库。  
用于描述“某种期待如何回收”。

#### `scene_templates`
场景模板库。  
用于给场景结构提供常用骨架。

#### `roadmap`
模板库建设路线图，记录目标数量、当前数量、状态说明等。

---

### 6.3 `entity_registry`

实体注册表，用来给 story domains 做索引。

#### `by_type`
按类型列出已有实体名。

#### `card_ids`
按类型维护卡片 ID 映射。

#### `next_seq`
每种实体类型的下一个序号，用于新建卡片 ID。

#### `last_rebuilt_at`
上次重建注册表的时间。

它的作用不是表达剧情，而是支撑“实体可索引、可选择、可引用”。

---

## 7. 规划与复盘层

### 7.1 `active_arc`

当前正在执行的剧情弧。

它通常包含：

- `arc_no`：弧编号；
- `start_chapter` / `end_chapter`：覆盖范围；
- `focus`：这一弧的核心焦点；
- `bridge_note`：向下一段过渡的桥注；
- `chapters`：章节计划列表。

其中 `chapters` 内的元素就是 `ChapterPlan`。

#### `ChapterPlan` 里的关键参数

##### `chapter_no`
第几章。

##### `title`
规划标题。

##### `goal`
本章目标。

##### `ending_hook`
章末钩子。

##### `chapter_type`
章节类型。

##### `event_type`
事件类型。  
用来控制连续几章不要总写成同类桥段。

##### `progress_kind`
推进类型。  
比如推进资源、推进关系、推进风险、推进信息。

##### `flow_template_id / flow_template_tag / flow_template_name`
本章匹配了哪个流程模板。

##### `flow_turning_points`
关键转折点列表。

##### `flow_variation_note`
这次流程模板应该怎样变体，避免套模版感太重。

##### `proactive_move`
主角主动动作。  
这很重要，因为系统明确要求主角不能总被推着走。

##### `payoff_or_pressure`
本章是偏兑现还是偏加压。

##### `hook_kind`
钩子类型。

##### `target_visible_chars_min / max`
期望本章显性出场角色数量区间。

##### `hook_style`
钩子风格。

##### `main_scene`
主要场景。

##### `conflict`
本章核心冲突。

##### `opening_beat`
开头拍子。

##### `mid_turn`
中段转折。

##### `discovery`
发现点。

##### `closing_image`
收束画面。

##### `supporting_character_focus`
本章重点配角。

##### `supporting_character_note`
配角使用说明。

##### `new_resources`
本章可能引入的新资源。

##### `new_factions`
本章可能引入的新势力。

##### `new_relations`
本章可能建立的新关系提示。

##### `stage_casting_action / target / note`
舞台调度动作，决定是否该引入新角色、刷新角色功能位等。

##### `writing_note`
给正文生成的额外文字提示。

##### `agency_mode` 以及一组 `agency_*`
这是主角能动性模式说明，用来细化主角应该如何主动。

---

### 7.2 `pending_arc`

待切换剧情弧。  
当当前 arc 快写完时，系统会提前预取下一段 arc。  
这样下一章不会在快没纲的时候突然掉进黑洞。

---

### 7.3 `outline_state`

近纲总状态。

通常会包含：

- `planned_until`：已经规划到第几章；
- `next_arc_no`：下一段 arc 编号；
- `bootstrap_generated_until`：初始化阶段一次性生成到哪一章。

它是“规划边界标记”。

---

### 7.4 `planner_state`

规划器状态。字段含义如下：

#### `recent_flow_usage`
最近用过哪些流程模板。  
防止重复。

#### `chapter_element_selection`
每章选了哪些实体/元素。

#### `resource_plan_cache`
资源规划缓存。

#### `resource_capability_plan_cache`
资源能力规划缓存。

#### `resource_plan_history`
资源规划历史。

#### `resource_capability_history`
资源能力历史。

#### `selected_entities_by_chapter`
按章节记录选中的实体。

#### `continuity_packet_cache`
连续性包缓存。

#### `rolling_continuity_history`
滚动连续性历史。

#### `last_planned_chapter`
最近规划到哪一章。

#### `last_continuity_review_chapter`
最近做连续性审查到哪一章。

#### `status`
状态说明，当前默认是 `foundation_ready`。

---

### 7.5 `retrospective_state`

复盘状态。

#### `last_review_chapter`
最近复盘到哪一章。

#### `last_stage_review_chapter`
最近阶段复盘到哪一章。

#### `pending_character_reviews`
待处理的人物复盘任务。

#### `relationship_watchlist`
需要关注的关系线。

#### `scheduled_review_interval`
复盘间隔，默认每 5 章。

#### `last_review_notes`
上次复盘笔记。

#### `latest_stage_character_review`
最新阶段角色复盘结果。

#### `pending_payoff_compensation`
待补偿的 payoff。  
这很关键：如果某章的兑现不够，系统不是装没看见，而是会把“补偿任务”挂进后续窗口。

#### `status`
状态。

---

### 7.6 `flow_control`

流程控制器。

#### `anti_repeat_window`
防重复窗口，默认 5。  
表示最近 5 章内要防止同类流程反复出现。

#### `recent_event_types`
最近事件类型列表。

#### `recent_flow_ids`
最近流程模板 ID 列表。

#### `consecutive_flow_penalty`
连续使用同类流程的惩罚系数。

#### `status`
状态。

---

### 7.7 `planning_layers`

这是“哪些规划层已经准备好了”的标志集。  
例如：

- 全书总纲是否就绪；
- 卷卡是否就绪；
- 第一段近纲是否就绪；
- 第一批章节卡是否就绪；
- 连载规则是否就绪；
- 长期状态是否就绪；
- 初始化包是否就绪。

它更像“施工检查表”。

---

## 8. 连载运行层

### 8.1 `serial_rules`

连载规则是整个供应链的总法律。

#### `published_chapters_immutable`
已发布章节不可改。

#### `published_text_is_not_draft`
已发布文本不是草稿。

#### `fact_priority`
事实优先级。  
通常是：已发布章节 > 库存章节 > 规划文档。

#### `fact_ledger_policy`
事实账本策略，包括：
- 是否启用；
- 已发布事实是否锁定；
- 库存事实能否提升为正式事实；
- 回退索引策略。

#### `inventory_policy`
库存策略，包括：
- 未发布库存是否允许修；
- 只允许修尾部；
- 已发布章节永不回写。

#### `batch_generation`
批量生成策略，包括：
- 只允许顺序生成；
- 每章之间必须刷新状态；
- 禁止并行批量。

#### `daily_modes`
允许的日常模式，目前是 `live_publish` 与 `stockpile`。

#### `problem_resolution_policy`
一旦出问题，优先改后续结构与库存，不回改已发布硬事实。

#### `ending_policy`
项目必须能收束，不允许无止境往前拖。

#### `hard_fact_guard`
硬事实守卫规则本体。

---

### 8.2 `serial_runtime`

这是当前连载时态。

#### `delivery_mode`
当前交付模式。

#### `supports_live_publish`
是否支持即时发布。

#### `supports_stockpile`
是否支持库存模式。

#### `last_publish_action`
最近一次发布动作记录。

#### `continuity_mode`
当前承接模式，代码里常见是 `strong_bridge`。

#### `previous_chapter_bridge`
上一章承接桥。  
这是非常重要的下一章开头上下文来源。

---

### 8.3 `fact_ledger`

事实账本。  
虽然具体内部结构由 `story_fact_ledger` 维护，但功能非常明确：

- 已发布事实单独锁定；
- 库存事实可转正；
- 每章产生的关键事实会入账；
- 后续章节生成必须优先服从事实账本。

它是“小说记忆”的正式账本。

---

### 8.4 `hard_fact_guard`

硬事实守卫。  
用于防止新章节和旧章节发生不可接受的硬冲突，比如：

- 人物状态反复横跳；
- 已明确的事实被后文推翻；
- 已锁定发布内容被隐式篡改。

它不是简单文本比对，而是“事实约束层”。

---

### 8.5 `long_term_state`

长期状态层是另一个特别重要的大块。

#### `protagonist_profile`
主角长期画像。

#### `character_states`
其他角色长期状态。

#### `resource_states`
资源长期状态。

#### `relation_states`
关系长期状态。

#### `faction_states`
势力长期状态。

#### `foreshadowing_state`
伏笔状态数组。

#### `history_summaries`
历史摘要。  
用于滚动保留长期记忆。

#### `volume_progress`
卷进度。

#### `planner_state_snapshot`
规划状态快照。

#### `fact_ledger`
长期状态层里的事实账本镜像。

#### `chapter_release_state`
章节发布状态对象，里面包含：

##### `delivery_mode`
当前交付模式。

##### `published_through`
已发布到第几章。

##### `latest_generated_chapter`
最近生成到第几章。

##### `latest_available_chapter`
当前可供使用的最靠后章节。

##### `stock_chapter_count`
库存章数量。

##### `published_chapter_count`
已发布章数量。

##### `locked_chapter_count`
已锁定章节数量。

##### `chapters`
按章节号记录每章的发布状态细节。

这部分其实就是“供应链仪表板”。

---

## 9. 工作流与 UI 快照层

### 9.1 `story_workspace`

这是给工作台看的综合控制台。初始结构里主要有：

#### `protagonist_profile`
主角当前画像卡。包括境界、主技能、限制、资源、目标、风险等。

#### `power_ledger`
力量压制与战斗边界说明。

#### `cast_cards`
角色卡快照。

#### `relationship_journal`
关系日志。

#### `foreshadowing`
伏笔列表。

#### `timeline`
时间线。

#### `near_7_chapter_outline`
近 7 章简版提纲。

#### `near_30_progress`
近 30 章推进位置说明。

#### `daily_workbench`
日工作台，包括昨天结尾、今天功能、三行提纲、明日提示。

#### `chapter_retrospectives`
章节复盘。

#### `volume_reviews`
卷复盘。

后续 `refresh_planning_views()` 还会往里面补：

- `chapter_card_queue`
- `planning_status`
- `current_execution_packet`

所以它既是“给人看”的控制台，又是“当前窗口摘要层”。

---

### 9.2 `workflow_state`

这是流程工作流状态，不是单纯剧情规划状态。

其中很重要的一块是 `current_pipeline`，会描述：

- 当前目标章节号；
- 项目卡是否就绪；
- 当前卷卡是否就绪；
- 近纲是否就绪；
- 章节卡是否就绪；
- 草稿是否就绪；
- 摘要复盘是否就绪；
- 上次完成到哪个阶段；
- 上次完成到哪一章。

另外它还会保存 bootstrap 的状态与错误信息。

---

### 9.3 `story_state`

这是一个更偏“运行中临时状态桶”的结构。  
项目会往里面塞诸如：

- 当前 planning window 信息；
- live runtime 快照；
- 当前 pipeline 视图等。

它更接近“控制台背后的实时缓存状态”。

---

### 9.4 `daily_workflow`

这不是实时状态，而是给系统和工作台的日常创作流程指导：

- 回看昨天结尾；
- 明确今天这章的功能；
- 写三行章纲；
- 写正文时盯住主角行动、事件推进、新变化和章末拉力；
- 收工时留下明天提示。

还带一组质量底线检查项。

---

### 9.5 `initialization_packet`

初始化包。  
它是把系统认为“初始化已经准备好的关键材料”打一个快照，方便工作台和后续流程使用。

---

## 10. 上一章承接桥：`previous_chapter_bridge`

这是 `serial_runtime` 里极有实战价值的对象。

它通常会包括：

- 来源章节号；
- 标题简版；
- 尾段摘录；
- 最后两段文本；
- 最后场景卡摘要；
- 场景执行卡摘要；
- scene outline 压缩版；
- scene handoff card；
- 未解决动作链；
- 需带入下一章的线索；
- 当前在场人物；
- 下一章开头指令；
- 开头锚点。

它相当于：  
**系统专门为了“下一章开头别断气”准备的一份桥接包。**

---

## 11. 生成元数据里的运行态结构

虽然不属于 `story_bible` 顶层，但每章 `generation_meta` 也保存大量运行态信息，值得一起理解。

常见重要块包括：

### `chapter_plan`
本章最后实际使用的规划卡。

### `chapter_plan_packet`
本章的规划包。

### `length_targets`
字数/出场角色等目标。

### `context_stats`
本章上下文包统计。

### `manual_framework`
记录这章是否启用了 project card、volume card、story workspace、strict pipeline 等。

### `llm_call_trace`
本章调用模型的轨迹信息。

### `serial_generation_guard`
生成守卫配置，比如：
- 当前处于生成锁；
- LLM 调用最小间隔；
- 草稿最大尝试次数；
- 总尝试上限；
- arc 预取阈值；
- 每章刷新状态；
- 禁止并行批量。

### `fact_entries`
本章写入了哪些事实。

### `hard_fact_report`
硬事实审查结果。

### `continuity_bridge`
本章生成后为下一章准备的桥。

### `title_refinement`
标题精修信息。

### `quality_rejections`
质量拒稿记录。

### `payoff_delivery`
本章 payoff 兑现评估。

### `structural_signals`
本章结构信号，包括事件类型、推进类型、钩子类型、能动性模式等。

这等于是“单章级运行快照”。

---

## 12. 这一层真正体现的设计哲学

Story Bible 这一层说明了项目最核心的思路：

### 第一，小说状态必须结构化
否则一旦写到几十章，系统就会失忆。

### 第二，规划、世界、事实、连载状态必须分层
否则不同粒度的信息会混成一锅。

### 第三，前端看到的工作台只是这个大状态的投影
真正驱动后续生成的是结构化域，不是 UI 卡片本身。

### 第四，系统不是“写过就忘”
它通过事实账本、长期状态、桥接包、复盘状态，把每一章的结果带向下一章。

这就是为什么这个项目已经不再像一个普通 prompt 工具，而像一个“叙事操作系统”。
