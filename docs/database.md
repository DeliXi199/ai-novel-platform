# 数据库设计说明

## 1. novels
一本小说的全局信息。

关键字段：
- `genre`：题材
- `premise`：一句话背景
- `protagonist_name`：主角名
- `style_preferences`：用户长期偏好
- `story_bible`：故事圣经（JSON）
- `current_chapter_no`：当前已生成章节号

## 2. characters
角色动态信息。

关键字段：
- `role_type`：主角/配角/反派等
- `core_profile`：基础设定
- `dynamic_state`：当前状态
- `reader_weight`：读者偏好权重

## 3. chapters
章节正文。

关键字段：
- `chapter_no`
- `title`
- `content`
- `generation_meta`

## 4. chapter_summaries
章节结构化摘要。

关键字段：
- `event_summary`
- `character_updates`
- `new_clues`
- `open_hooks`
- `closed_hooks`

## 5. interventions
用户干预记录。

关键字段：
- `raw_instruction`
- `parsed_constraints`
- `effective_chapter_span`
- `applied`

## 6. 后续建议增加的表

- `plot_threads`
- `world_state_snapshots`
- `reader_sessions`
- `branch_novels`
- `generation_logs`
