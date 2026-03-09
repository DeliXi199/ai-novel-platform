# 模型接入说明（OpenAI / Groq / Mock）

这个项目支持三种模式：

- `LLM_PROVIDER=mock`：本地占位逻辑，先跑通流程。
- `LLM_PROVIDER=openai`：调用 OpenAI Python SDK + Responses API。
- `LLM_PROVIDER=groq`：调用 Groq 的 OpenAI-compatible Responses API（适合先用免费层验证流程）。

## 1. 最省事的做法

直接修改：

```text
backend/.env
```

### 用 Groq 免费层

```env
LLM_PROVIDER=groq
GROQ_API_KEY=你的真实_groq_key
GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_MODEL=openai/gpt-oss-20b
```

### 用 OpenAI

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=你的真实_openai_key
OPENAI_MODEL=gpt-5.4
```

## 2. 如何判断已经走真实模型

新生成章节的 `generation_meta` 里：

- 如果看到 `generator=mock_*`，说明还在 mock
- 如果看到 `generator=responses_api`，且 `provider=openai` 或 `provider=groq`，说明已经走真实模型

## 3. 关键代码位置

```text
backend/app/services/openai_story_engine.py
```

这个文件现在同时负责：

- OpenAI
- Groq
- 统一 Responses API 请求

虽然文件名还叫 `openai_story_engine.py`，但内部已经支持两个 provider。
