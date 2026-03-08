# AI Novel Platform MVP

一个面向读者的 **AI 连载小说平台** 最小可运行后端骨架。

目标：
- 用户创建一本小说（题材、背景、主角名、偏好）
- 系统生成小说基础信息
- 系统按章节持续生成内容
- 用户可在章与章之间提交偏好/建议
- 后端维护小说状态、角色状态、章节摘要、用户干预

当前仓库提供：
- FastAPI 后端框架
- PostgreSQL 数据库模型
- Docker Compose 本地数据库
- 环境变量示例
- 初始化脚本
- 基础 API 路由
- 文档：架构、数据库、开发路线

---

## 1. 项目结构

```text
ai-novel-platform-mvp/
├── README.md
├── .gitignore
├── .env.example
├── docker-compose.yml
├── docs/
│   ├── architecture.md
│   ├── database.md
│   └── roadmap.md
└── backend/
    ├── requirements.txt
    ├── app/
    │   ├── main.py
    │   ├── core/
    │   │   └── config.py
    │   ├── db/
    │   │   ├── base.py
    │   │   ├── init_db.py
    │   │   └── session.py
    │   ├── api/
    │   │   └── routes/
    │   │       ├── health.py
    │   │       └── novels.py
    │   ├── models/
    │   │   ├── character.py
    │   │   ├── chapter.py
    │   │   ├── chapter_summary.py
    │   │   ├── intervention.py
    │   │   └── novel.py
    │   ├── schemas/
    │   │   ├── chapter.py
    │   │   ├── intervention.py
    │   │   └── novel.py
    │   └── services/
    │       ├── chapter_generation.py
    │       └── novel_bootstrap.py
    └── tests/
        └── test_health.py
```

---

## 2. 本地启动

### 2.1 克隆仓库

```bash
git clone <your-repo-url>
cd ai-novel-platform-mvp
```

### 2.2 启动 PostgreSQL

```bash
docker compose up -d
```

### 2.3 创建 Python 虚拟环境

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows 用 .venv\Scripts\activate
pip install -r requirements.txt
```

### 2.4 配置环境变量

```bash
cp ../.env.example .env
```

然后按本机情况修改 `.env`。

### 2.5 初始化数据库

```bash
python -m app.db.init_db
```

### 2.6 启动服务

```bash
uvicorn app.main:app --reload
```

打开：
- API 根路径: `http://127.0.0.1:8000/`
- Swagger 文档: `http://127.0.0.1:8000/docs`

---

## 3. 已实现 API

### 健康检查
- `GET /api/v1/health`

### 小说
- `POST /api/v1/novels` 创建小说并生成第 1 章
- `GET /api/v1/novels/{novel_id}` 获取小说详情
- `GET /api/v1/novels/{novel_id}/chapters/{chapter_no}` 获取章节
- `POST /api/v1/novels/{novel_id}/interventions` 提交用户建议
- `POST /api/v1/novels/{novel_id}/next-chapter` 生成下一章

---

## 4. 当前生成逻辑说明

当前仓库里的“生成”是 **占位版 deterministic/mock 逻辑**，目的是先把：
- 数据流
- 状态流
- API 契约
- 数据库设计

全部搭起来。

后面你只需要把 `services/novel_bootstrap.py` 和 `services/chapter_generation.py` 替换成真实 LLM 调用即可。

---

## 5. 建议开发顺序

1. 跑通本地服务和数据库
2. 用 Swagger 测试创建小说与续章
3. 接入真实模型 API
4. 补章节规划器和状态提取器
5. 增加前端阅读页
6. 增加用户偏好控制面板
7. 增加分支小说与版本回滚

详细说明见：
- `docs/architecture.md`
- `docs/database.md`
- `docs/roadmap.md`
