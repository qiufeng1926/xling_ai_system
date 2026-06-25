"""用户账号生命周期状态（与 status 启用/禁用正交）"""

ACTIVE = "active"
OFFBOARDING = "offboarding"
OFFBOARDED = "offboarded"

OFFBOARD_RETENTION_DAYS = 60

# 离职交接记录状态
RECORD_PENDING = "pending"
RECORD_AWAITING_DOCUMENTS = "awaiting_documents"
RECORD_AWAITING_HANDOVER_CONFIRM = "awaiting_handover_confirm"
RECORD_AWAITING_FINAL_APPROVAL = "awaiting_final_approval"
RECORD_PROCESSING = "processing"
RECORD_COMPLETED = "completed"
RECORD_CANCELLED = "cancelled"
RECORD_FAILED = "failed"

# 进行中的交接（未终结）
ACTIVE_RECORD_STATUSES = frozenset(
    {
        RECORD_PENDING,
        RECORD_AWAITING_DOCUMENTS,
        RECORD_AWAITING_HANDOVER_CONFIRM,
        RECORD_AWAITING_FINAL_APPROVAL,
        RECORD_PROCESSING,
        RECORD_FAILED,
    }
)

# 最终执行失败后可重试批准的状态
FINAL_APPROVAL_RETRY_STATUSES = frozenset({RECORD_AWAITING_FINAL_APPROVAL, RECORD_PROCESSING, RECORD_FAILED})
