"""三级角色定义"""

SUPER_ADMIN = "super_admin"
ADMIN = "admin"
USER = "user"

# 历史兼容
LEGACY_OPERATOR = "operator"
LEGACY_ADMIN = "admin"

ALL_ROLES = (SUPER_ADMIN, ADMIN, USER)
MANAGEABLE_ROLES = (ADMIN, USER)  # 超级管理员可分配的角色

ROLE_LABELS = {
    SUPER_ADMIN: "超级管理员",
    ADMIN: "管理员",
    USER: "普通用户",
    LEGACY_OPERATOR: "普通用户",
}

ROLE_LEVEL = {
    SUPER_ADMIN: 3,
    ADMIN: 2,
    USER: 1,
    LEGACY_OPERATOR: 1,
}
