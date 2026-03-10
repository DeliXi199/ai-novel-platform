# v3 API 连接修正版说明

这版保留了 v3 的功能性改动，包括：

- 严格文档先行工作流
- planning-state / prepare-next-window 接口
- 紧凑 arc outline schema
- 分块 arc outline 生成
- JSON repair 与 regeneration

同时只针对 API 连接链路做了修正与增强：

1. 对 provider / api key / base_url / model 做统一清洗：去掉首尾空格、单双引号、末尾多余斜杠。
2. DeepSeek 的 `https://api.deepseek.com/v1` 会自动归一化为 `https://api.deepseek.com`，避免 OpenAI SDK 拼接路径时出现兼容问题。
3. 在优先读取 `.env` 配置的同时，也兼容读取以下环境变量：
   - DeepSeek: `DEEPSEEK_API_KEY` / `LLM_API_KEY` / `API_KEY`
   - DeepSeek Base URL: `DEEPSEEK_BASE_URL` / `LLM_BASE_URL` / `BASE_URL`
4. 新增 `GET /api/v1/health/llm`：
   - 默认返回当前生效的 provider / model / base_url / key 是否存在 / key 尾号掩码
   - `?ping=true` 时会实际发起一次极小请求验证连通性

## 推荐排查顺序

1. `GET /api/v1/health`
2. `GET /api/v1/health/llm`
3. `GET /api/v1/health/llm?ping=true`
4. `POST /api/v1/novels`
5. `POST /api/v1/novels/{id}/prepare-next-window`
6. `POST /api/v1/novels/{id}/next-chapter`

## 说明

这版没有回退 v3 的功能性逻辑，也没有删掉 JSON repair。仅对 API 读取与连通性诊断做增强。
