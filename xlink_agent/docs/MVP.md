# xlink Agent MVP 说明书

> 状态：已确认，可作为一期开发依据  
> 对标：腾讯 WorkBuddy（办公对话式智能体）  
> 文档版本：v1.0｜2026-07-14

---

## 1. 目标与定位

在 xlink 门户中提供名为 **「智能体」** 的对话式办公 Agent：

- 用户用自然语言下发任务，Agent 规划、调用工具、交付可下载结果
- 支持自定义 Skill、私有/全局知识库（RAG）、服务端隔离浏览器（实时预览）
- 记忆与数据按门户用户 `uid` 严格隔离
- 一期以 **Web 服务** 交付，架构预留后续桌面壳（Electron 等）

**非目标（一期不做）**

- 本机文件系统读写
- IM（飞书/企微/Telegram 等）远程触发
- 与飞书文档库、会议纪要等模块的真实数据打通（仅预留接口）
- WorkBuddy 式多专家深度并行编排（二期）
- WebRTC 真视频流浏览器预览（二期）

---

## 2. 一期范围（Must）

| 能力 | 说明 |
|------|------|
| 多轮对话 + 流式输出 | SSE 或 WebSocket；中间聊天区展示 |
| 短期会话记忆 | 当前会话消息完整持久化 |
| 长期用户画像 | 跨会话偏好/项目摘要，按 `uid` 存储与注入 |
| 检索命中记录 | RAG / 工具检索的引用可回溯 |
| 自定义 Skill | Markdown/YAML + 工具清单；仅创建者可见 |
| Skill「市场」 | **仅系统/官方 Skill** 可安装到「我的 Skill」；用户自建永不共享 |
| 知识库 + RAG | 用户私有库；超管可管理全局库 |
| 自主浏览 | 服务端 Playwright/Chromium；每人一隔离实例；禁内网 |
| 实时预览 | CDP screencast 或定时截图 + WebSocket 推前端 |
| 文档生成 | Word / Excel / PPT / PDF，写入用户工作区并可下载 |
| 人工确认 | 危险操作（表单提交、外呼写操作、删文件等）需前端确认后继续 |
| 执行轨迹 | 展示计划步骤与工具调用（可折叠） |
| 轻量多 Skill | 单主 Agent（**ReAct**）；可挂多个 Skill；工具串行或轻量并行 |
| 门户入口 | 侧栏菜单「智能体」 |
| 工程接入 | 端口 `8003`；Compose 服务 `xlink-agent`；独立 MySQL 库 |

**明确不做（一期）**：本机文件、IM 远程、飞书/会议真打通、多专家深度并行、WebRTC。

---

## 3. 产品决策摘要

| # | 决策 |
|---|------|
| 形态 | 先 Web（A），预留桌面（B） |
| 浏览器 | 服务端 Chromium/Playwright；会话内嵌实时预览；要展示操作过程 |
| 隔离 | 每用户一浏览器实例；禁止访问内网（RFC1918 等） |
| Skill 格式 | Markdown/YAML 描述 + 允许工具清单 |
| Skill 可见性 | 用户自建仅自己；官方可「安装」 |
| 工具权限 | 可外呼 API、写工作区文件、开浏览器；后续对接会议/文件时必须校验系统权限 |
| 知识库 | 每人私有；超管管全局；单文件 ≤ 30MB |
| 格式 | PDF、Word、Markdown、TXT、Excel、HTML |
| 记忆 | 会话 + 长期画像 + 检索记录，全部要 |
| 向量库 | Qdrant（免费开源；开发 local 嵌入式 / 生产 Docker） |
| UI | 左会话 / 中聊天 / 右（浏览器 \| 知识库 \| Skill） |
| 模型 | 先 GLM；预留多模型切换接口 |
| 现有模块 | 先不打通，预留 Connector |
| 并发 | 一期约 8 人同时在线 |
| 写文件 | 每用户服务端工作区；可预览/下载；可归档到知识库 |

