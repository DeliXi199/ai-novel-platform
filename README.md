# AI Novel Platform MVP · Fullstack Studio Edition

这一版在已有后端基础上，补齐了一个可直接操作的前端工作台，并把前后端联调方式收束成更稳定的同源模式。

同时，这个持续优化版已经做了多轮结构整理：后端小说路由、章节生成支撑层、故事架构支撑层、硬事实守卫都已分层拆分，前端也开始把全局状态、UI 辅助层逐步模块化抽离。

## 现在可以直接做什么

- 书架查看：按更新时间查看所有小说，支持搜索
- 新建小说：填写题材、主角、前提与风格偏好，初始化全书粗纲和首段 arc
- 小说工作台：查看当前进度、规划窗口、控制台摘要、章节目录
- 单章生成：直接生成下一章
- 批量生成：通过 SSE 实时查看逐章进度与报错
- 人工干预：添加阶段性读者/作者指令
- 导出成书：支持 `txt / md / docx / pdf`
- 健康检查：前端可直接检测后端和模型接口状态

## 这版新增的关键工程改动

### 前端

- 新增 `frontend/` 同源静态工作台
- 页面入口：`/app`
- 不依赖额外 Node 前端服务，默认由 FastAPI 直接提供
- 书架、创建表单、章节阅读器、控制台摘要、批量日志均已接通

### 后端 API

补充了前端必需的轻量接口：

- `GET /api/v1/novels`：书架列表
- `GET /api/v1/novels/{id}/chapters`：章节目录
- `GET /api/v1/novels/{id}/interventions`：人工干预列表
- `GET /api/v1/novels/{id}/story-studio`：Story Studio 聚合数据（减少前端碎请求）

同时保留已有能力：

- `POST /api/v1/novels`
- `POST /api/v1/novels/{id}/next-chapter`
- `POST /api/v1/novels/{id}/next-chapters/stream`
- `POST /api/v1/novels/{id}/prepare-next-window`
- `GET /api/v1/novels/{id}/story-studio`
- `GET /api/v1/novels/{id}/export?format=pdf`

### 稳定性

- 前端改为同源访问，默认不需要额外配置跨域
- 仍保留 CORS 中间件，方便你以后拆分前端独立开发
- `/health/llm?ping=true` 失败时返回真实 HTTP 错误码
- 新增 `/health/llm?ping=true&stage=bootstrap`，可直接模拟“创建小说/初始化大纲”阶段的模型连通性
- DeepSeek 连接失败时会自动在 `https://api.deepseek.com` 与 `https://api.deepseek.com/v1` 两种地址间重试一次
- 初始化阶段支持单独指定 `BOOTSTRAP_MODEL`，默认建议用 `deepseek-chat` 而不是 reasoning 模型
- 测试已覆盖健康检查、轻量列表接口、前端入口页
- `backend/app/api/routes/novels.py` 已改为聚合入口，具体职责拆到 `novel_management.py / novel_runtime.py / novel_chapters.py / novel_interventions.py`
- 章节生成已拆出 `chapter_runtime_support.py / chapter_retry_support.py / chapter_context_support.py / chapter_planning_support.py`
- 故事架构已拆出 `story_runtime_support.py / story_fact_ledger.py / story_character_support.py / story_blueprint_builders.py`
- 新增 `story_state.py` 作为 Story Bible 域状态访问层，统一管理 workflow / planning / serial runtime / story_state 等结构补全与读取
- 硬事实守卫已拆出 `hard_fact_guard_utils.py / hard_fact_guard_extractors.py / hard_fact_guard_conflicts.py / hard_fact_guard_review.py`
- 前端 `frontend/assets/app.js` 已进一步抽离出 `frontend/assets/app/core.js`、`frontend/assets/app/ui_helpers.js` 与 `frontend/assets/app/renderers.js`，将状态/API、UI 辅助、页面渲染职责分开
- 新增 Alembic 迁移基线与 GitHub Actions 后端 CI 工作流


## 文档导航

- `docs/product_spec.md`：项目定位、工作流与整体架构说明
- `docs/architecture.md`：系统分层与模块关系
- `docs/database.md`：数据库设计
- `docs/openai_integration.md`：模型接入说明
- `docs/export.md`：导出能力说明
- `docs/roadmap.md`：后续开发路线
- `CHANGELOG.md`：合并后的版本变更记录

## 快速启动

### 1. 启动数据库

```bash
docker compose up -d
```

### 2. 配置环境变量

复制根目录 `.env.example` 到 `backend/.env`，填写你要用的模型 key。

### 3. 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

### 4. 初始化数据库

当前版本默认会在应用启动时自动调用 `init_db()`，因此开发期直接启动即可。

如果你要严格走迁移链路，可以把 `AUTO_INIT_DB_ON_STARTUP=false`，然后执行：

```bash
alembic upgrade head
```

### 5. 启动服务

```bash
uvicorn app.main:app --reload
```

## 打开方式

- 前端工作台：`http://127.0.0.1:8000/app`
- Swagger 文档：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/api/v1/health`

## 环境变量补充

如果你未来要把前端单独跑在别的端口，可以改：

```env
CORS_ALLOW_ORIGINS=http://127.0.0.1:5173,http://localhost:5173
```

## 运行测试

在项目根目录执行：

```bash
pytest -q backend/tests
```

当前仓库已经包含 100+ 个后端测试用例；建议每次修改后执行一次完整回归。

如果你使用 GitHub，这一版已经自带 `.github/workflows/backend-ci.yml`，提交后会自动跑后端测试。

## 章节超时排查

若第 2 章开始偶发 `chapter_extension / CHAPTER_PIPELINE_TIMEOUT`，优先检查这几项：

- `CHAPTER_EXTENSION_MIN_LLM_TIMEOUT_SECONDS`：补尾阶段的硬下限，默认 20。
- `CHAPTER_EXTENSION_SOFT_MIN_TIMEOUT_SECONDS`：当剩余预算不足硬下限但仍足够做一次短补尾时，允许降到这个软下限，默认 12。
- `CHAPTER_GENERATION_WALL_CLOCK_LIMIT_SECONDS`：单章总时限，默认 420。
- `CHAPTER_RUNTIME_SUMMARY_RESERVE_SECONDS`：给摘要和收尾预留的预算，默认 12。

当前版本还做了两条结构性优化：

- `CHAPTER_TOO_SHORT` 不再走全文补写，而是走紧凑重生成。
- `CHAPTER_ENDING_INCOMPLETE` 只在首轮草稿时补尾，且补尾 prompt 只喂正文结尾片段，不再把整章正文重新发给模型。
