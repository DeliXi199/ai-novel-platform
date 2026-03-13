# AI Serial Novel Platform

一个面向**网络连载**场景的长篇小说创作平台。它不是“一次性生成整本书”的脚本，而是一套支持**建书、初始化设定、逐章生成、批量串行生成、人工干预、硬事实校验、库存发布、导出成书**的完整前后端系统。

当前版本采用：

- **后端**：FastAPI + SQLAlchemy + Pydantic + PostgreSQL + Alembic
- **前端**：原生 HTML / CSS / JavaScript，同源静态工作台
- **模型接入**：支持 `deepseek / openai / groq`
- **测试**：pytest 回归测试 + GitHub Actions 后端 CI

---

## 1. 项目定位

这个项目专门解决“网络连载小说”而不是“一次性成书”的问题。

和普通文本生成工具不同，它的核心前提是：

- 前面已经生成并发布的章节**不能随意回改**
- 后续章节必须建立在**既有正文事实**之上继续推进
- 可以一次生成 1 章，也可以连续生成多章，但必须**逐章串行执行**
- 每生成一章，都要先做**质量检查、摘要回写、状态刷新、事实登记**，再进入下一章
- 当章节出现过短、尾巴断掉、硬事实冲突等问题时，系统优先走**修复链路**，而不是静默兜底乱写

所以，这个项目本质上是一个**长期可续写、结构可控、状态可追踪、支持日更与库存连载的小说生产系统**。

---

## 2. 适合什么场景

这个项目尤其适合下面几类使用方式：

- 想做**日更网络小说**，每天生成一章或几章
- 想做**库存连载**，先攒稿再分批发布
- 想让 AI 按既有剧情持续往后写，而不是反复推翻前文
- 想对生成过程进行**人工干预**，例如插入阶段性要求、读者反馈、剧情矫正指令
- 想把小说状态、规划、事实、摘要都保留为结构化数据，而不是只保留一段纯文本

---

## 3. 当前版本的核心能力

### 3.1 书架与建书

- 查看全部小说，按更新时间排序
- 支持关键词搜索
- 新建小说时填写：题材、前提、主角名、风格偏好
- 初始化时生成 Story Bible、总纲、Arc 结构与控制台快照
- 默认**不再预生成开头几章正文**，更符合真实连载流程

### 3.2 小说工作台

前端工作台由后端同源提供，默认入口：

- `http://127.0.0.1:8000/app`

工作台可直接完成：

- 书架浏览
- 小说创建
- 控制台查看
- 规划窗口查看
- 章节目录浏览
- 单章生成
- 批量生成
- 人工干预
- 章节发布
- 删尾回退
- 全书导出

### 3.3 单章与多章生成

支持两种生产方式：

- **单章生成**：生成下一章
- **批量生成**：连续生成多章，但按“生成一章 → 校验一章 → 刷新状态 → 再生成下一章”的顺序串行执行

这意味着即使你一次要求生成 8 章，它也不会把 8 章当成一整段长文本粗暴输出，而是逐章推进。

### 3.4 连载模式

当前支持两类交付模式：

- `live_publish`：生成后直接进入发布链路
- `stockpile`：先作为库存章保存，再按需要批量发布

### 3.5 人工干预

可向某本小说插入阶段性人工指令，例如：

- 某个角色近期要强化存在感
- 某条支线不要提前揭露
- 接下来几章风格要更紧张
- 读者反馈希望尽快推进某条伏笔

系统会将人工干预作为运行时约束的一部分纳入后续生成。

### 3.6 导出成书

支持导出为：

- `txt`
- `md`
- `docx`
- `pdf`

导出时会自动附带书名、题材、主角、简介、风格等基础元信息。

### 3.7 健康检查与模型连通性检测

内置健康检查接口：

- `GET /api/v1/health`
- `GET /api/v1/health/llm`

其中：

- `ping=false` 时只返回当前模型配置
- `ping=true` 时会真实请求一次模型接口
- `stage=bootstrap` 时会按初始化阶段配置做单独检测

这对排查“模型能连通，但初始化阶段仍报错”的问题很有帮助。

---

## 4. 这版最终结构的关键升级点

相较于早期版本，这个最终版已经不再是简单的单文件堆逻辑，而是完成了比较明确的模块化重构。

### 4.1 API 路由拆分

原本集中在一个大文件里的小说相关接口，已经拆成更清晰的职责模块：