---

## 4. 总体架构

```
┌─────────────────────────────────────────────────────────────┐
│  Information_Aggregation/frontend  （Vue3 + Element Plus）   │
│  模块：智能体  modules/agent/                                 │
│  左：会话列表 │ 中：聊天+轨迹+确认 │ 右：浏览器/知识库/Skill   │
└───────────────┬─────────────────────────────┬───────────────┘
                │ JWT Bearer / WS?token=      │
                ▼                             ▼
┌───────────────────────────────┐   ┌─────────────────────────┐
│  xlink_agent backend :8003    │   │  实时通道                 │
│  FastAPI                      │   │  对话流式 / 浏览器帧     │
│  · 对话编排（单智能体 ReAct）  │   │  工具事件 / 确认请求     │
│  · Skill / KB / Memory        │   └─────────────────────────┘
│  · Browser pool（按 uid）     │
│  · Workspace 文件             │
│  · 人工确认状态机             │
└───────────┬─────────┬─────────┘
            │         │
            ▼         ▼
     MySQL            Qdrant
  xlink_agent      向量集合按
  （元数据）        uid / kb 隔离
            │
            ▼
     工作区磁盘
  /data/workspaces/{uid}/
```

**与门户关系**

- 认证：复用门户 JWT（`uid` / `role` / `perms`），模式对齐 flybook（无状态校验）
- 前端：挂在现有 SPA，不新开独立前端工程
- 代理：Vite dev + nginx 增加 `/api/agent/*` → `:8003`
- Docker：根目录 `docker-compose.yml` 增加 `xlink-agent`、`qdrant`；MySQL init 增加 `xlink_agent` 库与授权

**预留（不实现）**

- `connectors/feishu.py`、`connectors/meeting.py`：空实现 + 配置开关
- `desktop/` 或文档中的桌面壳扩展点（本机 Chrome / 本机文件）

---

## 5. 目录结构（规划）

```
xlink_agent/
  docs/
    MVP.md                 # 本文档
  backend/
    Dockerfile
    requirements.txt
    .env.example
    app/
      main.py
      config.py
      portal_auth.py       # JWT 校验（对齐 flybook）
      db/
        models.py
        session.py
      api/
        conversations.py
        messages.py        # 含流式
        skills.py
        knowledge.py
        browser.py
        workspace.py
        confirmations.py
        health.py
      agent/
        orchestrator.py    # 单智能体 ReAct 循环
        react.py           # Thought/Action/Observation 协议与轨迹
        context.py         # 任务工作记忆
        memory_service.py
        model_router.py    # GLM 实现 + 多模型接口
        events.py          # 流式事件协议
      skills/
        loader.py          # 解析 MD/YAML
        registry.py
        builtin/           # 官方 Skill
      tools/
        browser_tools.py
        kb_tools.py
        http_tools.py
        file_tools.py      # Office/PDF 生成与工作区
      browser/
        pool.py            # 每 uid 一实例
        session.py
        screencast.py
        net_guard.py       # 禁内网
      rag/
        ingest.py
        retrieve.py
        qdrant_client.py
      connectors/          # 一期 stub
        feishu.py
        meeting.py
  # 前端代码落在门户：
  # Information_Aggregation/frontend/src/modules/agent/
```

---

## 6. 技术选型

