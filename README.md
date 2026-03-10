# AI Novel Platform MVP (Layered Outline Edition)

这是一个面向长篇连载的 AI 小说生成后端原型。

当前版本的核心思路不是“建书后立刻吐出很多正文”，而是：

- 建书时先生成 **全书粗纲（Global Outline）**
- 再生成 **第一段小弧线（Active Arc）**
- **不预生成正文**
- 后续按章生成，并为每章提取摘要作为轻量记忆
- 支持连续生成多章与导出 `txt / md / docx / pdf`

## 这版重点修正了什么

### 1. 文档与代码状态重新对齐

项目文档已同步到当前真实行为：

- 初始化只建书，不预生成前三章
- 不再支持 `mock` provider
- 默认工作流是按章生成，而不是先拍前 10 章再直接批量生成前 10 章

### 2. LLM 调用节流不再是全局单点

现在节流按 **provider + base_url + model** 维度隔离：

- 同一模型链路仍会自动留间隔
- 不同 provider / model 不会共享同一个全局节流时间戳

### 3. 摘要策略更合理

`CHAPTER_SUMMARY_MODE=auto` 现在会：

- 先尝试模型摘要
- 只有摘要阶段失败时才退回启发式摘要

也支持：

- `llm`
- `heuristic`
- `auto`

### 4. 读者干预解析增强

读者指令现在是：

- **模型解析优先**
- **启发式解析兜底**
- 两者会合并，而不是模型失败后只剩极简关键词判断

启发式解析可识别更多内容：

- 角色戏份倾向
- 语气倾向
- 节奏倾向
- 保护角色
- 关系走向

### 5. 核心服务拆分

为了减少超大文件，核心逻辑已拆为：

- `backend/app/services/openai_story_engine.py`
- `backend/app/services/llm_runtime.py`
- `backend/app/services/llm_types.py`
- `backend/app/services/chapter_context.py`
- `backend/app/services/instruction_parser.py`

### 6. 增加了测试

新增测试覆盖：

- 配置校验
- 指令解析兜底
- 指令解析合并
- 摘要模式 fallback

## 快速开始

### 1. 启动数据库

```bash
docker compose up -d
```

### 2. 配置模型 API

复制根目录 `.env.example` 到 `backend/.env`，填写真实 key。

#### OpenAI

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=你的真实_openai_key
OPENAI_MODEL=gpt-5.4
```

#### DeepSeek

```env
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=你的真实_deepseek_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

#### Groq

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

## 核心接口

### 创建小说

```http
POST /api/v1/novels
```

行为：

- 生成标题
- 生成 `global_outline`
- 生成第一段 `active_arc`
- 保存小说对象
- `current_chapter_no = 0`

不会预生成正文。

### 生成下一章

```http
POST /api/v1/novels/{novel_id}/next-chapter
```

行为：

- 锁定该小说，避免并发写入
- 读取当前拍表
- 若当前章 plan 缺失，则现场补一段 arc
- 生成正文
- 质量校验
- 生成摘要
- 入库

### 连续生成多章

```http
POST /api/v1/novels/{novel_id}/next-chapters
```

请求体：

```json
{
  "count": 3
}
```

### 连续生成多章（SSE）

```http
POST /api/v1/novels/{novel_id}/next-chapters/stream
```

事件：

- `batch_started`
- `chapter_started`
- `chapter_succeeded`
- `error`
- `completed`

## 失败策略

项目不会静默 fallback 正文。

以下情况都会直接返回结构化错误：

- provider 未配置
- API key 错误
- 超时
- 限流
- 网络错误
- 模型 JSON 非法
- 章节质量不达标

失败章节不会入库。

## 测试

```bash
cd backend
pytest
```