- `backend/app/api/routes/novels.py`：聚合入口
- `backend/app/api/routes/novel_management.py`：建书、查书、删书、bootstrap 重试
- `backend/app/api/routes/novel_runtime.py`：控制台、规划状态、serial state、事实状态
- `backend/app/api/routes/novel_chapters.py`：章节列表、单章/批量生成、发布、删尾、导出
- `backend/app/api/routes/novel_interventions.py`：人工干预
- `backend/app/api/routes/novel_common.py`：共享工具函数

### 4.2 章节生成链路模块化

章节生成主流程不再靠一个巨大的函数硬撑，而是拆出多个支撑模块：

- `chapter_generation.py`
- `chapter_runtime_support.py`
- `chapter_context_support.py`
- `chapter_planning_support.py`
- `chapter_generation_support.py`
- `chapter_retry_support.py`

这样做的好处是：

- 更容易定位“卡在生成、卡在摘要、卡在补尾、卡在重试”的具体阶段
- 更容易单独优化某一段逻辑
- 更容易为不同类型的失败接入不同修复策略

### 4.3 Story Bible / 运行时状态层拆分

当前版本新增并强化了以下模块：

- `story_state.py`
- `story_runtime_support.py`
- `story_fact_ledger.py`
- `story_character_support.py`
- `story_blueprint_builders.py`
- `novel_lifecycle.py`

这意味着项目已经不仅仅保存一份“小说 JSON”，而是开始按“故事设定、长程状态、事实账本、角色变化、运行时快照”来分层处理。

### 4.4 硬事实守卫（Hard Fact Guard）

这是当前版本最关键的质量升级之一。

新增模块包括：

- `hard_fact_guard.py`
- `hard_fact_guard_utils.py`
- `hard_fact_guard_extractors.py`
- `hard_fact_guard_conflicts.py`
- `hard_fact_guard_review.py`

它的作用不是做普通文风评分，而是专门检查**高风险硬事实冲突**，例如：

- 前文已确认死亡的人物，后文无解释突然正常出现
- 已确认公开的信息，后文又当作未知处理
- 已锁定的设定、状态、因果链出现明显自相矛盾

### 4.5 专用章节修复管线（Repair Pipeline）

当前版本把章节修复从“混在一起的重试”里独立出来，形成更清晰的 repair pipeline。

重点不再是“失败了就再请求一次模型”，而是区分问题类型，例如：

- 篇幅偏短
- 结尾断掉
- 最后一段太虚
- 结构推进太弱
- 存在事实冲突

不同问题可以走不同修复策略，这比统一重试更稳定，也更容易继续扩展。

### 4.6 前端模块化

前端已经从单个 `app.js` 继续拆出：

- `frontend/assets/app/core.js`
- `frontend/assets/app/ui_helpers.js`
- `frontend/assets/app/renderers.js`

现在前端职责更明确：

- `core.js`：状态、DOM、基础工具、API 请求、日志
- `ui_helpers.js`：弹窗、确认动作、SSE block 解析、表单辅助
- `renderers.js`：书架、控制台、目录、阅读区等渲染逻辑
- `app.js`：整体编排层

### 4.7 正式迁移基线与 CI

当前版本新增：

- Alembic 迁移基线
- GitHub Actions 后端测试工作流

这让项目从“本地能跑”向“可持续维护”迈了一步。

---

## 5. 系统整体工作流

### 5.1 建书初始化

创建小说后，系统会执行一条偏“架构化”的初始化流程：

1. 接收基础输入：题材、前提、主角名、风格偏好
2. 生成 Story Bible
3. 生成全书级总纲
4. 生成首段 Arc / 规划窗口
5. 初始化控制台、serial runtime、story state 等结构
6. 保存到数据库

注意：

- 当前版本默认 **`BOOTSTRAP_INITIAL_CHAPTERS=0`**
- 也就是初始化阶段只做“建书与规划”，**不默认预生成正文**

### 5.2 单章生成

生成下一章的大致流程如下：

1. 读取当前小说状态
2. 加载最新规划窗口与控制台数据
3. 读取最近章节摘要、必要上下文、人工干预
4. 生成章节草稿
5. 执行质量检查
6. 执行硬事实校验
7. 需要时进入 repair pipeline
8. 保存章节正文与生成元数据
9. 写入章节摘要、事实账本、serial runtime、story state
10. 视情况预取下一规划窗口

### 5.3 多章串行生成

批量生成不是并行灌出多章，而是：

1. 先生成第 N 章
2. 通过质检与事实检查
3. 写回摘要与状态
4. 再生成第 N+1 章
5. 重复直到结束或中途失败

这也是整个项目最重要的设计原则之一：

> 多章生成必须逐章刷新状态，而不是把多章当作一次长输出。