| 层 | 选型 | 备注 |
|----|------|------|
| 后端 | FastAPI + SQLAlchemy 2 + Pydantic 2 | 与现有卫星服务一致 |
| 认证 | 门户 JWT（`SECRET_KEY`/`JWT_SECRET`） | 声明 `uid` |
| 数据库 | MySQL 8 独立库 `xlink_agent` | 会话/记忆/Skill/KB 元数据/确认单/文件索引 |
| 向量 | Qdrant | 开发：`QDRANT_MODE=local` 嵌入式；生产：Compose `qdrant` 服务 + `QDRANT_MODE=url` |
| LLM | 智谱 GLM | `ModelRouter` 抽象，预留 DeepSeek/OpenAI 等 |
| 浏览器 | Playwright + Chromium | 每用户 Context；headless |
| 预览 | CDP screencast 或 JPEG 帧 + WS | 8 人够用 |
| 文档生成 | python-docx / openpyxl / python-pptx / reportlab 或 weasyprint | 写入工作区 |
| 解析入库 | pypdf / python-docx / openpyxl / BeautifulSoup | 单文件 ≤ 30MB |
| 前端 | Vue 3 + TS + Pinia + Element Plus | 门户模块 `agent` |
| 流式 | 对话建议 SSE；浏览器帧/确认建议 WS | 也可统一 WS，实现时二选一写清 |

---

## 7. 数据模型（要点）

关联键：**`user_id` = 门户 JWT `uid`（BigInteger）**，不自建用户表做身份源。

### 7.1 会话与消息

- `conversations`：id, user_id, title, status, created_at, updated_at
- `messages`：id, conversation_id, user_id, role(`user`/`assistant`/`system`/`tool`), content, metadata_json, created_at
- `run_events`（可选）：计划步骤、工具调用、确认等待等轨迹事件，便于回放

### 7.2 记忆

- `memory_profiles`：user_id, summary, preferences_json, updated_at（长期画像）
- `memory_items`：id, user_id, kind, content, source_ref, score, created_at（可检索碎片）
- `retrieval_logs`：id, user_id, conversation_id, query, hits_json, created_at

### 7.3 Skill

- `skills`：id, owner_user_id(nullable=系统), scope(`builtin`/`user`), name, slug, description, body_md, tools_json, version, enabled, created_at
- `user_skill_installs`：user_id, skill_id, installed_at（仅对 builtin 有意义）
- 约束：`scope=user` 的行 **仅** `owner_user_id` 可读写；禁止共享字段

### 7.4 知识库

- `knowledge_bases`：id, owner_user_id(nullable=全局), kind(`private`/`global`), name, created_at
- `knowledge_documents`：id, kb_id, user_id, filename, mime, size, status, storage_path, created_at
- `knowledge_chunks` 元数据可选落 MySQL；向量在 Qdrant（payload 含 `user_id`/`kb_id`/`doc_id`）

权限：

- 私有库：仅 owner
- 全局库：全员只读检索；**仅超管** CRUD

### 7.5 工作区与确认

- `workspace_files`：id, user_id, conversation_id(nullable), path, name, mime, size, created_at
- `confirmations`：id, user_id, conversation_id, run_id, action_type, payload_json, status(`pending`/`approved`/`rejected`/`expired`), created_at, resolved_at

### 7.6 Qdrant

- Collection 建议：`kb_chunks`
- Payload 必含：`user_id`, `kb_id`, `doc_id`, `kind`（private/global）
- 检索过滤：`(kind=global) OR (user_id = 当前用户)`

---

## 8. Skill 格式（一期约定）

文件形态：仓库内 builtin 用目录；用户创建存 DB（`body_md` + `tools_json`）。

```yaml
---
name: web-research
slug: web-research
description: 使用浏览器检索并整理公开网页信息
version: 1
tools:
  - browser_navigate
  - browser_click
  - browser_type
  - browser_extract
  - kb_search
  - file_write_markdown
permissions:
  network: external   # 禁止 intranet
  confirm:
    - browser_submit
    - http_request_write
---

# 使用说明（给模型的 Skill 提示）

当用户需要调研公开网页时……
```

- 主 Agent 根据用户启用的 Skill 合并工具白名单与提示片段
- 一期：多 Skill = 合并工具 + 拼接说明；执行仍由 **单智能体 ReAct 编排器** 调度（串行主路径）

### 8.1 单智能体 ReAct（通用 Agent）

