# OpenAI / Codex 接入说明

这个项目现在支持两种生成模式：

- `LLM_PROVIDER=mock`：本地占位逻辑，方便先跑通接口。
- `LLM_PROVIDER=openai`：调用 OpenAI Python SDK + Responses API，真实生成章节。

## 为什么这里默认推荐 `gpt-5.4`

当前 OpenAI 官方文档把 `gpt-5.4` 作为广义默认模型，也说明它是 Codex 和 Codex CLI 当前使用的最新模型；如果你的工作流同时包含代码开发、规划和写作，它是更好的默认选择。文档也提到 `gpt-5.3-codex` 仍可在 Responses API 中使用，更偏 agentic coding 场景。  
参考：
- Using GPT-5.4（OpenAI official）
- Code generation guide（OpenAI official）
- API deprecations（`codex-mini-latest` 已移除，推荐迁移到 `gpt-5-codex-mini` / 新模型）

## 环境变量

复制根目录的 `.env.example` 为 `.env`，然后至少修改：

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=你的key
OPENAI_MODEL=gpt-5.4
```

## 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

## 当前接入方式

项目目前通过 `backend/app/services/openai_story_engine.py` 调用 OpenAI：

- 创建新书时：生成真实第 1 章
- 续写时：根据故事圣经、最近章节摘要、上一章尾段、读者干预来写下一章
- 解析读者干预时：可选调用模型将自然语言转成结构化控制参数

## 重要提醒

1. 这一版先追求“稳定可跑”，所以没有上 streaming。
2. 这一版用的是“严格 JSON 输出 + 本地解析”策略，足够做 MVP。
3. 真正上线前，建议再加：
   - 重试机制
   - 更严格的结构化输出
   - 请求日志 / trace id
   - 成本统计
   - 安全审核
