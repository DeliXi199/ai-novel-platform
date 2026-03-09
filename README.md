# AI Novel Platform MVP

一个面向读者的 **AI 连载小说 MVP**。  
用户可以创建一本个性化小说，系统按章生成内容；每章之间，用户可以输入偏好或要求，影响后续章节走向。

当前版本包含：

- FastAPI 后端
- PostgreSQL 数据模型
- Docker Compose 数据库
- Novel / Chapter / Intervention 基础接口
- Mock 生成模式
- OpenAI 真实生成模式（Responses API）
- Groq 免费层真实生成模式（OpenAI-compatible Responses API）
- 整本导出：txt / md / docx / pdf

---

## 1. 项目结构

```text
ai-novel-platform-mvp/
├── README.md
├── .env.example
├── docker-compose.yml
├── docs/
│   ├── architecture.md
│   ├── database.md
│   ├── roadmap.md
│   ├── export.md
│   └── openai_integration.md
└── backend/
    ├── requirements.txt
    ├── app/
    │   ├── main.py
    │   ├── core/
    │   ├── db/
    │   ├── api/routes/
    │   ├── models/
    │   ├── schemas/
    │   └── services/
    └── tests/
```

---

## 2. 你真正要改的地方

**只需要改 `backend/.env` 里的 API key 和 provider。**

推荐流程：

1. 复制项目根目录 `.env.example` 到根目录 `.env`
2. 再复制到 `backend/.env`
3. 在 `backend/.env` 里填你的 key
4. 启动后端

> 注意：因为 `backend/app/core/config.py` 读取的是当前工作目录下的 `.env`，所以你从 `backend/` 目录启动时，**真正生效的是 `backend/.env`**。

---

## 3. 快速启动

### 3.1 启动 PostgreSQL

在项目根目录执行：

```bash
docker compose up -d
```

### 3.2 配置环境变量

先在项目根目录复制：

```bash
cp .env.example .env
```

然后再进入 `backend` 目录复制：

```bash
cd backend
cp ../.env.example .env
```

### 3.3 填 API key

#### 方案 A：Groq 免费层（推荐先跑通）

把 `backend/.env` 改成：

```env
LLM_PROVIDER=groq
GROQ_API_KEY=你的_groq_key
GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_MODEL=openai/gpt-oss-20b

OPENAI_API_KEY=
```

#### 方案 B：OpenAI

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=你的_openai_key
OPENAI_MODEL=gpt-5.4
```

#### 方案 C：Mock（不调模型）

```env
LLM_PROVIDER=mock
```

### 3.4 安装后端依赖

```bash
pip install -r requirements.txt
```

### 3.5 初始化数据库

```bash
python -m app.db.init_db
```

### 3.6 启动服务

```bash
uvicorn app.main:app --reload
```

打开 Swagger：

```text
http://127.0.0.1:8000/docs
```

---

## 4. 核心接口

### 4.1 创建小说

`POST /api/v1/novels`

示例请求：

```json
{
  "genre": "凡人流修仙",
  "premise": "灵气衰败的时代，一个边陲少年意外得到残缺古卷，从散修一步步卷入宗门、王朝与上古遗迹的争斗。",
  "protagonist_name": "林玄",
  "style_preferences": {
    "tone": "冷峻慢热",
    "forbidden": ["后宫", "无脑开挂", "纯爽文"]
  }
}
```

### 4.2 获取章节

`GET /api/v1/novels/{novel_id}/chapters/{chapter_no}`

### 4.3 提交读者干预

`POST /api/v1/novels/{novel_id}/interventions`

示例：

```json
{
  "chapter_no": 1,
  "raw_instruction": "下一章轻松一点，多写某个角色的戏份，别太虐",
  "effective_chapter_span": 5
}
```

### 4.4 生成下一章

`POST /api/v1/novels/{novel_id}/next-chapter`

### 4.5 导出整本小说

- `GET /api/v1/novels/{novel_id}/export?format=txt`
- `GET /api/v1/novels/{novel_id}/export?format=md`
- `GET /api/v1/novels/{novel_id}/export?format=docx`
- `GET /api/v1/novels/{novel_id}/export?format=pdf`

---

## 5. 一次完整测试顺序

1. `POST /api/v1/novels` 创建新书
2. `GET /api/v1/novels/{id}/chapters/1` 读取第 1 章
3. `POST /api/v1/novels/{id}/next-chapter` 生成第 2 章
4. `POST /api/v1/novels/{id}/interventions` 提建议
5. `POST /api/v1/novels/{id}/next-chapter` 生成第 3 章
6. `GET /api/v1/novels/{id}/export?format=docx` 或 `pdf` 导出整本

---

## 6. 常见问题

### Q1：为什么我填了根目录 `.env` 但没生效？
因为你通常是从 `backend/` 目录启动 `uvicorn`，此时配置默认读的是 **`backend/.env`**。

### Q2：为什么正文还是像模板？
因为当前很可能还在 `mock` 模式，或者真实 provider key 没生效。新生成章节的 `generation_meta.generator` 应该不是 `mock_*`。

### Q3：导出中文文件名为什么以前报错？
这个版本已经修好，使用了 `filename` + `filename*` 双写法，兼容中文文件名。

---

## 7. 说明

- 这是一版 **MVP 骨架**，重点是跑通：创建 → 连载 → 干预 → 导出。
- 真正上线前，建议再加：重试、流式生成、章节规划器、更强的状态提取器、前端阅读页。
