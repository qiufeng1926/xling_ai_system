"""
数据库模型定义
"""
from datetime import datetime
from sqlalchemy import Column, String, Text, Integer, DateTime, Index, Boolean, ForeignKey, create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

Base = declarative_base()


class User(Base):
    """用户表"""
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    username = Column(String(64), unique=True, nullable=False, index=True, comment='用户名')
    nickname = Column(String(64), nullable=False, comment='昵称')
    password_hash = Column(String(256), nullable=False, comment='密码哈希')
    role = Column(String(20), nullable=False, default='user', comment='角色: user-普通用户, admin-管理员, root-超级管理员')
    can_view_all = Column(Boolean, nullable=False, default=False, comment='是否可查看所有会议')
    can_view_root_meetings = Column(Boolean, nullable=False, default=False, comment='管理员是否可查看超级管理员会议(限3天)')
    can_view_all_roots = Column(Boolean, nullable=False, default=False, comment='超级管理员是否可查看其他超级管理员的会议')
    can_download = Column(Boolean, nullable=False, default=False, comment='是否可下载/导出会议文件')
    can_approve_download = Column(Boolean, nullable=False, default=False, comment='管理员是否可审批下载权限申请')
    created_at = Column(DateTime, nullable=False, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    meetings = relationship('Meeting', back_populates='owner')
    permission_requests = relationship('PermissionRequest', back_populates='applicant', foreign_keys='PermissionRequest.user_id')

    def to_dict(self, include_sensitive=False):
        data = {
            'id': self.id,
            'username': self.username,
            'nickname': self.nickname,
            'role': self.role,
            'can_view_all': self.can_view_all or self.role == 'root',
            'can_view_root_meetings': self.can_view_root_meetings,
            'can_view_all_roots': self.can_view_all_roots,
            'can_download': self.can_download or self.role == 'root',
            'can_approve_download': self.can_approve_download or self.role == 'root',
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        if include_sensitive:
            data['password_hash'] = self.password_hash
        return data

    def can_view_all_meetings(self) -> bool:
        return self.is_root() or self.can_view_all

    def is_admin(self) -> bool:
        return self.role in ('admin', 'root')

    def is_root(self) -> bool:
        return self.role == 'root'

    def can_view_peer_root_meetings(self) -> bool:
        """是否可查看其他超级管理员的会议（默认超级管理员之间互不可见）"""
        return self.is_root() and self.can_view_all_roots

    def can_download_files(self) -> bool:
        return self.is_root() or self.can_download

    def can_approve_download_requests(self) -> bool:
        return self.is_root() or (self.role == 'admin' and self.can_approve_download)


class MeetingDownloadLog(Base):
    """会议文件下载记录"""
    __tablename__ = 'meeting_download_logs'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True, comment='下载用户ID')
    file_id = Column(String(64), nullable=True, index=True, comment='会议 file_id')
    meeting_name = Column(String(255), nullable=False, comment='会议名称')
    export_type = Column(String(32), nullable=False, comment='导出类型: summary_docx/visual_html/visual_json')
    meeting_user_id = Column(Integer, ForeignKey('users.id'), nullable=True, comment='会议创建者ID')
    created_at = Column(DateTime, nullable=False, default=datetime.now, comment='下载时间')

    downloader = relationship('User', foreign_keys=[user_id])
    meeting_owner = relationship('User', foreign_keys=[meeting_user_id])

    __table_args__ = (
        Index('idx_download_log_created_at', 'created_at'),
        Index('idx_download_log_user_id', 'user_id'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'username': self.downloader.username if self.downloader else None,
            'nickname': self.downloader.nickname if self.downloader else None,
            'file_id': self.file_id,
            'meeting_name': self.meeting_name,
            'export_type': self.export_type,
            'meeting_user_id': self.meeting_user_id,
            'meeting_owner_username': self.meeting_owner.username if self.meeting_owner else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class PermissionRequest(Base):
    """权限申请表"""
    __tablename__ = 'permission_requests'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True, comment='申请人ID')
    request_type = Column(String(20), nullable=False, comment='申请类型: view_all-查看全部会议, admin-成为管理员')
    reason = Column(Text, nullable=True, comment='申请理由')
    status = Column(String(20), nullable=False, default='pending', comment='状态: pending-待审批, approved-已通过, rejected-已拒绝')
    reviewer_id = Column(Integer, ForeignKey('users.id'), nullable=True, comment='审批人ID')
    review_note = Column(Text, nullable=True, comment='审批备注')
    created_at = Column(DateTime, nullable=False, default=datetime.now, comment='申请时间')
    reviewed_at = Column(DateTime, nullable=True, comment='审批时间')

    applicant = relationship('User', back_populates='permission_requests', foreign_keys=[user_id])
    reviewer = relationship('User', foreign_keys=[reviewer_id])

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'username': self.applicant.username if self.applicant else None,
            'nickname': self.applicant.nickname if self.applicant else None,
            'request_type': self.request_type,
            'reason': self.reason,
            'status': self.status,
            'reviewer_id': self.reviewer_id,
            'reviewer_username': self.reviewer.username if self.reviewer else None,
            'review_note': self.review_note,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'reviewed_at': self.reviewed_at.isoformat() if self.reviewed_at else None,
        }


class MeetingViewGrant(Base):
    """单条会议浏览授权（审批通过或超管直接下发）"""
    __tablename__ = 'meeting_view_grants'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    username = Column(String(64), nullable=True, index=True, comment='申请人门户用户名，用于跨会话匹配')
    file_id = Column(String(64), nullable=False, index=True)
    granted_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    granted_at = Column(DateTime, nullable=False, default=datetime.now)

    __table_args__ = (
        Index('idx_meeting_view_grant_user_file', 'user_id', 'file_id', unique=True),
        Index('idx_meeting_view_grant_username_file', 'username', 'file_id'),
    )


class MeetingViewRequest(Base):
    """单条会议浏览权限申请"""
    __tablename__ = 'meeting_view_requests'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    file_id = Column(String(64), nullable=False, index=True)
    meeting_name = Column(String(255), nullable=True)
    reason = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default='pending')
    reviewer_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    review_note = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    reviewed_at = Column(DateTime, nullable=True)

    applicant = relationship('User', foreign_keys=[user_id])
    reviewer = relationship('User', foreign_keys=[reviewer_id])

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'username': self.applicant.username if self.applicant else None,
            'nickname': self.applicant.nickname if self.applicant else None,
            'file_id': self.file_id,
            'meeting_name': self.meeting_name,
            'reason': self.reason,
            'status': self.status,
            'reviewer_id': self.reviewer_id,
            'reviewer_username': self.reviewer.username if self.reviewer else None,
            'reviewer_nickname': self.reviewer.nickname if self.reviewer else None,
            'review_note': self.review_note,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'reviewed_at': self.reviewed_at.isoformat() if self.reviewed_at else None,
        }


