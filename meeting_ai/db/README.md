# 会议 AI 数据库

MySQL 库名默认 `meeting_ai`。应用启动时会建表，并通过 `migrate_schema` 为既有库自动补齐新增列。

模型定义：`models.py`；会话与 CRUD 辅助：`session.py`；手工初始化：`init_db.py` / `create_table.sql`。

---

## 配置

```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=meeting_ai
DB_CHARSET=utf8mb4
```

```bash
# 可选：手工初始化
python db/init_db.py
```

```sql
CREATE DATABASE meeting_ai CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

---

## 主要表

| 表 | 说明 |
|----|------|
| `users` | 用户与角色、浏览/下载及审批相关权限开关 |
| `meetings` | 会议主表：转写、Markdown/图文速览、听悟摘要字段、协作标记 |
| `permission_requests` | 全局类权限申请（如查看全部会议） |
| `meeting_view_grants` / `meeting_view_requests` | 会议浏览授权与申请 |
| `meeting_download_grants` / `meeting_download_requests` | 下载授权与申请 |
| `meeting_download_logs` | 导出/下载审计 |
| `collaborative_rooms` | 协作房间（进行中状态、合并转写缓冲） |
| `room_invitations` | 协作邀请 |
| `room_participants` | 协作参与者 |

门户 JWT 首次访问会议 API 时，`portal_auth` 会按用户名同步/创建 `users` 行并更新权限字段。

### meetings 要点字段

| 字段 | 说明 |
|------|------|
| `file_id` | UUID，业务主键 |
| `user_id` | 所属用户 |
| `meeting_type` | `batch` / `realtime` |
| `transcript` / `summary` / `summary_visual` | 正文与纪要 |
| `tingwu_*` | 听悟任务与大模型摘要相关 |
| `is_collaborative` / `room_code` / `host_username` | 协作会议 |

---

## 与业务接口的关系

- 批量上传 `POST /api/meeting/upload`、实时 WS `/api/ws/transcribe` 结束时写入 `meetings`
- 协作流程写入 `collaborative_rooms` 等，结束后合并为会议记录
- 导出走 `/api/export/*`，可记入 `meeting_download_logs`

常用查询请通过 `session.py` / 服务层，避免直接拼 SQL。

---

## 故障排查

| 现象 | 处理 |
|------|------|
| Can't connect | 确认 MySQL 已启动，`DB_HOST`/`DB_PORT` |
| Access denied | 账号密码；Docker 可运行 `docker/scripts/win/fix-mysql-grants.cmd` |
| Unknown database | 先 `CREATE DATABASE meeting_ai ...` |
| 缺 pymysql | `pip install PyMySQL SQLAlchemy` |

---

## 注意

1. 勿将含密码的 `.env` 提交 Git
2. 使用 `utf8mb4`
3. 常用查询字段已建索引；迁移失败请查 `logs/` 后按 `models.py` 手工对齐列
