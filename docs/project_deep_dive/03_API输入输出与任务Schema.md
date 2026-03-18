# 03 API 输入输出与任务 Schema

这一份讲接口层的数据外壳。  
重点不是重复代码，而是解释：前端和后端到底如何说话，传的每个参数想表达什么。

---

## 1. 为什么 Schema 层很重要

这个项目的 service 层很复杂。  
如果没有一层清晰的 Schema 做边界，前端就会直接吞一堆混乱 JSON，工作台很快会变成事故现场。

Schema 层的价值是：

- 约束输入参数；
- 统一输出格式；
- 给前端稳定契约；
- 避免 service 层内部结构直接外泄。

---

## 2. 小说相关 Schema

对应文件：`backend/app/schemas/novel.py`

### 2.1 `NovelCreate`

这是创建小说时的输入结构。

#### `genre`
题材。  
不能为空，长度上限 100。  
它会参与初始化分析、题材引擎判断、包装信息生成。

#### `premise`
故事 premise。  
不能为空。  
这是生成总纲和剧情弧时的核心依据。

#### `protagonist_name`
主角名。  
不能为空，长度上限 100。  
初始化时会把它植入项目卡、角色域、控制台、上下文系统。

#### `style_preferences`
风格偏好字典。  
默认空字典。  
它不是一个死板 schema，而是给系统提供额外创作倾向和定制设定。  
很多 builder 都会从这里拿值，比如境界、节奏、世界尺度、金手指、开局状态等。

---

### 2.2 `NovelRenameRequest`

#### `title`
新书名。  
不能为空，长度上限 255。  
这个接口除了更新数据库字段，也会同步更新 `story_bible` 里的相关标题，避免状态层出现“双标题”。

---

### 2.3 `NovelListItemResponse`

这是列表页摘要对象，字段包括：

#### `id`
小说 ID。

#### `title`
当前标题。

#### `genre`
题材。

#### `protagonist_name`
主角名。

#### `current_chapter_no`
当前已生成的最大章节号。

#### `status`
当前状态，例如初始化中、可生成、生成中等。

#### `created_at`
创建时间。

#### `updated_at`
更新时间。

它的目的不是把全书状态全部拉回来，而是给列表页一个轻量概览。

---

### 2.4 `NovelListResponse`

#### `total`
总条数。

#### `limit`
分页大小。

#### `offset`
分页偏移。

#### `items`
列表项数组，也就是一组 `NovelListItemResponse`。

---

### 2.5 `NovelResponse`

这是单本小说详情对象。  
相比列表摘要，它会包含更多内容。

#### `id / title / genre / premise / protagonist_name`
基础信息，不再重复。

#### `style_preferences`
原始风格偏好。  
给前端和后端都保留可追溯的初始化输入。

#### `story_bible`
整本书的大状态 JSON。  
这意味着有些接口会直接把整个 Story Bible 带回来。  
对于工作台类页面，这很实用；对于纯列表页则太重。

#### `current_chapter_no`
当前已生成章号。

#### `status`
总状态。

#### `created_at / updated_at`
时间信息。

---

### 2.6 `NovelDeleteResponse`

#### `deleted_novel_id`
被删除的小说 ID。

#### `deleted_title`
被删除作品标题。

#### `deleted_chapter_count`
连带删除了多少章节。

这是一种很稳妥的删除回执设计：告诉前端“删掉的是谁，影响了多少正文数据”。

---

## 3. 章节相关 Schema

对应文件：`backend/app/schemas/chapter.py`

### 3.1 类型别名：`ChapterSerialStage`

允许值：

- `draft`
- `stock`
- `published`

它表示章节在连载供应链中的状态。  
在实际项目里：

- `stock` 更像“库存稿”；
- `published` 更像“已上架”；
- `draft` 是保留概念位。

---

### 3.2 类型别名：`DeliveryMode`

允许值：

- `live_publish`
- `stockpile`

它描述的是**生成后的交付模式**，而不是章节当前状态。

#### `live_publish`
生成一章就立刻发布并锁定。