class MeetingDownloadGrant(Base):
    """单条会议下载授权"""
    __tablename__ = 'meeting_download_grants'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    username = Column(String(64), nullable=True, index=True, comment='申请人门户用户名')
    file_id = Column(String(64), nullable=False, index=True)
    granted_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    granted_at = Column(DateTime, nullable=False, default=datetime.now)

    __table_args__ = (
        Index('idx_meeting_download_grant_user_file', 'user_id', 'file_id', unique=True),
        Index('idx_meeting_download_grant_username_file', 'username', 'file_id'),
    )


class MeetingDownloadRequest(Base):
    """单条会议下载权限申请"""
    __tablename__ = 'meeting_download_requests'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    file_id = Column(String(64), nullable=False, index=True)
    meeting_name = Column(String(255), nullable=True)
    reason = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default='pending')
    reviewer_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    review_note = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    reviewed_at = Column(DateTime, nullable=True)

    applicant = relationship('User', foreign_keys=[user_id])
    reviewer = relationship('User', foreign_keys=[reviewer_id])

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'username': self.applicant.username if self.applicant else None,
            'nickname': self.applicant.nickname if self.applicant else None,
            'file_id': self.file_id,
            'meeting_name': self.meeting_name,
            'reason': self.reason,
            'status': self.status,
            'reviewer_id': self.reviewer_id,
            'reviewer_username': self.reviewer.username if self.reviewer else None,
            'reviewer_nickname': self.reviewer.nickname if self.reviewer else None,
            'review_note': self.review_note,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'reviewed_at': self.reviewed_at.isoformat() if self.reviewed_at else None,
        }


