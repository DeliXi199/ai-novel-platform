# 模型接入说明（OpenAI / DeepSeek / Groq）

项目当前只支持这三种 provider：

- `LLM_PROVIDER=openai`
- `LLM_PROVIDER=deepseek`
- `LLM_PROVIDER=groq`

不再支持 `mock` provider，也不会静默退回本地占位正文。

## 1. 配置位置

推荐直接在：

```text
backend/.env
```

里配置真实 key。

## 2. 示例配置

### OpenAI

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=你的真实_openai_key
OPENAI_MODEL=gpt-5.4
OPENAI_REASONING_EFFORT=medium
```

### DeepSeek

```env
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=你的真实_deepseek_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

### Groq

```env
LLM_PROVIDER=groq
GROQ_API_KEY=你的真实_groq_key
GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_MODEL=openai/gpt-oss-20b
```

## 3. 运行时行为

### 正文生成

- OpenAI / Groq 使用 Responses API
- DeepSeek 使用 Chat Completions API

### 摘要生成

`CHAPTER_SUMMARY_MODE` 默认是 `auto`：

- 先调用模型生成摘要
- 如果摘要阶段失败，再退回启发式摘要
- 不会因为摘要失败就把正文静默改写成 fallback

## 4. 关键代码位置

```text
backend/app/services/openai_story_engine.py
backend/app/services/llm_runtime.py
backend/app/services/llm_types.py
```

其中：

- `openai_story_engine.py` 负责高层生成函数
- `llm_runtime.py` 负责 provider 选择、client 初始化、节流、trace 和错误包装
- `llm_types.py` 放统一的 payload schema

## 5. 如何判断是否真的调用了模型

新生成章节的 `generation_meta` 里会记录：

- `provider`
- `trace_id`
- `llm_call_trace`
- `summary_mode_configured`

`llm_call_trace` 中会包含：

- `stage`
- `provider`
- `model`
- `throttle_scope`
- `waited_ms`
- `duration_ms`
- `response_chars`
- 错误时的请求 ID / 限流头（若 provider 返回）

## 6. 失败策略

这些情况会直接返回结构化错误，而不是写入 fallback 文本：

- provider 未配置
- API key 错误
- 超时
- 限流
- 网络失败
- 模型输出格式无效
- 章节质量校验失败