#### `stockpile`
生成一章先进入库存，后续再批量发布。

---

### 3.3 `ChapterListItemResponse`

给章节列表页用的轻量对象。

#### `id`
章节记录 ID。

#### `chapter_no`
章节号。

#### `title`
章节标题。

#### `content_preview`
正文预览片段。  
用于列表中快速浏览，不拉全量正文。

#### `char_count`
字符数。  
帮助前端显示篇幅信息。

#### `serial_stage`
章节当前连载阶段。

#### `is_published`
是否已发布。

#### `locked_from_edit`
是否锁定编辑。

#### `published_at`
发布时间。

#### `created_at`
创建时间。

---

### 3.4 `ChapterListResponse`

#### `novel_id`
属于哪本书。

#### `total`
章节数。

#### `items`
章节列表项数组。

---

### 3.5 `ChapterResponse`

单章详情对象。

#### `id / novel_id / chapter_no / title`
基础标识。

#### `content`
完整正文。

#### `generation_meta`
该章生成元信息。  
这个字段很重，但对调试和工作台非常关键。

#### `serial_stage / is_published / locked_from_edit / published_at / created_at`
连载与时间相关信息。

---

### 3.6 `ChapterBatchGenerateRequest`

#### `count`
要连续生成多少章。  
最少 1，最多 20。

注意这个批量生成不是并行多线程乱冲，而是**顺序逐章生成**。  
这是项目的重要约束，因为每生成完一章都要刷新状态，下一章必须吃到最新状态。

---

### 3.7 `ChapterBatchResponse`

#### `novel_id`
哪本书。

#### `requested_count`
请求生成多少章。

#### `generated_count`
实际成功生成多少章。

#### `started_from_chapter`
起始章号。

#### `ended_at_chapter`
结束时写到了哪一章。

#### `chapters`
返回的章节详情列表。

#### `progress`
批量过程中的进度快照列表。

---

### 3.8 `ChapterDeleteTailRequest`

这是一个相当谨慎的删除尾章接口。  
它只允许删除末尾连续章节，避免把中间章挖空。

#### `count`
从末尾往回删多少章。

#### `from_chapter_no`
从某章开始一直删到末尾，包含该章。

#### `chapter_nos`
显式指定要删的章节号列表，但必须严格是末尾连续章节。

这个对象有一个自校验规则：  
**三种选择器只能且必须提供一种。**  
这能避免调用方同时传多个删除条件导致语义混乱。

---

### 3.9 `ChapterDeleteTailResponse`

#### `novel_id`
哪本书。

#### `deleted_count`
删了多少章。

#### `deleted_chapter_nos`
删掉的章节号列表。

#### `deleted_titles`
删掉的标题列表。

#### `current_chapter_no`
删除后，当前最高章节号回退到哪里。

---

### 3.10 `ChapterPublishBatchRequest`

#### `count`
从当前最早未发布库存开始，连续发布多少章。  
最少 1，最多 50。

这个接口服务于 `stockpile` 模式，等于把“库存稿”推到“已发布”。

---

### 3.11 `ChapterPublishBatchResponse`

#### `novel_id`
小说 ID。

#### `published_count`
本次发布了多少章。

#### `published_chapter_nos`
发布了哪些章节号。

#### `published_titles`
对应标题。

#### `published_through`
当前已经发布到第几章。

#### `delivery_mode`
当前交付模式。

---

### 3.12 `SerialModeUpdateRequest`

#### `delivery_mode`
要切换到的交付模式，只能是 `live_publish` 或 `stockpile`。

---

### 3.13 `SerialModeResponse`

#### `novel_id`
小说 ID。

#### `delivery_mode`
当前交付模式。

#### `serial_runtime`
序列运行态快照。  
这可以帮助前端立刻知道切换后系统当前的发布/库存状态。

---

### 3.14 TTS 相关 Schema

#### `ChapterTtsVoiceOption`
- `value`：内部语音值；
- `label`：展示给用户的名字。