一期采用经典 **ReAct**，定位为**全能办公 Agent**（能力对齐 OpenClaw）：  
同一套工具循环完成任意任务，**不按业务场景硬编码强制路由**（天气/书单等仅为评测样例）。

```
Thought → Action（单个 typed 工具）→ Observation → Thought → … → finish
```

| 步骤 | 含义 |
|------|------|
| Thought | 推理下一步为何、做什么 |
| Action | 调用能力层工具，或 `finish` 交付 |
| Observation | 真实结果回填，供下一轮使用 |

能力层工具：`web_search` / `web_fetch` / `browser_*` / `kb_search` / `file_write_*` 等。  
运行时只做单步解析、入参校验、Observation 回填、失败退避——**不做**「问天气必须走 X」类特例。

输出协议：

```json
{"thought":"...","action":"web_search","action_input":{"query":"..."}}
{"thought":"...","action":"finish","action_input":"给用户的中文答案"}
```

### 8.2 记忆分层（防串题）

| 层 | 存什么 | 边界 |
|----|--------|------|
| 本轮 TaskContext | 当前目标 + 本轮工具 Observation 提炼 | 每条用户消息重建；禁止灌入上一轮结论 / 浏览器残留页 |
| 会话 messages | 最近对话（换题时压缩为摘要提醒） | 主题切换后禁止沿用旧结论回答 |
| 长期画像 | 「我喜欢/请记住」类偏好 | 注入前按当前目标做相关性过滤 |

### 8.3 工具失败与兜底

1. Observation 按**当前目标相关性**入库，避免串题  
2. 任意任务多轮仍无相关事实 → 通用知识兜底（不按场景写死话术）  
3. 最终输出再做「是否贴合当前目标」校验  

---

## 9. 工具清单（一期）

| 工具 | 作用 | 默认需确认 |
|------|------|------------|
| `web_search` | 联网搜索（摘要） | 否 |
| `web_fetch` | 抓取公开网页正文 | 否 |
| `browser_navigate` | 打开 URL | 否（内网 URL 直接拒绝） |
| `browser_click` / `browser_type` | 交互 | 否 |
| `browser_submit` | 提交表单 | **是** |
| `browser_extract` | 抽取可见文本（selector 失败自动回退 body） | 否 |
| `browser_screenshot` | 截图 | 否 |
| `kb_search` | RAG 检索 | 否 |
| `kb_archive_file` | 工作区文件归档入知识库 | 否 |
| `http_request` | 底层 HTTP GET | GET 否；写方法 **是** |
| `file_write_*` | 生成 md/docx/xlsx/pptx/pdf | 否 |
| `file_list` | 工作区列表 | 删文件 **是** |

会议/飞书相关工具：一期注册为 **disabled stub**，调用返回「未启用」。

---

## 10. 浏览器与网络安全

- 每 `uid` 最多 1 个活跃 BrowserContext；空闲超时回收（建议 15–30 分钟）
- 并发按约 8 人预留 Chromium 资源（Compose 内存建议单独评估，初值可 2–4GB 给 agent 服务）
- `net_guard`：拦截 `localhost`、`127.0.0.0/8`、`10.0.0.0/8`、`172.16.0.0/12`、`192.168.0.0/16`、链路本地等
- 不注入门户内网 Cookie；不提供「访问公司内网」能力
- 右侧面板：最新帧 + 当前 URL + 简易状态（loading/idle/error）

---

## 11. 对话事件协议（前端约定）

流式事件类型（示例）：

| event | 含义 |
|-------|------|
| `message.delta` | 助手文本增量（finish 答案） |
| `think.open` / `think.delta` / `think.close` | ReAct 轨迹展示（兼容） |
| `react.thought` / `react.action` / `react.observation` / `react.finish` | 规范 ReAct 步骤 |
| `tool.started` / `tool.finished` | 工具调用轨迹 |
| `browser.frame` | 预览帧（或走独立 WS） |
| `confirmation.required` | 弹出确认卡 |
| `file.ready` | 工作区产物可下载 |
| `error` / `done` | 结束 |

