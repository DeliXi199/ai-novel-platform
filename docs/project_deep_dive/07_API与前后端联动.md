# 07 API 与前后端联动

这一份讲前端工作台怎么和后端配合。  
它不是视觉设计说明，而是“页面上的动作，对应后台哪些状态变化”。

---

## 1. 前端不是创作引擎，而是控制面板

`frontend/` 的结构很轻：

- `index.html`
- `assets/app.js`
- `assets/app/core.js`
- `assets/app/renderers.js`
- `assets/app/ui_helpers.js`
- `assets/app.css`

这意味着前端的职责主要是：

- 发请求；
- 刷快照；
- 渲染面板；
- 显示任务与运行态。

真正复杂的创作状态都在后端。

---

## 2. 页面大概有哪些功能块

从 HTML 和 JS 结构看，前端主要围绕几个区块组织：

### 书架/小说列表
显示所有作品摘要，支持进入某本书。

### 新建作品面板
提交题材、premise、主角、风格偏好，触发创建或异步初始化。

### 任务面板
显示：
- 当前活跃任务；
- 最近任务；
- 任务进度；
- 失败与重试入口。

### 工作台/控制台
显示：
- 当前项目卡；
- 世界观与规则；
- 近纲；
- 当前卷卡；
- 主角状态；
- 规划状态；
- 长期状态摘要；
- 当前 live runtime。

### 章节区
显示章节列表与所选章节内容。

---

## 3. 前端最依赖哪些接口

### 3.1 小说管理

#### `GET /novels`
拿小说列表。

#### `POST /novels`
同步创建并初始化一本小说。

#### `POST /novels/tasks/bootstrap`
异步提交初始化任务。

#### `POST /novels/{novel_id}/bootstrap/retry`
重试初始化。

#### `PATCH /novels/{novel_id}/title`
改标题。

#### `DELETE /novels/{novel_id}`
删整本书。

---

### 3.2 工作台与状态快照

#### `GET /novels/{novel_id}/story-studio`
前端最重的聚合接口之一。  
进入一本书时，通常会优先用它拉整页核心数据。

#### `GET /novels/{novel_id}/planning-state`
拿规划状态、chapter queue、planning layers。

#### `GET /novels/{novel_id}/story-workspace`
拿 Story Workspace 快照。

#### `GET /novels/{novel_id}/live-runtime`
拿实时运行态。

#### `GET /novels/{novel_id}/serial-state`
拿连载发布状态。

#### `GET /novels/{novel_id}/facts`
拿事实层信息。

#### `GET /novels/{novel_id}/hard-facts`
拿硬事实报告或守卫信息。

---

### 3.3 章节操作

#### `GET /novels/{novel_id}/chapters`
拿章节列表。

#### 章节生成相关接口
用于生成下一章或批量生成多章。具体路径在 `novel_chapters.py` 中定义，前端以任务或直接请求方式触发。

#### `POST /novels/{novel_id}/chapters/publish-batch`
批量发布库存章。

#### `POST /novels/{novel_id}/chapters/delete-tail`
删除尾章。

#### 导出与 TTS 相关接口
用于把章节内容导出或生成音频。

---

### 3.4 干预操作

#### `GET /novels/{novel_id}/interventions`
查看干预。

#### `POST /novels/{novel_id}/interventions`
新增干预。

---

### 3.5 任务系统

#### `GET /novels/{novel_id}/tasks`
任务列表。

#### `GET /novels/{novel_id}/tasks/{task_id}`
任务详情。

#### `GET /novels/{novel_id}/tasks/{task_id}/events`
任务事件流。

#### `POST /novels/{novel_id}/tasks/{task_id}/cancel`
取消任务。

#### `POST /novels/{novel_id}/tasks/{task_id}/retry`
重试任务。

#### `POST /novels/{novel_id}/tasks/cleanup`
清理历史任务。

---

## 4. 前端为什么频繁拉快照，而不是自己拼状态

因为后端状态太复杂。  
如果前端自己去拼：

- 一部分在 `Novel`；
- 一部分在 `Chapter`；
- 一部分在 `ChapterSummary`；
- 一部分在 `story_bible`；
- 一部分在任务表；
- 一部分在 live runtime；

那前端会马上变成泥潭。

所以后端提供 `story-studio`、`story-workspace` 这类聚合接口，本质上是把“可展示状态”预先整理好。  
这样前端只负责渲染，不负责理解小说生成引擎内部逻辑。

---

## 5. live runtime 的作用

前端不是只在任务结束后刷新一次。  
它会关心“现在正在做什么”。

`live-runtime` 这类接口一般会给前端这些信号：

- 当前目标章节号；
- 当前阶段，比如 drafting / quality_check / title_refinement / next_entry_ready；
- 当前提示消息；
- 当前 planning meta；
- 当前 payoff / stage casting 等运行补充。

所以用户不会觉得系统在“卡住”，而是能看到后台正处于哪个阶段。

---

## 6. 前端如何处理异步任务

从 JS 结构能看出，前端对任务系统有明显支持，通常会做：

- 提交任务；
- 记录返回的 task id；
- 轮询 task status；
- 轮询或查看 task events；
- 在任务完成后刷新 story-studio / chapters / runtime。

这说明任务不是附属功能，而是前端交互的一等公民。

---

## 7. 为什么工作台要同时显示“章节列表”和“控制台”

因为这两个视角不一样。

### 章节列表回答的是：
“已经写出来了什么？”

### 控制台回答的是：
“系统现在信什么？接下来打算写什么？运行到哪了？”

如果只有章节列表，用户只能看结果。  
如果只有控制台，用户看不到正文产物。  
两个一起放，才像真正的生产工作台。

---

## 8. 一个值得注意的接口层细节

后端内部 `build_story_workspace_snapshot()` 返回的内容比 `StoryWorkspaceResponse` 暴露的字段更丰富。  
这意味着前端当前拿到的是“被 schema 裁切后的控制台”。

换句话说，后端内部已经有更丰富的材料，只是 API 契约暂时没有全部放出来。  
后续如果要扩展前端面板，可以优先检查这里，而不是重新发明状态结构。

---

## 9. 从前后端联动看，这个项目更像什么

它不像普通网页“表单提交 -> 显示结果”。  
更像一个创作控制台：

- 前端发命令；
- 后端启动流水线；
- 任务系统负责进度可见；
- Story Bible 负责状态连续；
- 快照接口负责把复杂状态翻译回 UI。

所以它更像“小说工厂驾驶舱”，不是“聊天窗口附带一个写作按钮”。

---

## 10. 给继续开发的人一个阅读顺序建议

如果你是想继续改前端，建议先看：

1. `frontend/index.html`
2. `frontend/assets/app.js`
3. `backend/app/api/routes/novel_runtime.py`
4. `backend/app/api/routes/novel_chapters.py`
5. `backend/app/services/story_architecture.py`

因为前端页面的大部分复杂感，其实都来自后端快照结构，而不是浏览器里的技巧。

一句话总结：  
**这个前端的难点不在渲染，而在理解后端已经整理好的“叙事运行快照”。**