---

## 6. 项目目录结构

```text
.
├─ backend/
│  ├─ alembic/                      # 数据库迁移
│  ├─ app/
│  │  ├─ api/routes/               # API 路由层
│  │  ├─ core/                     # 配置与基础设施
│  │  ├─ db/                       # 数据库初始化与会话
│  │  ├─ models/                   # SQLAlchemy 模型
│  │  ├─ schemas/                  # Pydantic schema
│  │  └─ services/                 # 核心业务与生成链路
│  ├─ tests/                       # pytest 回归测试
│  ├─ alembic.ini
│  └─ requirements.txt
├─ frontend/
│  ├─ index.html                   # 工作台入口
│  └─ assets/
│     ├─ app.css
│     ├─ app.js
│     └─ app/
│        ├─ core.js
│        ├─ renderers.js
│        └─ ui_helpers.js
├─ docs/
│  ├─ architecture.md              # 架构说明
│  ├─ database.md                  # 数据库说明
│  ├─ export.md                    # 导出说明
│  ├─ openai_integration.md        # 模型接入说明
│  ├─ product_spec.md              # 产品与流程说明
│  └─ roadmap.md                   # 后续规划
├─ .github/workflows/
│  └─ backend-ci.yml               # 后端 CI
├─ docker-compose.yml              # PostgreSQL 启动
├─ .env.example                    # 环境变量模板
├─ CHANGELOG.md                    # 版本变更记录
└─ README.md
```

---

## 7. 主要 API 一览

下面只列高频接口。

### 7.1 健康检查

- `GET /api/v1/health`
- `GET /api/v1/health/llm`

### 7.2 小说管理

- `GET /api/v1/novels`
- `POST /api/v1/novels`
- `GET /api/v1/novels/{novel_id}`
- `DELETE /api/v1/novels/{novel_id}`
- `POST /api/v1/novels/{novel_id}/bootstrap/retry`

### 7.3 运行时与控制台

- `GET /api/v1/novels/{novel_id}/planning-state`
- `POST /api/v1/novels/{novel_id}/prepare-next-window`
- `POST /api/v1/novels/{novel_id}/refresh-serial-state`
- `GET /api/v1/novels/{novel_id}/live-runtime`
- `GET /api/v1/novels/{novel_id}/control-console`
- `GET /api/v1/novels/{novel_id}/serial-state`
- `GET /api/v1/novels/{novel_id}/facts`
- `GET /api/v1/novels/{novel_id}/hard-facts`
- `POST /api/v1/novels/{novel_id}/serial-mode`

### 7.4 章节相关

- `GET /api/v1/novels/{novel_id}/chapters`
- `GET /api/v1/novels/{novel_id}/chapters/{chapter_no}`
- `POST /api/v1/novels/{novel_id}/next-chapter`
- `POST /api/v1/novels/{novel_id}/next-chapters`
- `POST /api/v1/novels/{novel_id}/next-chapters/stream`
- `POST /api/v1/novels/{novel_id}/chapters/publish-batch`
- `POST /api/v1/novels/{novel_id}/chapters/delete-tail`
- `GET /api/v1/novels/{novel_id}/export?format=pdf`

### 7.5 人工干预

- `GET /api/v1/novels/{novel_id}/interventions`
- `POST /api/v1/novels/{novel_id}/interventions`

---

## 8. 数据与状态设计概览

当前数据库核心表包括：

- `novels`
- `characters`
- `chapters`
- `chapter_summaries`
- `interventions`

其中比较关键的是：

### 8.1 novels

存小说级信息，例如：

- 书名
- 题材
- 前提
- 主角名
- 风格偏好
- Story Bible
- 当前章节号
- 当前状态

### 8.2 chapters

存章节正文及其运行时属性，例如：

- `chapter_no`
- `title`
- `content`
- `generation_meta`
- `serial_stage`
- `is_published`
- `locked_from_edit`
- `published_at`

### 8.3 chapter_summaries

存每章的结构化摘要，用于后续上下文压缩、状态回写和规划衔接。

### 8.4 interventions

存人工干预指令与解析后的约束。

### 8.5 story_bible / story_state / serial_runtime

当前有一部分运行时状态仍以内嵌 JSON 的形式存在于小说级数据中，包括：

- story state
- long-term state
- control console
- planning layers
- fact ledger
- hard fact guard
- serial runtime

这既保证了当前版本可快速迭代，也为后续继续拆表留下空间。

---

## 9. 模型接入说明

当前项目支持三类 provider：

- `deepseek`
- `openai`
- `groq`