确认流：`confirmation.required` → 用户点同意/拒绝 → `POST /confirmations/{id}` → 编排器继续或中止。

---

## 12. API 轮廓（前缀 `/api/agent/v1`）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET/POST | `/conversations` | 列表/创建 |
| GET/PATCH/DELETE | `/conversations/{id}` | 详情/重命名/删除 |
| GET | `/conversations/{id}/messages` | 历史消息 |
| POST | `/conversations/{id}/chat` | 发消息（SSE 流） |
| GET/POST | `/skills` | 我的 + 可安装官方列表 / 创建 |
| POST | `/skills/install/{id}` | 安装官方 Skill |
| PATCH/DELETE | `/skills/{id}` | 更新/删除（仅自己的） |
| GET/POST | `/knowledge-bases` | 库列表/创建 |
| POST | `/knowledge-bases/{id}/documents` | 上传（≤30MB） |
| DELETE | `/knowledge-bases/{id}/documents/{doc_id}` | 删除文档 |
| GET | `/workspace/files` | 工作区文件 |
| GET | `/workspace/files/{id}/download` | 下载 |
| POST | `/workspace/files/{id}/archive` | 归档到知识库 |
| WS | `/ws/browser` | 预览帧与浏览器状态 |
| GET/POST | `/confirmations/{id}` | 查询/同意拒绝 |
| GET/PATCH | `/memory/profile` | 长期画像查看/手动修订（可选） |

所有接口：`Authorization: Bearer <portal_jwt>`；按 `uid` 做行级隔离。超管接口单独鉴权 `role=super_admin`（全局知识库）。

---

## 13. 前端 UI 规格

**入口**：门户侧栏菜单文案 **「智能体」**，路由建议 `/agent`。

**布局**

```
┌──────────┬────────────────────────────┬─────────────────────┐
│ 会话列表  │  消息流（流式）              │ Tab: 浏览器          │
│ 新建会话  │  计划/工具轨迹（可折叠）      │      知识库          │
│          │  确认条（危险操作）           │      Skill          │
│          │  输入框 + 附件（可选后期）    │                     │
└──────────┴────────────────────────────┴─────────────────────┘
```

- 浏览器 Tab：实时画面、URL、停止/刷新（可选）
- 知识库 Tab：私有库管理；超管可见全局库管理入口
- Skill Tab：已启用、官方可安装、自建编辑器（MD/YAML）

视觉：遵循现有门户 Element Plus 与布局，不另起设计体系。

---

## 14. 权限与安全

1. **身份**：仅门户 JWT；`user_id` 一律来自 token，不信任请求体中的 uid  
2. **数据隔离**：会话、记忆、私有 KB、工作区、浏览器实例均按 uid  
3. **全局 KB**：超管写，登录用户读（检索）  
4. **会议/文件**：一期无数据通路；二期打通时必须复用门户 `perms`，无权限则工具拒绝  
5. **网络**：浏览器与 `http_request` 均禁内网  
6. **确认**：高风险动作默认 pending，超时作废（建议 10 分钟）  
7. **上传**：类型白名单 + 30MB；病毒扫描一期可不做，文档注明风险  

---

## 15. 配置与部署

### 15.1 服务

- 容器名建议：`xlink_agent`
- 端口：`8003`
- 依赖：开发机可用嵌入式 Qdrant（无 Docker）；生产依赖 Compose 中的 `mysql`、`qdrant`；可选复用现有 `redis`

### 15.2 环境变量（示例）

