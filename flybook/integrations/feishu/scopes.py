"""飞书 OAuth scope 常量与校验"""

from __future__ import annotations

# 云文档列表/读写所需的用户身份权限（任一满足即可读；写需 drive:drive + docx）
DOCS_DRIVE_SCOPES = frozenset(
    {
        "drive:drive",
        "drive:drive:readonly",
        "space:document:retrieve",
    }
)

DOCS_DOCX_SCOPES = frozenset(
    {
        "docx:document",
        "docx:document:create",
        "docx:document:readonly",
    }
)

DEFAULT_OAUTH_SCOPE = "offline_access drive:drive docx:document docx:document:create"


MINUTES_SEARCH_SCOPES = frozenset({"minutes:minutes.search:read"})
MINUTES_READ_SCOPES = frozenset(
    {
        "minutes:minutes",
        "minutes:minutes:readonly",
        "minutes:minutes.basic:read",
    }
)
MINUTES_ARTIFACTS_SCOPES = frozenset({"minutes:minutes.artifacts:read"})
MINUTES_CREATE_SCOPES = frozenset({"minutes:minutes"})


def scope_tokens(scope: str | None) -> set[str]:
    if not scope:
        return set()
    return {part.strip() for part in scope.split() if part.strip()}


def has_minutes_scope(scope: str | None) -> bool:
    granted = scope_tokens(scope)
    search_ok = bool(granted & MINUTES_SEARCH_SCOPES)
    read_ok = bool(granted & MINUTES_READ_SCOPES)
    artifacts_ok = bool(granted & MINUTES_ARTIFACTS_SCOPES)
    return search_ok and read_ok and artifacts_ok


def has_docs_drive_scope(scope: str | None) -> bool:
    granted = scope_tokens(scope)
    return bool(granted & DOCS_DRIVE_SCOPES)


def has_docs_docx_scope(scope: str | None) -> bool:
    granted = scope_tokens(scope)
    return bool(granted & DOCS_DOCX_SCOPES)


def has_docs_scope(scope: str | None) -> bool:
    return has_docs_drive_scope(scope) and has_docs_docx_scope(scope)
