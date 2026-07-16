---
name: web-research
slug: web-research
description: 使用浏览器检索并整理公开网页信息
version: 1
tools:
  - browser_navigate
  - browser_click
  - browser_type
  - browser_extract
  - browser_screenshot
  - kb_search
  - file_write_markdown
permissions:
  network: external
  confirm:
    - browser_submit
---

# 网页调研 Skill

当用户需要调研公开网页、竞品页面或公开文档时：

1. 先用 `browser_navigate` 打开目标 URL（禁止内网）
2. 用 `browser_extract` 提取正文
3. 必要时截图或写入 Markdown 报告到工作区
4. 涉及表单提交必须等待用户确认