环境变量里可配置：

- 默认运行模型
- 初始化阶段模型
- 是否优先使用非 reasoning 模型
- 各 provider 的 base URL、model、timeout、output token 上限

### 当前默认配置

```env
LLM_PROVIDER=deepseek
BOOTSTRAP_MODEL=deepseek-chat
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

### 重要说明

当前版本已经明确：

- **只支持真实 provider**：`openai | deepseek | groq`
- **不再支持 mock 静默兜底**
- 如果模型接口报错、超时、返回格式错误、初始化失败，应明确暴露错误，而不是无声生成一个假结果

这对连载系统非常重要，因为“带着错误状态继续写”比“明确失败并重试”更危险。

---

## 10. 快速启动

### 10.1 启动 PostgreSQL

在项目根目录执行：

```bash
docker compose up -d
```

默认数据库配置为：

- host: `127.0.0.1`
- port: `5432`
- db: `novel_db`
- user: `novel_user`
- password: `novel_password`

### 10.2 配置环境变量

把根目录的 `.env.example` 复制到 `backend/.env`。

#### Windows PowerShell

```powershell
Copy-Item .env.example backend/.env
```

#### macOS / Linux

```bash
cp .env.example backend/.env
```

然后根据你要使用的 provider 填写 API Key。

### 10.3 安装后端依赖

```bash
cd backend
pip install -r requirements.txt
```

建议使用独立虚拟环境。

### 10.4 初始化数据库

当前版本应用启动时会自动执行 `init_db()`，开发阶段可直接启动。

但从工程实践上，仍建议在正式使用前执行迁移：

```bash
cd backend
alembic upgrade head
```

### 10.5 启动服务

```bash
cd backend
uvicorn app.main:app --reload
```

启动后可访问：

- 工作台：`http://127.0.0.1:8000/app`
- Swagger：`http://127.0.0.1:8000/docs`
- 根入口：`http://127.0.0.1:8000/`

---

## 11. 常用开发命令

### 启动数据库

```bash
docker compose up -d
```

### 停止数据库

```bash
docker compose down
```

### 应用迁移

```bash
cd backend
alembic upgrade head
```

### 启动后端

```bash
cd backend
uvicorn app.main:app --reload
```

### 运行测试

```bash
pytest -q backend/tests
```

---

## 12. 环境变量说明

这里只列最重要的一部分。

### 基础配置

```env
APP_NAME=AI Novel Platform MVP
APP_ENV=development
APP_DEBUG=true
API_V1_PREFIX=/api/v1
CORS_ALLOW_ORIGINS=http://127.0.0.1:5173,http://localhost:5173
```

### 数据库

```env
DATABASE_URL=postgresql+psycopg2://novel_user:novel_password@127.0.0.1:5432/novel_db
```

### 模型基础配置

```env
LLM_PROVIDER=deepseek
BOOTSTRAP_LLM_PROVIDER=
BOOTSTRAP_MODEL=deepseek-chat
BOOTSTRAP_TIMEOUT_SECONDS=180
BOOTSTRAP_PREFER_NON_REASONING=true
```

### 章节生成与修复关键参数

```env
CHAPTER_TARGET_WORDS=1500
CHAPTER_MIN_VISIBLE_CHARS=1200
CHAPTER_DRAFT_MAX_ATTEMPTS=2
CHAPTER_TOO_SHORT_RETRY_ATTEMPTS=1
CHAPTER_TAIL_FIX_ATTEMPTS=1
CHAPTER_GENERATION_WALL_CLOCK_LIMIT_SECONDS=420
CHAPTER_RUNTIME_MIN_LLM_TIMEOUT_SECONDS=25
CHAPTER_RUNTIME_SUMMARY_RESERVE_SECONDS=12
HARD_FACT_LLM_REVIEW_ENABLED=true
```

### 分层规划参数

```env
BOOTSTRAP_INITIAL_CHAPTERS=0
GLOBAL_OUTLINE_ACTS=4
ARC_OUTLINE_SIZE=5
PLANNING_WINDOW_SIZE=7
PLANNING_STRICT_MODE=true
```

如果你未来想把前端单独跑在别的端口，只要调整：

```env
CORS_ALLOW_ORIGINS=http://127.0.0.1:5173,http://localhost:5173
```

---

## 13. 测试与质量保障

当前仓库已经包含多类测试，覆盖范围包括：

- 健康检查
- API 基础联通
- Prompt 模板
- 章节质量检查
- 章节修复链路
- 硬事实守卫
- LLM 运行时
- Story state
- 数据库会话
- 若干轮隐藏回归测试

