# 数据库使用说明

## 概述

会议AI系统现已支持将会议数据保存到MySQL数据库中，包括：
- 批量上传的会议记录
- 实时转写的会议记录
- 完整的转写文本和会议纪要
- 处理性能指标（ASR耗时、LLM耗时等）

## 数据库配置

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

新增依赖：
- SQLAlchemy==2.0.36
- PyMySQL==1.1.0

### 2. 配置数据库连接

在 `.env` 文件中配置MySQL数据库连接信息：

```env
# MySQL 数据库配置
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=meeting_ai
DB_CHARSET=utf8mb4
```

**重要提示：**
- 请修改 `DB_PASSWORD` 为你的实际MySQL密码
- 确保MySQL服务正在运行
- 确保数据库用户有创建表的权限

### 3. 初始化数据库

运行初始化脚本创建数据库表：

```bash
python db/init_db.py
```

这将自动创建 `meetings` 表，包含以下字段：
- 主键ID（自增）
- 文件唯一ID（UUID，带唯一索引）
- 会议名称
- 原始文件名
- 会议类型（batch/realtime）
- 文件路径（音频、转写文本、纪要）
- 转写内容和纪要内容
- 数据统计（文本长度、音频时长）
- 性能指标（ASR耗时、LLM耗时、总耗时）
- 时间戳（创建时间、更新时间，带索引）
- 状态和错误信息

## 数据库表结构

### meetings 表

| 字段名 | 类型 | 说明 | 索引 |
|--------|------|------|------|
| id | INT | 主键，自增 | PRIMARY KEY |
| file_id | VARCHAR(64) | 文件唯一ID (UUID) | UNIQUE, INDEX |
| meeting_name | VARCHAR(255) | 会议名称 | - |
| original_filename | VARCHAR(255) | 原始文件名 | - |
| meeting_type | VARCHAR(20) | 会议类型: batch/realtime | INDEX |
| audio_file_path | VARCHAR(500) | 音频文件路径 | - |
| transcript_file_path | VARCHAR(500) | 转写文本文件路径 | - |
| summary_file_path | VARCHAR(500) | 会议纪要文件路径 | - |
| transcript | TEXT | 转写文本内容 | - |
| summary | TEXT | 会议纪要内容 | - |
| transcript_length | INT | 转写文本长度 | - |
| summary_length | INT | 纪要文本长度 | - |
| audio_duration | VARCHAR(50) | 音频时长 | - |
| asr_duration_ms | INT | ASR识别耗时(毫秒) | - |
| llm_duration_ms | INT | LLM生成耗时(毫秒) | - |
| total_duration_ms | INT | 总处理耗时(毫秒) | - |
| created_at | DATETIME | 创建时间 | INDEX |
| updated_at | DATETIME | 更新时间 | - |
| status | VARCHAR(20) | 状态: processing/completed/failed | INDEX |
| error_message | TEXT | 错误信息 | - |

## API使用

所有会议处理接口都会自动将数据保存到数据库：

### 批量上传会议
```
POST /api/meeting/upload
```

### 实时转写会议
```
WebSocket /api/ws/transcribe
```

会议结束后会自动保存到数据库。

## 数据库操作函数

在代码中可以使用以下函数操作数据库：

```python
from db.session import (
    save_meeting_to_db,      # 保存会议记录
    get_meeting_by_file_id,  # 根据file_id获取会议
    get_all_meetings,        # 获取所有会议（分页）
    update_meeting_status,   # 更新会议状态
    delete_meeting           # 删除会议记录
)
```

### 示例

```python
# 保存会议记录
meeting_data = {
    'file_id': 'uuid-string',
    'meeting_name': '周会',
    'original_filename': 'meeting.wav',
    'meeting_type': 'batch',
    'transcript_file_path': '/path/to/transcript.txt',
    'summary_file_path': '/path/to/summary.md',
    'transcript': '转写文本内容...',
    'summary': '会议纪要内容...',
    'status': 'completed'
}
save_meeting_to_db(meeting_data)

# 查询会议
meeting = get_meeting_by_file_id('uuid-string')
if meeting:
    print(meeting.to_dict())

# 获取所有会议（分页）
meetings = get_all_meetings(limit=20, offset=0)
for meeting in meetings:
    print(meeting.to_dict())
```

## 故障排查

### 问题1：连接失败

**症状：** `Can't connect to MySQL server`

**解决方案：**
1. 检查MySQL服务是否运行
2. 验证 `.env` 中的主机、端口配置
3. 检查防火墙设置

### 问题2：认证失败

**症状：** `Access denied for user`

**解决方案：**
1. 检查用户名和密码是否正确
2. 确认用户有访问该数据库的权限

### 问题3：数据库不存在

**症状：** `Unknown database 'meeting_ai'`

**解决方案：**
手动创建数据库：
```sql
CREATE DATABASE meeting_ai CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 问题4：缺少依赖

**症状：** `ModuleNotFoundError: No module named 'pymysql'`

**解决方案：**
```bash
pip install PyMySQL SQLAlchemy
```

## 注意事项

1. **数据安全**：不要将 `.env` 文件提交到版本控制系统
2. **字符编码**：使用 utf8mb4 以支持完整的Unicode字符（包括emoji）
3. **性能优化**：已为常用查询字段添加索引
4. **错误处理**：数据库操作失败不会影响文件保存，会记录日志
5. **事务管理**：使用上下文管理器确保事务正确提交或回滚

## 后续扩展

可以基于数据库实现更多功能：
- 会议搜索和过滤
- 统计分析（会议数量、平均时长等）
- 用户权限管理
- 会议标签和分类
- 数据导出功能