class Meeting(Base):
    """会议记录表"""
    __tablename__ = 'meetings'
    
    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    
    # 唯一标识
    file_id = Column(String(64), unique=True, nullable=False, index=True, comment='文件唯一ID (UUID)')

    # 创建用户
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True, index=True, comment='创建用户ID')
    
    # 会议基本信息
    meeting_name = Column(String(255), nullable=True, comment='会议名称')
    original_filename = Column(String(255), nullable=True, comment='原始文件名')
    meeting_type = Column(String(20), nullable=False, default='batch', comment='会议类型: batch-批量上传, realtime-实时转写')
    
    # 文件路径
    audio_file_path = Column(String(500), nullable=True, comment='音频文件路径')
    transcript_file_path = Column(String(500), nullable=False, comment='转写文本文件路径')
    summary_file_path = Column(String(500), nullable=True, comment='会议纪要文件路径')
    
    # 内容数据
    transcript = Column(Text, nullable=False, comment='转写文本内容')
    summary = Column(Text, nullable=True, comment='会议纪要内容(Markdown速览)')
    summary_visual = Column(Text, nullable=True, comment='图文速览JSON')
    summary_visual_status = Column(
        String(20), nullable=True, comment='图文状态: completed/failed/skipped'
    )
    
    # 数据统计
    transcript_length = Column(Integer, nullable=False, default=0, comment='转写文本长度')
    summary_length = Column(Integer, nullable=True, default=0, comment='纪要文本长度')
    audio_duration = Column(String(50), nullable=True, comment='音频时长')
    
    # 性能指标
    asr_duration_ms = Column(Integer, nullable=True, comment='ASR识别耗时(毫秒)')
    llm_duration_ms = Column(Integer, nullable=True, comment='LLM生成耗时(毫秒)')
    total_duration_ms = Column(Integer, nullable=True, comment='总处理耗时(毫秒)')
    
    # 时间戳
    created_at = Column(DateTime, nullable=False, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now, comment='更新时间')
    
    # 状态
    status = Column(String(20), nullable=False, default='completed', comment='状态: processing-处理中, completed-已完成, failed-失败')
    error_message = Column(Text, nullable=True, comment='错误信息')

    # 协作会议
    is_collaborative = Column(Boolean, nullable=False, default=False, comment='是否协作会议')
    room_code = Column(String(16), nullable=True, index=True, comment='协作房间码')
    host_username = Column(String(64), nullable=True, index=True, comment='发起人门户用户名')
    
    owner = relationship('User', back_populates='meetings')

    # 索引
    __table_args__ = (
        Index('idx_file_id', 'file_id'),
        Index('idx_user_id', 'user_id'),
        Index('idx_created_at', 'created_at'),
        Index('idx_meeting_type', 'meeting_type'),
        Index('idx_status', 'status'),
    )
    
    def to_list_dict(self) -> dict:
        """列表接口轻量字段（不含全文 transcript/summary）"""
        return {
            "id": self.id,
            "file_id": self.file_id,
            "user_id": self.user_id,
            "meeting_name": self.meeting_name,
            "original_filename": self.original_filename,
            "meeting_type": self.meeting_type,
            "transcript_length": self.transcript_length,
            "summary_length": self.summary_length,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "status": self.status,
            "has_summary": bool(self.summary),
            "has_visual_summary": bool(self.summary_visual),
            "summary_visual_status": self.summary_visual_status,
            "preview": (self.transcript or "")[:200],
            "is_collaborative": bool(getattr(self, "is_collaborative", False)),
            "room_code": getattr(self, "room_code", None),
            "host_username": getattr(self, "host_username", None),
        }

    def to_dict(self, include_content: bool = True):
        """转换为字典；include_content=False 时同 to_list_dict"""
        if not include_content:
            return self.to_list_dict()
        return {
            "id": self.id,
            "file_id": self.file_id,
            "user_id": self.user_id,
            "meeting_name": self.meeting_name,
            "original_filename": self.original_filename,
            "meeting_type": self.meeting_type,
            "audio_file_path": self.audio_file_path,
            "transcript_file_path": self.transcript_file_path,
            "summary_file_path": self.summary_file_path,
            "transcript": self.transcript,
            "summary": self.summary,
            "transcript_length": self.transcript_length,
            "summary_length": self.summary_length,
            "audio_duration": self.audio_duration,
            "asr_duration_ms": self.asr_duration_ms,
            "llm_duration_ms": self.llm_duration_ms,
            "total_duration_ms": self.total_duration_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "status": self.status,
            "error_message": self.error_message,
            "has_summary": bool(self.summary),
            "has_visual_summary": bool(self.summary_visual),
            "summary_visual_status": self.summary_visual_status,
            "preview": (self.transcript or "")[:200],
            "is_collaborative": bool(self.is_collaborative),
            "room_code": self.room_code,
            "host_username": self.host_username,
        }


