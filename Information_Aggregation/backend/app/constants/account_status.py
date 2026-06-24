"""用户账号生命周期状态（与 status 启用/禁用正交）"""

ACTIVE = "active"
OFFBOARDING = "offboarding"
OFFBOARDED = "offboarded"

OFFBOARD_RETENTION_DAYS = 60

# 离职交接记录状态
RECORD_PENDING = "pending"
RECORD_PROCESSING = "processing"
RECORD_COMPLETED = "completed"
RECORD_CANCELLED = "cancelled"
RECORD_FAILED = "failed"

# 仍可取消、重试交接的状态
ACTIVE_RECORD_STATUSES = frozenset({RECORD_PENDING, RECORD_PROCESSING, RECORD_FAILED})
