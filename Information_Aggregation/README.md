# 达人信息聚合系统 (Influencer Information Aggregation)

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)](https://fastapi.tiangolo.com/)
[![Vue](https://img.shields.io/badge/Vue-3.4+-brightgreen.svg)](https://vuejs.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 📖 项目简介

达人信息聚合系统是一个**智能化的多平台达人数据采集、管理与匹配平台**，支持抖音（星图）、小红书（蒲公英）等主流社交媒体平台的达人信息自动采集、智能标签分类、精准匹配推荐等功能。

### ✨ 核心特性

- 🚀 **多平台自动化采集**：基于 Playwright 的浏览器自动化，支持抖音星图、小红书蒲公英
- 🏷️ **智能标签系统**：多层级标签分类，自动打标与手动管理结合
- 🎯 **智能匹配引擎**：基于多维度指标的达人精准匹配算法
- 👥 **RBAC 权限管理**：超级管理员/管理员/用户三级权限体系
- 📊 **MCN 机构管理**：机构信息与旗下达人关联管理
- ✅ **审核工作流**：采集数据审核入库机制
- 🔐 **安全可靠**：JWT 认证、登录限流、CORS 防护
- 🐳 **容器化部署**：Docker Compose 一键启动

---

## 🏗️ 技术架构

### 后端技术栈

- **框架**: FastAPI 0.109+
- **ORM**: SQLAlchemy 2.0 + Alembic
- **数据库**: MySQL 8.0
- **缓存**: Redis 7
- **认证**: JWT (python-jose) + bcrypt
- **自动化**: Playwright 1.41+
- **配置管理**: Pydantic Settings
- **日志**: Python logging + RotatingFileHandler

### 前端技术栈

- **框架**: Vue 3.4 + TypeScript
- **UI 组件**: Element Plus 2.5
- **状态管理**: Pinia 2.1
- **路由**: Vue Router 4.3
- **HTTP 客户端**: Axios 1.6
- **构建工具**: Vite 5.1

### 系统架构图

```
┌─────────────┐         ┌──────────────┐         ┌─────────────┐
│   Frontend  │ ◄─────► │   Backend    │ ◄─────► │   MySQL     │
│  Vue 3 + TS │  HTTP   │   FastAPI    │  SQL    │   Database  │
│  Element+   │         │  Services    │         │             │
└─────────────┘         └──────────────┘         └─────────────┘
                               │
                        ┌──────┴──────┐
                        │             │
                  ┌─────▼─────┐ ┌────▼──────┐
                  │  Redis    │ │Playwright │
                  │  (Cache)  │ │Collectors │
                  └───────────┘ └───────────┘
```

---

## 📁 项目结构

```
Information_Aggregation/
├── backend/                    # 后端服务
│   ├── app/
│   │   ├── api/v1/            # API 路由层
│   │   │   ├── auth.py        # 认证接口
│   │   │   ├── influencers.py # 达人接口
│   │   │   ├── collection.py  # 采集任务接口
│   │   │   ├── match.py       # 匹配接口
│   │   │   ├── agencies.py    # MCN 机构接口
│   │   │   ├── tags.py        # 标签接口
│   │   │   ├── users.py       # 用户管理接口
│   │   │   └── permissions.py # 权限接口
│   │   ├── collectors/        # 采集器模块
│   │   │   ├── base.py        # 抽象基类
│   │   │   ├── xingtu_browser.py    # 星图浏览器采集
│   │   │   ├── pugongying_browser.py # 蒲公英浏览器采集
│   │   │   └── registry.py    # 采集器注册表
│   │   ├── services/          # 业务逻辑层
│   │   │   ├── collection_service.py
│   │   │   ├── influencer_service.py
│   │   │   ├── match_engine.py
│   │   │   └── ...
│   │   ├── models/            # 数据模型
│   │   ├── schemas/           # Pydantic 验证模型
│   │   ├── utils/             # 工具函数
│   │   ├── config.py          # 配置管理
│   │   ├── database.py        # 数据库连接
│   │   └── main.py            # 应用入口
│   ├── cookies/               # 浏览器登录态存储
│   ├── logs/                  # 日志文件
│   ├── scripts/               # 辅助脚本
│   ├── alembic/               # 数据库迁移
│   ├── .env                   # 环境变量配置
│   ├── requirements.txt       # Python 依赖
│   └── Dockerfile
│
├── frontend/                  # 前端应用
│   ├── src/
│   │   ├── api/              # API 请求封装
│   │   ├── components/       # 公共组件
│   │   ├── views/            # 页面组件
│   │   ├── router/           # 路由配置
│   │   ├── stores/           # Pinia 状态管理
│   │   ├── utils/            # 工具函数
│   │   └── App.vue
│   ├── package.json
│   └── Dockerfile
│
├── scripts/                   # 部署脚本
│   ├── setup_local.ps1       # 本地数据库初始化
│   ├── start_backend.bat     # 启动后端
│   ├── start_dev.bat         # 开发环境启动
│   └── stop_all.bat          # 停止所有服务
│
└── docker-compose.yml         # Docker 编排配置
```

---

## 🚀 快速开始

### 前置要求

- **Python**: 3.10+
- **Node.js**: 18+
- **MySQL**: 8.0+
- **Redis**: 7+
- **Playwright**: 需安装 Chromium 浏览器

### 方式一：Docker Compose 部署（推荐）

```bash
# 1. 克隆项目
git clone <repository-url>
cd Information_Aggregation

# 2. 配置环境变量
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env

# 3. 一键启动所有服务
docker-compose up -d

# 4. 访问应用
# 前端: http://localhost:5173
# 后端 API: http://localhost:8000
# API 文档: http://localhost:8000/docs
```

### 方式二：本地开发环境

#### 1. 数据库初始化

```powershell
# Windows PowerShell
cd scripts
.\setup_local.ps1

# 或使用 Python 脚本
python setup_db.py
```

#### 2. 后端启动

```bash
# 进入后端目录
cd backend

# 创建虚拟环境
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# 安装依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器
playwright install chromium

# 配置环境变量
copy .env.example .env
# 编辑 .env 文件，设置数据库连接等信息

# 启动服务
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### 3. 前端启动

```bash
# 进入前端目录
cd frontend

# 安装依赖
npm install

# 配置环境变量
copy .env.example .env

# 启动开发服务器
npm run dev
```

#### 4. 访问应用

- **前端界面**: http://localhost:5173
- **后端 API**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs (Swagger UI)
- **健康检查**: http://localhost:8000/health

---

## ⚙️ 配置说明

### 后端配置 (backend/.env)

```bash
# 基础配置
DEBUG=true
SECRET_KEY=dev-local-secret-key-at-least-32-characters-long

# 首次启动自动创建管理员
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change-me-on-first-run

# 数据库配置
DB_HOST=localhost
DB_PORT=3306
DB_USER=app_user
DB_PASSWORD=app123
DB_NAME=influencer_db

# Redis 配置
REDIS_URL=redis://localhost:6379/0

# 采集配置
COLLECTOR_MODE=browser  # mock / api / browser

# Playwright 配置
PLAYWRIGHT_HEADLESS=false
PLAYWRIGHT_SLOW_MO=80

# CORS 配置（局域网访问需添加 IP）
CORS_ORIGINS=http://localhost:5173,http://192.168.1.100:5173
```

### 前端配置 (frontend/.env)

```bash
# API 代理目标
VITE_API_TARGET=http://127.0.0.1:8000

# 如需直接指定 API 地址（内网穿透场景）
# VITE_API_BASE_URL=http://192.168.1.100:8000/api/v1
```

---

## 🔑 默认账号

首次启动时，系统会自动创建超级管理员账号：

- **用户名**: `qiufengai`
- **密码**: `qfai12@@`

或在 `.env` 中通过 `ADMIN_USERNAME` 和 `ADMIN_PASSWORD` 自定义。

---

## 📊 核心功能

### 1. 自动采集

支持多平台达人信息自动化采集：

- **抖音星图**: 基于 Playwright 浏览器自动化
- **小红书蒲公英**: 基于 Playwright 浏览器自动化
- **筛选条件**: 粉丝数、互动率、报价范围、内容类型等多维度筛选

**使用流程**:
1. 保存登录态: `python scripts/save_xingtu_session.py`
2. 创建采集任务（前端界面或 API）
3. 后台异步执行采集
4. 审核采集结果后入库

### 2. 智能标签

- **预置标签**: 系统内置行业、领域、内容类型等标签
- **层级管理**: 支持父子标签分类
- **自动打标**: 基于达人信息自动匹配标签
- **手动管理**: 管理员可自定义标签体系

### 3. 智能匹配

基于多维度指标的智能匹配算法：

- 粉丝量级匹配
- 互动率评估
- 性价比分析（CPM/CPE）
- 标签相似度计算
- 内容风格匹配

### 4. 权限管理

三级 RBAC 权限体系：

| 角色 | 权限范围 |
|------|---------|
| **超级管理员** | 全部权限，包括用户管理 |
| **管理员** | 达人库、采集任务、匹配、标签管理 |
| **用户** | 查看达人库、申请权限、提交采集任务 |

### 5. MCN 机构管理

- 机构信息维护
- 旗下达人关联
- 合作政策记录

---

## 🛠️ 常用命令

### 后端

```bash
# 启动开发服务器
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 生成数据库迁移
alembic revision --autogenerate -m "description"

# 执行迁移
alembic upgrade head

# 运行采集任务（独立进程）
python scripts/run_collect_worker.py <task_id>
```

### 前端

```bash
cd frontend

# 开发模式
npm run dev

# 生产构建
npm run build

# 预览构建结果
npm run preview
```

### Docker

```bash
# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f backend

# 停止服务
docker-compose down

# 重新构建
docker-compose up -d --build
```

---

## 🧪 测试

```bash
# 后端测试（待实现）
cd backend
pytest

# 前端测试（待实现）
cd frontend
npm run test
```

> ⚠️ **注意**: 当前版本测试覆盖率较低，建议在修改核心逻辑后手动验证功能。

---

## 📝 API 文档

启动后端服务后，访问以下地址查看 API 文档：

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### 主要接口概览

| 模块 | 路径前缀 | 说明 |
|------|---------|------|
| 认证 | `/api/v1/auth` | 登录、登出、刷新 Token |
| 达人 | `/api/v1/influencers` | 达人列表、详情、搜索 |
| 采集 | `/api/v1/collection` | 创建任务、任务状态、审核 |
| 匹配 | `/api/v1/match` | 创建匹配、查看结果 |
| 标签 | `/api/v1/tags` | 标签 CRUD、层级管理 |
| 机构 | `/api/v1/agencies` | MCN 机构管理 |
| 用户 | `/api/v1/users` | 用户管理（超管） |
| 权限 | `/api/v1/permissions` | 权限申请与审核 |

---

## 🔒 安全建议

### 生产环境部署

1. **修改默认密钥**
   ```bash
   SECRET_KEY=<至少32位的随机字符串>
   ```

2. **关闭调试模式**
   ```bash
   DEBUG=false
   ```

3. **限制 CORS 来源**
   ```bash
   CORS_ORIGINS=https://your-domain.com
   ```

4. **使用强密码**
   - 数据库密码
   - 管理员密码
   - Redis 密码（如启用）

5. **启用 HTTPS**
   - 使用 Nginx 反向代理
   - 配置 SSL 证书

6. **定期更新依赖**
   ```bash
   pip list --outdated
   npm outdated
   ```

---

## 🐛 常见问题

### 1. 数据库连接失败

```
错误: Can't connect to MySQL server
```

**解决方案**:
```powershell
# 检查 MySQL 服务是否启动
Get-Service MySQL*

# 重新初始化数据库
.\scripts\setup_local.ps1
```

### 2. Playwright 浏览器未安装

```
错误: Executable doesn't exist at ...
```

**解决方案**:
```bash
cd backend
playwright install chromium
```

### 3. 采集任务一直 pending

**检查项**:
- Redis 服务是否正常运行
- Worker 进程是否启动
- 查看后端日志: `backend/logs/`

### 4. CORS 跨域错误

**解决方案**:
在 `backend/.env` 中添加前端地址：
```bash
CORS_ORIGINS=http://localhost:5173,http://your-ip:5173
```

### 5. Cookie 过期导致采集失败

**解决方案**:
```bash
# 重新保存登录态
python scripts/save_xingtu_session.py
python scripts/save_pugongying_session.py
```

---

## 📈 性能优化建议

### 数据库优化

- 为常用查询字段添加索引（`platform_uid`, `follower_count`）
- 定期清理过期日志和临时数据
- 使用连接池（已配置 `pool_pre_ping`）

### 缓存策略

- Redis 缓存热点数据（标签列表、达人详情）
- 设置合理的 TTL（Time-To-Live）

### 采集优化

- 调整 `PLAYWRIGHT_SLOW_MO` 平衡速度与稳定性
- 使用代理 IP 池避免封禁
- 实施请求频率限制

---

## 🗺️ 路线图

### v1.0 (当前版本)
- ✅ 多平台采集
- ✅ 基础标签系统
- ✅ 智能匹配
- ✅ RBAC 权限

### v1.1 (计划中)
- [ ] 单元测试覆盖率达到 60%
- [ ] Celery 异步任务队列
- [ ] Prometheus 监控集成
- [ ] 前端 E2E 测试

### v2.0 (长期规划)
- [ ] 微服务架构拆分
- [ ] Elasticsearch 全文检索
- [ ] 机器学习增强匹配
- [ ] 消息队列解耦

---

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

---

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

---

## 👥 联系方式

- **项目维护者**: 秋枫
- **邮箱**: [your-email@example.com]
- **Issue**: [GitHub Issues](https://github.com/your-repo/issues)

---

## 🙏 致谢

感谢以下开源项目：

- [FastAPI](https://fastapi.tiangolo.com/)
- [Vue.js](https://vuejs.org/)
- [Element Plus](https://element-plus.org/)
- [Playwright](https://playwright.dev/)
- [SQLAlchemy](https://www.sqlalchemy.org/)

---

<div align="center">

**如果这个项目对你有帮助，请给个 ⭐ Star 支持一下！**

Made with ❤️ by 秋枫团队

</div>
