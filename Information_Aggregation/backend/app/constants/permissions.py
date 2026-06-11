"""xling 平台统一权限申请类型"""

# 达人模块
REQ_VIEW_LIBRARY = "view_library"

# 会议 AI 模块
REQ_VIEW_ALL_MEETINGS = "view_all_meetings"
REQ_DOWNLOAD_MEETINGS = "download_meetings"
REQ_VIEW_ROOT_MEETINGS = "view_root_meetings"
REQ_PROMOTE_ADMIN = "promote_admin"

ALL_REQUEST_TYPES = (
    REQ_VIEW_LIBRARY,
    REQ_VIEW_ALL_MEETINGS,
    REQ_DOWNLOAD_MEETINGS,
    REQ_VIEW_ROOT_MEETINGS,
    REQ_PROMOTE_ADMIN,
)

REQUEST_TYPE_LABELS = {
    REQ_VIEW_LIBRARY: "查阅达人库",
    REQ_VIEW_ALL_MEETINGS: "查阅全部会议",
    REQ_DOWNLOAD_MEETINGS: "会议导出/下载",
    REQ_VIEW_ROOT_MEETINGS: "查阅超管会议（限3天）",
    REQ_PROMOTE_ADMIN: "升级为管理员",
}
