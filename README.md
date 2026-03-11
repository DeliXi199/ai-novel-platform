# AI Novel Platform MVP · Fullstack Studio Edition

这一版在已有后端基础上，补齐了一个可直接操作的前端工作台，并把前后端联调方式收束成更稳定的同源模式。

## 现在可以直接做什么

- 书架查看：按更新时间查看所有小说，支持搜索
- 新建小说：填写题材、主角、前提与风格偏好，初始化全书粗纲和首段 arc
- 小说工作台：查看当前进度、规划窗口、控制台摘要、章节目录
- 单章生成：直接生成下一章
- 批量生成：通过 SSE 实时查看逐章进度与报错
- 人工干预：添加阶段性读者/作者指令
- 导出成书：支持 `txt / md / docx / pdf`
- 健康检查：前端可直接检测后端和模型接口状态

## 这版新增的关键工程改动

### 前端

- 新增 `frontend/` 同源静态工作台
- 页面入口：`/app`
- 不依赖额外 Node 前端服务，默认由 FastAPI 直接提供
- 书架、创建表单、章节阅读器、控制台摘要、批量日志均已接通

### 后端 API

补充了前端必需的轻量接口：

- `GET /api/v1/novels`：书架列表
- `GET /api/v1/novels/{id}/chapters`：章节目录
- `GET /api/v1/novels/{id}/interventions`：人工干预列表

同时保留已有能力：

- `POST /api/v1/novels`
- `POST /api/v1/novels/{id}/next-chapter`
- `POST /api/v1/novels/{id}/next-chapters/stream`
- `POST /api/v1/novels/{id}/prepare-next-window`
- `GET /api/v1/novels/{id}/control-console`
- `GET /api/v1/novels/{id}/export?format=pdf`

### 稳定性

- 前端改为同源访问，默认不需要额外配置跨域
- 仍保留 CORS 中间件，方便你以后拆分前端独立开发
- `/health/llm?ping=true` 失败时返回真实 HTTP 错误码
- 测试已覆盖健康检查、轻量列表接口、前端入口页

## 快速启动

### 1. 启动数据库

```bash
docker compose up -d
```

### 2. 配置环境变量

复制根目录 `.env.example` 到 `backend/.env`，填写你要用的模型 key。

### 3. 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

### 4. 初始化数据库

```bash
python -m app.db.init_db
```

### 5. 启动服务

```bash
uvicorn app.main:app --reload
```

## 打开方式

- 前端工作台：`http://127.0.0.1:8000/app`
- Swagger 文档：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/api/v1/health`

## 环境变量补充

如果你未来要把前端单独跑在别的端口，可以改：

```env
CORS_ALLOW_ORIGINS=http://127.0.0.1:5173,http://localhost:5173
```

## 运行测试

在项目根目录执行：

```bash
pytest -q backend/tests
```

当前这版已通过 8 个测试。