#### `ChapterTtsGeneratedVariant`
描述已经生成的一种音频版本。  
包含 voice、速率、音量、音调、音频 URL、字幕 URL、文件大小、生成时间等字段。  
它本质上是“一个成品 TTS 变体”的说明书。

#### `ChapterTtsStatusResponse`
这是 TTS 工作台用的状态对象。  
里面会告诉前端：

- 这一章是否允许 TTS；
- 当前是否已就绪；
- 是否正在生成；
- 是否过期需要重做；
- 使用的 voice / rate / volume / pitch；
- 已生成的音频与字幕地址；
- 原因说明；
- 可选 voice 列表；
- 已有变体列表。

#### `ChapterTtsGenerateRequest`
允许前端自定义：

- `voice`
- `rate`
- `volume`
- `pitch`
- `force_regenerate`

这个接口设计明显是为了让 TTS 成为章节的“后处理工序”，而不是写死的一次性产物。

---

## 4. 干预相关 Schema

对应文件：`backend/app/schemas/intervention.py`

### 4.1 `InterventionCreate`

#### `chapter_no`
干预从第几章开始生效，最小值为 1。

#### `raw_instruction`
原始自然语言干预指令。不能为空。

#### `effective_chapter_span`
影响后续多少章。默认 5，最少 1，最多 100。

---

### 4.2 `InterventionResponse`

#### `id / novel_id / chapter_no`
标识信息。

#### `raw_instruction`
原始指令文本。

#### `parsed_constraints`
结构化约束结果。  
这是系统把人话翻译成“更适合机器用的短期控制参数”。

#### `effective_chapter_span`
有效跨度。

#### `applied`
是否已被消费。

#### `created_at`
创建时间。

---

### 4.3 `InterventionListResponse`

#### `novel_id`
小说 ID。

#### `total`
总数量。

#### `items`
干预列表。

---

## 5. 任务相关 Schema

对应文件：`backend/app/schemas/task.py`

### 5.1 类型别名：`TaskType`

允许值：

- `generate_next_chapter`
- `generate_next_chapters_batch`
- `generate_chapter_tts`
- `bootstrap_novel`

它定义了任务大类。

---

### 5.2 类型别名：`TaskStatus`

允许值：

- `queued`
- `running`
- `succeeded`
- `failed`
- `cancelled`

---

### 5.3 `AsyncTaskResponse`

这是任务详情对象，字段很多，但每个都很有用。

#### `id`
任务 ID。

#### `novel_id`
关联小说。

#### `chapter_no`
关联章节；如果任务不针对某一章，可为空。

#### `task_type`
任务类型。

#### `status`
当前状态。

#### `reused_existing`
是否复用已有活跃任务。  
这是去重提交的重要提示，前端可以知道“不是又新开了一个任务”。

#### `owner_key`
用于任务归属和去重判断的键。

#### `request_payload`
原始请求载荷。

#### `progress_message`
当前进度文案。

#### `progress_payload`
当前结构化进度。

#### `result_payload`
结果载荷。

#### `error_payload`
错误载荷。

#### `retry_of_task_id`
若这是重试任务，则指向原任务 ID。

#### `cancel_requested_at`
请求取消时间。

#### `cancelled_at`
真正取消时间。

#### `retryable`
当前是否允许重试。

#### `can_cancel`
当前是否允许取消。

#### `can_retry`
当前是否允许前端显示“重试”按钮。

#### `created_at / updated_at / started_at / finished_at`
任务时间线。

#### `duration_seconds`
执行耗时。

#### `queue_wait_seconds`
排队耗时。

#### `status_url`
可直达的状态接口 URL。

#### `events_url`
可直达的事件流接口 URL。

---

### 5.4 `AsyncTaskListResponse`

#### `novel_id`
小说 ID。

#### `total`
任务数。

#### `items`
任务列表。

---

### 5.5 `AsyncTaskEventResponse`

#### `id`
事件 ID。

#### `task_id`
所属任务。

#### `novel_id`
所属小说。

#### `event_type`
事件类型。

#### `level`
事件级别。

#### `message`
事件文案。

