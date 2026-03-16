# Architecture (Serial Production Edition)

## Goal

这个项目不是“一次性生成整本小说”，而是一个面向网络连载的逐章生产系统：

1. 初始化 Story Bible 与全书总纲
2. 生成当前 Arc 的章节拍表
3. 逐章生成正文
4. 做章节质检与硬事实校验
5. 同步长期状态、控制台与连载运行层
6. 支持库存发布、删尾回退与继续续写

## Current backend structure

### API layer

- `backend/app/api/routes/novels.py`：聚合入口，只负责挂载子路由
- `backend/app/api/routes/novel_management.py`：建书、查书、删书、bootstrap 重试
- `backend/app/api/routes/novel_runtime.py`：规划窗口、控制台、serial state、facts、serial mode、workspace 聚合载入
- `backend/app/api/routes/novel_chapters.py`：章节列表、发布、删尾、导出、单章/批量生成
- `backend/app/api/routes/novel_interventions.py`：人工干预
- `backend/app/api/routes/novel_common.py`：共享辅助函数与运行态快照缓存接线

### Service layer

- `story_architecture.py`：Story Bible / outline / console / long-term state 的主编排层
- `story_state.py`：Story Bible 域状态访问层，统一补齐 workflow/control_console/planning_layers/story_state/serial_runtime
- `chapter_generation.py`：逐章生成主流水线
- `chapter_quality.py`：质量检查与反馈
- `hard_fact_guard.py`：硬事实守卫与冲突报告
- `novel_lifecycle.py`：bootstrap 与快照同步
- `runtime_snapshot_cache.py`：控制台 / serial-state / facts 等读取型接口的轻量 LRU 快照缓存

## Frontend structure

- `frontend/assets/app.js`：工作台主编排层，优先通过 workspace 聚合接口完成整页装载
- `frontend/assets/app/core.js`：全局状态、DOM 引用、基础工具、API 请求、活动日志
- `frontend/assets/app/ui_helpers.js`：确认框、章节卡片、SSE block 解析、创建表单辅助
- `frontend/assets/app/renderers.js`：书架、主控台、目录、预览、阅读页渲染

## Build flow

### On novel creation

- Build story bible
- Generate global outline
- Generate first active arc outline
- Persist initialization packet and control console snapshot
- Do **not** pre-generate opening chapters by default

### On next chapter request

- Load latest story state and active interventions
- Ensure planning window exists
- Read current chapter plan from queue
- Generate draft
- Run quality checks and hard-fact validation
- Persist chapter, summary, runtime snapshot, serial layers
- Prefetch next planning window when needed

## Why this structure is better

- 路由按职责拆开后，接口层不再由一个超大文件承载全部逻辑
- 前端进一步拆出 renderers 后，`app.js` 更像编排层，状态/API/渲染边界更清晰
- Story Bible 现在多了一层 `story_state` 域快照，为后续拆表、状态迁移和观测埋点准备了稳定接口
- 默认初始化不再预生成正文，更符合连载项目的真实使用方式
- 保留单体部署优点，但内部结构更适合继续扩展
- 运行态读取接口不再次次全量重算 Story Bible 快照，长书场景下更稳