class CollaborativeRoom(Base):
    """协作会议房间（进行中）"""
    __tablename__ = 'collaborative_rooms'

    id = Column(Integer, primary_key=True, autoincrement=True)
    room_code = Column(String(16), unique=True, nullable=False, index=True, comment='房间码')
    file_id = Column(String(64), unique=True, nullable=False, index=True, comment='会议 file_id')
    host_username = Column(String(64), nullable=False, index=True, comment='发起人用户名')
    host_user_id = Column(Integer, ForeignKey('users.id'), nullable=True, comment='发起人 meeting_ai user_id')
    meeting_name = Column(String(255), nullable=False, comment='会议名称')
    status = Column(
        String(20), nullable=False, default='waiting',
        comment='waiting/live/ending/completed/cancelled',
    )
    merged_transcript = Column(Text, nullable=False, default='', comment='合并转写缓冲')
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)

    host = relationship('User', foreign_keys=[host_user_id])
    invitations = relationship('RoomInvitation', back_populates='room', cascade='all, delete-orphan')
    participants = relationship('RoomParticipant', back_populates='room', cascade='all, delete-orphan')

    def to_dict(self, include_transcript: bool = False):
        data = {
            'id': self.id,
            'room_code': self.room_code,
            'file_id': self.file_id,
            'host_username': self.host_username,
            'meeting_name': self.meeting_name,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'ended_at': self.ended_at.isoformat() if self.ended_at else None,
        }
        if include_transcript:
            data['merged_transcript'] = self.merged_transcript or ''
        return data


class RoomInvitation(Base):
    """协作会议邀请"""
    __tablename__ = 'room_invitations'

    id = Column(Integer, primary_key=True, autoincrement=True)
    room_id = Column(Integer, ForeignKey('collaborative_rooms.id'), nullable=False, index=True)
    invitee_username = Column(String(64), nullable=False, index=True)
    invited_by = Column(String(64), nullable=False)
    role = Column(String(20), nullable=False, default='recorder', comment='recorder/viewer')
    status = Column(String(20), nullable=False, default='pending', comment='pending/accepted/declined')
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    responded_at = Column(DateTime, nullable=True)

    room = relationship('CollaborativeRoom', back_populates='invitations')

    __table_args__ = (
        Index('idx_room_invitee', 'room_id', 'invitee_username', unique=True),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'room_id': self.room_id,
            'invitee_username': self.invitee_username,
            'invited_by': self.invited_by,
            'role': self.role,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'responded_at': self.responded_at.isoformat() if self.responded_at else None,
        }


class RoomParticipant(Base):
    """协作会议参与者"""
    __tablename__ = 'room_participants'

    id = Column(Integer, primary_key=True, autoincrement=True)
    room_id = Column(Integer, ForeignKey('collaborative_rooms.id'), nullable=False, index=True)
    username = Column(String(64), nullable=False, index=True)
    nickname = Column(String(64), nullable=False, default='')
    role = Column(String(20), nullable=False, comment='host/recorder/viewer')
    joined_at = Column(DateTime, nullable=True)
    left_at = Column(DateTime, nullable=True)

    room = relationship('CollaborativeRoom', back_populates='participants')

    __table_args__ = (
        Index('idx_room_participant', 'room_id', 'username', unique=True),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'room_id': self.room_id,
            'username': self.username,
            'nickname': self.nickname,
            'role': self.role,
            'joined_at': self.joined_at.isoformat() if self.joined_at else None,
            'left_at': self.left_at.isoformat() if self.left_at else None,
        }


