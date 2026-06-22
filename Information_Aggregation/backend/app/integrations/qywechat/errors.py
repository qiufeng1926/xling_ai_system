from app.integrations.qywechat.client import WeComError


def translate_wecom_error(exc: Exception) -> str:
    if isinstance(exc, WeComError):
        hints = {
            40014: "access_token 无效，请检查 WECOM_CORP_ID / WECOM_CORP_SECRET",
            60020: (
                "企业微信拒绝访问：请在「应用管理 → 你的自建应用 → 企业可信IP」"
                "添加本服务器出口公网 IP；并确认应用已开通邮件/审批且加入「审批-可调用接口的应用」"
            ),
            81013: "应用邮箱未配置，请在管理后台绑定应用邮箱",
            301025: "请求参数错误，请检查 template_id / sp_no 等参数",
            301026: "企业微信审批/邮件内部接口失败",
            301055: "无审批应用数据拉取权限，请在「审批-API-审批数据权限」中授权本应用",
            301112: "查询时间范围过大，请缩小后重试（单次不超过 31 天）",
        }
        hint = hints.get(exc.errcode)
        msg = str(exc.errmsg or "")
        if exc.errcode == 60020 and "ip" in msg.lower():
            hint = (
                "本服务器 IP 未加入企业可信 IP。"
                "请登录企业微信管理后台 → 应用管理 → 自建应用 → 企业可信IP，"
                "添加入网公网 IP 后约 5 分钟生效"
            )
        return msg + (f"（{hint}）" if hint else "")
    return str(exc)
