# 数据库设计说明

## 当前状态

项目目前仍兼容两种初始化方式：

- **快速开发模式**：`python -m app.db.init_db`
- **正式迁移模式**：`cd backend && alembic upgrade head`

其中 `init_db` 仍保留，是为了兼容你现在的本地开发和已有数据库；但从工程化角度，后续结构变更应优先走 **Alembic 迁移**。

---

## 1. novels
一本小说的全局信息。

关键字段：
- `genre`：题材
- `premise`：一句话背景
- `protagonist_name`：主角名
- `style_preferences`：用户长期偏好
- `story_bible`：故事圣经（JSON）
- `current_chapter_no`：当前已生成章节号
- `status`：当前小说运行状态
- 运行热路径索引：`updated_at`、`status + updated_at`

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
- `serial_stage`
- `is_published`
- `locked_from_edit`
- `published_at`
- `updated_at`：章节最近一次被修改的时间，用于运行态快照缓存失效判断
- 运行热路径索引：`novel_id + created_at`、`novel_id + serial_stage + chapter_no`、`novel_id + updated_at`

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
- 运行热路径索引：`novel_id + created_at`

---

## Alembic

这版已经新增：

- `backend/alembic.ini`
- `backend/alembic/env.py`
- `backend/alembic/versions/20260313_0001_initial_schema.py`
- `backend/alembic/versions/20260314_0002_runtime_snapshot_indexes.py`

用途：

- 为后续表结构演进建立正式版本线
- 避免继续只靠 `create_all()` + 手写 DDL 修补字段
- 方便以后新增 `chapter_cards / plot_threads / state_snapshots / generation_logs` 等表时可追踪变更

---

## 后续建议继续拆出的表

当前很多运行时状态仍在 `story_bible` JSON 中。后续值得优先拆表的方向：

- `planning_windows`
- `chapter_cards`
- `plot_threads`
- `world_state_snapshots`
- `fact_ledgers`
- `generation_logs`
- `reader_sessions`
- `branch_novels`

建议顺序：先拆 **规划窗口 / chapter cards / generation logs**，因为这三块最容易形成稳定结构，也最能减轻 `story_bible` 压力。
