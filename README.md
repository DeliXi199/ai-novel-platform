# AI Novel Platform MVP (Manual-Driven Architecture Edition)

这版在原有“分层大纲 + 按章/批量生成 + 明确报错”的基础上，进一步把“修仙日更网文作者工作手册”映射进代码架构：

- 项目卡 / 世界骨架 / 修炼体系 / 分卷卡
- 连载控制台（主角状态、战力账本、角色卡、关系、伏笔、时间线）
- 每章执行卡（昨天结尾、今天功能、三行章纲、明天提示）
- 卷末复盘
- `GET /api/v1/novels/{id}/control-console` 查看当前控制台

更详细说明见 `docs/manual_architecture.md`。

# AI Novel Platform MVP (Layered Outline Edition)

一个面向读者的 AI 连载小说原型：

- 建书时先生成 **全书粗纲（Global Outline）**
- 再生成 **第一段小弧线（Arc Outline）**
- **不再预生成前三章正文**
- 后续由你手动一章章生成
- 章节生成默认启用 **轻量上下文模式（light context）**
- 支持导出 `txt / md / docx / pdf`

## 这次新增的稳态改动

这版重点不是继续压 prompt，而是处理你在 Groq 上看到的“总量没爆表但仍然 429”的问题。

### 1. 同一本书章节生成加了后端互斥锁

现在 `POST /api/v1/novels/{id}/next-chapter` 会先对这本书的数据库行加锁：

- 同一本书同一时间只允许一个章节生成任务
- 再次点击时不会并发打第二个请求
- 如果已有生成任务在跑，会返回 `CHAPTER_ALREADY_GENERATING` 和 HTTP 409

### 2. 模型调用改成更严格的串行节流

现在每次模型调用之间会自动留出一个最小时间间隔：

- `LLM_CALL_MIN_INTERVAL_MS=1200`
- 章节正文和章节摘要不会贴着一起打给 Groq
- 这能降低“瞬时突发请求”导致的 429

### 3. 一次章节默认只尝试 1 次正文生成

以前如果正文质量不过关，内部会立刻再打一遍模型。
现在默认：

- `CHAPTER_DRAFT_MAX_ATTEMPTS=3`
- 质量不达标直接报错
- 不会为了“内部再试一次”把瞬时请求数堆高

### 4. 未来 arc 改成按需生成，不在当前请求里预抓

以前当当前 arc 快写完时，会顺手预生成下一段 arc。
现在默认：

- `ARC_PREFETCH_THRESHOLD=0`
- 只有在下一章真的缺 plan 时，才现场生成新的 arc
- 大多数“生成下一章”请求只做两次模型调用：正文 + 摘要

### 5. 更细的调用跟踪

每次章节生成都会记录：

- `trace_id`
- 每个阶段的 `stage`
- provider / model
- prompt 字符数
- `max_output_tokens`
- 节流等待时间
- 调用耗时
- 是否成功或被限流

这些信息会写进章节的 `generation_meta.llm_call_trace`。
如果请求在模型阶段失败，错误返回里的 `detail.details` 也会尽量携带：

- `trace_id`
- `duration_ms`
- `request_id`
- `retry_after` / 相关限流头（如果 provider 返回了）

## 之前保留的改动

### 1. 去掉静默 fallback

现在不会再因为接口没配好、超时、限流、鉴权失败、返回 JSON 乱掉，就偷偷退回模板文本或 mock 大纲。
失败会直接返回结构化错误，失败章节不会入库。

### 2. 初始化只建书，不预生成正文

`POST /api/v1/novels` 只会：

- 生成书名
- 生成 `global_outline`
- 生成第一个 `active_arc`
- 保存小说对象

不会再默认生成正文。

### 3. 章节生成继续使用轻量上下文

章节生成默认只传：

- 书名、题材、主角、前提
- 当前阶段的核心写作约束
- 当前 act / active arc 的压缩信息
- 最近 2 章压缩摘要
- 上一章末尾约 400 字
- 当前有效的结构化读者干预


## 这一版继续加强了什么

### 1. 文风继续往“小说正文”靠

这版进一步强化了三类规则：

- **句子辨识度**：减少“温凉 / 微弱 / 若有若无 / 看了片刻 / 没有再说什么”这类安全表达反复出现
- **反派具体性**：帮派、恶人、威胁角色不能只会吓唬人，至少要带一个能被记住的危险细节
- **主角情绪沉半层**：林玄在离别、失去、当旧物、被迫抉择时，不再一句带过，会更强调动作、停顿、沉默和旧物处理

### 2. 失败后会多尝试几次，再停止

默认参数现在是：

- `CHAPTER_DRAFT_MAX_ATTEMPTS=4`
- `CHAPTER_TOO_SHORT_RETRY_ATTEMPTS=3`
- `CHAPTER_TAIL_FIX_ATTEMPTS=2`

不是机械重复同一版 prompt，而是会逐次切换侧重点：

- 去模板化、换句式
- 配角更像人
- 反派更具体
- 林玄情绪再沉半层
- 章末允许平稳过渡，而不是章章硬钩子

### 3. 新增“连续生成 N 章”接口

你现在不必一直点“下一章”了。后端新增了两个接口：

#### 一次性连续生成多章（普通 JSON 返回）

```http
POST /api/v1/novels/{novel_id}/next-chapters
```

请求体：

```json
{
  "count": 3
}
```

返回：

- `generated_count`
- `started_from_chapter`
- `ended_at_chapter`
- `chapters`
- `progress`（每一章的开始/完成日志）

