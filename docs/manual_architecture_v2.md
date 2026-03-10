# 手册驱动强化版架构说明

这版在上一版“手册驱动架构”的基础上，进一步改成了更强约束的工作流：

## 1. 初始化只生成文档，不生成正文

创建小说时只会生成：
- 项目卡
- 世界骨架
- 修炼体系
- 全书总纲
- 分卷卡
- 第一组近 7 章近纲 / 章节卡

不会在初始化阶段直接生成任何正文。

## 2. 严格的章节流水线

章节生成被显式拆成 6 个阶段：
1. project_card
2. current_volume_card
3. near_outline
4. chapter_execution_card
5. chapter_draft
6. summary_and_review

这些阶段会被写入 `novel.story_bible.workflow_state`，并同步显示在控制台接口中。

## 3. 文档优先 + 正文后置

正文生成前会先检查：
- project_card 是否存在
- world_bible 是否存在
- cultivation_system 是否存在
- volume_cards 是否存在
- global_outline 是否存在
- 第 N 章对应的近纲 / 章节卡是否已经就绪

如果缺失，不会 silent fallback，而是直接报错。

## 4. 新增接口

### GET /api/v1/novels/{novel_id}/planning-state
查看当前规划状态：
- planning_layers
- planning_state
- planning_status
- chapter_card_queue

### POST /api/v1/novels/{novel_id}/prepare-next-window
只准备下一批近纲 / 章节卡，不生成正文。

可用参数：
- `force=true`：强制重建下一批规划窗口

## 5. 原有接口仍保留

- POST /api/v1/novels/{novel_id}/next-chapter
- POST /api/v1/novels/{novel_id}/next-chapters
- POST /api/v1/novels/{novel_id}/next-chapters/stream
- GET /api/v1/novels/{novel_id}/control-console

但它们现在会遵守更强的 pipeline 约束。

## 6. 推荐使用顺序

1. 创建小说
2. 查看 control-console / planning-state
3. 如有需要，先调用 prepare-next-window
4. 再调用 next-chapter 或 next-chapters
5. 写完后通过 control-console 查看 daily_workbench、volume_reviews、foreshadowing、chapter_card_queue