运行方式：

```bash
pytest -q backend/tests
```

项目还带有：

- `.github/workflows/backend-ci.yml`

也就是说，推到 GitHub 后可以自动跑后端回归测试。

---

## 14. 已知设计取向

为了更贴合“连载系统”的真实需求，这个项目有几个明确的设计取向：

### 14.1 不追求静默兜底

当模型不可用、超时、返回格式不合法时，项目更倾向于：

- 明确报错
- 停止当前阶段
- 让用户重试该阶段

而不是假装成功。

### 14.2 不把多章当一次长输出

批量生成必须逐章推进，每一章都会刷新状态。

### 14.3 先保留 JSON 运行时层，再逐步拆表

当前版本已经具备 Story Bible / runtime state / fact ledger 等层，但仍有部分状态保存在 JSON 中，后续适合继续拆分为独立表。

### 14.4 前后端优先同源部署

当前前端不依赖额外 Node 开发服务，默认由 FastAPI 直接提供静态资源，部署更简单、联调更稳定。

---

## 15. 常见问题

### Q1：初始化成功后，为什么没有自动生成前几章？

因为当前版本默认：

```env
BOOTSTRAP_INITIAL_CHAPTERS=0
```

也就是初始化只做“建书 + 总纲 + 规划”，正文由你之后按章生成。

### Q2：为什么批量生成不是一次直接吐出很多章？

因为这个项目是连载系统，不是长文本一次性生成器。多章必须逐章刷新状态，否则后文容易脱离前文事实。

### Q3：模型能 ping 通，为什么初始化还是报错？

因为初始化阶段可以使用不同的 provider / model / timeout。你可以用：

```text
GET /api/v1/health/llm?ping=true&stage=bootstrap
```

专门测试 bootstrap 阶段。

### Q4：导出支持哪些格式？

支持：

- txt
- md
- docx
- pdf

### Q5：前端要单独跑 Node 服务吗？

不用。当前版本默认由 FastAPI 直接提供 `/app` 与 `/app/assets`。

---

## 16. 章节超时与补尾排查建议

如果生成中出现章节耗时过长、补尾失败或尾部不完整，可以优先检查这些参数：

- `CHAPTER_EXTENSION_MIN_LLM_TIMEOUT_SECONDS`
- `CHAPTER_EXTENSION_SOFT_MIN_TIMEOUT_SECONDS`
- `CHAPTER_GENERATION_WALL_CLOCK_LIMIT_SECONDS`
- `CHAPTER_RUNTIME_SUMMARY_RESERVE_SECONDS`
- `CHAPTER_DRAFT_MAX_ATTEMPTS`
- `CHAPTER_TOO_SHORT_RETRY_ATTEMPTS`
- `CHAPTER_TAIL_FIX_ATTEMPTS`

当前版本在这块已经做了两条比较重要的优化：

1. `CHAPTER_TOO_SHORT` 优先走紧凑重生成，不再简单粗暴全文补写
2. `CHAPTER_ENDING_INCOMPLETE` 的补尾更聚焦于结尾片段，而不是把整章再喂一遍模型

---

## 17. 后续推荐演进方向

当前版本已经具备比较完整的“连载生产系统”雏形，但后续仍有几个很值得继续推进的方向：

- 将 `planning_windows`、`chapter_cards`、`fact_ledgers`、`generation_logs` 进一步拆表
- 加入更细的生成日志与阶段耗时统计
- 为 repair pipeline 扩展更多可插拔策略
- 增加更强的章节对比、回滚和分支续写能力
- 给前端补充更强的调试视图，例如 hard-fact 冲突面板、规划窗口 diff、状态快照对比

---

## 18. 文档导航

- `docs/product_spec.md`：项目定位与工作流说明
- `docs/architecture.md`：系统结构与模块关系
- `docs/database.md`：数据库设计说明
- `docs/openai_integration.md`：模型接入说明
- `docs/export.md`：导出能力说明
- `docs/roadmap.md`：后续规划
- `CHANGELOG.md`：版本变更记录

---

## 19. 一句话总结

这不是一个“输入一句话，立刻生成整本修仙小说”的玩具项目。

它是一套面向**长期连载**的小说生产系统：

- 能建书
- 能规划
- 能逐章续写
- 能批量串行生成
- 能校验质量
- 能检查硬事实
- 能人工干预
- 能库存发布
- 能导出成书

如果你的目标是做一个真正能持续往后写、而不是写几章就崩的 AI 连载平台，这个版本已经具备一个比较扎实的基础。