#### 连续生成多章（SSE 实时进度流）

```http
POST /api/v1/novels/{novel_id}/next-chapters/stream
```

请求体同样是：

```json
{
  "count": 3
}
```

服务端会逐章推送：

- `batch_started`
- `chapter_started`
- `chapter_succeeded`
- `error`
- `completed`

这样前端就可以在生成过程中显示：

- 正在生成第几章
- 已完成几章
- 哪一章失败
- 最终一共成功了几章

### 4. 批量生成的停止规则

批量生成不是盲目一路冲下去，而是：

- 每一章内部会先按当前策略多次尝试
- 某一章如果最终仍失败，就在那一章停下
- SSE 会立刻推送 `error` 事件
- 已成功入库的前面章节会保留

## 快速开始

### 1. 启动数据库

```bash
docker compose up -d
```

### 2. 配置模型 API

复制根目录 `.env.example` 到 `backend/.env`，然后填写 key。

#### OpenAI 示例

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=你的真实_openai_key
OPENAI_MODEL=gpt-5.4
```

#### DeepSeek 示例

```env
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=你的真实_deepseek_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

#### Groq 示例

```env
LLM_PROVIDER=groq
GROQ_API_KEY=你的真实_groq_key
GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_MODEL=openai/gpt-oss-20b
```

### 3. 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

### 4. 初始化数据库

```bash
python -m app.db.init_db
```

### 5. 启动后端

```bash
uvicorn app.main:app --reload
```

打开：

```text
http://127.0.0.1:8000/docs
```

## 核心流程

### 建书时

- 生成 `global_outline`
- 生成 `active_arc`（默认第 1–5 章）
- 不生成正文

### 后续生成

- 对小说行加锁，防止同书并发生成
- 读取当前 `active_arc`
- 若当前章缺 plan，则即时生成下一段 arc
- 生成正文
- 做质量校验
- 再生成结构化摘要
- 全部成功后才入库

## 失败时返回什么

失败时 API 会返回结构化错误，例如：

```json
{
  "detail": {
    "code": "API_RATE_LIMITED",
    "stage": "chapter_generation",
    "message": "chapter_generation 失败：模型接口触发限流，请稍后重新生成。",
    "retryable": true,
    "provider": "groq",
    "details": {
      "trace_id": "novel-12-chapter-7-3ab4c5d6e7f8",
      "duration_ms": 214,
      "request_id": "req_xxx",
      "retry_after": "2"
    }
  }
}
```

常见错误码：

- `PROVIDER_NOT_CONFIGURED`
- `API_TIMEOUT`
- `API_RATE_LIMITED`
- `API_AUTH_FAILED`
- `MODEL_RESPONSE_INVALID`
- `CHAPTER_TOO_SHORT`
- `CHAPTER_TOO_SIMILAR`
- `CHAPTER_META_TEXT`
- `CHAPTER_DUPLICATED_PARAGRAPHS`
- `CHAPTER_ALREADY_GENERATING`

## 默认参数

在 `backend/app/core/config.py` 中：

- `chapter_context_mode = "light"`
- `chapter_recent_summary_limit = 2`
- `chapter_last_excerpt_chars = 400`
- `openai_chapter_max_output_tokens = 1500`
- `groq_chapter_max_output_tokens = 1400`
- `chapter_summary_max_output_tokens = 320`
- `chapter_draft_max_attempts = 1`
- `llm_call_min_interval_ms = 1200`
- `arc_prefetch_threshold = 0`
- `bootstrap_initial_chapters = 0`


## 章节摘要模式

- `CHAPTER_SUMMARY_MODE=auto`：默认。Groq / DeepSeek 使用本地启发式摘要，OpenAI 尝试 LLM 摘要。
- `CHAPTER_SUMMARY_MODE=heuristic`：始终用本地启发式摘要，不再额外请求模型。
- `CHAPTER_SUMMARY_MODE=llm`：始终请求模型提取摘要。


## 章节完整性与长度策略

- `CHAPTER_HARD_MIN_VISIBLE_CHARS=900`：全局硬下限，低于这一数值直接判定为半章。
- `CHAPTER_MIN_VISIBLE_CHARS=1200`：全局常规目标下限。
- `CHAPTER_PROBE_TARGET_MIN_VISIBLE_CHARS=1000` / `CHAPTER_PROBE_TARGET_MAX_VISIBLE_CHARS=1500`：试探、发现类章节。
- `CHAPTER_PROGRESS_TARGET_MIN_VISIBLE_CHARS=1400` / `CHAPTER_PROGRESS_TARGET_MAX_VISIBLE_CHARS=2200`：调查、交易、推进类章节。
- `CHAPTER_TURNING_POINT_TARGET_MIN_VISIBLE_CHARS=1800` / `CHAPTER_TURNING_POINT_TARGET_MAX_VISIBLE_CHARS=2600`：追逐、转折、重要揭示类章节。
- `CHAPTER_TOO_SHORT_RETRY_ATTEMPTS=2`：仅对过短正文做一次定向补写或重写，不做无限重试。
- `CHAPTER_TAIL_FIX_ATTEMPTS=2`：对疑似截断结尾做一次补尾。
- `CHAPTER_TAIL_FIX_DELAY_MS=900`：补尾前的短暂冷却，降低连续请求造成的 429。
- `RETURN_DRAFT_PAYLOAD_IN_META=false`：默认不在接口返回里附带整段草稿，避免和正式正文重复。
