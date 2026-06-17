-- 会议 AI 系统数据库建表脚本
-- 数据库: MySQL
-- 字符集: utf8mb4

-- 创建数据库（如果不存在）
CREATE DATABASE IF NOT EXISTS meeting_ai 
CHARACTER SET utf8mb4 
COLLATE utf8mb4_unicode_ci;

USE meeting_ai;

-- 创建会议记录表
CREATE TABLE IF NOT EXISTS meetings (
    -- 主键
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    
    -- 唯一标识
    file_id VARCHAR(64) NOT NULL UNIQUE COMMENT '文件唯一ID (UUID)',
    
    -- 会议基本信息
    meeting_name VARCHAR(255) DEFAULT NULL COMMENT '会议名称',
    original_filename VARCHAR(255) DEFAULT NULL COMMENT '原始文件名',
    meeting_type VARCHAR(20) NOT NULL DEFAULT 'batch' COMMENT '会议类型: batch-批量上传, realtime-实时转写',
    
    -- 文件路径
    audio_file_path VARCHAR(500) DEFAULT NULL COMMENT '音频文件路径',
    transcript_file_path VARCHAR(500) NOT NULL COMMENT '转写文本文件路径',
    summary_file_path VARCHAR(500) DEFAULT NULL COMMENT '会议纪要文件路径',
    
    -- 内容数据
    transcript LONGTEXT NOT NULL COMMENT '转写文本内容',
    summary TEXT DEFAULT NULL COMMENT '会议纪要内容',
    
    -- 数据统计
    transcript_length INT NOT NULL DEFAULT 0 COMMENT '转写文本长度',
    summary_length INT DEFAULT 0 COMMENT '纪要文本长度',
    audio_duration VARCHAR(50) DEFAULT NULL COMMENT '音频时长',
    
    -- 性能指标
    asr_duration_ms INT DEFAULT NULL COMMENT 'ASR识别耗时(毫秒)',
    llm_duration_ms INT DEFAULT NULL COMMENT 'LLM生成耗时(毫秒)',
    total_duration_ms INT DEFAULT NULL COMMENT '总处理耗时(毫秒)',
    
    -- 时间戳
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    
    -- 状态
    status VARCHAR(20) NOT NULL DEFAULT 'completed' COMMENT '状态: processing-处理中, completed-已完成, failed-失败',
    error_message TEXT DEFAULT NULL COMMENT '错误信息',
    
    -- 索引
    INDEX idx_file_id (file_id),
    INDEX idx_created_at (created_at),
    INDEX idx_meeting_type (meeting_type),
    INDEX idx_status (status)
    
) ENGINE=InnoDB 
DEFAULT CHARSET=utf8mb4 
COLLATE=utf8mb4_unicode_ci 
COMMENT='会议记录表';

-- 创建用户表
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    username VARCHAR(64) NOT NULL UNIQUE COMMENT '用户名',
    nickname VARCHAR(64) NOT NULL COMMENT '昵称',
    password_hash VARCHAR(256) NOT NULL COMMENT '密码哈希',
    role VARCHAR(20) NOT NULL DEFAULT 'user' COMMENT '角色: user-普通用户, admin-管理员, root-超级管理员',
    can_view_all TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否可查看所有会议',
    can_view_root_meetings TINYINT(1) NOT NULL DEFAULT 0 COMMENT '管理员是否可查看超级管理员会议(限3天)',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户表';

-- 创建权限申请表
CREATE TABLE IF NOT EXISTS permission_requests (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    user_id INT NOT NULL COMMENT '申请人ID',
    request_type VARCHAR(20) NOT NULL COMMENT '申请类型: view_all-查看全部会议, admin-成为管理员',
    reason TEXT DEFAULT NULL COMMENT '申请理由',
    status VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT '状态: pending-待审批, approved-已通过, rejected-已拒绝',
    reviewer_id INT DEFAULT NULL COMMENT '审批人ID',
    review_note TEXT DEFAULT NULL COMMENT '审批备注',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '申请时间',
    reviewed_at DATETIME DEFAULT NULL COMMENT '审批时间',
    INDEX idx_user_id (user_id),
    INDEX idx_status (status),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (reviewer_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='权限申请表';

-- 为已有 meetings 表添加 user_id（如不存在）
-- ALTER TABLE meetings ADD COLUMN user_id INT NULL COMMENT '创建用户ID';
-- ALTER TABLE meetings ADD INDEX idx_user_id (user_id);

-- 协作会议扩展字段（meetings 表）
-- ALTER TABLE meetings ADD COLUMN is_collaborative TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否协作会议';
-- ALTER TABLE meetings ADD COLUMN room_code VARCHAR(16) NULL COMMENT '协作房间码';
-- ALTER TABLE meetings ADD COLUMN host_username VARCHAR(64) NULL COMMENT '发起人门户用户名';

-- 协作会议房间表
CREATE TABLE IF NOT EXISTS collaborative_rooms (
    id INT AUTO_INCREMENT PRIMARY KEY,
    room_code VARCHAR(16) NOT NULL UNIQUE COMMENT '房间码',
    file_id VARCHAR(64) NOT NULL UNIQUE COMMENT '会议 file_id',
    host_username VARCHAR(64) NOT NULL COMMENT '发起人用户名',
    host_user_id INT NULL COMMENT '发起人 meeting_ai user_id',
    meeting_name VARCHAR(255) NOT NULL COMMENT '会议名称',
    status VARCHAR(20) NOT NULL DEFAULT 'waiting' COMMENT 'waiting/live/ending/completed/cancelled',
    merged_transcript LONGTEXT NOT NULL COMMENT '合并转写缓冲',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME NULL,
    ended_at DATETIME NULL,
    INDEX idx_room_code (room_code),
    INDEX idx_host_username (host_username),
    FOREIGN KEY (host_user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='协作会议房间';

-- 协作会议邀请表
CREATE TABLE IF NOT EXISTS room_invitations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    room_id INT NOT NULL,
    invitee_username VARCHAR(64) NOT NULL,
    invited_by VARCHAR(64) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'recorder' COMMENT 'recorder/viewer',
    status VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT 'pending/accepted/declined',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    responded_at DATETIME NULL,
    INDEX idx_room_id (room_id),
    INDEX idx_invitee (invitee_username),
    UNIQUE INDEX idx_room_invitee (room_id, invitee_username),
    FOREIGN KEY (room_id) REFERENCES collaborative_rooms(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='协作会议邀请';

-- 协作会议参与者表
CREATE TABLE IF NOT EXISTS room_participants (
    id INT AUTO_INCREMENT PRIMARY KEY,
    room_id INT NOT NULL,
    username VARCHAR(64) NOT NULL,
    nickname VARCHAR(64) NOT NULL DEFAULT '',
    role VARCHAR(20) NOT NULL COMMENT 'host/recorder/viewer',
    joined_at DATETIME NULL,
    left_at DATETIME NULL,
    INDEX idx_room_id (room_id),
    INDEX idx_username (username),
    UNIQUE INDEX idx_room_participant (room_id, username),
    FOREIGN KEY (room_id) REFERENCES collaborative_rooms(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='协作会议参与者';

-- 显示表结构
DESCRIBE meetings;
DESCRIBE users;
DESCRIBE permission_requests;

-- 示例查询
-- SELECT * FROM meetings ORDER BY created_at DESC LIMIT 10;
-- SELECT COUNT(*) FROM meetings WHERE status = 'completed';
-- SELECT meeting_type, COUNT(*) FROM meetings GROUP BY meeting_type;