#### `payload`
结构化补充内容。

#### `attempt_no`
第几次尝试。

#### `created_at`
发生时间。

---

### 5.6 `AsyncTaskEventListResponse`

#### `novel_id`
小说 ID。

#### `task_id`
任务 ID。

#### `total`
事件数。

#### `items`
事件列表。

---

### 5.7 `AsyncTaskCleanupResponse`

#### `novel_id`
哪本书。

#### `keep_latest`
保留最近多少条。

#### `deleted_count`
删掉了多少条终态任务。

#### `deleted_task_ids`
删掉了哪些任务 ID。

---

## 6. 工作台相关 Schema

对应文件：`backend/app/schemas/story_studio.py`

### `WorkspaceResponse`

这是前端工作台的总载荷，等于是“把用户打开某本书时需要看的主要块一次性打包”。

#### `novel`
一本书的基础信息，即 `NovelResponse`。

#### `chapters`
章节列表，即 `ChapterListResponse`。

#### `story_workspace`
控制台数据，即 `StoryWorkspaceResponse`。  
这里面会有 Story Bible 快照的重点区域。

#### `planning_data`
额外规划数据字典。  
适合塞轻量规划补充信息。

#### `interventions`
人工干预列表。

#### `selected_chapter`
当前选中的章节详情，可为空。  
前端如果指定查看某章，这里就能直接带回来。

#### `selected_chapter_no`
当前选中的章节号。

#### `active_tasks`
活跃任务列表。  
给前端显示“还有哪些任务正在跑”。

#### `recent_tasks`
最近任务列表。  
让前端可以快速显示最近执行历史。

---

## 7. 控制台 Schema

对应文件：`backend/app/schemas/story_story_studio.py`

这个对象是工作台的核心视觉数据源之一。

#### `novel_id`
小说 ID。

#### `title`
标题。

#### `project_card`
项目卡，属于高层创作定位。

#### `world_bible`
世界设定。

#### `cultivation_system`
修炼/力量体系。

#### `serial_rules`
连载规则。

#### `serial_runtime`
当前连载运行态。

#### `fact_ledger`
事实账本。

#### `hard_fact_guard`
硬事实守卫状态。

#### `long_term_state`
长期状态层。

#### `initialization_packet`
初始化包快照。

#### `current_volume_card`
当前卷卡。

#### `story_workspace`
控制台主体内容，如主角状态、近 7 章、工作台等。

#### `planning_layers`
规划层是否就绪。

#### `planning_state`
这里其实对应 workflow state，而不是狭义 planner state。  
它更像流程工作流状态。

#### `continuity_rules`
连续性规则列表。

#### `daily_workflow`
日常写作工作流说明。

#### `story_state`
运行时状态桶。

---

## 8. 一个很重要的细节：Schema 和实际快照并不完全一致

当前代码里，`build_story_workspace_snapshot()` 实际返回的字段比 `StoryWorkspaceResponse` 声明得更多，额外包括：

- `story_bible_meta`
- `power_system`
- `opening_constraints`
- `story_domains`
- `template_library`
- `planner_state`
- `retrospective_state`
- `flow_control`

但 `StoryWorkspaceResponse` 并没有完整声明这些字段。  
如果接口用了 `response_model=StoryWorkspaceResponse`，FastAPI 会把未声明字段裁掉。

这意味着什么？

意味着后端内部快照其实更丰富，但对外接口层未必全部放行。  
这是一个很值得后续整理的接口契约问题。

---

## 9. Schema 层的本质结论

Schema 层可以总结成三句话：

### 第一，它负责把复杂内部系统压成稳定外部协议
前端不需要知道 service 层每个中间对象长什么样。

### 第二，它把“章节产出”“任务状态”“Story Workspace 快照”都正式产品化了
不是临时拼 JSON。

### 第三，它暴露了项目的设计重心
从 Schema 数量看得很明显：这个项目最重视的不是“发 prompt”，而是：

- 小说对象管理；
- 章节供应链；
- 任务生命周期；
- 工作台状态展示。
