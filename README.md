# AI Novel Platform MVP

一个面向读者的 **AI 连载小说 MVP**。  
用户可以创建一本个性化小说，系统按章生成内容；每章之间，用户可以输入偏好或要求，影响后续章节走向。

当前版本包含：

- FastAPI 后端
- PostgreSQL 数据模型
- Docker Compose 数据库
- Novel / Chapter / Intervention 基础接口
- Mock 生成模式
- OpenAI 真实生成模式（OpenAI Python SDK + Responses API）

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

## 2. 快速启动

### 2.1 启动 PostgreSQL

在项目根目录执行：

```bash
docker compose up -d
```

### 2.2 配置环境变量

复制：

```bash
cp .env.example .env
```

默认情况下：

```env
LLM_PROVIDER=mock
```

这表示先使用本地占位生成逻辑。

如果你要真实调用 OpenAI：

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=你的key
OPENAI_MODEL=gpt-5.4
```

### 2.3 安装后端依赖

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows 用 .venv\Scripts\activate
pip install -r requirements.txt
```

### 2.4 初始化数据库

```bash
cp ../.env .env
python -m app.db.init_db
```

### 2.5 启动服务

```bash
uvicorn app.main:app --reload
```

打开 Swagger：

```text
http://127.0.0.1:8000/docs
```

---

## 3. 核心接口

### 3.1 创建小说

`POST /api/v1/novels`

示例请求：

```json
{
  "genre": "都市悬疑",
  "premise": "海边小城连续失踪案背后隐藏家族秘密",
  "protagonist_name": "沈昼",
  "style_preferences": {
    "tone": "压抑慢热",
    "forbidden": ["后宫", "无脑爽文"]
  }
}
```

### 3.2 获取章节

`GET /api/v1/novels/{novel_id}/chapters/{chapter_no}`

### 3.3 提交读者干预

`POST /api/v1/novels/{novel_id}/interventions`

示例：

```json
{
  "chapter_no": 1,
  "raw_instruction": "下一章轻松一点，别太虐，节奏快一点",
  "effective_chapter_span": 5
}
```

### 3.4 生成下一章

`POST /api/v1/novels/{novel_id}/next-chapter`

---

## 4. 当前生成链路

### 创建新书

1. 用户提交题材 / 背景 / 主角名 / 风格偏好  
2. 系统构建 `story_bible`  
3. 生成标题  
4. 生成第 1 章  
5. 自动生成第 1 章摘要并写入数据库  

### 续写下一章

1. 读取小说上下文  
2. 读取上一章尾段  
3. 读取最近几章摘要  
4. 读取仍生效的读者干预  
5. 生成下一章正文  
6. 提取章节摘要并写回数据库  

---

## 5. OpenAI / Codex 接入

详细见：

- `docs/openai_integration.md`

当前这一版采用：

- OpenAI Python SDK
- Responses API
- 默认模型：`gpt-5.4`
- 可选模型：`gpt-5.3-codex`

---

## 6. 下一步建议

当前版本已经完成“能跑的生成骨架”。下一步最值得做的是：

1. 前端阅读页（开书 / 阅读 / 下一章 / 提建议）
2. 更强的读者偏好解析
3. 角色状态表自动更新
4. 严格结构化输出 / 重试机制
5. 章节流式生成
6. 分支宇宙 / 回滚能力

---

## 7. 开发模式建议

- 先用 `mock` 跑通数据库和 API
- 再切换到 `openai`
- 先验证 10 章以内连续性
- 再扩展到 50 章、100 章

