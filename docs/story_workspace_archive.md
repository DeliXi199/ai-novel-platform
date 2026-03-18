# Story Workspace 本地快照

现在项目会在章节生成的关键节点，自动把 `Story Workspace` 快照保存到本地 JSON 文件，方便排查规划漂移、状态更新异常、场景衔接断裂之类的问题。

## 自动保存时机

默认会在这些时机落盘：

- 小说初始化（bootstrap）开始前：`before`
- 小说初始化（bootstrap）完成后：`after`
- 小说初始化（bootstrap）失败后：`failed`
- 章节生成开始前：`before`
- 章节生成成功完成后：`after`
- 章节生成失败后：`failed`
- 也支持手动导出：`manual`

## 默认保存目录

如果没有单独配置路径，默认目录是：

`backend/data/story_workspace_snapshots/`

目录结构示例：

```text
backend/data/story_workspace_snapshots/
  novel_3/
    chapter_0007/
      20260317T120102Z_before_chapter-generation-entry.json
      20260317T120318Z_after_next-entry-ready.json
```

## 文件内容

每个快照文件里会包含：

- `archive_meta`：保存时间、小说 ID、章节号、阶段、备注
- `live_runtime`：当时的运行态信息
- `current_pipeline`：当前流水线阶段
- `snapshot`：完整的 Story Workspace 快照
- `extra`：额外诊断信息（如 trace_id、报错详情、发布状态等）

默认**不**额外保存整份原始 `story_bible`，避免 JSON 过大。
如果确实要保留，可以开启：

```env
CONTROL_CONSOLE_ARCHIVE_INCLUDE_STORY_BIBLE=true
```

## 环境变量

```env
CONTROL_CONSOLE_ARCHIVE_ENABLED=true
CONTROL_CONSOLE_ARCHIVE_ROOT=
CONTROL_CONSOLE_ARCHIVE_PRETTY_JSON=true
CONTROL_CONSOLE_ARCHIVE_INCLUDE_STORY_BIBLE=false
CONTROL_CONSOLE_ARCHIVE_KEEP_FILES_PER_NOVEL=240
```

说明：

- `CONTROL_CONSOLE_ARCHIVE_ENABLED`：是否启用自动保存
- `CONTROL_CONSOLE_ARCHIVE_ROOT`：自定义保存目录，留空则使用默认目录
- `CONTROL_CONSOLE_ARCHIVE_PRETTY_JSON`：是否格式化 JSON，便于人工查看
- `CONTROL_CONSOLE_ARCHIVE_INCLUDE_STORY_BIBLE`：是否附带原始 story_bible
- `CONTROL_CONSOLE_ARCHIVE_KEEP_FILES_PER_NOVEL`：每本书最多保留多少个快照文件，超出会自动清理旧文件

## API

新增了几个接口：

- `GET /api/v1/novels/{novel_id}/story-workspace-archives`
  - 查看某本书的快照文件列表
- `GET /api/v1/novels/{novel_id}/story-workspace-archives/content?relative_path=...`
  - 读取某个快照文件内容
- `POST /api/v1/novels/{novel_id}/story-workspace-archives/snapshot`
  - 立即手动导出一份快照

## 建议排查方法

最实用的一种看法是直接对比：

- `before`：看生成前章纲、排队卡、live_runtime、scene_debug 是否已经异常
- `after`：看生成后长期状态、bridge、fact ledger、planning_status 有没有被正确推进
- `failed`：看失败时是场景连续性、硬事实、超时，还是规划层本身已经歪了
- bootstrap 阶段则主要看首个 arc、chapter queue、initialization packet 和 workflow_state 有没有在建书时就写歪

这能把“到底是生成坏了，还是生成前状态就坏了”这件事切开看，不会被日志糊一脸。