```env
JWT_SECRET=...                 # 与门户一致
PORTAL_API_URL=http://influencer-backend:8000
AGENT_DB_HOST=mysql
AGENT_DB_NAME=xlink_agent
AGENT_DB_USER=...
AGENT_DB_PASSWORD=...
# 生产 Docker：
QDRANT_MODE=url
QDRANT_URL=http://qdrant:6333
# 开发机无 Docker：QDRANT_MODE=local + QDRANT_PATH=./data/qdrant
LLM_PROVIDER=glm
GLM_API_KEY=...
GLM_MODEL=...
WORKSPACE_ROOT=/data/workspaces
BROWSER_IDLE_TTL_SEC=1800
AGENT_MAX_UPLOAD_MB=30
```

### 15.3 MySQL Init

- 新增 `docker/mysql/04-xlink-agent.sql`：建库 `xlink_agent` + grants  
- 与现有 `02-meeting-ai.sql` 方式一致

### 15.4 门户代理

- `vite.config.ts`：`/api/agent` → `localhost:8003`  
- `nginx.conf.template`：生产反代同等路径  

---

## 16. 一期里程碑（建议）

| 阶段 | 交付 | 验收要点 |
|------|------|----------|
| M1 骨架 | 服务启动、JWT、会话 CRUD、空聊天打通 | 菜单可进，能建会话 |
| M2 对话 | GLM 流式、轨迹事件、长期/短期记忆注入 | 多轮上下文正确；uid 隔离 |
| M3 知识库 | 上传解析、Qdrant、kb_search | 私有/全局权限正确；30MB 限制 |
| M4 Skill | 官方安装 + 用户自建 MD/YAML | 不可见他人 Skill |
| M5 浏览器 | 池化实例、禁内网、WS 预览、确认提交 | 8 人冒烟；内网 URL 被拒 |
| M6 文档 | 工作区生成四类文档 + 下载 + 归档 KB | 产物可打开 |
| M7 装配 | Compose/Qdrant/nginx/菜单权限 | 一键 compose 可用 |

二期候选：多专家并行、WebRTC、桌面壳、飞书/会议 Connector 真打通、Skill 版本与审计。

---

## 17. 验收标准（MVP Done）

1. 用户 A/B 互不可见会话、记忆、私有库、自建 Skill、工作区文件  
2. 超管可维护全局库；普通用户可检索全局库内容  
3. 对话流式输出，可见计划与工具轨迹  
4. 启用官方 Skill + 自建 Skill 后，主 Agent 能按白名单调工具  
5. 浏览器可打开公网页，右侧持续更新预览；内网地址失败且有明确错误  
6. 表单提交类操作出现确认卡，拒绝则不执行  
7. 能生成并可下载 Word/Excel/PPT/PDF；可归档进知识库  
8. `docker compose` 可启动 `xlink-agent` + `qdrant`，门户菜单「智能体」可访问  
9. 飞书/会议入口仅 stub，不泄露无权限数据  

---

## 18. 风险与约束

| 风险 | 缓解 |
|------|------|
| Chromium 内存 | 严格 1 uid 1 实例 + 空闲回收；限制同时 screencast 码率 |
| GLM 工具调用不稳定 | 编排层重试、JSON 修复、轨迹可观测 |
| 大文件解析 | 30MB 上限 + 异步入库状态（pending/ready/failed） |
| 提示注入经 KB/网页 | 系统提示隔离；工具结果标记为不可执行指令 |
| 外呼 API 滥用 | 确认写操作 + 超时 + 可选域名白名单（二期可加强） |

---

## 19. 确认记录

| 项 | 结论 |
|----|------|
| Skill 市场 | 方案 A：仅官方可安装；用户自建私有 |
| 写文件 | 服务端 `/data/workspaces/{uid}`；可下载；可归档知识库 |
| 多 Skill | 一期单主 Agent + 多 Skill 工具合并；二期专家并行 |
| 浏览器预览 | CDP screencast / 截图 + WebSocket |
| 文档状态 | 已确认，可进入实现 |

---

*本文档是一期开发的范围基线。若变更范围，先改本文档再改代码。*