def migrate_schema(engine):
    """为已有数据库补充新字段/表（create_all 不会修改已有表结构）"""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'meetings' AND COLUMN_NAME = 'user_id'
        """))
        if result.scalar() == 0:
            conn.execute(text(
                "ALTER TABLE meetings ADD COLUMN user_id INT NULL COMMENT '创建用户ID'"
            ))
            conn.execute(text("ALTER TABLE meetings ADD INDEX idx_user_id (user_id)"))
            conn.commit()
            print("[OK] meetings 表已添加 user_id 字段")

        result = conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND COLUMN_NAME = 'nickname'
        """))
        if result.scalar() == 0:
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN nickname VARCHAR(64) NULL COMMENT '昵称' AFTER username"
            ))
            conn.execute(text("UPDATE users SET nickname = username WHERE nickname IS NULL"))
            conn.execute(text(
                "ALTER TABLE users MODIFY nickname VARCHAR(64) NOT NULL COMMENT '昵称'"
            ))
            conn.commit()
            print("[OK] users 表已添加 nickname 字段")

        result = conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND COLUMN_NAME = 'can_view_root_meetings'
        """))
        if result.scalar() == 0:
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN can_view_root_meetings TINYINT(1) NOT NULL "
                "DEFAULT 0 COMMENT '管理员是否可查看超级管理员会议(限3天)'"
            ))
            conn.commit()
            print("[OK] users 表已添加 can_view_root_meetings 字段")

        result = conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND COLUMN_NAME = 'can_view_all_roots'
        """))
        if result.scalar() == 0:
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN can_view_all_roots TINYINT(1) NOT NULL "
                "DEFAULT 0 COMMENT '超级管理员是否可查看其他超级管理员的会议'"
            ))
            conn.commit()
            print("[OK] users 表已添加 can_view_all_roots 字段")
            conn.execute(text(
                "UPDATE users SET can_view_all_roots = 1 WHERE username = 'qiufengai' AND role = 'root'"
            ))
            conn.commit()

        for col, col_def in (
            ('can_download', "TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否可下载/导出会议文件'"),
            ('can_approve_download', "TINYINT(1) NOT NULL DEFAULT 0 COMMENT '管理员是否可审批下载权限申请'"),
        ):
            result = conn.execute(text(f"""
                SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users'
                AND COLUMN_NAME = '{col}'
            """))
            if result.scalar() == 0:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {col} {col_def}"))
                conn.commit()
                print(f"[OK] users 表已添加 {col} 字段")

        for col, col_def in (
            ('summary_visual', "TEXT NULL COMMENT '图文速览JSON'"),
            ('summary_visual_status', "VARCHAR(20) NULL COMMENT '图文状态'"),
        ):
            result = conn.execute(text(f"""
                SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'meetings'
                AND COLUMN_NAME = '{col}'
            """))
            if result.scalar() == 0:
                conn.execute(text(f"ALTER TABLE meetings ADD COLUMN {col} {col_def}"))
                conn.commit()
                print(f"[OK] meetings 表已添加 {col} 字段")

        for col, col_def in (
            ('is_collaborative', "TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否协作会议'"),
            ('room_code', "VARCHAR(16) NULL COMMENT '协作房间码'"),
            ('host_username', "VARCHAR(64) NULL COMMENT '发起人门户用户名'"),
        ):
            result = conn.execute(text(f"""
                SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'meetings'
                AND COLUMN_NAME = '{col}'
            """))
            if result.scalar() == 0:
                conn.execute(text(f"ALTER TABLE meetings ADD COLUMN {col} {col_def}"))
                conn.commit()
                print(f"[OK] meetings 表已添加 {col} 字段")

        result = conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'meeting_view_grants'
            AND COLUMN_NAME = 'username'
        """))
        if result.scalar() == 0:
            conn.execute(text(
                "ALTER TABLE meeting_view_grants ADD COLUMN username VARCHAR(64) NULL "
                "COMMENT '申请人门户用户名' AFTER user_id"
            ))
            conn.commit()
            conn.execute(text(
                "UPDATE meeting_view_grants g "
                "JOIN users u ON g.user_id = u.id "
                "SET g.username = u.username "
                "WHERE g.username IS NULL"
            ))
            conn.commit()
            try:
                conn.execute(text(
                    "CREATE INDEX idx_meeting_view_grant_username_file "
                    "ON meeting_view_grants (username, file_id)"
                ))
                conn.commit()
            except Exception:
                conn.rollback()
            print("[OK] meeting_view_grants 表已添加 username 字段")

        try:
            conn.execute(text("""
                INSERT INTO meeting_view_grants (user_id, username, file_id, granted_by, granted_at)
                SELECT r.user_id, u.username, r.file_id, r.reviewer_id, COALESCE(r.reviewed_at, NOW())
                FROM meeting_view_requests r
                JOIN users u ON r.user_id = u.id
                LEFT JOIN meeting_view_grants g
                    ON g.user_id = r.user_id AND g.file_id = r.file_id
                WHERE r.status = 'approved' AND g.id IS NULL
            """))
            conn.commit()
        except Exception:
            conn.rollback()

        try:
            conn.execute(text(
                "UPDATE meeting_view_grants g "
                "JOIN users u ON g.user_id = u.id "
                "SET g.username = u.username "
                "WHERE g.username IS NULL OR g.username = ''"
            ))
            conn.commit()
        except Exception:
            conn.rollback()

        try:
            conn.execute(text("""
                INSERT INTO meeting_download_grants (user_id, username, file_id, granted_by, granted_at)
                SELECT r.user_id, u.username, r.file_id, r.reviewer_id, COALESCE(r.reviewed_at, NOW())
                FROM meeting_download_requests r
                JOIN users u ON r.user_id = u.id
                LEFT JOIN meeting_download_grants g
                    ON g.user_id = r.user_id AND g.file_id = r.file_id
                WHERE r.status = 'approved' AND g.id IS NULL
            """))
            conn.commit()
        except Exception:
            conn.rollback()

        try:
            conn.execute(text(
                "UPDATE meeting_download_grants g "
                "JOIN users u ON g.user_id = u.id "
                "SET g.username = u.username "
                "WHERE g.username IS NULL OR g.username = ''"
            ))
            conn.commit()
        except Exception:
            conn.rollback()


def init_database(database_url: str):
    """初始化数据库"""
    from urllib.parse import urlparse
    
    # 解析数据库URL
    parsed = urlparse(database_url)
    db_name = parsed.path.lstrip('/')
    
    # 创建不带数据库名的连接来创建数据库
    base_url = f"{parsed.scheme}://{parsed.username}:{parsed.password}@{parsed.hostname}:{parsed.port}"
    
    try:
        # 尝试连接到MySQL服务器（不指定数据库）
        temp_engine = create_engine(base_url, echo=False)
        with temp_engine.connect() as conn:
            # 检查数据库是否存在
            result = conn.execute(
                text(f"SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = '{db_name}'")
            )
            if not result.fetchone():
                # 数据库不存在，创建它
                conn.execute(text(f"CREATE DATABASE `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
                print(f"[OK] 数据库 '{db_name}' 创建成功")
            else:
                print(f"[OK] 数据库 '{db_name}' 已存在")
        temp_engine.dispose()
    except Exception as e:
        print(f"[WARN] 自动创建数据库失败: {str(e)}")
        print(f"请手动执行: mysql -u root -p -e \"CREATE DATABASE {db_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\"")
        raise
    
    # 现在使用完整的数据库URL创建引擎并创建表
    engine = create_engine(database_url, echo=False, pool_pre_ping=True)
    Base.metadata.create_all(engine)
    migrate_schema(engine)
    print("[OK] 数据库表结构创建成功")
    return engine


def get_session_factory(engine):
    """获取会话工厂"""
    return sessionmaker(bind=engine)
