# Manual-Driven Novel Architecture

这版项目把“修仙日更网文工作手册”里的几层结构直接映射进后端生成框架。

## 1. 三层规划

- **项目卡 / 总纲**：写入 `story_bible.project_card` 与 `story_bible.global_outline`
- **分卷卡**：写入 `story_bible.volume_cards`
- **近 7 章推进区**：写入 `story_bible.control_console.near_7_chapter_outline`

## 2. 连载控制台

`story_bible.control_console` 现在集中维护：

- 主角状态卡
- 战力账本
- 关键角色卡
- 关系变化轨迹
- 伏笔表
- 时间线
- 近 30 章推进区
- 每日工作台
- 卷末复盘

## 3. 章节生成时新增的执行层

每次生成下一章时，系统会额外构造：

- 当前卷卡
- 本章执行卡
- 每日工作台（昨天结尾 / 今日功能 / 三行章纲 / 明天提示）
- 章节最低质量地板

这些内容会一起压进 `novel_context.story_memory.execution_brief`，让正文生成更接近日更作者的真实工作流，而不是单纯“把大纲展开一下”。

## 4. 章节写完后的自动更新

每章写完后，系统会根据章节摘要回写：

- 主角当前目标与状态
- 近期推进记录
- 伏笔开闭状态
- 时间线
- 配角卡与关系轨迹
- 卷末复盘（到达卷尾时）

## 5. 新增接口

- `GET /api/v1/novels/{novel_id}/control-console`

用于直接查看当前小说的“连载控制台”。

## 6. 兼容性说明

- 现有的 `next-chapter` / `next-chapters` / `next-chapters/stream` 都保留
- 没有引入新的数据库表，核心新结构仍然存放在 `novel.story_bible`
- `characters` 表会在章节生成后同步维护主角和关键配角的状态快照
