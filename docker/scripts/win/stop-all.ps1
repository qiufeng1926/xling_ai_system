# 停止全部 xlink 容器（保留数据卷）
# 用法: .\docker\scripts\win\stop-all.ps1

$names = @(
    "xlink_portal_frontend",
    "xlink_flybook",
    "xlink_meeting_ai",
    "xlink_influencer_backend",
    "xlink_redis",
    "xlink_mysql"
)

foreach ($n in $names) {
    $exists = docker ps -a --format "{{.Names}}" | Select-String -Pattern "^$([regex]::Escape($n))$" -Quiet
    if ($exists) {
        docker rm -f $n | Out-Null
        Write-Host "已停止: $n"
    }
}
Write-Host "完成"
